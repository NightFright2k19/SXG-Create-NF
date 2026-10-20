# S-YXG2006LE: the original Yamaha engine (SGP2.OLD, or SGP2.DLL with the host lock already removed) is patched
# instead of converting its tables to the S-YXG50 engine. The DLL loads sxgbnw6l.tbl / sxgdat6l.tbl from its own folder.
# Patches:
#  - host lock off: the plugin only starts in a host whose vendor string is "YAMAHA" (0x2AAE je -> jmp)
#  - SGP2VSTi 1.0.2.22 copies (issue #54) also changed the debugger check at 0x4BFFB; that change is undone, so
#    every accepted DLL gives the same plugin
#  - VST parameters in a new section .sxg (source: utility/dev/sgp2/params.asm, built with mksgp2.py), in the order
#    of the S-YXG50 plugins: Polyphony 8-256 (default 256, up to 8 engines of 32 voices), Reverb (CC 91) / Chorus
#    (CC 93) On / Off, Master Volume -12 ... +12 dB, Master Tune, Transpose, Reset Mode GM / GS / XGLite (default
#    XGLite, sent once; resets from the host follow it like in the MU plugins); Voices (display) under Polyphony. Saved in the plugin chunk
#    'SXR4' (the plugin saves nothing itself; older 'SXR3' / 'SXR2' chunks are converted).
import shutil, struct
import dllpatch
from pathlib import Path

B = 0x10000000
SECTION_VA = 0xE6000
CRC_OLD = 'A62F256A'        # SGP2.OLD (original)
CRC_UNLOCKED = '68FD2825'   # SGP2.DLL: SGP2.OLD with the host lock removed (0x2AAE 74 -> EB)
CRC_SGP2VSTI = 'F5037F5F'   # SGP2.DLL made by SGP2VSTi 1.0.2.22: host lock removed, 0x4BFFB 74 14 8B -> 90 90 FF
DLL_CRCS = (CRC_OLD, CRC_UNLOCKED, CRC_SGP2VSTI)
DEBUG_CHECK = 0x4BFFB       # detect_debugger: je 0x1004C011 / mov eax, [esi + 8] (SGP2VSTi: nop / nop / inc [esi + 8])
CRC_BANK = '692C7D6A'       # sxgbnw6l.tbl
CRC_WAVES = '3CB08464'      # sxgdat6l.tbl
DLL_NAME = 'syxg2006le.dll'
HOOK = 0x2CF4               # main(): lea eax, [esi + 0x20] / mov ecx, [esp + 4] -> jmp .sxg
LOADERS = (0x4C780, 0x4C7D0)  # table loaders (file size, read file): mov eax, [esp + 4] / push ebx / push esi

from sgp2code import SECTION_CODE, SECTION_RELOCS, MAIN_HOOK, FS_HOOK, FR_HOOK

def Find(crcs_paths : dict[str, Path]) -> tuple[Path, Path, Path] | None :
    dll = next((crcs_paths[c] for c in DLL_CRCS if c in crcs_paths), None)
    if dll and CRC_BANK in crcs_paths and CRC_WAVES in crcs_paths :
        return dll, crcs_paths[CRC_BANK], crcs_paths[CRC_WAVES]
    return None

def Parts(crcs_paths : dict[str, Path]) -> list[Path] :
    # any of the three S-YXG2006LE files (to keep them out of the MU conversion when the set is incomplete)
    return [crcs_paths[c] for c in DLL_CRCS + (CRC_BANK, CRC_WAVES) if c in crcs_paths]

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
    if d[DEBUG_CHECK : DEBUG_CHECK + 3] == bytes.fromhex('9090ff') : d[DEBUG_CHECK : DEBUG_CHECK + 3] = bytes.fromhex('74148b')
    assert d[DEBUG_CHECK : DEBUG_CHECK + 3] == bytes.fromhex('74148b')
    assert d[0x2AAE] == 0xEB and d[HOOK : HOOK + 7] == bytes.fromhex('8d46208b4c2404')
    for a in LOADERS : assert d[a : a + 6] == bytes.fromhex('8b4424045356')
    add_relocs(d, SECTION_RELOCS)
    assert add_section(d, b'.sxg', SECTION_CODE, 0xE0000020) == SECTION_VA
    jmp(d, HOOK, MAIN_HOOK, 7)
    jmp(d, LOADERS[0], FS_HOOK, 6); jmp(d, LOADERS[1], FR_HOOK, 6)
    # resources in a new section .rsrc2 (the old .rsrc is not the last section, so it can't grow): the version
    # info gets the build date and the credits like the MU plugins, --embed adds the tables as RT_RCDATA
    res = [(t, n, l, cp, Version_Date(b) if t == dllpatch.RT_VERSION else Panel_Dib(b) if (t, n) == (dllpatch.RT_BITMAP, PANEL_BITMAP) else b)
           for t, n, l, cp, b in dllpatch.read_resources(d)]
    lang = next(l for t, n, l, cp, b in res if (t, n) == (dllpatch.RT_BITMAP, PANEL_BITMAP))
    res += [(dllpatch.RT_BITMAP, i, lang, 0, dllpatch.bmp_to_dib24((dllpatch.BITMAP_DIR / f).read_bytes())[2]) for i, f in EDITOR_BITMAPS.items()]
    res += [(dllpatch.RT_RCDATA, n.upper(), 0, 0, b) for n, b in embed]
    pe = struct.unpack_from('<I', d, 0x3C)[0]; opt = pe + 24
    tmp = bytearray(d); va = add_section(tmp, b'.rsrc2', b'', 0x40000040)
    rsrc = dllpatch.build_resources(res, va)
    assert add_section(d, b'.rsrc2', rsrc, 0x40000040) == va
    struct.pack_into('<II', d, opt + 96 + 2 * 8, va, len(rsrc))
    pe = struct.unpack_from('<I', d, 0x3C)[0]; opt = pe + 24
    struct.pack_into('<I', d, opt + 64, Checksum(d, opt + 64))
    return bytes(d)

