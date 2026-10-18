# template.py - pre-patched plugin templates (issue #40)
#
# A template is the finished plugin of one model without ROM data: syxg50.dll with every patch of dllpatch.py
# for that model (code, bitmaps, Setup pages, names, version info), and the table and wave file as embedded
# RT_RCDATA resources (as with --embed) whose contents are zeroes. The patcher only converts the ROMs and
# writes the table and wave file into those two placeholders; it no longer needs syxg50.dll.
#   templates/<plugin name>.tpl   syxgmu50.tpl, syxg80.tpl, syxg90.tpl, syxg100.tpl, syxg128.tpl, syxg1000.tpl, syxg2000.tpl
#   templates/templates.json      sizes of the placeholders per model (measured from converted plugins)
# Templates are made from source/syxg50.dll (python utility/template.py --make, also run by the Autobuild
# workflow whenever their sources change). The version info carries the date of the last commit that changed
# the templates' sources, so the same commit always gives the same templates.
# Releases bundle the templates in one 7z archive (LZMA2, see .github/workflows/build.yml); Load reads it with
# the standard library (lzma), no 7-Zip needed on the user's system.
# If a converted table or wave file does not have the size of its placeholder (another ROM version, or the
# converter changed since the sizes were measured), the resources are rebuilt instead (dllpatch.embed_files):
# the plugin is the same, only the slower way. --measure updates the sizes.
import json, lzma, struct, subprocess, sys
from pathlib import Path

import dllpatch

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
TEMPLATE_DIR = REPO / 'templates'
SIZES_FILE = TEMPLATE_DIR / 'templates.json'
ARCHIVE = 'templates.7z'
DLL_SOURCE = REPO / 'source' / 'syxg50.dll'

# per model: table version (16 bytes max), table file, wave file, big table layout ("Full" DLL patch)
MODEL_FILES = {
    'MU50'   : ('SXGMU50a1',  'SXGMU50a1.TBL', 'SXGMU50a1.UPCM', False),
    'MU80'   : ('SXG MU80',   'SXGMU80a1.TBL', 'SXGMU80a1.UPCM', False),
    'MU90'   : ('SXG MU90',   'SXGMU90t.TBL',  'SXGMU90.UPCM',   False),
    'MU100'  : ('SXG MU100',  'SXGMU100X.TBL', 'SXGMU100X.UPCM', True),
    'MU128'  : ('SXG MU128',  'SXGMU128X.TBL', 'SXGMU128X.UPCM', True),
    'MU1000' : ('SXG MU1000', 'SXGMU1KX.TBL',  'SXGMU1KX.UPCM',  True),
    'MU2000' : ('SXG MU2000', 'SXGMU2KX.TBL',  'SXGMU2KX.UPCM',  True),    # only built without the MU1000 set (#53)
}

# what the templates are made of: a commit that changes one of these gets new templates
SOURCES = ['source/syxg50.dll', 'utility/dllpatch.py', 'utility/template.py', 'utility/bitmaps', 'templates/templates.json']

class TemplateError(Exception) :
    pass

def Name(model : str) -> str :
    return Path(dllpatch.Model_Dll_Name(model)).stem + '.tpl'


# ----------------------------------------------------------------------------- placeholders

def rcdata_slots(data : bytes | bytearray) -> dict[str, tuple[int, int, int]] :
    # named RT_RCDATA resources -> {NAME: (file offset of the data entry, file offset of the data, size)}
    pe = struct.unpack_from('<I', data, 0x3C)[0]
    opt = pe + 24
    ddir = opt + (96 if struct.unpack_from('<H', data, opt)[0] == 0x10B else 112)
    base = dllpatch.rva_to_offset(data, struct.unpack_from('<I', data, ddir + 16)[0])
    def entries(d) :
        n = sum(struct.unpack_from('<HH', data, d + 12))
        return [struct.unpack_from('<II', data, d + 16 + 8 * i) for i in range(n)]
    out = {}
    for t, p1 in entries(base) :
        if t != dllpatch.RT_RCDATA : continue
        for n, p2 in entries(base + (p1 & 0x7FFFFFFF)) :
            if not n & 0x80000000 : continue
            o = base + (n & 0x7FFFFFFF); k = struct.unpack_from('<H', data, o)[0]
            name = bytes(data[o + 2 : o + 2 + 2 * k]).decode('utf-16le').upper()
            langs = entries(base + (p2 & 0x7FFFFFFF))
            if not langs : continue
            entry = base + langs[0][1]
            rva, size = struct.unpack_from('<II', data, entry)
            out[name] = (entry, dllpatch.rva_to_offset(data, rva), size)
    return out

