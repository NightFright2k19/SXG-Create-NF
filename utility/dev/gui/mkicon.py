# Builds the patcher icon files in utility/icons (patcher.ico, patcher.icns, patcher.png, patcher_32.png, patcher_16.png).
# usage: python mkicon.py <path to the original "VST" icon PNG, 512 x 512, RGBA>
# 16 and 32 px are drawn by hand (small(), pixel by pixel, no folded corner, simplified label); every other size is
# scaled down from the full artwork.
# The original is "Vst icon" by SyafriStudio (Magnific, formerly Freepik; family "Generic color outline",
# resource 13122094). It is not stored in this repository; the generated files are derived from it
# (light rounded base, white paper, light blue label) and credited in README.md.
# Needs Pillow and SciPy (development only; the patcher itself needs neither).
import sys, io, struct
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

OUT = Path(__file__).resolve().parents[2] / 'icons'
BASE, BORDER = '#F0F3F8', '#B9C4D6'
PAPER, FOLD, LABEL = (255, 255, 255), (226, 232, 242), (214, 228, 250)

def build(src : Image.Image) -> Image.Image :
    src = src.convert('RGBA')
    px = np.array(src)
    lab, n = ndi.label(px[..., 3] < 40)                 # transparent regions (outside and enclosed)
    areas = []
    for i in range(1, n + 1) :
        ys, xs = np.where(lab == i)
        areas.append((i, len(ys), xs.min(), ys.min(), xs.max(), ys.max(), ys.mean()))
    outside = next(a[0] for a in areas if a[2] == 0 and a[3] == 0)
    fill = px.copy()
    for i, size, x0, y0, x1, y1, cy in areas :
        if i == outside or size < 30 : continue
        if y1 < 150 and size < 6000 : color = FOLD                          # folded corner
        elif 190 <= cy <= 450 and size < 70000 and not (y0 > 410 and size > 10000) : color = LABEL   # banner and its curls
        else : color = PAPER                                                # paper above / below the banner
        fill[lab == i] = [*color, 255]
    icon = Image.alpha_composite(Image.fromarray(fill), src)           # outline and lettering on top
    size = 512
    canvas = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle([4, 4, size - 5, size - 5], radius = int(size * 0.2), fill = BASE, outline = BORDER, width = 6)
    art = icon.resize((int(size * 0.80),) * 2, Image.LANCZOS)
    canvas.alpha_composite(art, ((size - art.width) // 2, (size - art.height) // 2))
    return canvas

NAVY, ORANGE = (15, 30, 74), (241, 146, 32)
def _hex(c) : c = c.lstrip('#'); return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))

LETTERS = {'V' : ['X..X', 'X..X', 'X..X', '.XX.', '.XX.'],
           'S' : ['.XXX', 'X...', '.XX.', '...X', 'XXX.'],
           'T' : ['XXXX', '.XX.', '.XX.', '.XX.', '.XX.']}

