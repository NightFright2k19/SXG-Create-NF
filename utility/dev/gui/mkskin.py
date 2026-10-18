# mkskin.py: second panel skin "Modern" (issue #52), drawn after the mockup of the issue (pip: pillow numpy). Run in
# utility/dev/gui:   python3 mkskin.py [--preview]
# Every picture keeps the size and position of its original counterpart (the drawing code of the DLL is unchanged):
#   101 panel 400 x 114 (+ model name 100 x 23 at x 300), 102 meter screen 288 x 47 at (11, 57),
#   103 XG / GS lamps 4 x 40 x 39 at (308, 48) / (350, 48), 104 level meter 9 x 11 x 28 at (19 + 11 * part, 62),
#   105 digits 11 x 10 x 13, 106 SETUP 2 x 80 x 16 at (309, 88) + pressed left / right button 15 x 15 + dash.
# --preview writes skin52/preview.png (both skins with sample values, 1:1 and enlarged) for the approval.
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops
HERE = Path(__file__).resolve().parent; OUT = HERE / 'skin52'; B = HERE.parent.parent / 'bitmaps'
SS = 4                                                        # supersampling
FONT = '/usr/share/fonts/opentype/inter/InterDisplay-%s.otf'
BG, PANEL_T, PANEL_B, HI, SH = (14, 18, 22), (42, 49, 57), (24, 29, 35), (70, 80, 90), (5, 7, 9)
SCREEN, CELL = (6, 10, 13), (5, 8, 10)
CYAN, CYAN_DIM, LABEL, WHITE, GREY = (70, 222, 238), (11, 26, 30), (86, 200, 222), (232, 238, 242), (190, 198, 205)

