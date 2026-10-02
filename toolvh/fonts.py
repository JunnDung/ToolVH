"""Font diagnostics and verified, reversible repairs for supported formats."""
from __future__ import annotations
import io
import json
import os
import re
import shutil
import tempfile
import unicodedata
from pathlib import Path
from collections import defaultdict
from fontTools.ttLib import TTFont
from .model import atomic_write, digest, safe_child
from .unity import load_unity, object_key, script_reference
from .bitmap_bindings import english_font_usage
from .bitmap_fonts import script_matches, parse_bitmap, encode_bitmap, extend_atlas, TEXT_FONTS

VIETNAMESE = set(map(ord, 'ĂÂĐÊÔƠƯăâđêôơưÀÁÃÈÉÌÍÒÓÕÙÚÝàáãèéìíòóõùúý')) | set(range(0x1EA0,0x1EFA))

def icon_name(name):
    return bool(re.search(r'keyboard|controller|icons?|symbols?',name,re.I))


def font_coverage(source):
    data=source if isinstance(source,bytes) else Path(source).read_bytes()
    if len(data)>32*1024*1024:raise ValueError('Font nguồn lớn hơn 32 MB.')
    with TTFont(io.BytesIO(data),lazy=False,fontNumber=0) as font:
        cmap=font.getBestCmap()
        if not cmap:raise ValueError('Font không có Unicode cmap.')
        return {int(c) for c,g in cmap.items() if g!='.notdef'}

def required_characters(project):
    from .translation import TOKENS
    translated=''.join(TOKENS.sub('',e.translation) for e in project.entries if e.enabled and e.translation)
    chars={ord(c) for c in translated if not c.isspace()}
    return chars | VIETNAMESE

def describe_missing(required,available):
    return ''.join(chr(c) for c in sorted(set(required)-set(available)))

def _texture_image(obj,root,relative):
    texture=obj.read()
    if not texture.image_data and texture.m_StreamData and texture.m_StreamData.size:
        stream=texture.m_StreamData
        resource=safe_child(root,(Path(relative).parent/stream.path.replace('\\','/')).as_posix())
        if stream.size>64*1024*1024:raise ValueError('Atlas font lớn hơn 64 MB.')
        with resource.open('rb') as f:
            f.seek(stream.offset);texture.image_data=f.read(stream.size)
        if len(texture.image_data)!=stream.size:raise ValueError('Atlas stream bị cắt.')
    return texture,texture.image.convert('RGBA')

