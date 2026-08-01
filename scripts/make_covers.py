#!/usr/bin/env python3
"""一次生成小红书/抖音双封面: 竖 3:4 (1242×1656) + 横 4:3 (1440×1080)。

抖音发布页有两个独立封面槽 (横封面4:3 / 竖封面3:4), 只给一张会挂「横/竖双封面缺失」,
且信息流露出的是竖封面。横版必须按 4:3 重新排版 —— 拿竖版裁一刀会把下方标题条整块裁掉。

用法:
  make_covers.py --video 成片.mp4 --t 24.5 --title "函館の記憶" \
      --sub "回忆，不必留在这里" --tag "AI 短片 · 北海道函館" --outdir final/

  # 或直接给一张图当素材
  make_covers.py --image frame.png --title "..." --outdir final/

要点:
  --t 选**没有片尾标题的那一帧** (否则片中标题和封面标题重复); 优先选有故事张力的一帧,
     而不是单纯好看的空镜。
  竖版 = 主图 + 下方独立标题区; 横版 = 标题叠在画面下三分之一 + 渐变保可读。
"""
import argparse, os, subprocess, sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

FONT_JA = "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc"   # 日文明朝
FONT_CN = "/System/Library/Fonts/Hiragino Sans GB.ttc"    # 中文黑体
# 标题衬线字体候选链 (path, ttc_index)。按顺序取**第一个能覆盖标题全部字符**的:
#   日文明朝没有简体专用字形 (剑/说/讲…) —— 直接用会渲染成豆腐块 ☒ 且不报错。
#   日文标题(函館の記憶)仍走明朝, 中文标题自动落到宋体, 两边都不牺牲。
FONT_TITLE_CHAIN = [
    (FONT_JA, 0),                                            # Hiragino Mincho ProN W3
    ("/System/Library/Fonts/Supplemental/Songti.ttc", 1),     # Songti SC Bold
]
V_W, V_H = 1242, 1656   # 竖 3:4
H_W, H_H = 1440, 1080   # 横 4:3


def pick_font(path, size, index=0):
    try:
        return ImageFont.truetype(path, size, index=index)
    except OSError:
        return ImageFont.truetype(FONT_CN, size)


def _glyph_bytes(font, ch):
    m = font.getmask(ch)
    if not m.size[0]:
        return b""
    return Image.frombytes("L", m.size, bytes(m)).tobytes()


def _covers(font, text):
    """字体是否覆盖 text 全部字符。

    PIL 缺字时**静默画 .notdef 豆腐块**, getbbox/getmask 都照样返回尺寸, 所以不能靠
    有没有 bbox 判断 —— 只能把每个字的位图跟一个保证缺失的码位 (U+FFFF) 比对。
    """
    probe = _glyph_bytes(font, "￿")
    return all(_glyph_bytes(font, c) != probe
               for c in set(text) if not c.isspace())


def pick_title_font(size, text):
    """标题字体 = 候选链里第一个能完整覆盖 text 的; 都不行则用最后一个并告警。"""
    last = None
    for path, idx in FONT_TITLE_CHAIN:
        try:
            f = ImageFont.truetype(path, size, index=idx)
        except OSError:
            continue
        last = f
        if _covers(f, text):
            return f
    if last is not None:
        missing = "".join(sorted({c for c in text
                                  if not c.isspace() and not _covers(last, c)}))
        print(f"⚠ 标题字体候选链都缺字: {missing!r} —— 这些字会渲染成豆腐块, "
              f"请在 FONT_TITLE_CHAIN 里补一个覆盖它们的字体")
        return last
    return ImageFont.truetype(FONT_CN, size)


def shadow(dr, x, y, txt, font, fill, alpha=165):
    for ox, oy, al in [(-2,0,alpha),(2,0,alpha),(0,-2,alpha),(0,2,alpha),
                       (0,4,int(alpha*.75)),(3,3,int(alpha*.55))]:
        dr.text((x+ox, y+oy), txt, font=font, fill=(0,0,0,al))
    dr.text((x, y), txt, font=font, fill=fill)


