# mkpanel.py: panel bitmaps of issue #42 (pip: pillow). Run in utility/dev/gui:
#   python3 mkpanel.py
# Inputs (panel42/): template.png (bitmap 101, 400 x 114, no model name, from the issue), mockup_mu90.png (the same
# with the control row CHN / PRG / MSB / LSB and values, from the issue), Bitmap101_MU50_original.png (the original
# S-YXG50 bitmap 101), Bitmap101_<model>.bmp (the 400 x 90 model bitmaps of the earlier versions, only for their
# model names), PresetButtons_old.bmp (pressed buttons of #35), and ../../bitmaps/Bitmap105.bmp.
# Outputs (../../bitmaps/):
#   Panel101.bmp       bitmap 101 for every model: template + the control row of the mockup, value cells blank
#   Name_<model>.bmp   the model name (title strip x 300-399, y 0-22) pasted into bitmap 101 per model
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
print('Panel101.bmp, Name_*.bmp, PanelButtons.bmp written')