def Fill(tpl : bytes, files : list[tuple[str, bytes]]) -> bytes :
    # writes the table and wave file into the template's placeholders -> the finished plugin
    data = bytearray(tpl)
    slots = rcdata_slots(data)
    fits = all(name.upper() in slots and slots[name.upper()][2] == len(b) for name, b in files)
    if fits :
        for name, b in files :
            _, off, size = slots[name.upper()]
            if any(data[off : off + size]) : raise TemplateError(f'placeholder {name} is not empty')
            data[off : off + size] = b
        print('  template: ' + ', '.join(f'{n} ({len(b):,} bytes)' for n, b in files) + ' written into the placeholders')
    else :
        have = ', '.join(f'{n} {s[2]:,}' for n, s in slots.items())
        print(f'  template: placeholder sizes differ (template: {have}), resources rebuilt')
        data = dllpatch.embed_files(data, files)
    struct.pack_into('<I', data, dllpatch.pe_checksum_offset(data), dllpatch.pe_checksum(data))
    return bytes(data)

def Strip(tpl : bytes) -> bytes :
    # the template without its placeholders: a plugin that loads the table named in its ini (no --embed)
    data = dllpatch.embed_files(bytearray(tpl), [])
    struct.pack_into('<I', data, dllpatch.pe_checksum_offset(data), dllpatch.pe_checksum(data))
    return bytes(data)


def Write(tpl : bytes, out_dir : str, table_name : str, model : str, embed : list[tuple[str, bytes]] | None = None,
          dll_name : str | None = None) :
    # as dllpatch.Write: with embed (--embed) the finished plugin and no ini, else the plugin without
    # placeholders and <name>.ini, which selects the table
    out = Path(out_dir) / (dll_name or dllpatch.Model_Dll_Name(model))
    ini = out.with_suffix('.ini')
    data = Fill(tpl, embed) if embed else Strip(tpl)
    state = 'replaced' if out.exists() else 'wrote'
    out.write_bytes(data)
    print(f'template: {state} {out}, CRC32 {dllpatch.crc(data)}' + (f', {len(data):,} bytes' if embed else ''))
    if embed :
        if ini.exists() :
            ini.unlink()
            print(f'template: removed {ini} (not needed with embedded tables)')
    else :
        state = 'replaced' if ini.exists() else 'wrote'
        ini.write_bytes(dllpatch.INI_TEMPLATE.format(section = dllpatch.Ini_Id(model), table = table_name).encode('ascii'))
        print(f'template: {state} {ini}')


# ----------------------------------------------------------------------------- 7z archive (releases)
# Reads the archive the workflow makes with 7-Zip (7z, LZMA2, solid). Only what that needs: coders LZMA2 and
# LZMA (a compressed header), no filters, no encryption.

class _Reader :
    def __init__(self, b : bytes, p : int = 0) : self.b, self.p = b, p
    def byte(self) -> int :
        v = self.b[self.p]; self.p += 1; return v
    def bytes(self, n : int) -> bytes :
        v = self.b[self.p : self.p + n]; self.p += n; return v
    def u32(self) -> int : return struct.unpack('<I', self.bytes(4))[0]
    def num(self) -> int :
        first = self.byte(); mask = 0x80; value = 0
        for i in range(8) :
            if not first & mask : return value | ((first & (mask - 1)) << (8 * i))
            value |= self.byte() << (8 * i); mask >>= 1
        return value
    def bits(self, n : int) -> list[bool] :
        out = []; cur = mask = 0
        for _ in range(n) :
            if not mask : cur = self.byte(); mask = 0x80
            out.append(bool(cur & mask)); mask >>= 1
        return out
    def digests(self, n : int) :
        defined = [True] * n if self.byte() else self.bits(n)
        return [self.u32() if d else None for d in defined]

