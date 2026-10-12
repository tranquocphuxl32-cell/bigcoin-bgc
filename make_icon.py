#!/usr/bin/env python3
# Tao icon .ico cho BGC Miner: dong xu luc giac (hexagon), chu "B" + cham dien tu (AI/luong tu).
from PIL import Image, ImageDraw, ImageFont
import math

def hexagon(cx, cy, r, rot=math.pi/2):
    return [(cx+r*math.cos(rot+i*math.pi/3), cy+r*math.sin(rot+i*math.pi/3)) for i in range(6)]

def font(sz):
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]:
        try: return ImageFont.truetype(p, sz)
        except Exception: pass
    return ImageFont.load_default()

def render(S):
    im = Image.new("RGBA", (S, S), (0,0,0,0))
    d = ImageDraw.Draw(im)
    cx = cy = S/2
    R = S*0.46
    # vien ngoai (sang) + than (gradient gia lap bang 2 lop)
    d.polygon(hexagon(cx, cy, R), fill=(40,54,74,255))                 # vien toi
    d.polygon(hexagon(cx, cy, R*0.93), fill=(90,160,255,255))          # than xanh brand
    d.polygon(hexagon(cx, cy, R*0.93)[:3]+[(cx,cy)], fill=(120,180,255,255))  # cao sang nhe phia tren
    d.polygon(hexagon(cx, cy, R*0.74), fill=(20,28,44,255))            # dia trong toi
    # ban TO (>=128px): hien "BGC"; ban nho: hien "B" cho de doc
    if S>=128:
        t="BGC"; fsz=int(S*0.26); dy=-S*0.01
    else:
        t="B"; fsz=int(S*0.5); dy=-S*0.02
    fT=font(fsz); bb=d.textbbox((0,0),t,font=fT)
    d.text((cx-(bb[2]-bb[0])/2-bb[0], cy-(bb[3]-bb[1])/2-bb[1]+dy), t, font=fT, fill=(120,190,255,255))
    # "cham dien tu" (AI/luong tu)
    if S>=48:
        ax,ay=cx+R*0.52, cy-R*0.5
        d.ellipse([ax-S*0.06,ay-S*0.06,ax+S*0.06,ay+S*0.06], fill=(73,209,122,255))  # cham xanh la
    return im

master = render(256)
sizes=[16,24,32,48,64,128,256]
imgs=[render(s) for s in sizes]
# luu .ico da do phan giai + 1 ban .png de xem truoc
imgs[-1].save("bgc.ico", sizes=[(s,s) for s in sizes], append_images=imgs[:-1])
# Pillow ico: dung master lam goc, nhung de chac dung tung anh dung kich co:
master.save("bgc.ico", format="ICO", sizes=[(s,s) for s in sizes])
render(256).save("bgc_icon_preview.png")
print("bgc.ico + bgc_icon_preview.png da tao")
