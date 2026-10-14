# mkpreset.py <Bitmap101 any model>.bmp <Bitmap105.bmp> out_dir  (pip: pillow)
# Draws the panel controls of the title strip (issues #16, #23, #35): channel selector "CHN < 01 >" and the
# program / bank selector "PRE v < 001 >" (label switches PRE / MSB / LSB), centred between the YAMAHA logo
# and the model name, rows 4-18. Writes
#   PresetPanel_<dx>.bmp    the title strip area with both controls in their normal state (pasted into bitmap 101)
#   PresetButtons_<dx>.bmp  pressed left / right button, then the labels PRE / MSB / LSB with their mark (each
#                           LW x 15) and a dash in the style of the readout digits (10 x 13, for a bank select
#                           the engine ignores), appended to bitmap 106 (SETUP button) on its right
# for each offset dx in DXS (models with 7 / 8 / 9 characters in the name: +8 / +4 / 0, see panel.asm panel_dx);
# the title strip has a horizontal gradient, so each offset gets its own pictures
#   layout.txt         the positions for panel.asm and dllpatch.py
#   preview.png        enlarged preview (PRE, MSB, LSB)
from PIL import Image, ImageDraw, ImageFont
import sys, os

X0, Y0, W, H = 82, 1, 229, 21          # area replaced in bitmap 101 at x X0 + dx (logo ends at x 77, names start at 311 / 319 / 328)
DXS = (0, 4, 8)
CENTRE = 195                            # middle between the logo and the shortest gap to a name (S-YXG1000)
BTN, BY = 15, 4                         # button size, control rows 4-18 (same centre line as the logo)
GAP = 3                                 # button - box gap (as before)
BOX2, BOX3 = 27, 37                     # readout boxes for 2 and 3 digits (3 px border left, digits 10 px each)
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
LABELS = ('PRE', 'MSB', 'LSB')

def font() : return ImageFont.truetype(FONT, 8)
def text_w(t) :
    d = ImageDraw.Draw(Image.new('RGB', (40, 20))); return d.textbbox((0, 0), t, font = font())[2]
LW = max(text_w(t) for t in ('CHN',) + LABELS)
MARK = 7                                # mark after the switchable label: 5 px triangle + 2 px

def layout() :
    g1 = LW + GAP + BTN + GAP + BOX2 + GAP + BTN
    g2 = LW + MARK + GAP + BTN + GAP + BOX3 + GAP + BTN
    x = CENTRE - (g1 + 12 + g2) // 2
    L = dict(chn_label = x)
    x += LW + GAP; L['chn_l'] = x; x += BTN + GAP; L['chn_box'] = x; x += BOX2 + GAP; L['chn_r'] = x; x += BTN + 12
    L['mode_label'] = x; x += LW + MARK + GAP; L['mode_l'] = x; x += BTN + GAP; L['mode_box'] = x; x += BOX3 + GAP
    L['mode_r'] = x; L['end'] = x + BTN
    assert X0 <= L['chn_label'] and L['end'] <= X0 + W
    return L

def button(im, x, y, left, pressed) :
    d = ImageDraw.Draw(im)
    for i in range(BTN) :                          # vertical gradient face
        t = i / (BTN - 1)
        a, b = ((150, 152, 160), (222, 223, 228)) if pressed else ((238, 239, 243), (160, 162, 172))
        c = tuple(int(a[k] + (b[k] - a[k]) * t) for k in range(3))
        d.line((x, y + i, x + BTN - 1, y + i), fill = c)
    hi, lo = ((90, 92, 104), (250, 250, 252)) if pressed else ((255, 255, 255), (96, 98, 110))
    d.line((x, y, x + BTN - 2, y), fill = hi); d.line((x, y, x, y + BTN - 2), fill = hi)
    d.line((x + 1, y + BTN - 1, x + BTN - 1, y + BTN - 1), fill = lo); d.line((x + BTN - 1, y + 1, x + BTN - 1, y + BTN - 1), fill = lo)
    o = 1 if pressed else 0
    cx, cy = x + BTN // 2 + o, y + BTN // 2 + o
    for k in range(5) :                            # shaded triangle: dark tip, lighter base
        c = tuple(int(v) for v in (40 + 14 * k, 44 + 14 * k, 70 + 14 * k))
        if left : d.line((cx - 2 + k, cy - k, cx - 2 + k, cy + k), fill = c)
        else :    d.line((cx + 2 - k, cy - k, cx + 2 - k, cy + k), fill = c)

