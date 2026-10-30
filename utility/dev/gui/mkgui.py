# mkgui.py syxg50.dll gui.asm settings.asm ../poly/poly.asm -> SYXG50_GUI list and SYXG50_POLY for dllpatch.py
# (pip: keystone-engine). poly.asm goes into the section .sxp at 0x1005B000 (inserted in front of .rsrc);
# gui.asm calls into it (BOTH_SYSEX / BOTH_SHORT), poly.asm calls send_pending of gui.asm (SEND_PENDING).
import keystone, sys
from pathlib import Path
ks = keystone.Ks(keystone.KS_ARCH_X86, keystone.KS_MODE_32)
B = 0x10000000; POLY_VA = 0x5B000
CAVES = [(0x33150, 0x338C0), (0x2F6D3, 0x2FB60)]     # unused NOP blocks in .text: gui.asm, settings.asm
d = open(sys.argv[1], 'rb').read()
strip = lambda f : '\n'.join(l.split(';')[0] for l in open(f).read().split('\n'))
gui_src, set_src, poly_src = (strip(f) for f in sys.argv[2:5])
poly_src += '\n' + strip(str(Path(sys.argv[4]).with_name('panel.asm'))) + '\n' + strip(str(Path(sys.argv[4]).with_name('ini.asm')))
def asm(src, at) : return bytes(ks.asm(src, at)[0])
def lab(src, at, name) :
    c = asm(src, at); return int.from_bytes(asm(src + f'\n.int {name}', at)[len(c):], 'little')
# pass 1: placeholders (call rel32 has a fixed size, so the addresses do not move)
g0 = gui_src.replace('BOTH_SYSEX', hex(B + POLY_VA)).replace('BOTH_SHORT', hex(B + POLY_VA)).replace('PANEL_PROG', hex(B + POLY_VA))
sp = lab(g0, B + CAVES[0][0], 'send_pending')
poly = poly_src.replace('SEND_PENDING', hex(sp))
P = {n : lab(poly, B + POLY_VA, n) for n in ('poly_procR', 'poly_procA', 'both_sysex', 'both_short', 'poly_disp', 'poly_count', 'panel_prog',
                                           'lbd_hook', 'lbu_hook', 'paint_hook', 'idle_hook', 'def_hook', 'get_hook', 'ini_int', 'ini_str')}
gui = gui_src.replace('BOTH_SYSEX', hex(P['both_sysex'])).replace('BOTH_SHORT', hex(P['both_short'])).replace('PANEL_PROG', hex(P['panel_prog']))
assert lab(gui, B + CAVES[0][0], 'send_pending') == sp
srcs = [gui, set_src]
codes = []
for src, (cave, limit) in zip(srcs, CAVES) :
    code = asm(src, B + cave)
    assert cave + len(code) <= limit and set(d[cave:cave + len(code)]) == {0x90}
    codes.append(code)
label = lambda name, i = 0 : lab(srcs[i], B + CAVES[i][0], name)
def site(off, target, n) :
    c = asm(f'jmp {target:#x}', B + off); assert len(c) <= n
    return off, d[off:off + n], c + b'\x90' * (n - len(c))
sites = [site(0x30AF0, label('dlg_hook', 1), 7),
         site(0x3246B, P['lbd_hook'], 10), site(0x32427, P['lbu_hook'], 10), site(0x3233D, P['paint_hook'], 5),
         site(0x320EE, P['idle_hook'], 7), site(0x32407, P['def_hook'], 8), site(0x31142, label('lvl_clamp', 1), 10),
         site(0x30F31, label('poly_scroll', 1), 21)]
print('SYXG50_GUI = [')
for off, old, new in sites : print(f"    (0x{off:05X}, '{old.hex(' ')}', '{new.hex(' ')}'),")
for code, (cave, _) in zip(codes, CAVES) :
    print(f"    (0x{cave:05X}, ' '.join(['90'] * {len(code)}),\n              '{code.hex(' ')}'),")
print(']'); print(f'GUI_CHUNK_GET = 0x{label("chunk_get", 1):08X}'); print(f'GUI_CHUNK_SET = 0x{label("chunk_set", 1):08X}'); print(f'GUI_CAVE_END = 0x{CAVES[0][0] + len(codes[0]):05X}')
pc = asm(poly, B + POLY_VA)
psites = [site(0x010C0, P['poly_procR'], 7), site(0x010A0, P['poly_procA'], 7), site(0x01000, P['poly_disp'], 8),
          site(0x330FC, P['ini_int'], 5), site(0x3311C, P['ini_str'], 5)]
# panel readouts: the three Get calls of the idle redraw (op 2 part levels, 3 output levels, 4 voices in use) go through get_hook, which asks
# the engine of the port the panel shows (op 4 of port A: poly_count adds the voices of engine B)
c = asm(f'lea edx, [esp + 0x3c]\npush edx\npush 4\npush dword ptr [ebp + 8]\ncall {P["get_hook"]:#x}', B + 0x320A0)
assert len(c) <= 16
psites.append((0x320A0, d[0x320A0:0x320B0], c + b'\x90' * (16 - len(c))))
c = asm(f'lea edx, [esp + 0x28]\npush edx\npush 2\npush dword ptr [ebp + 8]\ncall {P["get_hook"]:#x}', B + 0x31F09)
assert len(c) <= 16
psites.append((0x31F09, d[0x31F09:0x31F19], c + b'\x90' * (16 - len(c))))
c = asm(f'push 3\npush dword ptr [ebp + 8]\ncall {P["get_hook"]:#x}', B + 0x31F86)
assert len(c) <= 11
psites.append((0x31F86, d[0x31F86:0x31F91], c + b'\x90' * (11 - len(c))))
c = asm(f'push 1\npush dword ptr [ebp + 8]\ncall {P["get_hook"]:#x}', B + 0x31E97)
assert len(c) <= 11
psites.append((0x31E97, d[0x31E97:0x31EA2], c + b'\x90' * (11 - len(c))))
print('SYXG50_POLY = [')
for off, old, new in psites : print(f"    (0x{off:05X}, '{old.hex(' ')}', '{new.hex(' ')}'),")
print(']'); print(f"POLY_VA = 0x{POLY_VA:05X}")
print(f"INI_ID_OFFSET = 0x{lab(poly, B + POLY_VA, 'ini_id') - B - POLY_VA:X}   # 16 bytes in POLY_CODE: the plugin's ini section, set per model"); print(f"POLY_CODE = bytes.fromhex('{pc.hex()}')")