# Editor (issue #39): the panel (bitmap 111 of the DLL, 400 x 90) gets the control row CHN / PRG / MSB / LSB of the MU
# plugins' panel (bitmaps/Panel101.bmp, rows 24-47) under the title strip, like #42: 400 x 114. The Yamaha bitmap
# itself is not part of this repository; it is taken from the user's DLL.
PANEL_BITMAP = 111
# for the control row: pressed buttons and dash (130) and the white digits (131) of the MU plugins' panel
EDITOR_BITMAPS = {130 : 'PanelButtons.bmp', 131 : 'Bitmap105.bmp'}

def Panel_Dib(dib : bytes) -> bytes :
    w, h, _, rows = dllpatch.dib_rows(dib)
    assert (w, h) == (400, 90), f'bitmap {PANEL_BITMAP} is {w}x{h}, expected 400x90'
    pw, ph, panel = dllpatch.bmp_to_dib24((dllpatch.BITMAP_DIR / 'Panel101.bmp').read_bytes())
    assert (pw, ph) == (400, 114)
    prows = dllpatch.dib_rows(panel)[3]
    nw, nh, name = dllpatch.bmp_to_dib24((dllpatch.BITMAP_DIR / 'Name_XG2006LE.bmp').read_bytes())     # "S-YXG2006LE", flush right
    for r, line in enumerate(dllpatch.dib_rows(name)[3]) : rows[r][3 * (400 - nw) : 1200] = line
    return dllpatch.rows_to_dib(400, rows[:24] + prows[24:48] + rows[24:])

def Version_Date(old : bytes, today = None) -> bytes :
    # FileVersion / ProductVersion 1.0.2.22 -> YYYY.MM.DD (build date), fixed file version YYYY,MM,DD,0,
    # FileDescription / ProductName 'YAMAHA SoftSynthesizer S-YXG2006LE' -> 'Yamaha S-YXG2006LE',
    # CompanyName 'YAMAHA CORPORATION' -> 'Yamaha Corporation',
    # LegalCopyright + credits (as dllpatch.apply_version_date does for the MU plugins)
    import datetime
    d = today or datetime.date.today()
    date = f'{d.year:04}.{d.month:02}.{d.day:02}'
    def strings(key, t) :
        if key in ('FileVersion', 'ProductVersion') : return date
        if key in ('FileDescription', 'ProductName') : return 'Yamaha S-YXG2006LE'
        if key == 'CompanyName' : return 'Yamaha Corporation'
        if key == 'LegalCopyright' and dllpatch.CREDITS_SGP2 not in t : return t + ', ' + dllpatch.CREDITS_SGP2
        return t
    new = bytearray(dllpatch.edit_version(old, strings))
    fixed = (6 + len('VS_VERSION_INFO\0') * 2 + 3) & ~3
    assert struct.unpack_from('<I', new, fixed)[0] == 0xFEEF04BD
    struct.pack_into('<HHHH', new, fixed + 8, d.month, d.year, 0, d.day)       # file version
    struct.pack_into('<HHHH', new, fixed + 16, d.month, d.year, 0, d.day)      # product version
    return bytes(new)

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
    print(f'S-YXG2006LE: {out_dir / DLL_NAME} written (original engine, host lock off, VST parameters), '
          + ('tables embedded' if embed else f'{bank.name} / {waves.name} copied'))