def diagnose(project,progress=lambda _:None,stop=None):
    root=Path(project.root).resolve();required=required_characters(project)
    result={'schema':1,'root':str(root),'required':''.join(chr(c) for c in sorted(required)),
            'fonts':[],'notes':[], 'engine_limits':'Unity dynamic Font, font TTF/OTF rời và Ori bitmap đã xác nhận. TMP static SDF một atlas có type tree; TMP dynamic/multi-atlas và UE/Godot cần adapter riêng.'}
    paths={r.path for r in project.files if r.kind=='unity' and r.size<=256*1024*1024}
    # Fonts often live in resources/globalgamemanagers even when no strings were selected there.
    for datafolder in root.glob('*_Data'):
        for name in ('resources.assets','globalgamemanagers.assets'):
            p=datafolder/name
            if p.exists():paths.add(p.relative_to(root).as_posix())
    if any(unicodedata.combining(chr(c)) for c in required):
        result['notes'].append('Bản dịch có dấu Unicode kết hợp: bấm Chuẩn hóa Unicode trước khi sửa font bitmap.')
    if any(r.kind in ('pck','locres') for r in project.files):
        result['notes'].append('Font trong PCK/PAK/IoStore chưa hỗ trợ sửa; chỉ kiểm tra font rời nếu có.')
    scripts={}
    ordered=sorted(paths,key=lambda p:(Path(p).name!='globalgamemanagers.assets',p))
    for index,relative in enumerate(ordered):
        if stop and stop.is_set():raise InterruptedError('Đã dừng quét font.')
        path=safe_child(root,relative)
        progress(f'Quét font [{index+1}/{len(ordered)}]: {relative}')
        try:
            if path.stat().st_size>256*1024*1024:continue
            data=path.read_bytes();sha=digest(data);env=load_unity(data)
            textures={}
            for obj in env.objects:
                if obj.type.name=='MonoScript':
                    tree=obj.read_typetree()
                    scripts[(relative,obj.path_id)]=tree
                elif obj.type.name=='Texture2D':
                    tree=obj.read_typetree();textures.setdefault(tree.get('m_Name'),[]).append(obj)
            try:usage=english_font_usage(env,relative,scripts)
            except (ValueError,UnicodeError) as exc:
                usage={}
                result['notes'].append(f'{relative}: Không đọc được liên kết font English: {exc}')
            for obj in env.objects:
                base=dict(file=relative,container=str(obj.assets_file.name),object=obj.path_id,sha256=sha)
                if obj.type.name=='Font':
                    tree=obj.read_typetree();name=tree.get('m_Name','Font');embedded=bytes(tree.get('m_FontData',[]))
                    coverage=font_coverage(embedded) if embedded else {r.get('index',-1) for r in tree.get('m_CharacterRects',[])}
                    icon=bool(re.search(r'keyboard|controller|icons?|symbols?|moon-tools',name,re.I))
                    dynamic=bool(embedded) and not tree.get('m_CharacterRects')
                    result['fonts'].append(dict(base,name=name,kind='unity-dynamic' if dynamic else 'unity-static',
                        missing=describe_missing(required,coverage),repairable=dynamic and not icon,
                        note='Font icon: giữ nguyên.' if icon else ('Có thể thay TTF nhúng.' if dynamic else 'Font atlas tĩnh cần adapter riêng.')))
                elif obj.type.name=='MonoBehaviour':
                    try:
                        tree=obj.read_typetree()
                        ref=script_reference(obj,tree,relative)
                        script=scripts.get(ref,{})
                        is_tmp=script.get('m_Namespace')=='TMPro' and script.get('m_ClassName')=='TMP_FontAsset' and script.get('m_AssemblyName')=='Unity.TextMeshPro.dll'
                    except Exception:
                        is_tmp=False
                    if is_tmp:
                        from .tmp_fonts import coverage, support
                        reason=support(tree)
                        rec=dict(base,name=tree.get('m_Name','TMP Font'),kind='tmp-static',missing=describe_missing(required,coverage(tree)),repairable=False,note=reason)
                        if not reason:
                            pointer=tree['m_AtlasTextures'][0]
                            atlas=next((o for o in env.objects if o.assets_file.name==obj.assets_file.name and o.path_id==pointer.get('m_PathID') and pointer.get('m_FileID')==0 and o.type.name=='Texture2D'),None)
                            if atlas is not None:
                                texture,image=_texture_image(atlas,root,relative)
                                if texture.m_TextureFormat in (1,4) and image.size==(tree.get('m_AtlasWidth'),tree.get('m_AtlasHeight')):
                                    rec.update(atlas=atlas.path_id,atlas_sha256=digest(image.tobytes()),dimensions=list(image.size),repairable=not icon_name(rec['name']),note='TMP static SDF: bổ sung glyph vào chỗ trống, giữ atlas và chữ gốc; cần thử trong game.')
                        result['fonts'].append(rec)
                        continue
                    raw=obj.get_raw_data()
                    if len(raw)<32:continue
                    try:header=parse_bitmap_header(raw)
                    except (ValueError,UnicodeError):continue
                    ref=script_reference(obj,{'m_Script':{'m_FileID':header[0],'m_PathID':header[1]}},relative)
                    tree=scripts.get(ref,{})
                    if not script_matches(tree):continue
                    name=header[2]
                    record=dict(base,name=name,kind='ori-bitmap',missing='Chưa kiểm tra',repairable=False,note='Font icon/ngoại ngữ không sửa tự động.')
                    if name in TEXT_FONTS:
                        parsed=parse_bitmap(raw);coverage={r['id'] for r in parsed['ascii']+parsed['other']}
                        record['missing']=describe_missing(required,coverage)
                        atlas=textures.get(name+'_0 distance map',[])
                        if len(atlas)==1:
                            texture,image=_texture_image(atlas[0],root,relative)
                            record.update(atlas=atlas[0].path_id,atlas_sha256=digest(image.tobytes()),repairable=True,
                                          note='Bổ sung glyph SDF trong chỗ trống atlas; giữ chữ gốc.',dimensions=list(image.size))
                    record['english_usage']=usage.get(obj.path_id,[])
                    if record['english_usage']:
                        record['note']+=' Dùng cho English: '+', '.join(record['english_usage'])
                    result['fonts'].append(record)
        except Exception as exc:
            result['notes'].append(f'{relative}: {type(exc).__name__}: {exc}')
    for path in root.rglob('*'):
        if stop and stop.is_set():raise InterruptedError('Đã dừng quét font.')
        if not path.is_file() or path.suffix.lower() not in ('.ttf','.otf','.fnt'):continue
        relative=path.relative_to(root).as_posix()
        try:
            data=path.read_bytes()
            if path.suffix.lower() in ('.ttf','.otf'):
                coverage=font_coverage(data)
                icon=bool(re.search(r'keyboard|controller|icons?|symbols?',path.stem,re.I))
                result['fonts'].append(dict(file=relative,name=path.name,kind='loose-font',sha256=digest(data),
                    missing=describe_missing(required,coverage),repairable=not icon,note='Thay file font rời; cần thử trong game.'))
            else:
                # Standard text/XML BMFont diagnostics. No blind atlas replacement.
                text=data.decode('utf-8-sig');ids=set()
                ids.update(int(v) for v in re.findall(r'(?:<char\s+[^>]*\bid="|\bchar\s+id=)(\d+)',text))
                if ids:result['fonts'].append(dict(file=relative,name=path.name,kind='bmfont',sha256=digest(data),missing=describe_missing(required,ids),repairable=False,note='BMFont: cần tạo lại atlas và metrics, chưa hỗ trợ ghi.'))
        except Exception as exc:result['notes'].append(f'{relative}: {exc}')
    if not result['fonts']:result['notes'].append('Chưa tìm thấy font đọc được; có thể font nằm trong container/atlas riêng.')
    return result

