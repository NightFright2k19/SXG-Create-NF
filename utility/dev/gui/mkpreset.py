# mkpreset.py <Bitmap101 any model>.bmp <Bitmap105.bmp> out_dir  (pip: pillow)
# Draws the preset control (issue #16) for the panel title strip: two shaded arrow buttons (normal and
# pressed), the frame of the 3-digit readout and the label "PRESET". Writes
#   PresetPanel.bmp    the title strip area with the control in its normal state (pasted into bitmap 101)
#   PresetButtons.bmp  pressed versions of both buttons side by side (blitted while a button is held)
#   preview.png        4x enlarged preview with "001" in the readout
from PIL import Image, ImageDraw
import sys, os

X0, Y0, W, H = 160, 1, 80, 21          # area replaced in bitmap 101 (title strip between logo and model name)
BTN = 15                                # button size
BL, BX, BR = 164, 182, 221              # left button x, readout box x, right button x (readout 37 x 15)
BY = 1
DIGX, DIGY = BX + 3, BY + 1             # first digit (10 x 13 each, from bitmap 105)

FONT = {  # 3 x 5 pixel caps
    'P' : ['111', '101', '111', '100', '100'],
    'R' : ['110', '101', '110', '101', '101'],
    'E' : ['111', '100', '110', '100', '111'],
    'S' : ['011', '100', '010', '001', '110'],
    'T' : ['111', '010', '010', '010', '010'],
}

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

def panel(base) :
    im = base.copy(); d = ImageDraw.Draw(im)
    button(im, BL, BY, True, False); button(im, BR, BY, False, False)
    d.rectangle((BX, BY, BX + 36, BY + 14), fill = (16, 14, 30), outline = (96, 98, 110))
    d.line((BX, BY + 14, BX + 36, BY + 14), fill = (250, 250, 252)); d.line((BX + 36, BY, BX + 36, BY + 14), fill = (250, 250, 252))
    text = 'PRESET'; tw = len(text) * 4 - 1; tx = BX + (37 - tw) // 2; ty = BY + 16
    for ch in text :
        for r, row in enumerate(FONT[ch]) :
            for c, bit in enumerate(row) :
                if bit == '1' : im.putpixel((tx + c, ty + r), (44, 48, 104))
        tx += 4
    return im

if __name__ == '__main__' :
    base = Image.open(sys.argv[1]).convert('RGB'); dig = Image.open(sys.argv[2]).convert('RGB'); out = sys.argv[3]
    im = panel(base)
    im.crop((X0, Y0, X0 + W, Y0 + H)).save(os.path.join(out, 'PresetPanel.bmp'))
    pr = Image.new('RGB', (2 * BTN, BTN))
    t = base.copy(); button(t, BL, BY, True, True); pr.paste(t.crop((BL, BY, BL + BTN, BY + BTN)), (0, 0))
    t = base.copy(); button(t, BR, BY, False, True); pr.paste(t.crop((BR, BY, BR + BTN, BY + BTN)), (BTN, 0))
    pr.save(os.path.join(out, 'PresetButtons.bmp'))
    pv = im.copy()
    for i, n in enumerate((0, 0, 1)) : pv.paste(dig.crop((n * 10, 0, n * 10 + 10, 13)), (DIGX + 10 * i, DIGY))
    pv.resize((pv.width * 2, pv.height * 2), Image.NEAREST).save(os.path.join(out, 'preview.png'))
    pv.crop((140, 0, 260, 30)).resize((480, 120), Image.NEAREST).save(os.path.join(out, 'preview_zoom.png'))
