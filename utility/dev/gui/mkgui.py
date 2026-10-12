# mkgui.py syxg50.dll gui.asm settings.asm -> SYXG50_GUI list for dllpatch.py (pip: keystone-engine)
import keystone, sys
ks = keystone.Ks(keystone.KS_ARCH_X86, keystone.KS_MODE_32)
B = 0x10000000
CAVES = [(0x33150, 0x338C0), (0x2F6D3, 0x2FB60)]     # unused NOP blocks in .text: gui.asm, settings.asm
d = open(sys.argv[1], 'rb').read()
srcs = ['\n'.join(l.split(';')[0] for l in open(f).read().split('\n')) for f in sys.argv[2:4]]
codes = []
for src, (cave, limit) in zip(srcs, CAVES) :
    code = bytes(ks.asm(src, B + cave)[0])
    assert cave + len(code) <= limit and set(d[cave:cave + len(code)]) == {0x90}
    codes.append(code)
def label(name, i = 0) :
    # address of a label: appended as a data word behind the code
    tail = bytes(ks.asm(srcs[i] + f'\n.int {name}', B + CAVES[i][0])[0])[len(codes[i]):]
    return int.from_bytes(tail, 'little')
def site(off, target, n) :
    c = bytes(ks.asm(f'jmp {target:#x}', B + off)[0]); assert len(c) <= n
    return off, d[off:off + n], c + b'\x90' * (n - len(c))
sites = [site(0x010C0, label('proc_hook'), 7), site(0x010A0, label('procacc_hook'), 7), site(0x30AF0, label('dlg_hook', 1), 7),
         site(0x3246B, label('lbd_hook'), 10), site(0x32427, label('lbu_hook'), 10), site(0x3233D, label('paint_hook'), 5),
         site(0x320EE, label('idle_hook'), 7), site(0x32407, label('def_hook'), 8), site(0x31142, label('lvl_clamp', 1), 10)]
print('SYXG50_GUI = [')
for off, old, new in sites : print(f"    (0x{off:05X}, '{old.hex(' ')}', '{new.hex(' ')}'),")
for code, (cave, _) in zip(codes, CAVES) :
    print(f"    (0x{cave:05X}, ' '.join(['90'] * {len(code)}),\n              '{code.hex(' ')}'),")
print(']'); print(f'GUI_CAVE_END = 0x{CAVES[0][0] + len(codes[0]):05X}')
