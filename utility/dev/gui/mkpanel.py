# mkpanel.py: panel bitmaps of issue #42 (pip: pillow). Run in utility/dev/gui:
#   python3 mkpanel.py
# Inputs (panel42/): template.png (bitmap 101, 400 x 114, no model name, from the issue), mockup_mu90.png (the same
# with the control row CHN / PRG / MSB / LSB and values, from the issue), Bitmap101_MU50_original.png (the original
# S-YXG50 bitmap 101), Bitmap101_<model>.bmp (the 400 x 90 model bitmaps of the earlier versions, only for their
# model names), PresetButtons_old.bmp (pressed buttons of #35), and ../../bitmaps/Bitmap105.bmp.
# Outputs (../../bitmaps/):
#   Panel101.bmp       bitmap 101 for every model: template + the control row of the mockup, value cells blank
#   Name_<model>.bmp   the model name S-YXGM<n> (title strip x 280-399, y 0-22, 120 x 23) pasted into bitmap 101 per model: the
#                      100 x 23 names of the earlier versions with an M drawn between G and the number (issue #74)
#   PortLabels.bmp     the port labels PORT A - PORT D (64 x 16 each, 256 x 16) appended to bitmap 106 at x 400 and drawn into the
#                      title strip at x 168, y 3 (issue #74, dev/poly/panel.asm): embossed PORT and a black box with the orange
#                      letter, the group centred on x 200
#   PanelButtons.bmp   appended to bitmap 106: pressed left / right button (15 x 15 each) and a dash digit (10 x 13)
from PIL import Image
from pathlib import Path
HERE = Path(__file__).resolve().parent; P = HERE / 'panel42'; B = HERE.parent.parent / 'bitmaps'
DIGITS = [(46, 2), (137, 3), (242, 3), (344, 3)]     # first digit x and count of CHN, PRG, MSB, LSB; row 32
NAME_BOX = (300, 0, 400, 23)
tpl = Image.open(P / 'template.png').convert('RGB'); mock = Image.open(P / 'mockup_mu90.png').convert('RGB')
dig = Image.open(B / 'Bitmap105.bmp').convert('RGB'); blank = dig.crop((100, 0, 110, 13))
panel = tpl.copy(); panel.paste(mock.crop((0, 23, 400, 114)), (0, 23))
# the mockup's label "PRE" becomes "PRG" (same font as the other labels: DejaVu Sans Bold 8, black), 2 pixels further
# left so it keeps 3 pixels to its button like CHN
from PIL import ImageDraw, ImageFont
panel.paste(tpl.crop((92, 29, 116, 47)), (92, 29))
ImageDraw.Draw(panel).text((94, 34), 'PRG', font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 8), fill = (0, 0, 0))
for x, n in DIGITS :
    for i in range(n) : panel.paste(blank, (x + 10 * i, 32))
panel.save(B / 'Panel101.bmp')
for model, src in [('MU50', P / 'Bitmap101_MU50_original.png')] + [(m, P / f'Bitmap101_{m}.bmp') for m in ('MU80', 'MU90', 'MU100', 'MU128', 'MU1000')] :
    Image.open(src).convert('RGB').crop(NAME_BOX).save(B / f'Name_{model}.bmp')
# MU2000 (#53): no earlier bitmap; the "1" of the MU1000 name replaced by the "2" of the MU128 name (9 pixels
# from x 74, alpha taken against each picture's own background, drawn 1 pixel left of the "1" so it keeps the
# digit spacing and does not touch the "0")
a = Image.open(B / 'Name_MU1000.bmp').convert('RGB'); b = Image.open(B / 'Name_MU128.bmp').convert('RGB')
pa, pb = a.load(), b.load(); n2000 = a.copy(); po = n2000.load()
for x in range(57, 67) :
    for y in range(5, 19) : po[x, y] = pa[x, 4]
for dx in range(9) :
    for y in range(5, 19) :
        bga, bgb, v = pa[57 + dx, 4], pb[74 + dx, 4], pb[74 + dx, y]
        al = max(0, min(1, (sum(v) - sum(bgb)) / max(1, 765 - sum(bgb))))
        c = tuple(round(bga[i] + (255 - bga[i]) * al) for i in range(3))
        po[57 + dx, y] = max(c, po[57 + dx, y], key = sum)
n2000.save(B / 'Name_MU2000.bmp')
old = Image.open(P / 'PresetButtons_old.bmp').convert('RGB')
strip = Image.new('RGB', (40, 15)); strip.paste(old.crop((0, 0, 30, 15)), (0, 0))
dash = blank.copy(); fg = max(dig.getdata(), key = sum)
for x in range(2, 8) :
    for y in (6, 7) : dash.putpixel((x, y), fg)
strip.paste(dash, (30, 0)); strip.save(B / 'PanelButtons.bmp')
# check: the mockup's own digits are the runtime digits (bitmap 105) at the positions above
for (x, n), txt in zip(DIGITS, ('01', '078', '001', '040')) :
    for i, c in enumerate(txt) :
        a = mock.crop((x + 10 * i, 32, x + 10 * i + 10, 45)); b = dig.crop((int(c) * 10, 0, int(c) * 10 + 10, 13))
        assert list(a.getdata()) == list(b.getdata()), (x, i)

