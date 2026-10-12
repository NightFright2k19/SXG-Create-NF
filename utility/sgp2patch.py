# S-YXG2006LE: the original Yamaha engine (SGP2.OLD, or SGP2.DLL with the host lock already removed) is patched
# instead of converting its tables to the S-YXG50 engine. The DLL loads sxgbnw6l.tbl / sxgdat6l.tbl from its own folder.
# Patches:
#  - host lock off: the plugin only starts in a host whose vendor string is "YAMAHA" (0x2AAE je -> jmp)
#  - two VST parameters in a new section .sxg (source: utility/dev/sgp2/params.asm, built with mksgp2.py):
#    Reset Mode (None / GM / GS / XGLite / GM2, default XGLite) sent at start and on change, and SysEx (On / Off,
#    Off drops SysEx from the MIDI stream). Both are saved in the plugin chunk (the plugin saves nothing itself).
import shutil, struct
import dllpatch
from pathlib import Path

B = 0x10000000
SECTION_VA = 0xE6000
CRC_OLD = 'A62F256A'        # SGP2.OLD (original)
CRC_UNLOCKED = '68FD2825'   # SGP2.DLL: SGP2.OLD with the host lock removed (0x2AAE 74 -> EB)
CRC_BANK = '692C7D6A'       # sxgbnw6l.tbl
CRC_WAVES = '3CB08464'      # sxgdat6l.tbl
DLL_NAME = 'syxg2006le.dll'
HOOK = 0x2CF4               # main(): lea eax, [esi + 0x20] / mov ecx, [esp + 4] -> jmp .sxg
LOADERS = (0x4C780, 0x4C7D0)  # table loaders (file size, read file): mov eax, [esp + 4] / push ebx / push esi

from sgp2code import SECTION_CODE, SECTION_RELOCS, MAIN_HOOK, FS_HOOK, FR_HOOK

def Find(crcs_paths : dict[str, Path]) -> tuple[Path, Path, Path] | None :
    dll = crcs_paths.get(CRC_OLD) or crcs_paths.get(CRC_UNLOCKED)
    if dll and CRC_BANK in crcs_paths and CRC_WAVES in crcs_paths :
        return dll, crcs_paths[CRC_BANK], crcs_paths[CRC_WAVES]
    return None

def jmp(d : bytearray, at : int, to : int, n : int) -> None :
    d[at : at + n] = b'\xE9' + struct.pack('<i', to - (at + 5)) + b'\x90' * (n - 5)

def add_section(d : bytearray, name : bytes, body : bytes, flags : int) -> int :
    # appended behind the last section -> its virtual address
    pe = struct.unpack_from('<I', d, 0x3C)[0]; nsec = struct.unpack_from('<H', d, pe + 6)[0]
    opt = pe + 24; sh = opt + struct.unpack_from('<H', d, pe + 20)[0]; last = sh + 40 * (nsec - 1)
    va = (struct.unpack_from('<I', d, last + 12)[0] + struct.unpack_from('<I', d, last + 8)[0] + 0xFFF) & ~0xFFF
    raw = (len(d) + 0x1FF) & ~0x1FF; size = (len(body) + 0x1FF) & ~0x1FF
    assert sh + 40 * (nsec + 1) <= struct.unpack_from('<I', d, opt + 60)[0]          # room for the header
    d += b'\0' * (raw - len(d)) + body + b'\0' * (size - len(body))
    d[last + 40 : last + 80] = struct.pack('<8sIIIIIIHHI', name, len(body), va, size, raw, 0, 0, 0, 0, flags)
    struct.pack_into('<H', d, pe + 6, nsec + 1)
    struct.pack_into('<I', d, opt + 56, va + ((len(body) + 0xFFF) & ~0xFFF))          # SizeOfImage
    return va

