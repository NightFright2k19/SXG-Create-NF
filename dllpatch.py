# dllpatch.py - patches a user supplied syxg50.dll for the table being built
#
# The DLL is given on the command line together with the ROMs, under any file name (it is
# recognised by its content). SXG-Create writes next to the table and wave file:
#   <name>.dll  the patched DLL, same name as the supplied one (e.g. mu800.dll)
#   <name>.ini  its settings (the DLL reads the ini with its own name), e.g. mu800.ini
# If the supplied DLL is in the output folder itself, it is replaced and the original is kept as
# <name>.orig.dll (later runs patch from that copy). The ini selects the table with
# SoftSynth=<table>.TBL, the wave file name is stored in the table header.
#
# syxg50.dll (S-YXG50, 626,688 bytes, or 5,070,848 bytes with embedded tables). The patch level
# follows the table, no switch needed:
#   "Enhanced"  MU50 / MU80 / MU90 (classic table layout)
#     * ini section [Config] and key SoftSynth (originally [SYXG50] / VoiceTable)
#     * 24-bit loop length (loops > 65,535 samples: MU90 and some MU80 voices)
#   "Full"      MU100 / MU128 / MU1000 (big table layout)
#     * everything from "Enhanced"
#     * table size limits: 32-bit sample addresses (up to 64 MB of 8/16-bit samples), 512 multisamples,
#       32-bit voice and ext voice offsets. The sound engine (incl. MMX/SSE) is unchanged.

import zlib, struct
from pathlib import Path


class DllPatchError(Exception) :
    pass


# ----------------------------------------------------------------------------- patch data
# (file offset, original bytes, patched bytes)

SYXG50_24BIT = [
    # voice setup masks start offset and loop length with 0xFFFF (and edx, 0xFFFF) -> 0xFFFFFF
    (0x1A6F0, '00', 'ff'),
    (0x1A6FC, '00', 'ff'),
]

# "Full": big table layout (MU100 / MU128 / MU1000), see buildtarget.py
SYXG50_BIG = [
    # voice map 32-bit
    (0x045E0, '66 8b 04 46 66 3d 00 80 5e 5b 73 11 8b 0d dc 52 05 10 33 d2 66 8b d0 8d 04 51 c2 10 00 8b 0d 08 53 05 10 05 00 80 00 00 33 d2 66 8b d0 8d 04 51 c2 10',
              '8b 04 86 5e 5b 90 90 90 90 90 90 90 8b 0d dc 52 05 10 8d 04 01 c2 10 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90'),
    # wavedata offsets 32-bit, 512 multisamples (hook)
    (0x04DF4, '0f b6 08 8b 15 04 53 05 10 0f b7 04 4a 03 05 fc 52 05 10',
              'e9 67 a5 03 00 cc cc cc cc cc cc cc cc cc cc cc cc cc cc'),
    # wavedata offsets 32-bit, 512 multisamples (code cave)
    (0x3F360, '00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00',
              '0f b6 08 56 e8 00 00 00 00 5e 8b 96 93 5f 01 00 2b 96 9b 5f 01 00 81 fa 00 04 00 00 76 0e 3b 86 9f 5f 01 00 72 06 81 c1 00 01 00 00 8b 96 9b 5f 01 00 8b 04 8a 03 86 93 5f 01 00 5e e9 66 5a fc ff'),
    # drum: ext voice check +0x11
    (0x05BFE, '80 79 10 ff',
              '80 79 11 ff'),
    # drum: ext voice check +0x11
    (0x16E6F, '8a 50 10',
              '8a 50 11'),
    # drum: ext voice check +0x11
    (0x16EA5, '8a 50 10',
              '8a 50 11'),
    # drum: ext voice check +0x11
    (0x16EC4, '8a 50 10',
              '8a 50 11'),
    # drum: ext voice check +0x11
    (0x16EDB, '8a 50 10',
              '8a 50 11'),
    # ext voice index 16-bit, 32-bit offsets
    (0x0AFDA, '0f b6 42 11 8b 0d f0 52 05 10 0f b7 1c 41',
              '0f b7 42 10 8b 0d f0 52 05 10 8b 1c 81 90'),
    # wavedata format +0x0D
    (0x05C13, '8a 52 0c',
              '8a 52 0d'),
    # wavedata format +0x0D
    (0x05CB0, '8a 52 0c',
              '8a 52 0d'),
    # drum format in address MSB
    (0x05C44, '8a 51 1b',
              '8a 51 18'),
    # drum root key +0x0A
    (0x1379D, '66 0f b6 4a 12',
              '66 0f b6 4a 0a'),
    # drum setup +0x0A = 1
    (0x08325, '8a 50 0a 88 56 0a',
              'b2 01 90 88 56 0a'),
    # drum setup +0x0A = 1
    (0x08410, '8a 48 0a 88 4e 0a',
              'b1 01 90 88 4e 0a'),
    # drum sample fields
    (0x138F0, '8b 44 24 08 8b 40 30 0f b6 50 13 0f b6 48 14 c1 e2 08 03 d1 8b 4c 24 04 89 91 cc 01 00 00 0f b6 50 16 56 0f b6 70 17 c1 e2 08 03 d6 89 91 d4 01 00 00 0f b6 50 18 0f b6 70 19 c1 e2 08 03 d6 0f b6 70 1a c1 e2 08 03 d6 89 91 d0 01 00 00 8a 40 1b 88 81 cb 01 00 00 5e c2 08 00 90 90 90 90 90',
              '8b 44 24 08 8b 40 30 8b 4c 24 04 8b 50 12 0f ca c1 ea 08 89 91 cc 01 00 00 8b 50 15 0f ca c1 ea 08 89 91 d4 01 00 00 8b 50 18 0f ca 89 d0 81 e2 ff ff ff 03 89 91 d0 01 00 00 c1 e8 18 24 c0 88 81 cb 01 00 00 c2 08 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90'),
    # wavedata fields
    (0x15620, '8b 44 24 0c 8b 40 24 0f b6 48 06 0f b6 50 07 c1 e1 08 03 ca 0f b6 50 08 c1 e1 08 03 ca 8b 54 24 04 89 8a d4 01 00 00 8a 48 0c 88 8a cb 01 00 00 0f b6 48 09 c1 e1 08 56 0f b6 70 0a 03 ce 0f b6 70 0b c1 e1 08 03 ce 89 8a d0 01 00 00',
              '8b 44 24 0c 8b 40 24 8b 54 24 04 8b 48 05 0f c9 81 e1 ff ff ff 00 89 8a d4 01 00 00 8a 48 0d 88 8a cb 01 00 00 8b 48 09 0f c9 89 8a d0 01 00 00 56 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90'),
]
BIG_CAVE_END = 0x3F360 + 0x41   # code cave at the end of .text, the section's VirtualSize is enlarged to cover it

