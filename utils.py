from zlib import crc32
from pathlib import Path
from typing import Literal
from pathlib import Path

# Read bytes

def calccrc32(fileName : Path) -> str:
    with open(fileName, 'rb') as fh:
        hash = 0
        while True:
            s = fh.read(65536)
            if not s:
                break
            hash = crc32(s, hash)
        return "%08X" % (hash & 0xFFFFFFFF)

def Dejumble(bytes : bytes | bytearray) :
    b = bytearray(len(bytes))
    for i in range(0, len(b)-1, 2) : 
        b[i], b[i+1] = bytes[i+1], bytes[i]
    return b

def assemble_waverom(list : list[Path]) -> bytes : 
    out : bytearray = bytearray()
    for path in list : 
        out = out + open(path, mode='rb').read()
    return bytes(out)


# Write bytes

def FileExists(filename : str, root_dir) : 
    outfile = Path(root_dir) / filename
    if outfile.exists() : 
        return True
    return False

def WriteBytesToFile(b : bytes | bytearray, filename : str, root_dir) : 

    outfile = Path(root_dir) / filename
    if outfile.exists() : 
        print(f'WriteBytesToFile: file {outfile} already exists! Skipping...')
        return
    
    with open(outfile, 'wb') as writer : 
        writer.write(b)

    print(f'WriteBytesToFile: wrote {len(b):,} bytes to {outfile}')


def WriteTXT(s : str, filename : str, root_dir) : 

    outfile = Path(root_dir) / filename
    if outfile.exists() : 
        print(f'WriteTXT: file {outfile} already exists! Skipping...')
        return
    
    with open(outfile, 'w') as writer : 
        writer.write(s)

    print(f'WriteTXT: wrote {len(s):,} bytes to {outfile}')


# UX

def Friendly_error(s : str | None) : 
    print(s)
    input('press any key to exit')
    exit(1)




# investigation helpers
# not used in table creation

def fmtbyte(b) -> str : return '{:02X}'.format(b)
def fmtbytes(ba) -> str : 
    s : str = ''
    for b in ba : 
        s = s + '{:02X}'.format(b) + ' '
    return s

def ExtractColumn(b : bytes | bytearray, entry_len : int, offset : int) -> bytes :
    return bytes([b[i+offset] for i in range(0, len(b), entry_len)])

# helper for decoding offset tables
# ... drumkit keymaps, program maps, drumvocie ext.voice offset table, wavedata offsets 
def decode_16bittable(b : bytes | bytearray, mult : int = 1, endian : Literal['big','little'] = 'big') -> list[int] : 
    return [(int.from_bytes(b[idx : idx + 2], byteorder=endian) * mult) for idx in range(0, len(b), 2)]