def small(size : int) -> Image.Image :
    """Hand-drawn 16 / 32 px version: light base, white paper with outline, light blue label with VST."""
    im = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    px = im.load()
    def rect(x0, y0, x1, y1, c) :
        for y in range(y0, y1 + 1) :
            for x in range(x0, x1 + 1) : px[x, y] = (*c, 255)
    def box(x0, y0, x1, y1, outline, fill) :
        rect(x0, y0, x1, y1, outline); rect(x0 + 1, y0 + 1, x1 - 1, y1 - 1, fill)
    # base: rounded square with 1 px border; the corner pixels are cut
    rect(0, 0, size - 1, size - 1, _hex(BORDER)); rect(1, 1, size - 2, size - 2, _hex(BASE))
    for (cx, cy, sx, sy) in ((0, 0, 1, 1), (size - 1, 0, -1, 1), (0, size - 1, 1, -1), (size - 1, size - 1, -1, -1)) :
        px[cx, cy] = (0, 0, 0, 0)
        if size == 32 :
            px[cx + sx, cy] = (0, 0, 0, 0); px[cx, cy + sy] = (0, 0, 0, 0)
            px[cx + sx, cy + sy] = (*_hex(BORDER), 255)
    if size == 32 :
        box(9, 4, 22, 27, NAVY, PAPER)                       # paper
        for y in range(4, 9) :                               # folded corner: cut the corner, then outline the flap
            for x in range(9, 14) :
                d = (x - 9) + (y - 4)
                if d < 4 : px[x, y] = (*_hex(BASE), 255)
                elif d == 4 : px[x, y] = (*NAVY, 255)
                elif x < 13 and y < 8 : px[x, y] = (*FOLD, 255)
        rect(13, 4, 13, 8, NAVY); rect(9, 8, 13, 8, NAVY)
        box(4, 12, 27, 21, NAVY, LABEL)                      # label band, wider than the paper
        x, y = 8, 14
        for ch in 'VST' :
            for j, row in enumerate(LETTERS[ch]) :
                for i, v in enumerate(row) :
                    if v == 'X' : px[x + i, y + j] = (*ORANGE, 255)
            x += 5
    else :
        box(4, 2, 11, 13, NAVY, PAPER)                       # paper, wider than at first so that it does not read as a cross
        px[4, 2] = (*_hex(BASE), 255); px[5, 3] = (*FOLD, 255)   # dog-ear
        box(2, 6, 13, 10, NAVY, LABEL)                       # label band
        for x in (4, 7, 10) : px[x, 8] = (*ORANGE, 255); px[x + 1, 8] = (*ORANGE, 255)
    return im

def png(im : Image.Image) -> bytes :
    b = io.BytesIO(); im.save(b, 'PNG', optimize = True); return b.getvalue()

def write_ico(path : Path, images : dict) -> None :
    """images: size -> RGBA image. All entries are PNG-compressed (Windows Vista and later)."""
    sizes = sorted(images); data = [png(images[n]) for n in sizes]
    head = struct.pack('<HHH', 0, 1, len(sizes)); offset = 6 + 16 * len(sizes); table = b''
    for n, d in zip(sizes, data) :
        table += struct.pack('<BBBBHHII', n % 256, n % 256, 0, 0, 1, 32, len(d), offset); offset += len(d)
    path.write_bytes(head + table + b''.join(data))

def write_icns(path : Path, chunks : list) -> None :
    """chunks: (type, image) in file order; PNG data inside, as macOS 10.7 and later reads it."""
    body = b''.join(t.encode('ascii') + struct.pack('>I', 8 + len(d)) + d for t, d in ((t, png(i)) for t, i in chunks))
    path.write_bytes(b'icns' + struct.pack('>I', 8 + len(body)) + body)

if __name__ == '__main__' :
    full = build(Image.open(sys.argv[1]))
    def scaled(n) : return full.resize((n, n), Image.LANCZOS)
    hand = {16 : small(16), 32 : small(32)}                                   # hand-drawn, not scaled
    pick = lambda n : hand[n] if n in hand else scaled(n)
    OUT.mkdir(exist_ok = True)
    write_ico(OUT / 'patcher.ico', {n : pick(n) for n in (16, 24, 32, 48, 64, 128, 256)})
    write_icns(OUT / 'patcher.icns', [('icp4', pick(16)), ('icp5', pick(32)), ('icp6', pick(64)), ('ic07', pick(128)),
                                      ('ic08', pick(256)), ('ic09', full), ('ic11', pick(32)), ('ic12', pick(64)),
                                      ('ic13', pick(256)), ('ic14', full)])
    scaled(256).save(OUT / 'patcher.png')                                     # window icons (Tk picks the best size)
    hand[32].save(OUT / 'patcher_32.png'); hand[16].save(OUT / 'patcher_16.png')
    print('written to', OUT)
