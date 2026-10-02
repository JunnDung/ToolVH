"""Verified Ori language-style links used to select fonts, independent of names."""
import struct

STYLE_HASH = bytes.fromhex('7f17b01d7ddca8e4f4c039c94177834c')
LANGUAGE_HASH = bytes.fromhex('4c992cc23909f5994431daa1be4bfa0e')

def binding_script(tree):
    h=tree.get('m_PropertiesHash',{})
    fingerprint=bytes(h.get(f'bytes[{i}]',0) for i in range(16))
    if tree.get('m_AssemblyName')!='__mainWisp.dll':return None
    if (tree.get('m_Namespace'),tree.get('m_ClassName'),fingerprint)==('CatlikeCoding.TextBox','TextStyleCollection',STYLE_HASH):return 'styles'
    if (tree.get('m_Namespace'),tree.get('m_ClassName'),fingerprint)==('','MessageBoxLanguageStyles',LANGUAGE_HASH):return 'languages'
    return None

def _header(data):
    if len(data)<32:raise ValueError('Style header bị cắt.')
    n=struct.unpack_from('<i',data,28)[0]
    if not 0<=n<=256 or 32+n>len(data):raise ValueError('Tên style không hợp lệ.')
    return data[32:32+n].decode('utf8'),(32+n+3)&~3

def parse_language_style(data):
    name,pos=_header(data)
    # Seven language pointers, one padding scalar, then fourteen pointers.
    if len(data)-pos!=256:raise ValueError('Language style không khớp schema 21 ngôn ngữ.')
    return name,struct.unpack_from('<iq',data,pos)

def parse_style_fonts(data):
    name,pos=_header(data)
    if pos+4>len(data):raise ValueError('Style bị cắt.')
    count=struct.unpack_from('<i',data,pos)[0];pos+=4
    if not 1<=count<=128:raise ValueError('Số style không hợp lệ.')
    rows=[]
    for _ in range(count):
        if pos+4>len(data):raise ValueError('Style bị cắt.')
        n=struct.unpack_from('<i',data,pos)[0];pos+=4
        if not 0<=n<=256 or pos+n>len(data):raise ValueError('Tên style không hợp lệ.')
        label=data[pos:pos+n].decode('utf8');pos=(pos+n+3)&~3
        if pos+60>len(data):raise ValueError('Style fields bị cắt.')
        font=struct.unpack_from('<iq',data,pos+4)
        # The bool fields are serialized as one byte + alignment padding.
        for offset in (36,44,48,52,56):
            if data[pos+offset] not in (0,1):raise ValueError('Style bool không hợp lệ.')
        if font[0]<0 or font[1]<0:raise ValueError('Font pointer không hợp lệ.')
        rows.append((label,font));pos+=60
    if pos!=len(data):raise ValueError('Style có phần mở rộng chưa hỗ trợ.')
    return name,rows

def english_font_usage(env,relative,scripts):
    from .unity import script_reference
    styles={};languages=[]
    for obj in env.objects:
        if obj.type.name!='MonoBehaviour':continue
        raw=obj.get_raw_data()
        if len(raw)<32:continue
        fid,sid=struct.unpack_from('<iq',raw,16)
        reference=script_reference(obj,{'m_Script':{'m_FileID':fid,'m_PathID':sid}},relative)
        kind=binding_script(scripts.get(reference,{}))
        if kind=='styles':
            name,rows=parse_style_fonts(raw);styles[obj.path_id]=(name,rows)
        elif kind=='languages':languages.append(parse_language_style(raw))
    usage={}
    for language_name,(fid,style_id) in languages:
        if fid!=0 or style_id not in styles:continue
        style_name,rows=styles[style_id]
        for label,(font_file,font_id) in rows:
            if font_file==0 and font_id:
                usage.setdefault(font_id,set()).add(f'{language_name} / {style_name} / {label}')
    return {key:sorted(values) for key,values in usage.items()}