KNOWN = {
    # CRC32 of the original file -> (kind, description)
    '38A60E61' : ('syxg50', 'syxg50.dll, external tables (626,688 bytes)'),
    '80EFA471' : ('syxg50', 'syxg50.dll, embedded tables (5,070,848 bytes)'),
}

# ini section and key: [SYXG50] VoiceTable -> [Config] SoftSynth
SYXG50_INI = [
    (0x519EC, '53 59 58 47 35 30 00',             '43 6f 6e 66 69 67 00'),           # "SYXG50" -> "Config"
    (0x519F4, '56 6f 69 63 65 54 61 62 6c 65 00', '53 6f 66 74 53 79 6e 74 68 00 00'), # "VoiceTable" -> "SoftSynth"
]

SIZES = {626688 : 'syxg50', 5070848 : 'syxg50'}

INI_TEMPLATE = (
    '[Config]\r\n'
    'SoftSynth={table}\r\n'
    'Process=1\r\n'
    'XGLite=0\r\n'
    'DebugPanel=0\r\n'
    'DisableGUI=0\r\n'
)


# ----------------------------------------------------------------------------- helpers

def crc(data : bytes) -> str :
    return f'{zlib.crc32(data) & 0xFFFFFFFF:08X}'

def pe_checksum_offset(data : bytes) -> int :
    pe = struct.unpack_from('<I', data, 0x3C)[0]
    assert data[pe:pe+4] == b'PE\0\0', 'not a PE file'
    return pe + 24 + 64      # optional header + 64 = CheckSum

def pe_checksum(data : bytes) -> int :
    # the standard PE checksum (same as Windows' CheckSumMappedFile)
    off = pe_checksum_offset(data)
    buf = bytearray(data)
    buf[off:off+4] = b'\0\0\0\0'
    if len(buf) % 2 : buf += b'\0'
    s = 0
    for (w,) in struct.iter_unpack('<H', buf) :
        s += w
        s = (s & 0xFFFF) + (s >> 16)
    s = (s & 0xFFFF) + (s >> 16)
    return (s + len(data)) & 0xFFFFFFFF

