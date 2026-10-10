# mkreset.py syxg50.dll reset.asm -> SYXG50_RESET list for dllpatch.py (pip: keystone-engine)
import keystone, sys
ks = keystone.Ks(keystone.KS_ARCH_X86, keystone.KS_MODE_32)
B = 0x10000000; CAVE = 0x3FA80
d = open(sys.argv[1], 'rb').read()
src = '\n'.join(l.split(';')[0] for l in open(sys.argv[2]).read().split('\n'))
code = bytes(ks.asm(src, B + CAVE)[0])
def label(name) :
    # address of a label: appended as a data word behind the code
    tail = bytes(ks.asm(src + f'\n.int {name}', B + CAVE)[0])[len(code):]
    return int.from_bytes(tail, 'little')
def site(off, target, n) :
    c = bytes(ks.asm(f'jmp {target:#x}', B + off)[0]); assert len(c) <= n
    return off, d[off:off + n], c + b'\x90' * (n - len(c))
sites = [site(0x010C0, label('proc_hook'), 7), site(0x010A0, label('procacc_hook'), 7), site(0x30AF0, label('dlg_hook'), 7)]
print('SYXG50_RESET = [')
for off, old, new in sites : print(f"    (0x{off:05X}, '{old.hex(' ')}', '{new.hex(' ')}'),")
print(f"    (0x{CAVE:05X}, ' '.join(['00'] * {len(code)}),\n              '{code.hex(' ')}'),")
print(']'); print(f'RESET_CAVE_END = 0x{CAVE + len(code):05X}')