def parse_bitmap_header(raw):
    import struct
    if len(raw)<32:raise ValueError('Truncated header')
    fid,sid=struct.unpack_from('<iq',raw,16);n=struct.unpack_from('<i',raw,28)[0]
    if not 0<=n<=256 or 32+n>len(raw):raise ValueError('Invalid name')
    return fid,sid,raw[32:32+n].decode('utf8')

def suggested_font(name):
    root=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'
    # Use fonts already on the user's machine; never bundle system font files.
    for candidate in (['Candara.ttf'] if name in ('candara','sakkalMajalla') else ['times.ttf'] if name=='nyala' else [])+['segoeui.ttf','arial.ttf']:
        path=root/candidate
        if path.exists() and VIETNAMESE<=font_coverage(path):return path
    raise ValueError('Chọn file TTF/OTF có đủ tiếng Việt.')

def _font_name(data):
    with TTFont(io.BytesIO(data)) as font:
        names=font['name'].names
        for rec in names:
            if rec.nameID==1:
                return rec.toUnicode()
    raise ValueError('Font nguồn không có family name.')

def rebuild_font_asset(data,records,root,relative,required,font_path=None,progress=lambda _:None):
    env=load_unity(data);objects={object_key(o):o for o in env.objects};modified=set();details=[]
    for record in records:
        key=(record['container'],record['object']);obj=objects.get(key)
        if obj is None:raise ValueError('Font object không còn tồn tại.')
        chosen=Path(font_path) if font_path else suggested_font(record['name'])
        if not font_path and record['kind']=='ori-bitmap' and record['name']=='roboto':
            for candidate in objects.values():
                if candidate.type.name=='Font':
                    tree=candidate.read_typetree()
                    if tree.get('m_Name')=='Roboto-Light':
                        embedded=bytes(tree.get('m_FontData',[]))
                        if required<=font_coverage(embedded):
                            chosen=embedded
                            break
        if record['kind']=='unity-dynamic':
            if obj.type.name!='Font':raise ValueError('Font type đã thay đổi.')
            tree=obj.read_typetree()
            if tree.get('m_CharacterRects') or not tree.get('m_FontData'):raise ValueError('Chỉ hỗ trợ Font dynamic có TTF nhúng.')
            replacement=chosen.read_bytes();old=bytes(tree['m_FontData']);coverage=font_coverage(replacement)
            # Replacement must not remove ANY existing code point.
            missing=(required|font_coverage(old))-coverage
            if missing:raise ValueError('Font thay thế thiếu ký tự đang dùng: '+''.join(chr(c) for c in sorted(missing))[:150])
            tree['m_FontData']=list(replacement);tree['m_FontNames']=[_font_name(replacement)];obj.save_typetree(tree);modified.add(key)
            details.append({'name':record['name'],'mode':'replace-dynamic'})
        elif record['kind']=='tmp-static':
            from .tmp_fonts import extend
            tree=obj.read_typetree()
            atlas_key=(record['container'],record['atlas']);atlasobj=objects.get(atlas_key)
            if atlasobj is None or atlasobj.type.name!='Texture2D':raise ValueError('TMP atlas không tồn tại.')
            texture,image=_texture_image(atlasobj,root,relative)
            if digest(image.tobytes())!=record['atlas_sha256']:raise ValueError('TMP atlas đã thay đổi; quét font lại.')
            updated,output,count=extend(tree,image,chosen,required)
            if count:
                obj.save_typetree(updated);texture.set_image(output,target_format=texture.m_TextureFormat,mipmap_count=1);texture.save()
                modified.update((key,atlas_key));details.append({'name':record['name'],'mode':'extend-tmp-sdf','added':count})
        elif record['kind']=='ori-bitmap':
            parsed=parse_bitmap(obj.get_raw_data())
            if parsed['name'] not in TEXT_FONTS:raise ValueError('Không sửa font icon/ngoại ngữ.')
            atlas_key=(record['container'],record['atlas']);atlasobj=objects.get(atlas_key)
            if atlasobj is None or atlasobj.type.name!='Texture2D':raise ValueError('Atlas không tồn tại.')
            texture,image=_texture_image(atlasobj,root,relative)
            if digest(image.tobytes())!=record['atlas_sha256']:raise ValueError('Atlas thay đổi sau chẩn đoán; quét font lại.')
            fallbacks=[]
            if not font_path:
                absent=required-font_coverage(chosen)-{r['id'] for r in parsed['ascii']+parsed['other']}
                # Preserve non-Latin names too. Collections use their first face;
                # only the needed glyphs are rasterized into this bitmap atlas.
                system_fonts=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'
                for filename in ('msjh.ttc','msyh.ttc','meiryo.ttc','malgun.ttf','simsun.ttc'):
                    if not absent:break
                    source=system_fonts/filename
                    if not source.is_file():continue
                    try:coverage=font_coverage(source)
                    except Exception:continue
                    if absent & coverage:
                        fallbacks.append(source);absent-=coverage
            updated,output,count=extend_atlas(parsed,image,chosen,required,fallbacks)
            if count:
                obj.set_raw_data(encode_bitmap(updated,[]));texture.set_image(output,target_format=1 if texture.m_TextureFormat==1 else 4,mipmap_count=1);texture.save()
                modified.update((key,atlas_key));details.append({'name':record['name'],'mode':'extend-bitmap','added':count})
    if not modified:return data,details
    result=env.file.save();verify=load_unity(result);reopened={object_key(o):o for o in verify.objects}
    if objects.keys()!=reopened.keys():raise ValueError('Object Unity thay đổi ngoài dự kiến.')
    for key,obj in objects.items():
        if key not in modified and obj.get_raw_data()!=reopened[key].get_raw_data():raise ValueError('Bản vá làm thay đổi object ngoài font.')
    for record in records:
        key=(record['container'],record['object'])
        if key not in modified:continue
        obj=reopened[key]
        if record['kind']=='unity-dynamic':
            if not required<=font_coverage(bytes(obj.read_typetree()['m_FontData'])):raise ValueError('Font reopen thiếu ký tự.')
        elif record['kind']=='tmp-static':
            from .tmp_fonts import coverage
            if not required<=coverage(obj.read_typetree()):raise ValueError('TMP reopen thiếu glyph.')
            texture,image=_texture_image(reopened[(record['container'],record['atlas'])],root,relative)
            if tuple(record['dimensions'])!=image.size:raise ValueError('TMP atlas đổi kích thước.')
        else:
            parsed=parse_bitmap(obj.get_raw_data())
            if not required<={r['id'] for r in parsed['ascii']+parsed['other']}:raise ValueError('Bitmap reopen thiếu glyph.')
            texture,image=_texture_image(reopened[(record['container'],record['atlas'])],root,relative)
            if tuple(record['dimensions'])!=image.size:raise ValueError('Atlas đổi kích thước ngoài dự kiến.')
    return result,details