def text_virtual_size(data : bytearray, minimum : int) :
    # the code cave lies behind the .text VirtualSize: Windows would zero it when loading
    pe = struct.unpack_from('<I', data, 0x3C)[0]
    sec = pe + 24 + struct.unpack_from('<H', data, pe + 20)[0]
    assert data[sec:sec+5] == b'.text'
    vsize, va, raw = struct.unpack_from('<III', data, sec + 8)
    need = minimum - va          # minimum is an RVA (= file offset in .text)
    if vsize < need :
        assert need <= raw
        struct.pack_into('<I', data, sec + 8, raw)

def apply(data : bytearray, patches, label : str) :
    # all-or-nothing: every patch must find its original bytes (or be applied already)
    todo = []
    for off, old, new in patches :
        old = bytes.fromhex(old); new = bytes.fromhex(new)
        cur = bytes(data[off:off+len(old)])
        if cur == new :
            continue
        if cur != old :
            raise DllPatchError(f'{label}: unexpected bytes at 0x{off:X} ({cur.hex(" ")}), is this the right DLL version?')
        todo.append((off, new))
    for off, new in todo :
        data[off:off+len(new)] = new
    state = 'applied' if todo else 'already applied'
    print(f'  {label}: {state}')


# ----------------------------------------------------------------------------- API

def Is_Dll(path : Path) -> bool :
    # a PE file (MZ header) among the input files
    with open(path, 'rb') as f :
        head = f.read(2)
    return head == b'MZ'

def Identify(path : Path) -> str :
    # -> description; raises DllPatchError if the file is not a syxg50.dll
    data = path.read_bytes()
    c = crc(data)
    if c in KNOWN :
        return KNOWN[c][1]
    if len(data) not in SIZES :
        raise DllPatchError(f'{path.name}: not a supported syxg50.dll (CRC32 {c}, {len(data):,} bytes), '
                            'expected syxg50.dll with 626,688 or 5,070,848 bytes')
    # a file that already carries (some of) the patches: checked patch by patch
    return f'{path.name}, not an original syxg50.dll (CRC32 {c}), checking patch by patch'

def Patch(path : Path, full : bool) -> bytes :
    # full = False: "Enhanced" (classic table layout), True: "Full" (big table layout)
    data = bytearray(path.read_bytes())
    Identify(path)
    print(f'patching {path.name}: ' + ('"Full" (loop length + table size limits)' if full else '"Enhanced" (loop length)'))
    apply(data, SYXG50_INI, 'ini [Config] / SoftSynth')
    apply(data, SYXG50_24BIT, '24-bit loop length')
    if full :
        if len(data) == 5070848 :
            print('  note: 5 MB syxg50.dll, its embedded (classic) tables are not used, the ini selects the table')
        apply(data, SYXG50_BIG, 'table size limits (big layout)')
        text_virtual_size(data, BIG_CAVE_END)
    struct.pack_into('<I', data, pe_checksum_offset(data), pe_checksum(data))
    return bytes(data)

def Write(dll_path : Path, out_dir : str, table_name : str, full : bool) :
    # the patched DLL keeps the name of the supplied DLL (any name, e.g. mu800.dll), the ini gets the
    # same name with .ini (the DLL looks for <its own name>.ini). The ini selects the table.
    import os, shutil
    name = dll_path.name if dll_path.suffix else dll_path.name + '.dll'
    stem = Path(name).stem
    out = Path(out_dir) / name
    src = dll_path
    if out.exists() and os.path.samefile(out, dll_path) :
        # the supplied DLL sits in the output folder: keep the original as <name>.orig.dll and
        # always patch from that copy (so a rerun with another layout starts from the original again)
        backup = out.with_name(f'{stem}.orig{out.suffix}')
        if not backup.exists() :
            shutil.copy2(dll_path, backup)
            print(f'dllpatch: original saved as {backup}')
        src = backup
    data = Patch(src, full)
    ini = out.with_name(f'{stem}.ini')
    for path, content in ((out, data), (ini, INI_TEMPLATE.format(table=table_name).encode('ascii'))) :
        state = 'replaced' if path.exists() else 'wrote'
        path.write_bytes(content)
        print(f'dllpatch: {state} {path}' + (f', CRC32 {crc(content)}' if path == out else ''))
