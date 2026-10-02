"""Strict adapter for the shipped Ori WotW bitmap-font schema.

Only supported text fonts are extended. Original glyph records, kerning and atlas
pixels stay intact; new glyphs occupy previously unused atlas space.
"""
from __future__ import annotations
import copy
import io
import math
import struct
from PIL import Image, ImageDraw, ImageFont

BITMAP_HASH = bytes.fromhex('f447c507ac7ae305f0b4bb5b62901911')
TEXT_FONTS = {'candara', 'roboto', 'nyala', 'sakkalMajalla'}

def script_matches(tree):
    h=tree.get('m_PropertiesHash',{})
    return (tree.get('m_AssemblyName')=='__mainWisp.dll' and tree.get('m_Namespace')=='CatlikeCoding.TextBox'
            and tree.get('m_ClassName')=='BitmapFont'
            and [h.get(f'bytes[{i}]') for i in range(16)]==list(BITMAP_HASH))

def parse_bitmap(data):
    if len(data)<40:raise ValueError('Bitmap font bị cắt.')
    fid,sid=struct.unpack_from('<iq',data,16)
    length=struct.unpack_from('<i',data,28)[0]
    if not 0<=length<=256 or 32+length>len(data):raise ValueError('Tên bitmap font không hợp lệ.')
    name=data[32:32+length].decode('utf8')
    pos=(32+length+3)&~3
    header=data[:pos]
    def integer():
        nonlocal pos
        if pos+4>len(data):raise ValueError('Bitmap font bị cắt.')
        result=struct.unpack_from('<i',data,pos)[0];pos+=4;return result
    def chars(ascii=False):
        nonlocal pos
        count=integer()
        if not 0<=count<=65536 or (ascii and count!=94):raise ValueError('Số glyph không khớp schema.')
        result=[]
        for i in range(count):
            start=pos
            if pos+44>len(data):raise ValueError('Glyph bị cắt.')
            cid,kind,*metrics=struct.unpack_from('<ii9f',data,pos);pos+=44
            if kind!=0 or not 0<=cid<=65535 or (ascii and cid not in (0,i+33)):
                raise ValueError('Font icon/schema mở rộng chưa hỗ trợ.')
            if any(not math.isfinite(v) for v in metrics):raise ValueError('Glyph có tọa độ không hợp lệ.')
            if not (0<=metrics[0]<=metrics[1]<=1 and 0<=metrics[2]<=metrics[3]<=1):raise ValueError('Glyph UV ngoài atlas.')
            a=integer()
            if not 0<=a<=65536 or pos+a*4>len(data):raise ValueError('Kerning bị cắt.')
            pos+=a*4;b=integer()
            if a!=b or pos+b*4>len(data):raise ValueError('Kerning không khớp.')
            pos+=b*4
            result.append({'id':cid,'metrics':metrics,'raw':data[start:pos]})
        return result
    ascii=chars(True);other=chars()
    if len(data)-pos!=36:raise ValueError('Bitmap font có phần mở rộng chưa hỗ trợ.')
    line,base,bottom,space=struct.unpack_from('<4f',data,pos)
    if not 8<=line<=512 or not all(math.isfinite(v) for v in (base,bottom,space)):
        raise ValueError('Thông số dòng bitmap không hợp lệ.')
    ids=[r['id'] for r in other]
    if len(set(ids))!=len(ids):raise ValueError('Bitmap font trùng glyph.')
    return dict(name=name,file_id=fid,script_id=sid,header=header,ascii=ascii,other=other,tail=data[pos:],line=line)

def encode_bitmap(parsed, additions):
    other=sorted(parsed['other']+additions,key=lambda r:r['id'])
    data=parsed['header']+struct.pack('<i',94)+b''.join(r['raw'] for r in parsed['ascii'])
    data+=struct.pack('<i',len(other))+b''.join(r['raw'] for r in other)+parsed['tail']
    parse_bitmap(data)
    return data

def _edt_1d(values):
    # Lower envelope of parabolas: linear-time squared Euclidean distance.
    n=len(values);sites=[i for i,v in enumerate(values) if v<1e15]
    if not sites:return [1e16]*n
    v=[0]*n;z=[0.0]*(n+1);k=0;v[0]=sites[0];z[0]=-math.inf;z[1]=math.inf
    for q in sites[1:]:
        s=((values[q]+q*q)-(values[v[k]]+v[k]*v[k]))/(2*(q-v[k]))
        while s<=z[k]:
            k-=1
            s=((values[q]+q*q)-(values[v[k]]+v[k]*v[k]))/(2*(q-v[k]))
        k+=1;v[k]=q;z[k]=s;z[k+1]=math.inf
    out=[];k=0
    for q in range(n):
        while z[k+1]<q:k+=1
        out.append((q-v[k])**2+values[v[k]])
    return out

def _distance(mask,inside):
    w,h=mask.size;pixels=list(mask.get_flattened_data())
    rows=[_edt_1d([0 if ((pixels[y*w+x]>=128)==inside) else 1e16 for x in range(w)]) for y in range(h)]
    result=[0]*(w*h)
    for x in range(w):
        column=_edt_1d([rows[y][x] for y in range(h)])
        for y,value in enumerate(column):result[y*w+x]=value
    return result