def export_font_patch(project,report,selected,destination,font_path=None,progress=lambda _:None):
    from .addressables import catalog_updates
    root=Path(project.root).resolve();destination=Path(destination).resolve()
    if str(root)!=report['root']:raise ValueError('Báo cáo font thuộc game khác; quét font lại.')
    if destination.exists() or destination.is_relative_to(root) or root.is_relative_to(destination):raise ValueError('Chọn thư mục bản vá mới ngoài game.')
    if not selected:raise ValueError('Chọn font có hỗ trợ sửa trước.')
    identities=[(r.get('file'),r.get('container'),r.get('object')) for r in selected if isinstance(r,dict)]
    if len(identities)!=len(set(identities)):raise ValueError('Danh sách font bị trùng.')
    atlases=[(r.get('file'),r.get('container'),r['atlas']) for r in selected if isinstance(r,dict) and 'atlas' in r]
    if len(atlases)!=len(set(atlases)):raise ValueError('Các font được chọn dùng chung atlas; hãy sửa từng font và quét lại trước lượt tiếp theo.')
    if any(not isinstance(r,dict) or not r.get('repairable') or r not in report['fonts'] for r in selected):raise ValueError('Danh sách font không hợp lệ hoặc chưa hỗ trợ sửa.')
    required=required_characters(project)
    # Keep signed distance generator bounded, and reject unrenderable surrogate/control text.
    if any(c>65535 or 0xD800<=c<=0xDFFF or c<32 for c in required):raise ValueError('Có ký tự ngoài BMP/điều khiển; cần adapter font riêng.')
    if any(r['kind'] in ('ori-bitmap','tmp-static') for r in selected) and any(unicodedata.combining(chr(c)) for c in required):
        raise ValueError('Bản dịch có dấu kết hợp: bấm Chuẩn hóa Unicode và quét font lại trước.')
    if font_path and not required<=font_coverage(font_path):raise ValueError('Font nguồn không đủ ký tự cho bản dịch.')
    changes={};details=[];groups=defaultdict(list)
    for record in selected:groups[record['file']].append(record)
    for relative,records in groups.items():
        progress('Đang tạo font: '+relative)
        original=safe_child(root,relative).read_bytes()
        if any(digest(original)!=r['sha256'] for r in records):raise ValueError('File game đổi sau chẩn đoán; quét font lại: '+relative)
        if records[0]['kind']=='loose-font':
            chosen=Path(font_path) if font_path else suggested_font(records[0]['name']);modified=chosen.read_bytes()
            absent=(required|font_coverage(original))-font_coverage(modified)
            if absent:raise ValueError('Font thay thế làm mất glyph gốc; chọn font khác.')
            details.append({'name':records[0]['name'],'mode':'replace-loose'})
        else:modified,items=rebuild_font_asset(original,records,root,relative,required,font_path,progress);details.extend(items)
        if modified!=original:changes[relative]=(original,modified)
    if not changes:raise ValueError('Font đã có đủ ký tự; không cần tạo bản vá.')
    changes.update(catalog_updates(root,changes))
    destination.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix='.toolvh-font-',dir=destination.parent))
    manifest={'schema':1,'kind':'font','game_root':str(root),'files':[],'translated':0,'remaining':0,'font_repairs':details}
    try:
        for relative,(original,modified) in changes.items():
            atomic_write(safe_child(stage/'files',relative),modified);atomic_write(safe_child(stage/'backup',relative),original)
            manifest['files'].append({'path':relative,'original_sha256':digest(original),'patched_sha256':digest(modified)})
        atomic_write(stage/'manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf8'))
        atomic_write(stage/'README.txt',('ToolVH: bản vá font. Đóng game trước khi cài/khôi phục. Backup chứa trạng thái game trước khi sửa font, gồm cả bản dịch đang cài. Khôi phục font trước khi khôi phục bản dịch.\n'+json.dumps(details,ensure_ascii=False,indent=2)).encode('utf8'))
        os.replace(stage,destination)
    finally:
        if stage.exists():shutil.rmtree(stage)
    return manifest

def apply_font_patch(project,patch,save=lambda:None):
    from .patching import install_patch
    manifest=json.loads((Path(patch)/'manifest.json').read_text(encoding='utf8'))
    if manifest.get('kind')!='font' or Path(manifest['game_root']).resolve()!=Path(project.root).resolve():raise ValueError('Bản vá font thuộc game khác.')
    path=str(Path(patch).resolve())
    if path not in project.font_patches:
        project.font_patches.append(path)
        try:save()
        except Exception:
            project.font_patches.pop();raise
    return install_patch(patch,project.root)

def restore_font(project,save=lambda:None):
    from .patching import install_patch
    if not project.font_patches:raise ValueError('Project chưa có bản vá font đã cài.')
    count=install_patch(project.font_patches[-1],project.root,restore=True)
    project.font_patches.pop();save();return count
