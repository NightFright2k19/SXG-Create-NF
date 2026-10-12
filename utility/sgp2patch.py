# S-YXG2006LE: the original Yamaha engine (SGP2.OLD, or SGP2.DLL with the host lock already removed) is patched
# instead of converting its tables to the S-YXG50 engine. The DLL loads sxgbnw6l.tbl / sxgdat6l.tbl from its own folder.
# Patches:
#  - host lock off: the plugin only starts in a host whose vendor string is "YAMAHA" (0x2AAE je -> jmp)
#  - two VST parameters in a new section .sxg (source: utility/dev/sgp2/params.asm, built with mksgp2.py):
#    Reset Mode (None / GM / GS / XGLite / GM2, default XGLite) sent at start and on change, and SysEx (On / Off,
#    Off drops SysEx from the MIDI stream). Both are saved in the plugin chunk (the plugin saves nothing itself).
import shutil, struct
from pathlib import Path

B = 0x10000000
SECTION_VA = 0xE6000
CRC_OLD = 'A62F256A'        # SGP2.OLD (original)
CRC_UNLOCKED = '68FD2825'   # SGP2.DLL: SGP2.OLD with the host lock removed (0x2AAE 74 -> EB)
CRC_BANK = '692C7D6A'       # sxgbnw6l.tbl
CRC_WAVES = '3CB08464'      # sxgdat6l.tbl
DLL_NAME = 'syxg2006le.dll'
HOOK = 0x2CF4               # main(): lea eax, [esi + 0x20] / mov ecx, [esp + 4] -> jmp .sxg

from sgp2code import SECTION_CODE

def Find(crcs_paths : dict[str, Path]) -> tuple[Path, Path, Path] | None :
    dll = crcs_paths.get(CRC_OLD) or crcs_paths.get(CRC_UNLOCKED)
    if dll and CRC_BANK in crcs_paths and CRC_WAVES in crcs_paths :
        return dll, crcs_paths[CRC_BANK], crcs_paths[CRC_WAVES]
    return None

def Patch(data : bytes) -> bytes :
    d = bytearray(data)
    if d[0x2AAE] == 0x74 : d[0x2AAE] = 0xEB
    assert d[0x2AAE] == 0xEB and d[HOOK : HOOK + 7] == bytes.fromhex('8d46208b4c2404')
    pe = struct.unpack_from('<I', d, 0x3C)[0]; nsec = struct.unpack_from('<H', d, pe + 6)[0]
    opt = pe + 24; sh = opt + struct.unpack_from('<H', d, pe + 20)[0]
    last = sh + 40 * (nsec - 1)
    assert (struct.unpack_from('<I', d, last + 12)[0] + struct.unpack_from('<I', d, last + 8)[0] + 0xFFF) & ~0xFFF == SECTION_VA
    raw = (len(d) + 0x1FF) & ~0x1FF; size = (len(SECTION_CODE) + 0x1FF) & ~0x1FF
    d += b'\0' * (raw - len(d)) + SECTION_CODE + b'\0' * (size - len(SECTION_CODE))
    d[last + 40 : last + 80] = struct.pack('<8sIIIIIIHHI', b'.sxg', len(SECTION_CODE), SECTION_VA, size, raw, 0, 0, 0, 0, 0xE0000020)
    struct.pack_into('<H', d, pe + 6, nsec + 1)
    struct.pack_into('<I', d, opt + 56, SECTION_VA + ((len(SECTION_CODE) + 0xFFF) & ~0xFFF))     # SizeOfImage
    d[HOOK : HOOK + 7] = b'\xE9' + struct.pack('<i', SECTION_VA - (HOOK + 5)) + b'\x90\x90'
    struct.pack_into('<I', d, opt + 64, Checksum(d, opt + 64))
    return bytes(d)

def Checksum(d : bytes, at : int) -> int :
    s = 0
    for i in range(0, len(d) - len(d) % 2, 2) :
        if i in (at, at + 2) : continue
        s += d[i] | d[i + 1] << 8; s = (s & 0xFFFF) + (s >> 16)
    if len(d) % 2 : s += d[-1]; s = (s & 0xFFFF) + (s >> 16)
    return ((s + (s >> 16)) & 0xFFFF) + len(d)

def Build(found : tuple[Path, Path, Path], out_dir : Path) -> None :
    dll, bank, waves = found
    out_dir.mkdir(exist_ok=True)
    (out_dir / DLL_NAME).write_bytes(Patch(dll.read_bytes()))
    for f in (bank, waves) :
        shutil.copyfile(f, out_dir / f.name.lower())
    print(f'S-YXG2006LE: {out_dir / DLL_NAME} written (original engine, host lock off, parameters Reset Mode / SysEx), '
          f'{bank.name} / {waves.name} copied')