def add_relocs(d : bytearray, rvas : list[int]) -> None :
    # base relocation blocks (HIGHLOW) for the new code, in the slack of .reloc (last section before .sxg)
    pe = struct.unpack_from('<I', d, 0x3C)[0]; opt = pe + 24; ddir = opt + 96
    rva, size = struct.unpack_from('<II', d, ddir + 5 * 8)
    blocks = b''
    for page in sorted({r & ~0xFFF for r in rvas}) :
        e = [0x3000 | (r & 0xFFF) for r in rvas if r & ~0xFFF == page]
        if len(e) % 2 : e.append(0)
        blocks += struct.pack('<II', page, 8 + 2 * len(e)) + struct.pack(f'<{len(e)}H', *e)
    secs = [struct.unpack_from('<8sIIII', d, opt + struct.unpack_from('<H', d, pe + 20)[0] + 40 * i)
            for i in range(struct.unpack_from('<H', d, pe + 6)[0])]
    name, vs, va, rs, rp = next(x for x in secs if x[2] <= rva < x[2] + x[3])
    assert size + len(blocks) <= rs, 'no room in .reloc'
    d[rp + size : rp + size + len(blocks)] = blocks
    struct.pack_into('<I', d, ddir + 5 * 8 + 4, size + len(blocks))
    i = [x[2] for x in secs].index(va)
    sh = opt + struct.unpack_from('<H', d, pe + 20)[0] + 40 * i
    struct.pack_into('<I', d, sh + 8, max(vs, size + len(blocks)))

def Patch(data : bytes, embed : list[tuple[str, bytes]] = ()) -> bytes :
    d = bytearray(data)
    if d[0x2AAE] == 0x74 : d[0x2AAE] = 0xEB
    assert d[0x2AAE] == 0xEB and d[HOOK : HOOK + 7] == bytes.fromhex('8d46208b4c2404')
    for a in LOADERS : assert d[a : a + 6] == bytes.fromhex('8b4424045356')
    add_relocs(d, SECTION_RELOCS)
    assert add_section(d, b'.sxg', SECTION_CODE, 0xE0000020) == SECTION_VA
    jmp(d, HOOK, MAIN_HOOK, 7)
    jmp(d, LOADERS[0], FS_HOOK, 6); jmp(d, LOADERS[1], FR_HOOK, 6)
    if embed :
        # the tables as RT_RCDATA in a new resource section (the old .rsrc is not the last section)
        res = dllpatch.read_resources(d) + [(dllpatch.RT_RCDATA, n.upper(), 0, 0, b) for n, b in embed]
        pe = struct.unpack_from('<I', d, 0x3C)[0]; opt = pe + 24
        tmp = bytearray(d); va = add_section(tmp, b'.rsrc2', b'', 0x40000040)
        rsrc = dllpatch.build_resources(res, va)
        assert add_section(d, b'.rsrc2', rsrc, 0x40000040) == va
        struct.pack_into('<II', d, opt + 96 + 2 * 8, va, len(rsrc))
    pe = struct.unpack_from('<I', d, 0x3C)[0]; opt = pe + 24
    struct.pack_into('<I', d, opt + 64, Checksum(d, opt + 64))
    return bytes(d)

def Checksum(d : bytes, at : int) -> int :
    s = 0
    for i in range(0, len(d) - len(d) % 2, 2) :
        if i in (at, at + 2) : continue
        s += d[i] | d[i + 1] << 8; s = (s & 0xFFFF) + (s >> 16)
    if len(d) % 2 : s += d[-1]; s = (s & 0xFFFF) + (s >> 16)
    return ((s + (s >> 16)) & 0xFFFF) + len(d)

def Build(found : tuple[Path, Path, Path], out_dir : Path, embed : bool = False) -> None :
    dll, bank, waves = found
    out_dir.mkdir(exist_ok=True)
    files = [('sxgbnw6l.tbl', bank.read_bytes()), ('sxgdat6l.tbl', waves.read_bytes())] if embed else []
    (out_dir / DLL_NAME).write_bytes(Patch(dll.read_bytes(), files))
    if not embed :
        for f in (bank, waves) :
            shutil.copyfile(f, out_dir / f.name.lower())
    print(f'S-YXG2006LE: {out_dir / DLL_NAME} written (original engine, host lock off, parameters Reset Mode / SysEx), '
          + ('tables embedded' if embed else f'{bank.name} / {waves.name} copied'))