# --- issue #74: the multi-port plugins are named S-YXGM<n>: an M between G and the number (the earlier 100 x 23 names move 11 pixels
# to the left, the picture grows to 120 x 23 so the number stays where it was), and the port labels
import numpy as np
FONT = '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf'
def text_mask(text, size, sx, w, h, base, x0 = 1, S = 8) :
    f = ImageFont.truetype(FONT, int(size * S))
    m = Image.new('L', (int(w * S / sx), h * S), 0); ImageDraw.Draw(m).text((x0 * S, base * S), text, font = f, fill = 255, anchor = 'ls')
    m = m.resize((w * S, h * S), Image.LANCZOS)
    return np.asarray(m.resize((w, h), Image.LANCZOS), dtype = float) / 255
def emboss(a, bg, dark = 0.70, strength = 0.6) :
    # white text with a darker edge up and to the left on the strip background bg (rows x cols x 3), like the names
    a = np.clip(a ** 0.65, 0, 1); sh = np.zeros_like(a); sh[:-1, :-1] = a[1:, 1:]
    return np.uint8(np.clip((bg * (1 - strength * sh[..., None]) + bg * dark * strength * sh[..., None]) * (1 - a[..., None]) + 255 * a[..., None], 0, 255))
def with_m(old, prefix = 46, mw = 11, shift = 20) :
    a = np.asarray(old.convert('L'), dtype = int)[3:20]
    c0 = int(np.where((abs(a - 178) > 12).any(axis = 0))[0][0]); pend = c0 + prefix     # the prefix S-YXG is 46 pixels wide
    new = Image.new('RGB', (old.width + shift, old.height))
    for y in range(old.height) :
        for x in range(new.width) : new.putpixel((x, y), old.getpixel((0, y)))
    new.paste(old.crop((pend, 0, old.width, old.height)), (pend + shift, 0))
    new.paste(old.crop((c0, 0, pend, old.height)), (c0 + shift - mw, 0))
    m = text_mask('M', 17, 0.85, 20, old.height, 18.5); cols = np.where(m.max(axis = 0) > 0.3)[0]
    bg = np.array([[old.getpixel((0, y))] * 20 for y in range(old.height)], dtype = float)
    g = Image.fromarray(emboss(m, bg), 'RGB').crop((cols.min() - 1, 0, cols.min() - 1 + mw, old.height))
    new.paste(g, (pend + shift - mw, 0))
    return new
for model in ('MU50', 'MU80', 'MU90', 'MU100', 'MU128', 'MU1000', 'MU2000') :
    old = Image.open(B / f'Name_{model}.bmp').convert('RGB')
    if old.width == 100 : with_m(old).save(B / f'Name_{model}.bmp')        # the names already carry the M after the first run
LABEL = (168, 3, 64, 16)                                             # x, y, width, height in the title strip
# PORT (embossed like the names), a gap and the letter in a 17 x 15 box (bevel: dark top / left, light bottom / right) in the colours of the
# polyphony digits (bitmap 105: background (9, 7, 28), orange (255, 106, 0)); PORT + box are centred on the panel (x 200)
BOX_BG, ORANGE, GAP, BOXW, BOXH = (9, 7, 28), (255, 106, 0), 3, 17, 15
bg = np.asarray(panel.crop((LABEL[0], LABEL[1], LABEL[0] + LABEL[2], LABEL[1] + LABEL[3])), dtype = float)
TEXT_W = 38                                                                  # width of PORT in the approved mockup
mt = text_mask('PORT', 13, 0.9, LABEL[2], LABEL[3], 13.5, x0 = 0); cols = np.where(mt.max(axis = 0) > 0.25)[0]
size = 13 * TEXT_W / (cols.max() - cols.min() + 1)
mt = text_mask('PORT', size, 0.9, LABEL[2], LABEL[3], 13.5, x0 = 0); cols = np.where(mt.max(axis = 0) > 0.25)[0]
tw = int(cols.max() - cols.min() + 1); left = 200 - (tw + GAP + BOXW) // 2 - LABEL[0]            # label-relative x of the group
mt = text_mask('PORT', size, 0.9, LABEL[2], LABEL[3], 13.5, x0 = left - cols.min())
bx = left + tw + GAP; by = 1
gfont = ImageFont.truetype(FONT, 14 * 8)
labels = Image.new('RGB', (4 * LABEL[2], LABEL[3]))
for i, port in enumerate('ABCD') :
    cell = Image.fromarray(emboss(mt, bg, 0.40, 0.95), 'RGB')
    d = ImageDraw.Draw(cell)
    d.rectangle((bx, by, bx + BOXW - 1, by + BOXH - 1), fill = BOX_BG)
    d.line((bx, by, bx + BOXW - 2, by), fill = (0x60, 0x62, 0x6e)); d.line((bx, by, bx, by + BOXH - 2), fill = (0x60, 0x62, 0x6e))
    d.line((bx, by + BOXH - 1, bx + BOXW - 1, by + BOXH - 1), fill = (0xfa, 0xfa, 0xfc)); d.line((bx + BOXW - 1, by, bx + BOXW - 1, by + BOXH - 1), fill = (0xfa, 0xfa, 0xfc))
    g = Image.new('L', (40 * 8, 20 * 8), 0); ImageDraw.Draw(g).text((4 * 8, 16 * 8), port, font = gfont, fill = 255, anchor = 'ls')
    g = g.resize((40, 20), Image.BOX).point(lambda v : 255 if v >= 128 else 0)                  # crisp, like the digits
    gb = g.getbbox(); g = g.crop(gb)
    cell.paste(Image.new('RGB', g.size, ORANGE), (bx + 1 + (BOXW - 2 - g.width) // 2, by + 1 + (BOXH - 2 - g.height) // 2), g)
    labels.paste(cell, (i * LABEL[2], 0))
labels.save(B / 'PortLabels.bmp')
print('Panel101.bmp, Name_*.bmp, PanelButtons.bmp, PortLabels.bmp written')