def font(size, weight = 'Bold') : return ImageFont.truetype(FONT % weight, size * SS)
def canvas(w, h, c = BG) : return Image.new('RGB', (w * SS, h * SS), c)
def down(im) : return im.resize((im.width // SS, im.height // SS), Image.LANCZOS)
def box(x0, y0, x1, y1) : return [x0 * SS, y0 * SS, x1 * SS - 1, y1 * SS - 1]

def vgrad(im, x0, y0, x1, y1, top, bot, r = 0) :
    # vertical gradient in a rounded rectangle (panel coordinates)
    w, h = (x1 - x0) * SS, (y1 - y0) * SS
    g = Image.new('RGB', (1, h)); g.putdata([tuple(int(top[i] + (bot[i] - top[i]) * y / max(1, h - 1)) for i in range(3)) for y in range(h)])
    g = g.resize((w, h)); m = Image.new('L', (w, h), 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], r * SS, 255)
    im.paste(g, (x0 * SS, y0 * SS), m)

def bevel(im, x0, y0, x1, y1, r = 2, raised = True, fill = None, top = PANEL_T, bot = PANEL_B) :
    d = ImageDraw.Draw(im)
    a, b = (HI, SH) if raised else (SH, HI)
    d.rounded_rectangle(box(x0, y0, x1, y1), r * SS, fill = b)
    d.rounded_rectangle([x0 * SS, y0 * SS, x1 * SS - 1, y1 * SS - SS // 2 - 1], r * SS, fill = a)
    if fill : d.rounded_rectangle([x0 * SS + SS // 2, y0 * SS + SS // 2, x1 * SS - SS // 2 - 1, y1 * SS - SS // 2 - 1], r * SS, fill = fill)
    else : vgrad(im, x0, y0, x1, y1, top, bot, r) if False else None
    if not fill :
        w0, h0 = x0 * SS + SS // 2, y0 * SS + SS // 2
        g = Image.new('RGB', (1, (y1 - y0) * SS - SS)); n = g.height
        g.putdata([tuple(int(top[i] + (bot[i] - top[i]) * y / max(1, n - 1)) for i in range(3)) for y in range(n)])
        g = g.resize(((x1 - x0) * SS - SS, n)); m = Image.new('L', g.size, 0)
        ImageDraw.Draw(m).rounded_rectangle([0, 0, g.width - 1, g.height - 1], max(0, r * SS - SS // 2), 255)
        im.paste(g, (w0, h0), m)

def text(im, xy, s, size, color, weight = 'Bold', anchor = 'lm', squeeze = 1.0, glow = None, track = 0.0) :
    # text at panel coordinates; squeeze < 1 narrows it (condensed look); track = extra letter spacing in pixels;
    # glow = colour of a soft halo
    f = font(size, weight); l, t, r, b = f.getbbox(s); tr = track * SS
    w, h = int(f.getlength(s) + tr * (len(s) - 1)) + 8 * SS, b - t + 8 * SS
    layer = Image.new('L', (w, h), 0); dl = ImageDraw.Draw(layer); x = 4 * SS - l
    for ch in s : dl.text((x, 4 * SS - t), ch, font = f, fill = 255); x += f.getlength(ch) + tr
    if squeeze != 1.0 : layer = layer.resize((int(w * squeeze), h), Image.LANCZOS)
    x, y = xy[0] * SS, xy[1] * SS; tw, th = layer.width - 8 * SS, h - 8 * SS
    x -= {'l' : 0, 'm' : tw // 2, 'r' : tw}[anchor[0]]; y -= {'t' : 0, 'm' : th // 2, 'b' : th}[anchor[1]]
    pos = (int(x - 4 * SS), int(y - 4 * SS))
    if glow :
        halo = layer.filter(ImageFilter.GaussianBlur(2.2 * SS)).point(lambda v : int(v * 0.8))
        im.paste(Image.new('RGB', layer.size, glow), pos, halo)
    im.paste(Image.new('RGB', layer.size, color), pos, layer)

# techno stroke font (grid 4 x 6, chamfered corners) for the YAMAHA name, the model name and SETUP
GLYPHS = {
    'A' : [[(0, 6), (0, 1.5), (1.5, 0), (2.5, 0), (4, 1.5), (4, 6)], [(0, 3.6), (4, 3.6)]],
    'Y' : [[(0, 0), (0, 1.2), (2, 3.4), (4, 1.2), (4, 0)], [(2, 3.4), (2, 6)]],
    'M' : [[(0, 6), (0, 0), (2, 2.8), (4, 0), (4, 6)]],
    'H' : [[(0, 0), (0, 6)], [(4, 0), (4, 6)], [(0, 3), (4, 3)]],
    'S' : [[(4, 0), (1, 0), (0, 1), (0, 2), (1, 3), (3, 3), (4, 4), (4, 5), (3, 6), (0, 6)]],
    'E' : [[(4, 0), (0, 0), (0, 6), (4, 6)], [(0, 3), (3, 3)]],
    'T' : [[(0, 0), (4, 0)], [(2, 0), (2, 6)]],
    'U' : [[(0, 0), (0, 5), (1, 6), (3, 6), (4, 5), (4, 0)]],
    'P' : [[(0, 6), (0, 0), (3, 0), (4, 1), (4, 2), (3, 3), (0, 3)]],
    'G' : [[(4, 1), (3, 0), (1, 0), (0, 1), (0, 5), (1, 6), (3, 6), (4, 5), (4, 3), (2, 3)]],
    'X' : [[(0, 0), (4, 6)], [(4, 0), (0, 6)]],
    '-' : [[(0.5, 3), (3.5, 3)]],
    '0' : [[(1, 0), (3, 0), (4, 1), (4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0)]],
    '1' : [[(0.5, 1.2), (2, 0), (2, 6)]],
    '2' : [[(0, 1), (1, 0), (3, 0), (4, 1), (4, 2), (0, 6), (4, 6)]],
    '5' : [[(4, 0), (0, 0), (0, 3), (3, 3), (4, 4), (4, 5), (3, 6), (0, 6)]],
    '8' : [[(1, 0), (3, 0), (4, 1), (4, 2), (3, 3), (1, 3), (0, 2), (0, 1), (1, 0)], [(1, 3), (0, 4), (0, 5), (1, 6), (3, 6), (4, 5), (4, 4), (3, 3)]],
    '9' : [[(4, 3), (1, 3), (0, 2), (0, 1), (1, 0), (3, 0), (4, 1), (4, 5), (3, 6), (0, 6)]],
}

def stroke_text(im, x, cy, s, h, color, weight = 1.6, gap = 0.55, aspect = 0.72, anchor = 'l', glow = None, shadow = True) :
    # s drawn with GLYPHS: cap height h pixels, glyph width h * aspect, gap = fraction of the glyph width
    gw = h * aspect; adv = gw * (1 + gap); total = adv * (len(s) - 1) + gw
    x0 = x - {'l' : 0, 'm' : total / 2, 'r' : total}[anchor]
    def draw(target, col, w) :
        d = ImageDraw.Draw(target)
        for i, ch in enumerate(s) :
            for line in GLYPHS[ch] :
                pts = [((x0 + adv * i + px / 4 * gw) * SS, (cy - h / 2 + py / 6 * h) * SS) for px, py in line]
                d.line(pts, fill = col, width = int(w * SS), joint = 'curve')
                for q in (pts[0], pts[-1]) : d.ellipse([q[0] - w * SS / 2, q[1] - w * SS / 2, q[0] + w * SS / 2, q[1] + w * SS / 2], fill = col)
    if glow :
        g = Image.new('L', im.size, 0); draw(g, 255, weight); g = g.filter(ImageFilter.GaussianBlur(1.6 * SS)).point(lambda v : int(v * 0.6))
        im.paste(Image.new('RGB', im.size, glow), (0, 0), g)
    if shadow :                                                # soft drop shadow, 1 pixel down / right
        g = Image.new('L', im.size, 0); draw(g, 255, weight); g = ImageChops.offset(g, SS, SS).filter(ImageFilter.GaussianBlur(0.6 * SS))
        im.paste(Image.new('RGB', im.size, (1, 3, 5)), (0, 0), g.point(lambda v : min(255, int(v * 1.1))))
    draw(im, color, weight)

# ------------------------------------------------------------------ geometry of the original panel (do not move)
BUTTONS = [25, 73, 116, 174, 221, 279, 323, 381]             # 15 x 15, row 31
CELLS = [(46, 2), (137, 3), (242, 3), (344, 3)]              # digits 10 x 13 in row 32
LABELS = [(4, 'CHN'), (94, 'PRG'), (197, 'MSB'), (300, 'LSB')]
SCREEN_XY, LAMP_Y, LAMPS_X, SETUP_XY = (11, 57), 48, (308, 350), (309, 88)

def tri(im, cx, cy, left, color, s = 3.2) :
    d = ImageDraw.Draw(im); cx, cy = cx * SS, cy * SS; k = s * SS
    pts = [(cx - k * 0.6, cy), (cx + k * 0.5, cy - k), (cx + k * 0.5, cy + k)] if left else [(cx + k * 0.6, cy), (cx - k * 0.5, cy - k), (cx - k * 0.5, cy + k)]
    d.polygon(pts, fill = color)

def arrow_button(im, x, left, pressed = False) :
    bevel(im, x, 31, x + 15, 46, 2, not pressed, top = (34, 40, 47) if pressed else (58, 66, 75), bot = (22, 26, 31) if pressed else (30, 35, 41))
    tri(im, x + 7.5 + (0.5 if pressed else 0), 38.5 + (0.5 if pressed else 0), left, CYAN)

def logo(panel_rgb) :
    # the YAMAHA emblem and name of the original title strip (Panel101.bmp, x 8-80, y 2-19), recoloured:
    # white name, blue disc with white tuning forks
    src = Image.open(B / 'Panel101.bmp').convert('L'); out = Image.new('RGBA', (74, 19), (0, 0, 0, 0))
    for y in range(19) :
        for x in range(74) :
            sx, sy = x + 8, y + 2; v = src.getpixel((sx, sy)); bg = src.getpixel((sx, 1))
            ink = max(0.0, min(1.0, (bg - v) / max(1, bg - 40)))
            dx, dy = sx - 17.5, sy - 11.2; r = (dx * dx + dy * dy) ** 0.5
            if r <= 9.2 :
                disc = max(0.0, min(1.0, 9.2 - r))
                blue = (44, 86, 214) if r < 6 else (34, 66, 180)
                c = tuple(int(blue[i] + (WHITE[i] - blue[i]) * ink) for i in range(3))
                out.putpixel((x, y), c + (int(255 * disc),))
    return out

def make_panel() :
    im = canvas(400, 114)
    bevel(im, 2, 2, 398, 23, 3)                               # title strip
    bevel(im, 2, 26, 398, 51, 3)                              # control row
    bevel(im, 2, 54, 398, 112, 3)                             # lower part
    for x, n in CELLS : bevel(im, x - 3, 30, x + 10 * n + 3, 47, 2, False, CELL)
    for i, x in enumerate(BUTTONS) : arrow_button(im, x, i % 2 == 0)
    for x, s in LABELS : text(im, (x, 38.6), s, 9.5, LABEL, 'SemiBold', 'lm', 0.92)
    bevel(im, SCREEN_XY[0] - 2, SCREEN_XY[1] - 2, SCREEN_XY[0] + 290, SCREEN_XY[1] + 49, 3, False, SCREEN)
    bevel(im, 305, 85, 393, 107, 3, False, (10, 13, 16))      # SETUP well
    stroke_text(im, 32, 11.3, 'YAMAHA', 11, WHITE, 2.0, 0.42, 0.78)
    p = down(im); p.paste(logo(p), (11, 2), logo(p)); return p

def make_name(model) :
    im = canvas(100, 23); bevel(im, -5, 2, 98, 23, 3)
    stroke_text(im, 93, 11.6, 'S-YXG' + model[2:], 9, GREY, 2.1, 0.5, 0.7, 'r')
    return down(im).crop((0, 0, 100, 23))

def make_screen() :
    im = canvas(288, 47, SCREEN); d = ImageDraw.Draw(im)
    d.rectangle(box(226, 0, 233, 47), fill = (40, 46, 53)); d.rectangle(box(227, 0, 229, 47), fill = (62, 70, 79))
    d.rounded_rectangle(box(234, 1, 287, 46), 2 * SS, fill = (10, 15, 19), outline = (28, 34, 40), width = SS // 2)
    out = down(im)
    for i in range(18) :
        x = 8 + 11 * i if i < 16 else (194, 205)[i - 16]
        pixel_text(out, x + 6, 38, str(i + 1) if i < 16 else 'LR'[i - 16])
    pixel_text(out, 261, 38, 'POLYPHONY')
    return out

# 3 x 5 pixel font for the part numbers under the meters (sharp at 1:1, unlike a scaled font)
PIX = {'0' : '111101101101111', '1' : '010110010010111', '2' : '111001111100111', '3' : '111001111001111',
       '4' : '101101111001001', '5' : '111100111001111', '6' : '111100111101111', '7' : '111001010010010',
       '8' : '111101111101111', '9' : '111101111001111', 'L' : '100100100100111', 'R' : '110101110101101',
       'P' : '111101111100100', 'O' : '111101101101111', 'Y' : '101101010010010', 'H' : '101101111101101', 'N' : '110101101101101'}

def pixel_text(im, cx, y, s) :
    # centred on column cx (the right one of the two middle pixels)
    x0 = cx - (4 * len(s) - 1 + 1) // 2
    for k, ch in enumerate(s) :
        for j, bit in enumerate(PIX[ch]) :
            if bit == '1' : im.putpixel((x0 + 4 * k + j % 3, y + j // 3), LABEL)

def segments(lit) :
    # one meter frame 11 x 28: floor dash (always) + lit segments of 2 pixels, 3 pixels apart, cyan with a glow
    im = canvas(11, 28, SCREEN); d = ImageDraw.Draw(im); glow = Image.new('L', im.size, 0); g = ImageDraw.Draw(glow)
    for j in range(lit + 1) :
        y = 25 - 3 * j; c = CYAN if j else (54, 160, 176)
        d.rectangle(box(1, y, 10, y + 2), fill = c); g.rectangle(box(1, y, 10, y + 2), fill = 120 if j else 50)
    halo = glow.filter(ImageFilter.GaussianBlur(1.3 * SS))
    im = Image.composite(Image.new('RGB', im.size, CYAN), im, halo.point(lambda v : v // 3))
    for j in range(lit + 1) : ImageDraw.Draw(im).rectangle(box(1, 25 - 3 * j, 10, 27 - 3 * j), fill = CYAN if j else (54, 160, 176))
    return down(im)

def make_meters() :
    out = Image.new('RGB', (99, 28))
    for k in range(9) : out.paste(segments(k), (11 * k, 0))
    return out

SEG = {'a' : (1.6, 0.6, 8.4, 2.0), 'b' : (7.6, 1.2, 9.0, 6.4), 'c' : (7.6, 6.6, 9.0, 11.8), 'd' : (1.6, 11.0, 8.4, 12.4),
       'e' : (1.0, 6.6, 2.4, 11.8), 'f' : (1.0, 1.2, 2.4, 6.4), 'g' : (1.8, 5.8, 8.2, 7.2)}
DIG = ['abcdef', 'bc', 'abdeg', 'abcdg', 'bcfg', 'acdfg', 'acdefg', 'abc', 'abcdefg', 'abcdfg', '']

def digit(segs, bg = CELL) :
    # 7-segment digit 10 x 13, unlit segments faintly visible like the mockup's display
    im = canvas(10, 13, bg); d = ImageDraw.Draw(im); glow = Image.new('L', im.size, 0); gd = ImageDraw.Draw(glow)
    for s, (x0, y0, x1, y1) in SEG.items() :
        r = [x0 * SS, y0 * SS, x1 * SS, y1 * SS]
        d.rounded_rectangle(r, SS // 2, fill = CYAN if s in segs else CYAN_DIM)
        if s in segs : gd.rounded_rectangle(r, SS // 2, fill = 255)
    halo = glow.filter(ImageFilter.GaussianBlur(1.0 * SS)).point(lambda v : v // 4)
    im = Image.composite(Image.new('RGB', im.size, CYAN), im, halo)
    for s, (x0, y0, x1, y1) in SEG.items() :
        if s in segs : ImageDraw.Draw(im).rounded_rectangle([x0 * SS, y0 * SS, x1 * SS, y1 * SS], SS // 2, fill = CYAN)
    return down(im)

def make_digits() :
    out = Image.new('RGB', (110, 13))
    for k in range(11) : out.paste(digit(DIG[k]), (10 * k, 0))
    return out

def original_lamps() :
    # bitmap 103 of syxg50.dll (XG off / on, GS off / on, 40 x 39 each)
    import io, struct
    sys.path.insert(0, str(HERE.parent.parent.parent)); from utility import dllpatch as dp
    data = (HERE.parent.parent.parent / 'source' / 'syxg50.dll').read_bytes()
    dib = dp.resource_data(data, dp.resource_entries(data, dp.RT_BITMAP)[103])
    return Image.open(io.BytesIO(b'BM' + struct.pack('<IHHI', 14 + len(dib), 0, 0, 54) + dib)).convert('RGB')

def lamp_logo(im, k, on) :
    # the original lamp picture as a stamped-in logo: a recess in the panel (dark inner shadow along the top / left
    # edges, light edge along the bottom / right), contrast raised; off = dark grey metal, on = bright light blue
    src = original_lamps().crop((80 * k + 40 * on, 0, 80 * k + 40 * on + 40, 39))
    bg = Image.new('RGB', src.size, src.getpixel((0, 0)))
    m = ImageChops.difference(src, bg).convert('L').point(lambda v : min(255, v * 4) if v > 6 else 0)
    lum = src.convert('L'); lo = lum.getextrema()[0]
    lum = lum.point(lambda v : max(0, min(255, int((v - (60 if on else lo)) * (1.9 if on else 1.5)))))      # contrast stretch
    W, H = im.size; m = m.resize((W, H), Image.BICUBIC); lum = lum.resize((W, H), Image.BICUBIC)
    solid = m.point(lambda v : 255 if v > 90 else 0).filter(ImageFilter.GaussianBlur(0.5 * SS))
    lit = ImageChops.subtract(solid, ImageChops.offset(solid, SS, SS))                  # edges facing down / right
    dark = ImageChops.subtract(ImageChops.offset(solid, SS, SS), solid)                 # shadow top / left
    rim = Image.new('RGB', im.size, (96, 108, 120)); sh = Image.new('RGB', im.size, (2, 4, 6))
    im.paste(rim, (SS, SS), solid.filter(ImageFilter.MaxFilter(SS * 2 + 1)).point(lambda v : v // 3))   # light edge below
    im.paste(sh, (0, 0), ImageChops.subtract(ImageChops.offset(solid, -SS, -SS), solid).point(lambda v : int(v * 0.9)))
    if on :
        halo = m.filter(ImageFilter.GaussianBlur(2.4 * SS)).point(lambda v : int(v * 0.6))
        im.paste(Image.new('RGB', im.size, (30, 170, 200)), (0, 0), halo)
        face = Image.merge('RGB', [lum.point(lambda v, c = c : min(255, int(c * (0.62 + v / 330)))) for c in (110, 232, 255)])
    else :
        face = Image.merge('RGB', [lum.point(lambda v, c = c : int(c * (0.45 + v / 400))) for c in (150, 160, 172)])
    im.paste(face, (0, 0), m)

# Logos drawn by hand (skin52/src/, 1 pixel = 1 lamp pixel unless noted): logos_off_mockup.png = both unlit logos
# (XG at x 0, GS at x 42, rows 6 ... 37 of the lamp, background (51, 53, 63)); gs_lit_fixed.png = the lit GS with the
# corrected lower edge, 3 x enlarged, lamp pixels x 1 ... 35, y 9 ... 37. They are laid over the panel as a difference to their own
# background, so the panel's gradient shows through.
def mockup_overlay(lamp, path, box, size = None, bg = None) :
    # lamp: 40 x 39 RGB image, box = (x, y) of the mockup's top left corner in the lamp, size = target size (the
    # mockup is shrunk to it), bg = flat background colour of the mockup (default: its first column, row by row)
    import numpy as np
    m = Image.open(HERE / 'skin52' / 'src' / path).convert('RGB')
    if size : m = m.resize(size, Image.LANCZOS)
    a = np.asarray(m).astype(float); b = np.asarray(lamp).astype(float)
    ref = np.array(bg, float)[None, None, :] if bg else a[:, :1, :]
    x0, y0 = box; h, w = a.shape[:2]
    reg = b[y0 : y0 + h, x0 : x0 + w]; h, w = reg.shape[:2]
    reg += (a - ref)[:h, :w]
    return Image.fromarray(np.clip(b, 0, 255).astype('uint8'))

def make_lamps(panel) :
    out = Image.new('RGB', (160, 39)); off = Image.open(HERE / 'skin52' / 'src' / 'logos_off_mockup.png').convert('RGB')
    for k, x in enumerate((308, 308, 350, 350)) :
        im = canvas(40, 39); im.paste(panel.crop((x, LAMP_Y, x + 40, LAMP_Y + 39)).resize((40 * SS, 39 * SS), Image.LANCZOS))
        if k == 1 : lamp_logo(im, 0, 1)                                         # lit XG: drawn from the original lamp
        lamp = down(im)
        if k == 0 : lamp = lamp_off(lamp, off, 0)
        elif k == 2 : lamp = lamp_off(lamp, off, 42)
        elif k == 3 : lamp = mockup_overlay(lamp, 'gs_lit_fixed.png', (1, 9), (35, 28))
        out.paste(lamp, (40 * k, 0))
    return out

def lamp_off(lamp, off, mx0) :
    # unlit logo from the mockup: its columns mx0 ... mx0 + 39, difference to its background (51, 53, 63)
    import numpy as np
    a = np.asarray(off).astype(float)[:, mx0 : mx0 + 40]
    if a.shape[1] < 40 : a = np.concatenate([a, np.full((32, 40 - a.shape[1], 3), 1.0) * np.array([51, 53, 63.])], 1)
    b = np.asarray(lamp).astype(float); b[6 : 38] += a - np.array([51, 53, 63.])
    return Image.fromarray(np.clip(b, 0, 255).astype('uint8'))

def make_setup(panel) :
    out = Image.new('RGB', (80 * 2, 16))
    for k, pressed in enumerate((True, False)) :
        im = canvas(80, 16); im.paste(panel.crop((309, 88, 389, 104)).resize((80 * SS, 16 * SS), Image.LANCZOS))
        bevel(im, 0, 0, 80, 16, 2, not pressed, top = (30, 35, 41) if pressed else (60, 68, 77), bot = (20, 24, 28) if pressed else (32, 37, 43))
        stroke_text(im, 40 + (0.5 if pressed else 0), 8.2 + (0.5 if pressed else 0), 'SETUP', 7, (200, 208, 214) if pressed else WHITE, 1.3, 0.62, 0.72, 'm')
        out.paste(down(im), (80 * k, 0))
    return out

def make_buttons(panel) :
    # appended to bitmap 106: pressed left / right button and a dash digit
    out = Image.new('RGB', (40, 15))
    for k, x in enumerate(BUTTONS[:2]) :
        im = canvas(15, 15); im.paste(panel.crop((x, 31, x + 15, 46)).resize((15 * SS, 15 * SS), Image.LANCZOS))
        bevel(im, 0, 0, 15, 15, 2, False, top = (26, 31, 37), bot = (16, 19, 23)); tri(im, 8, 8, k == 0, CYAN)
        out.paste(down(im), (15 * k, 0))
    out.paste(digit('g'), (30, 0)); return out

# ------------------------------------------------------------------ preview with sample values (approval)
def compose(panel, name, screen, lamps, meters, digits, setup, btn, levels, poly, vals, xg = True) :
    p = panel.copy(); p.paste(name, (300, 0)); p.paste(screen, SCREEN_XY)
    for i, lv in enumerate(levels) :
        x = 19 + 11 * i if i < 16 else (205, 216)[i - 16]
        p.paste(meters.crop((11 * lv, 0, 11 * lv + 11, 28)), (x, 62))
    s = str(poly)
    for k, c in enumerate(reversed(s)) : p.paste(digits.crop((10 * int(c), 0, 10 * int(c) + 10, 13)), (276 - 10 * k, 73))
    for k in range(len(s), 3) : p.paste(digits.crop((100, 0, 110, 13)), (276 - 10 * k, 73))
    p.paste(lamps.crop((40 if xg else 0, 0, 80 if xg else 40, 39)), (308, LAMP_Y))
    p.paste(lamps.crop((80 if xg else 120, 0, 120 if xg else 160, 39)), (350, LAMP_Y))
    p.paste(setup.crop((80, 0, 160, 16)), SETUP_XY)
    for (x, n), v in zip(CELLS, vals) :
        for k, c in enumerate(v) : p.paste(digits.crop((10 * int(c), 0, 10 * int(c) + 10, 13)), (x + 10 * k, 32))
    return p

if __name__ == '__main__' :
    OUT.mkdir(exist_ok = True)
    panel = make_panel(); screen = make_screen(); meters = make_meters(); digits = make_digits()
    lamps = make_lamps(panel); setup = make_setup(panel); btn = make_buttons(panel)
    files = {'Panel101.bmp' : panel, 'Bitmap102.bmp' : screen, 'Bitmap103.bmp' : lamps, 'Bitmap104.bmp' : meters,
             'Bitmap105.bmp' : digits, 'Bitmap106.bmp' : setup, 'PanelButtons.bmp' : btn}
    for m in ('MU50', 'MU80', 'MU90', 'MU100', 'MU128', 'MU1000') : files[f'Name_{m}.bmp'] = make_name(m)
    for n, im in files.items() : im.save(OUT / n)
    if '--preview' in sys.argv :
        levels = [0, 6, 0, 0, 0, 6, 0, 0, 0, 7, 0, 4, 0, 0, 0, 0, 8, 8]
        new = compose(panel, files['Name_MU90.bmp'], screen, lamps, meters, digits, setup, btn, levels, 18, ['01', '049', '000', '000'])
        old = Image.open(HERE / 'panel_preset.png').convert('RGB')
        Z = 3; W = 400 * Z; sheet = Image.new('RGB', (W + 40, 114 * Z * 2 + 114 + 120), (245, 246, 248))
        d = ImageDraw.Draw(sheet); f = ImageFont.truetype(FONT % 'SemiBold', 18)
        d.text((20, 10), 'Original (default)', font = f, fill = (40, 40, 40)); sheet.paste(old.resize((W, 114 * Z), Image.NEAREST), (20, 36))
        y = 36 + 114 * Z + 20
        d.text((20, y), 'Modern (click on the YAMAHA logo switches)', font = f, fill = (40, 40, 40))
        sheet.paste(new.resize((W, 114 * Z), Image.NEAREST), (20, y + 26))
        y += 26 + 114 * Z + 20; d.text((20, y), 'Actual size:', font = f, fill = (40, 40, 40))
        sheet.paste(old, (150, y)); sheet.paste(new, (150 + 410, y))
        sheet.crop((0, 0, sheet.width, y + 124)).save(OUT / 'preview.png'); new.save(OUT / 'preview_modern_1x.png')
    print('written to', OUT)
