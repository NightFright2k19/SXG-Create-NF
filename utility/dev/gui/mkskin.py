# mkskin.py: second panel skin "Modern" (issue #52), drawn after the mockup of the issue (pip: pillow). Run in
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
    text(im, (29, 12.6), 'YAMAHA', 13.5, WHITE, 'ExtraBold', 'lm', 0.96, track = 0.6)
    p = down(im); p.paste(logo(p), (8, 2), logo(p)); return p

def make_name(model) :
    im = canvas(100, 23); bevel(im, -5, 2, 98, 23, 3)
    text(im, (93, 12.4), 'S-YXG' + {'MU50' : '50'}.get(model, model[2:]), 12, GREY, 'SemiBold', 'rm', 1.0, track = 0.7)
    return down(im).crop((0, 0, 100, 23))

def make_screen() :
    im = canvas(288, 47, SCREEN); d = ImageDraw.Draw(im)
    d.rectangle(box(226, 0, 233, 47), fill = (40, 46, 53)); d.rectangle(box(227, 0, 229, 47), fill = (62, 70, 79))
    d.rounded_rectangle(box(234, 1, 287, 46), 2 * SS, fill = (10, 15, 19), outline = (28, 34, 40), width = SS // 2)
    text(im, (260.5, 40.5), 'POLYPHONY', 6.2, LABEL, 'SemiBold', 'mm', 0.88, track = 0.3)
    out = down(im)
    for i in range(18) :
        x = 8 + 11 * i if i < 16 else (194, 205)[i - 16]
        pixel_text(out, x + 6, 38, str(i + 1) if i < 16 else 'LR'[i - 16])
    return out

# 3 x 5 pixel font for the part numbers under the meters (sharp at 1:1, unlike a scaled font)
PIX = {'0' : '111101101101111', '1' : '010110010010111', '2' : '111001111100111', '3' : '111001111001111',
       '4' : '101101111001001', '5' : '111100111001111', '6' : '111100111101111', '7' : '111001010010010',
       '8' : '111101111101111', '9' : '111101111001111', 'L' : '100100100100111', 'R' : '110101110101101'}

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

# stylised XG / GS logos after the original lamps (bitmap 103): an X merging into a square G; a slanted square G
# interlocked with an S. Polygons in lamp coordinates (40 x 39), sheared to the right.
G_BOX = lambda x0, y0, x1, y1, t : [[(x0, y0), (x1, y0), (x1, y0 + t), (x0, y0 + t)], [(x0, y0), (x0 + t, y0), (x0 + t, y1), (x0, y1)],
    [(x0, y1 - t), (x1, y1 - t), (x1, y1), (x0, y1)], [(x1 - t, (y0 + y1) / 2), (x1, (y0 + y1) / 2), (x1, y1), (x1 - t, y1)],
    [((x0 + x1) / 2 + 1, (y0 + y1) / 2), (x1, (y0 + y1) / 2), (x1, (y0 + y1) / 2 + t - 1), ((x0 + x1) / 2 + 1, (y0 + y1) / 2 + t - 1)]]
S_BOX = lambda x0, y0, x1, y1, t : [[(x0, y0), (x1, y0), (x1, y0 + t), (x0, y0 + t)], [(x0, y0), (x0 + t, y0), (x0 + t, (y0 + y1 + t) / 2), (x0, (y0 + y1 + t) / 2)],
    [(x0, (y0 + y1 - t) / 2), (x1, (y0 + y1 - t) / 2), (x1, (y0 + y1 + t) / 2), (x0, (y0 + y1 + t) / 2)],
    [(x1 - t, (y0 + y1 - t) / 2), (x1, (y0 + y1 - t) / 2), (x1, y1), (x1 - t, y1)], [(x0, y1 - t), (x1, y1 - t), (x1, y1), (x0, y1)]]
LOGOS = {
    0 : [[(4, 11), (10.5, 11), (21, 29), (14.5, 29)], [(14.5, 11), (21, 11), (10.5, 29), (4, 29)]] + G_BOX(20, 11, 36, 29, 4),
    1 : G_BOX(4, 9, 22, 27, 4) + S_BOX(20, 15, 35, 31, 3.4),
}

def lamp_logo(im, k, on) :
    m = Image.new('L', im.size, 0); d = ImageDraw.Draw(m); sh = 0.28 if k else 0.18
    for poly in LOGOS[k] : d.polygon([((x + sh * (20 - y)) * SS, y * SS) for x, y in poly], fill = 255)
    if k :                                                    # gap between G and S
        for poly in S_BOX(20, 15, 35, 31, 3.4) :
            g = [((x + sh * (20 - y)) * SS, y * SS) for x, y in poly]
            d.line(g + g[:1], fill = 0, width = int(1.2 * SS))
        for poly in S_BOX(20, 15, 35, 31, 3.4) : d.polygon([((x + sh * (20 - y)) * SS, y * SS) for x, y in poly], fill = 255)
    if on :
        halo = m.filter(ImageFilter.GaussianBlur(2.6 * SS)).point(lambda v : int(v * 0.8))
        im.paste(Image.new('RGB', im.size, (30, 160, 185)), (0, 0), halo)
        face = Image.new('RGB', im.size, CYAN); hl = Image.new('RGB', im.size, (190, 248, 255))
    else : face = Image.new('RGB', im.size, (74, 82, 91)); hl = Image.new('RGB', im.size, (104, 113, 122))
    im.paste(face, (0, 0), m)
    top = ImageChops.subtract(m, ImageChops.offset(m, 0, SS)).point(lambda v : v // 2)   # light top edges
    im.paste(hl, (0, 0), top)

def make_lamps(panel) :
    out = Image.new('RGB', (160, 39))
    for k, x in enumerate((308, 308, 350, 350)) :
        im = canvas(40, 39); im.paste(panel.crop((x, LAMP_Y, x + 40, LAMP_Y + 39)).resize((40 * SS, 39 * SS), Image.LANCZOS))
        lamp_logo(im, k // 2, k % 2); out.paste(down(im), (40 * k, 0))
    return out

def make_setup(panel) :
    out = Image.new('RGB', (80 * 2, 16))
    for k, pressed in enumerate((True, False)) :
        im = canvas(80, 16); im.paste(panel.crop((309, 88, 389, 104)).resize((80 * SS, 16 * SS), Image.LANCZOS))
        bevel(im, 0, 0, 80, 16, 2, not pressed, top = (30, 35, 41) if pressed else (60, 68, 77), bot = (20, 24, 28) if pressed else (32, 37, 43))
        text(im, (40 + (0.5 if pressed else 0), 8.4 + (0.5 if pressed else 0)), 'SETUP', 8.5, (200, 208, 214) if pressed else WHITE, 'Medium', 'mm', 1.0, track = 1.2)
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