def _streams_info(r : _Reader) -> dict :
    info = dict(pack_pos = 0, pack_sizes = [], folders = [], unpack_sizes = [], substreams = None)
    while True :
        pid = r.byte()
        if pid == 0x00 : break
        if pid == 0x06 :                                    # PackInfo
            info['pack_pos'] = r.num(); n = r.num()
            while True :
                k = r.byte()
                if k == 0x00 : break
                if k == 0x09 : info['pack_sizes'] = [r.num() for _ in range(n)]
                elif k == 0x0A : r.digests(n)
                else : raise TemplateError(f'7z: unexpected property {k} in PackInfo')
        elif pid == 0x07 :                                  # UnPackInfo
            if r.byte() != 0x0B : raise TemplateError('7z: folder list expected')
            nf = r.num()
            if r.byte() : raise TemplateError('7z: external folders are not supported')
            for _ in range(nf) :
                coders = []
                for _ in range(r.num()) :
                    flag = r.byte(); cid = r.bytes(flag & 0x0F)
                    if flag & 0x10 : raise TemplateError('7z: complex coders are not supported')
                    props = r.bytes(r.num()) if flag & 0x20 else b''
                    coders.append((cid, props))
                if len(coders) != 1 : raise TemplateError('7z: only one coder per folder is supported')
                info['folders'].append(coders[0])
            if r.byte() != 0x0C : raise TemplateError('7z: unpack sizes expected')
            info['unpack_sizes'] = [r.num() for _ in range(nf)]
            while True :
                k = r.byte()
                if k == 0x00 : break
                if k == 0x0A : r.digests(nf)
                else : raise TemplateError(f'7z: unexpected property {k} in UnPackInfo')
        elif pid == 0x08 :                                  # SubStreamsInfo
            nf = len(info['folders']); counts = [1] * nf; sizes = None
            while True :
                k = r.byte()
                if k == 0x00 : break
                if k == 0x0D : counts = [r.num() for _ in range(nf)]
                elif k == 0x09 :
                    sizes = []
                    for f, c in enumerate(counts) :
                        part = [r.num() for _ in range(c - 1)] if c else []
                        if c : part.append(info['unpack_sizes'][f] - sum(part))
                        sizes.append(part)
                elif k == 0x0A : r.digests(sum(counts))
                else : raise TemplateError(f'7z: unexpected property {k} in SubStreamsInfo')
            if sizes is None : sizes = [[info['unpack_sizes'][f]] if c else [] for f, c in enumerate(counts)]
            info['substreams'] = sizes
        else : raise TemplateError(f'7z: unexpected property {pid} in StreamsInfo')
    if info['substreams'] is None : info['substreams'] = [[s] for s in info['unpack_sizes']]
    return info