def box(d, x, w) :
    d.rectangle((x, BY, x + w - 1, BY + 14), fill = (16, 14, 30), outline = (96, 98, 110))
    d.line((x, BY + 14, x + w - 1, BY + 14), fill = (250, 250, 252)); d.line((x + w - 1, BY, x + w - 1, BY + 14), fill = (250, 250, 252))

def label(d, x, t, mark) :
    d.text((x + LW - text_w(t), BY + 3), t, font = font(), fill = (0, 0, 0))
    if mark : d.polygon([(x + LW + 2, BY + 6), (x + LW + 6, BY + 6), (x + LW + 4, BY + 9)], fill = (0, 0, 0))

def panel(base, L, mode = 'PRE') :
    im = base.copy(); d = ImageDraw.Draw(im)
    label(d, L['chn_label'], 'CHN', False); label(d, L['mode_label'], mode, True)
    for k, left in (('chn_l', True), ('chn_r', False), ('mode_l', True), ('mode_r', False)) : button(im, L[k], BY, left, False)
    box(d, L['chn_box'], BOX2); box(d, L['mode_box'], BOX3)
    return im

if __name__ == '__main__' :
    base = Image.open(sys.argv[1]).convert('RGB'); dig = Image.open(sys.argv[2]).convert('RGB'); out = sys.argv[3]
    L0 = layout()
    for dx in DXS :
        L = {k : v + dx for k, v in L0.items()}
        im = panel(base, L)
        im.crop((X0 + dx, Y0, X0 + dx + W, Y0 + H)).save(os.path.join(out, f'PresetPanel_{dx}.bmp'))
        strip = Image.new('RGB', (2 * BTN + 3 * (LW + MARK) + 10, BTN))
        t = base.copy(); button(t, 0, BY, True, True); strip.paste(t.crop((0, BY, BTN, BY + BTN)), (0, 0))
        t = base.copy(); button(t, 0, BY, False, True); strip.paste(t.crop((0, BY, BTN, BY + BTN)), (BTN, 0))
        for i, m in enumerate(LABELS) :
            t = base.copy(); label(ImageDraw.Draw(t), L['mode_label'], m, True)
            strip.paste(t.crop((L['mode_label'], BY, L['mode_label'] + LW + MARK, BY + BTN)), (2 * BTN + i * (LW + MARK), 0))
        dash = dig.crop((100, 0, 110, 13)).copy(); fg = max(dig.getdata(), key = sum)   # blank digit cell + bar
        for x in range(2, 8) :
            for y in (6, 7) : dash.putpixel((x, y), fg)
        strip.paste(dash, (2 * BTN + 3 * (LW + MARK), 0))
        strip.save(os.path.join(out, f'PresetButtons_{dx}.bmp'))
    with open(os.path.join(out, 'layout.txt'), 'w') as f :
        for k, v in L0.items() : f.write(f'{k} = {v}\n')
        f.write(f'label_w = {LW + MARK}\noffsets = {DXS}\n')
    rows = []
    for m, v in (('PRE', (0, 0, 1)), ('MSB', (0, 0, 0)), ('LSB', (0, 0, 0))) :
        pv = panel(base, L0, m)
        for i, n in enumerate((0, 1)) : pv.paste(dig.crop((n * 10, 0, n * 10 + 10, 13)), (L0['chn_box'] + 3 + 10 * i, BY + 1))
        for i, n in enumerate(v) : pv.paste(dig.crop((n * 10, 0, n * 10 + 10, 13)), (L0['mode_box'] + 3 + 10 * i, BY + 1))
        rows.append(pv.crop((0, 0, 400, 24)).resize((1200, 72), Image.NEAREST))
    p = Image.new('RGB', (1200, 3 * 82), (255, 255, 255))
    for i, r in enumerate(rows) : p.paste(r, (0, i * 82))
    p.save(os.path.join(out, 'preview.png'))
    print(L0, 'label width', LW + MARK)
