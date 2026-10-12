# mksgp2.py params.asm -> SECTION_CODE for utility/sgp2patch.py (pip: keystone-engine)
# The code is assembled for the new section .sxg at SECTION_VA (first free page after .reloc of SGP2.OLD)
import keystone, sys, textwrap
sys.path.insert(0, __file__.rsplit('/', 4)[0] + '/utility')
from sgp2patch import B, SECTION_VA
src = '\n'.join(l.split(';')[0] for l in open(sys.argv[1]).read().split('\n'))
code = bytes(keystone.Ks(keystone.KS_ARCH_X86, keystone.KS_MODE_32).asm(src, B + SECTION_VA)[0])
print('SECTION_CODE = bytes.fromhex(')
for l in textwrap.wrap(code.hex(), 112) : print(f"    '{l}'")
print(')')