def _decoder(cid : bytes, props : bytes, unpack_size : int) :
    # the dictionary never needs to be larger than the data
    if cid == b'\x21' :                                    # LZMA2
        p = props[0]
        d = 0xFFFFFFFF if p >= 40 else (2 | (p & 1)) << (p // 2 + 11)
        return lzma.LZMADecompressor(lzma.FORMAT_RAW, filters = [dict(id = lzma.FILTER_LZMA2,
                                     dict_size = max(4096, min(d, unpack_size)))])
    if cid == b'\x03\x01\x01' :                            # LZMA
        lc = props[0] % 9; lp = (props[0] // 9) % 5; pb = props[0] // 45
        d = struct.unpack_from('<I', props, 1)[0]
        return lzma.LZMADecompressor(lzma.FORMAT_RAW, filters = [dict(id = lzma.FILTER_LZMA1, lc = lc, lp = lp, pb = pb,
                                     dict_size = max(4096, min(d, unpack_size)))])
    raise TemplateError(f'7z: unsupported coder {cid.hex()} (expected LZMA2)')

def _unpack(f, pack_offset : int, pack_size : int, coder, unpack_size : int, start : int, size : int) -> bytes :
    # bytes start ... start + size of a folder's unpacked stream (decoded from its beginning, solid archive)
    d = _decoder(*coder, unpack_size)
    f.seek(pack_offset); left = pack_size; pos = 0; out = bytearray()
    while len(out) < size :
        chunk = b''
        if d.needs_input :
            if not left : raise TemplateError('7z: archive is truncated')
            chunk = f.read(min(1 << 20, left)); left -= len(chunk)
        buf = d.decompress(chunk, max_length = 1 << 22)
        lo = max(start - pos, 0); hi = min(start + size - pos, len(buf))
        if lo < hi : out += buf[lo : hi]
        pos += len(buf)
        if d.eof and len(out) < size : raise TemplateError('7z: stream ends early')
    return bytes(out)

def Archive_Read(path : Path, name : str) -> bytes :
    with open(path, 'rb') as f :
        sig = f.read(32)
        if sig[:6] != b'7z\xBC\xAF\x27\x1C' : raise TemplateError(f'{path.name} is not a 7z archive')
        off, size = struct.unpack_from('<QQ', sig, 12)
        f.seek(32 + off); r = _Reader(f.read(size))
        pid = r.byte()
        if pid == 0x17 :                                    # compressed header
            info = _streams_info(r)
            hdr = _unpack(f, 32 + info['pack_pos'], info['pack_sizes'][0], info['folders'][0], info['unpack_sizes'][0],
                          0, info['unpack_sizes'][0])
            r = _Reader(hdr); pid = r.byte()
        if pid != 0x01 : raise TemplateError('7z: header expected')
        info = None; names = []; empty = []
        while True :
            k = r.byte()
            if k == 0x00 : break
            if k == 0x04 : info = _streams_info(r)
            elif k in (0x02, 0x03) : raise TemplateError('7z: archive properties are not supported')
            elif k == 0x05 :                                # FilesInfo
                n = r.num(); empty = [False] * n
                while True :
                    t = r.byte()
                    if t == 0x00 : break
                    s = r.num(); body = _Reader(r.bytes(s))
                    if t == 0x0E : empty = body.bits(n)
                    elif t == 0x11 :
                        if body.byte() : raise TemplateError('7z: external names are not supported')
                        names = bytes(body.b[1:]).decode('utf-16le').split('\0')[:n]
        if info is None : raise TemplateError('7z: no streams')
        # files with data, in order, are the substreams of the folders, in order
        streams = [(fi, sum(subs[:j]), sz) for fi, subs in enumerate(info['substreams']) for j, sz in enumerate(subs)]
        k = 0; pack = 32 + info['pack_pos']; packs = []
        for ps in info['pack_sizes'] : packs.append(pack); pack += ps
        for i, nm in enumerate(names) :
            if empty[i] : continue
            fi, start, sz = streams[k]; k += 1
            if nm.replace('\\', '/').split('/')[-1].lower() == name.lower() :
                return _unpack(f, packs[fi], info['pack_sizes'][fi], info['folders'][fi], info['unpack_sizes'][fi], start, sz)
    raise TemplateError(f'{name} not found in {path.name}')


# ----------------------------------------------------------------------------- loading

def search_dirs() -> list[Path] :
    # checkout: templates/ in the repository; patcher (PyInstaller): the archive next to the modules
    if hasattr(sys, '_MEIPASS') : return [Path(sys._MEIPASS)]
    return [TEMPLATE_DIR]

def Load(model : str) -> bytes | None :
    # -> the template of a model, None if there is none
    name = Name(model)
    for d in search_dirs() :
        if (d / name).is_file() :
            print(f'template: {d / name}')
            return (d / name).read_bytes()
    for d in search_dirs() :
        if (d / ARCHIVE).is_file() :
            print(f'template: {name} from {d / ARCHIVE}')
            return Archive_Read(d / ARCHIVE, name)
    return None


# ----------------------------------------------------------------------------- making templates

def source_date() :
    # date of the last commit that changed the templates' sources (today without git or outside a checkout)
    import datetime
    try :
        out = subprocess.run(['git', 'log', '-1', '--format=%cs', '--'] + SOURCES, cwd = REPO,
                             capture_output = True, text = True, timeout = 30).stdout.strip()
        if out : return datetime.date.fromisoformat(out)
    except Exception : pass
    return datetime.date.today()

def read_sizes() -> dict :
    return json.loads(SIZES_FILE.read_text()) if SIZES_FILE.is_file() else {}

def Make(dll : Path, model : str, table_size : int, wave_size : int, date) -> bytes :
    _, table, wave, full = MODEL_FILES[model]
    return dllpatch.Patch(dll, full, model, table, [(table, bytes(table_size)), (wave, bytes(wave_size))], today = date)

def make_all(dll : Path, out_dir : Path, date = None) :
    sizes = read_sizes()
    date = date or source_date()
    out_dir.mkdir(exist_ok = True)
    for model in MODEL_FILES :
        if model not in sizes : raise TemplateError(f'{SIZES_FILE.name}: no sizes for {model}')
        s = sizes[model]
        print(f'\n==== {Name(model)} ({model}, {date})')
        data = Make(dll, model, s['table'], s['wave'], date)
        path = out_dir / Name(model)
        old = path.read_bytes() if path.is_file() else None
        if old == data : print(f'template: {path} unchanged')
        else :
            path.write_bytes(data)
            print(f'template: {"replaced" if old else "wrote"} {path}, {len(data):,} bytes, CRC32 {dllpatch.crc(data)}')

def measure(folder : Path) :
    # sizes of the tables in converted plugins (--embed) -> templates.json
    sizes = read_sizes()
    for model, (_, table, wave, _) in MODEL_FILES.items() :
        p = folder / dllpatch.Model_Dll_Name(model)
        if not p.is_file() : continue
        slots = rcdata_slots(p.read_bytes())
        if table.upper() not in slots or wave.upper() not in slots :
            print(f'{p.name}: no embedded {table} / {wave}, skipped'); continue
        sizes[model] = dict(table = slots[table.upper()][2], wave = slots[wave.upper()][2])
        print(f'{model}: table {sizes[model]["table"]:,} bytes, wave {sizes[model]["wave"]:,} bytes')
    sizes = {m : sizes[m] for m in MODEL_FILES if m in sizes}
    SIZES_FILE.parent.mkdir(exist_ok = True)
    SIZES_FILE.write_text(json.dumps(sizes, indent = 1) + '\n')
    print(f'wrote {SIZES_FILE}')

def check() :
    # every model has a template, its placeholders have the sizes of templates.json and are empty
    sizes = read_sizes()
    for model, (_, table, wave, _) in MODEL_FILES.items() :
        tpl = Load(model)
        if tpl is None : raise TemplateError(f'{Name(model)} not found')
        slots = rcdata_slots(tpl)
        for name, key in ((table, 'table'), (wave, 'wave')) :
            if name.upper() not in slots : raise TemplateError(f'{Name(model)}: no placeholder {name}')
            _, off, size = slots[name.upper()]
            if sizes and model in sizes and sizes[model][key] != size :
                raise TemplateError(f'{Name(model)}: {name} has {size:,} bytes, {SIZES_FILE.name} says {sizes[model][key]:,}')
            if any(tpl[off : off + size]) : raise TemplateError(f'{Name(model)}: placeholder {name} is not empty')
        print(f'{Name(model)}: ok, {len(tpl):,} bytes')

if __name__ == '__main__' :
    # python utility/template.py --make [--dll <syxg50.dll>] [--date YYYY-MM-DD]
    #                            --measure <folder with converted plugins (--embed)>
    #                            --check
    import argparse, datetime
    ap = argparse.ArgumentParser(description = 'SXG-Create-NF plugin templates')
    ap.add_argument('--make', action = 'store_true', help = 'make the templates from syxg50.dll')
    ap.add_argument('--dll', type = Path, default = DLL_SOURCE)
    ap.add_argument('--date', type = datetime.date.fromisoformat, help = 'version date (default: last commit of the sources)')
    ap.add_argument('--out', type = Path, default = TEMPLATE_DIR)
    ap.add_argument('--measure', type = Path, metavar = 'FOLDER', help = 'placeholder sizes from converted plugins')
    ap.add_argument('--check', action = 'store_true', help = 'check the templates')
    a = ap.parse_args()
    try :
        if a.measure : measure(a.measure)
        if a.make : make_all(a.dll, a.out, a.date)
        if a.check : check()
    except (TemplateError, dllpatch.DllPatchError) as e :
        print(f'error: {e}'); sys.exit(1)