def tracked(dr, txt, font, cx, y, fill, track_ratio=.30, alpha=175):
    """宽字距居中绘制 (明朝体标题的标准处理)"""
    tr = int(font.size * track_ratio)
    ws = [dr.textlength(c, font=font) for c in txt]
    x = cx - (sum(ws) + tr*(len(txt)-1)) / 2
    for i, c in enumerate(txt):
        shadow(dr, x, y, c, font, fill, alpha)
        x += ws[i] + tr


def blurred_bg(src, W, H, blur=45, bright=.38, sat=.7):
    sc = max(W/src.width, H/src.height) * 1.3
    bg = src.resize((int(src.width*sc), int(src.height*sc)), Image.LANCZOS)
    bg = bg.crop(((bg.width-W)//2, (bg.height-H)//2,
                  (bg.width-W)//2+W, (bg.height-H)//2+H))
    bg = bg.filter(ImageFilter.GaussianBlur(blur))
    bg = ImageEnhance.Brightness(bg).enhance(bright)
    return ImageEnhance.Color(bg).enhance(sat)


def soft_paste(canvas, img, x, y, edge=28):
    canvas.paste(img, (x, y))
    g = Image.new("L", (1, edge))
    for i in range(edge):
        g.putpixel((0, i), int(255*(i/edge)))
    canvas.paste(img.crop((0,0,img.width,edge)), (x,y), g.resize((img.width,edge)))
    canvas.paste(img.crop((0,img.height-edge,img.width,img.height)),
                 (x, y+img.height-edge),
                 g.transpose(Image.FLIP_TOP_BOTTOM).resize((img.width,edge)))


def crop_to(src, ratio_w, ratio_h, bias_x=.5):
    """按比例裁切, bias_x 控制水平取景重心 (0=靠左,1=靠右)"""
    target = ratio_w / ratio_h
    if src.width / src.height > target:
        cw = int(src.height * target); ch = src.height
    else:
        cw = src.width; ch = int(src.width / target)
    x = int((src.width - cw) * bias_x); y = (src.height - ch)//2
    return src.crop((x, y, x+cw, y+ch))


def make_vertical(src, title, sub, tag, out, bias_x=.5):
    """竖 3:4 — 满幅铺图, 标题叠在上三分之一 + 顶部渐变保可读"""
    base = crop_to(src, V_W, V_H, bias_x).resize((V_W, V_H), Image.LANCZOS)
    img = base.convert("RGBA")

    # 顶部渐变压暗 (上方最重, 向下淡出), 让叠字可读
    grad = Image.new("L", (1, V_H), 0)
    for y in range(V_H):
        t = max(0.0, 1.0 - y / (V_H * 0.52))
        grad.putpixel((0, y), int(205 * (t**1.4)))
    img = Image.alpha_composite(
        img, Image.merge("RGBA", (*[Image.new("L",(V_W,V_H),0)]*3,
                                  grad.resize((V_W, V_H)))))

    ov = Image.new("RGBA", (V_W,V_H), (0,0,0,0)); d = ImageDraw.Draw(ov)
    if tag:
        f = pick_font(FONT_CN, 40)
        shadow(d, (V_W-d.textlength(tag,font=f))/2, int(V_H*.085), tag,
               f, (230,224,212,235), 140)
    ft = pick_title_font(128, title)
    ty = int(V_H * .165)                      # 上三分之一
    tracked(d, title, ft, V_W/2, ty, (250,248,243,255))
    ly = ty + 128 + 54
    # 分隔线只在有副标题时画: 没副标题还画, 它会单独横穿主体(实测压在发髻上)
    if sub:
        d.line([(V_W/2-140, ly), (V_W/2+140, ly)], fill=(235,230,220,115), width=2)
        fs = pick_font(FONT_CN, 46)
        shadow(d, (V_W-d.textlength(sub,font=fs))/2, ly+40, sub, fs, (238,234,226,255), 145)
    Image.alpha_composite(img, ov).convert("RGB").save(out, "JPEG", quality=93, subsampling=0)
    return out


def make_horizontal(src, title, sub, tag, out, bias_x=.5):
    """横 4:3 — 满幅铺图, 标题叠在下三分之一 + 底部渐变保可读"""
    base = crop_to(src, H_W, H_H, bias_x).resize((H_W, H_H), Image.LANCZOS)
    img = base.convert("RGBA")

    # 底部渐变压暗, 让叠字可读
    grad = Image.new("L", (1, H_H), 0)
    for y in range(H_H):
        t = max(0.0, (y - H_H*0.48) / (H_H*0.52))
        grad.putpixel((0, y), int(215 * (t**1.5)))
    img = Image.alpha_composite(
        img, Image.merge("RGBA", (*[Image.new("L",(H_W,H_H),0)]*3,
                                  grad.resize((H_W, H_H)))))

    ov = Image.new("RGBA", (H_W,H_H), (0,0,0,0)); d = ImageDraw.Draw(ov)
    if tag:
        f = pick_font(FONT_CN, 34)
        shadow(d, (H_W-d.textlength(tag,font=f))/2, int(H_H*.055), tag,
               f, (228,222,210,225), 130)
    ft = pick_title_font(104, title)
    ty = int(H_H * .655)
    tracked(d, title, ft, H_W/2, ty, (250,248,243,255))
    ly = ty + 104 + 40
    if sub:
        d.line([(H_W/2-120, ly), (H_W/2+120, ly)], fill=(235,230,220,110), width=2)
        fs = pick_font(FONT_CN, 40)
        shadow(d, (H_W-d.textlength(sub,font=fs))/2, ly+30, sub, fs, (238,234,226,255), 140)
    Image.alpha_composite(img, ov).convert("RGB").save(out, "JPEG", quality=93, subsampling=0)
    return out


def main():
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--video"); g.add_argument("--image")
    p.add_argument("--t", type=float, default=0, help="抽帧秒 (选无片尾标题的一帧)")
    p.add_argument("--title", required=True)
    p.add_argument("--sub", default=""); p.add_argument("--tag", default="")
    p.add_argument("--outdir", default=".")
    p.add_argument("--bias", type=float, default=.5,
                   help="水平取景重心 0=靠左 .5=居中 1=靠右。竖版满幅要从16:9裁掉大半宽度, "
                        "主体偏一侧时必须指定, 否则会被裁掉")
    a = p.parse_args()
    if not 0 <= a.bias <= 1:
        p.error("--bias 必须在 0..1 之间")

    os.makedirs(a.outdir, exist_ok=True)
    if a.video:
        tmp = os.path.join(a.outdir, ".cover_frame.png")
        subprocess.run(["ffmpeg","-v","error","-ss",str(a.t),"-i",a.video,
                        "-frames:v","1",tmp,"-y"], check=True)
        src = Image.open(tmp).convert("RGB")
    else:
        src = Image.open(a.image).convert("RGB")

    v = make_vertical(src, a.title, a.sub, a.tag,
                      os.path.join(a.outdir,"封面图-竖3x4.jpg"), a.bias)
    h = make_horizontal(src, a.title, a.sub, a.tag,
                        os.path.join(a.outdir,"封面图-横4x3.jpg"), a.bias)
    for f in (v, h):
        im = Image.open(f)
        print(f"{f}  {im.size}  {os.path.getsize(f)/1024:.0f}KB")

    # 满幅 3:4 要从源里裁掉大半宽度, 放大倍数高时提示
    vc = crop_to(src, V_W, V_H, a.bias)
    up = V_W / vc.width
    if up > 1.8:
        print(f"⚠ 竖版放大 {up:.1f}× (源 {src.width}×{src.height} → 3:4 裁切区 "
              f"{vc.width}×{vc.height}) — 满幅构图的代价, 手机上通常可接受; "
              f"要更锐利需更高分辨率的源帧")


if __name__ == "__main__":
    sys.exit(main())