def signed_distance(mask,spread=4):
    inside=_distance(mask,True);outside=_distance(mask,False)
    # Signed half-pixel boundary, centered at 128 like the original atlas.
    values=[max(0,min(255,round(128+(math.sqrt(b)-math.sqrt(a))*127/spread))) for a,b in zip(inside,outside)]
    result=Image.new('L',mask.size);result.putdata(values);return result

class AtlasPacker:
    def __init__(self,size,rects,cell=4):
        self.cell=cell;self.width=size[0]//cell;self.height=size[1]//cell
        self.rows=[0]*self.height
        for x,y,w,h in rects:self.occupy(x,y,w,h)
    def occupy(self,x,y,w,h):
        c=self.cell;left=max(0,x//c);right=min(self.width,math.ceil((x+w)/c))
        bits=((1<<(right-left))-1)<<left
        for row in range(max(0,y//c),min(self.height,math.ceil((y+h)/c))):self.rows[row]|=bits
    def place(self,w,h):
        wc=math.ceil((w+2)/self.cell);hc=math.ceil((h+2)/self.cell)
        if wc>self.width or hc>self.height:raise ValueError('Glyph lớn hơn atlas.')
        full=(1<<self.width)-1
        for y in range(self.height-hc+1):
            used=0
            for r in self.rows[y:y+hc]:used|=r
            free=full^used;starts=free
            for shift in range(1,wc):starts&=free>>shift
            if starts:
                x=(starts & -starts).bit_length()-1
                self.occupy(x*self.cell,y*self.cell,wc*self.cell,hc*self.cell)
                return x*self.cell+1,y*self.cell+1
        raise ValueError('Atlas không đủ chỗ trống cho tiếng Việt; chưa sửa font này. Chọn font nhỏ hơn hoặc cần adapter mở rộng atlas.')

def glyph_rect(row,size):
    a,b,c,d,*_=row['metrics'];w,h=size
    return (round(a*w),round((1-d)*h),round((b-a)*w),round((d-c)*h))

def extend_atlas(parsed,atlas,font_path,required,fallback_sources=()):
    coverage=__import__('toolvh.fonts',fromlist=['font_coverage']).font_coverage
    sources=[font_path,*fallback_sources]
    cmaps=[coverage(source) for source in sources]
    known={r['id'] for r in parsed['ascii']+parsed['other']}
    missing=sorted(set(required)-known)
    if not missing:return parsed,atlas,0
    absent=set(missing)-set().union(*cmaps)
    if absent:raise ValueError('Font nguồn thiếu ký tự: '+''.join(chr(c) for c in sorted(absent)))
    # Match cap height to original H to avoid mixing mismatched text sizes.
    hrow=next(r for r in parsed['ascii'] if r['id']==ord('H'))
    x,y,w,h=glyph_rect(hrow,atlas.size)
    bbox=atlas.getchannel('A').crop((x,y,x+w,y+h)).point(lambda v:255 if v>=128 else 0).getbbox()
    if bbox is None:raise ValueError('Không đo được cap-height font gốc.')
    desired=bbox[3]-bbox[1]
    fonts=[]
    for source in sources:
        def load_font(size):
            return ImageFont.truetype(io.BytesIO(source) if isinstance(source,bytes) else str(source),size)
        probe=load_font(100)
        cap=probe.getbbox('H',anchor='ls');size=round(100*desired/(cap[3]-cap[1]))
        fonts.append(load_font(size))
    output=atlas.copy();packer=AtlasPacker(atlas.size,[glyph_rect(r,atlas.size) for r in parsed['ascii']+parsed['other'] if r['metrics'][1]>r['metrics'][0]])
    additions=[];pad=4;line=parsed['line']
    for code in missing:
        font=next(font for font,cmap in zip(fonts,cmaps) if code in cmap)
        char=chr(code);left,top,right,bottom=font.getbbox(char,anchor='ls')
        if right<=left or bottom<=top:raise ValueError('Font nguồn có glyph rỗng: '+char)
        mask=Image.new('L',(right-left+pad*2,bottom-top+pad*2))
        ImageDraw.Draw(mask).text((pad-left,pad-top),char,font=font,fill=255,anchor='ls')
        sdf=signed_distance(mask,pad)
        gx,gy=packer.place(*sdf.size)
        # The game samples alpha; preserve original RGB appearance in unused texels.
        glyph=Image.new('RGBA',sdf.size,(255,255,255,0));glyph.putalpha(sdf)
        output.paste(glyph,(gx,gy))
        sw,sh=sdf.size;aw,ah=atlas.size
        metrics=(gx/aw,(gx+sw)/aw,1-(gy+sh)/ah,1-gy/ah,
                 (left-pad)/line,(-top+pad)/line,sw/line,sh/line,font.getlength(char)/line)
        raw=struct.pack('<ii9fii',code,0,*metrics,0,0)
        additions.append(dict(id=code,metrics=list(metrics),raw=raw))
    result=copy.deepcopy(parsed);result['other']+=additions;result['other'].sort(key=lambda r:r['id'])
    return result,output,len(additions)
