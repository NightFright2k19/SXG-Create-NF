# analyze_drum_eg.py - compares MU80 drum voices with the S-YXG50 drum voices of the same kit and key
#
# Purpose: calibrate the drum envelope conversion (drum voice bytes 13/14/15) from real data
# instead of the current heuristic in cnv_fromBASE.py.
#
# Usage (in the SXG-Create folder):
#   python analyze_drum_eg.py yamaha_mu80.bin xq012b0-822.bin xq013b0-823.bin xq089b0-824.bin xq090b0-825.bin syxg50.dll
#
# The last argument is the S-YXG50 DLL that contains the embedded tables (the 5 MB version),
# or alternatively two files: SXGBIN41.TBL SXGWAVE4.TBL
# Writes drum_eg_compare.csv next to the first ROM and prints a summary.

import sys, csv
from pathlib import Path
from collections import Counter, defaultdict

from dataCRCs import ROMLIST
from dataenum import MU
from utils import calccrc32, Dejumble
import decode, decMU80, decMU50, decMU90, decMU100, decSYXG50


def pe_rcdata(dll : bytes) -> dict[str, bytes] :
    # minimal PE resource reader: returns the named RT_RCDATA (type 10) resources
    pe = int.from_bytes(dll[0x3C:0x40], 'little')
    nsec = int.from_bytes(dll[pe+6:pe+8], 'little')
    opt = pe + 24
    magic = int.from_bytes(dll[opt:opt+2], 'little')
    dd = opt + (96 if magic == 0x10B else 112)
    rsrc_rva = int.from_bytes(dll[dd+2*8:dd+2*8+4], 'little')
    sec = opt + int.from_bytes(dll[pe+20:pe+22], 'little')
    sections = []
    for i in range(nsec) :
        s = sec + i*40
        sections.append((int.from_bytes(dll[s+12:s+16],'little'), int.from_bytes(dll[s+8:s+12],'little'), int.from_bytes(dll[s+20:s+24],'little')))
    def off(rva) :
        for va, vs, raw in sections :
            if va <= rva < va + max(vs, 1) : return rva - va + raw
        raise ValueError(hex(rva))
    base = off(rsrc_rva)
    def entries(d) :
        n = int.from_bytes(dll[base+d+12:base+d+14],'little') + int.from_bytes(dll[base+d+14:base+d+16],'little')
        for i in range(n) :
            e = base + d + 16 + i*8
            yield int.from_bytes(dll[e:e+4],'little'), int.from_bytes(dll[e+4:e+8],'little')
    def name(v) :
        p = base + (v & 0x7FFFFFFF); ln = int.from_bytes(dll[p:p+2],'little')
        return dll[p+2:p+2+2*ln].decode('utf-16le')
    out = {}
    for tid, tptr in entries(0) :
        if tid != 10 : continue
        for nid, nptr in entries(tptr & 0x7FFFFFFF) :
            if not nid & 0x80000000 : continue
            for lid, lptr in entries(nptr & 0x7FFFFFFF) :
                de = base + (lptr & 0x7FFFFFFF)
                rva = int.from_bytes(dll[de:de+4],'little'); size = int.from_bytes(dll[de+4:de+8],'little')
                out[name(nid)] = dll[off(rva):off(rva)+size]
    return out


def load_source(files : list[Path]) :
    crcs = {calccrc32(f) : f for f in files}
    ref = next((r for r in ROMLIST if r.Is_List_Ours(crcs)), None)
    if ref is None :
        raise SystemExit('source ROM set not recognized')
    prg, waves = ref.Order_Pathlists(crcs)
    match ref.source :
        case MU.MU80 : dec = decMU80.MU80.From_Bytes(Dejumble(open(prg[0],'rb').read()))
        case MU.MU50 : dec = decMU50.MU50.From_Bytes(Dejumble(open(prg[0],'rb').read()))
        case MU.MU90 : 
            dec = decMU90.MU90.From_Bytes(Dejumble(open(prg[0],'rb').read()))
            return ref.name, decode.Create_Table(dec, ref.source, dec.data, waves)
        case MU.MU100 : 
            dec = decMU100.MU100.From_Bytes(Dejumble(open(prg[0],'rb').read()))
            return ref.name, decode.Create_Table(dec, MU.MU90, dec.data, waves)
        case MU.SYXG50 : dec = decSYXG50.SYXG50.From_Bytes(open(prg[0],'rb').read())
        case _ : raise SystemExit(f'unsupported source {ref.source}')
    return ref.name, decode.Create_Table(dec, ref.source, dec.data, waves)


def load_syxg50(args : list[str], workdir : Path) :
    if len(args) == 1 :
        res = pe_rcdata(open(args[0],'rb').read())
        if 'SXGBIN41.TBL' not in res :
            raise SystemExit('no embedded SXGBIN41.TBL in this DLL (use the 5 MB syxg50.dll or pass SXGBIN41.TBL SXGWAVE4.TBL)')
        tbl, wav = workdir / '_sxgbin41.tmp', workdir / '_sxgwave4.tmp'
        tbl.write_bytes(res['SXGBIN41.TBL']); wav.write_bytes(res['SXGWAVE4.TBL'])
    else :
        tbl, wav = Path(args[0]), Path(args[1])
    dec = decSYXG50.SYXG50.From_Bytes(open(tbl,'rb').read())
    table = decode.Create_Table(dec, MU.SYXG50, dec.data, [wav])
    if len(args) == 1 : 
        tbl.unlink(missing_ok=True); wav.unlink(missing_ok=True)
    return table


def drum_map(table) :
    # (bank, program, key) -> drum voice (internal sample only)
    out = {}
    for kit in table.drumkits.values() :
        entries = [(kit.bank, kit.prg)] + list(kit.aliases)
        for key in kit.drumvoices.keys() :
            dv = kit.get_drumvoice(table.DrumVoice_pool, key)
            if dv is None or dv.ext_Voice_address : continue
            for bank, prg in entries :
                out[(str(bank), prg, key)] = dv
    return out


def main() :
    args = sys.argv[1:]
    # S-YXG50 reference: the last argument (.dll) or the last two (SXGBIN41.TBL SXGWAVE4.TBL)
    split = len(args) - 1 if args[-1].lower().endswith('.dll') else len(args) - 2
    src_files = [Path(a) for a in args[:split]]
    name, src = load_source(src_files)
    ref = load_syxg50(args[split:], src_files[0].parent)

    a, b = drum_map(src), drum_map(ref)
    # count every (source drum voice, S-YXG50 drum voice) pair once, kits appear in many banks as aliases
    keys = []; seen = set()
    for k in sorted(set(a) & set(b)) : 
        pair = (id(a[k]), id(b[k]))
        if pair in seen : continue
        seen.add(pair); keys.append(k)
    print(f'{name}: {len({id(v) for v in a.values()})} drum voices, S-YXG50: {len({id(v) for v in b.values()})} drum voices, '
          f'matched pairs (same kit and key): {len(keys)}')
    if not keys :
        return

    eq = [0]*16
    x13 = defaultdict(Counter); x14 = defaultdict(Counter); x15 = defaultdict(Counter)
    d13 = Counter(); d14 = Counter(); d15 = Counter()
    rows = []
    for k in keys :
        x, y = a[k].data, b[k].data
        for i in range(16) :
            eq[i] += x[i] == y[i]
        x13[x[13]][y[13]] += 1; x14[x[14]][y[14]] += 1; x15[x[15]][y[15]] += 1
        d13[y[13]-x[13]] += 1; d14[y[14]-x[14]] += 1; d15[y[15]-x[15]] += 1
        rows.append([*k, *(f'{v:02X}' for v in x[:16]), *(f'{v:02X}' for v in y[:16])])

    print('\nshare of equal values per drum voice byte (source vs S-YXG50):')
    print('  ' + '  '.join(f'{i:>3}' for i in range(16)))
    print('  ' + '  '.join(f'{100*e//len(keys):>3}' for e in eq) + '   (%)')

    def crosstab(title, xt) :
        print(f'\n{title}  (source value -> S-YXG50 values)')
        for v in sorted(xt) :
            top = ', '.join(f'{w:02X}x{c}' for w, c in xt[v].most_common(6))
            print(f'  {v:02X} ({sum(xt[v].values()):3}) -> {top}')
    crosstab('byte 13', x13); crosstab('byte 14', x14); crosstab('byte 15', x15)
    for t, d in (('13', d13), ('14', d14), ('15', d15)) :
        print(f'\nbyte {t} difference S-YXG50 minus source, most common: ' + ', '.join(f'{k:+d}x{c}' for k, c in d.most_common(8)))

    out = src_files[0].parent / 'drum_eg_compare.csv'
    with open(out, 'w', newline='') as f :
        w = csv.writer(f)
        w.writerow(['bank', 'program', 'key'] + [f'src_{i}' for i in range(16)] + [f'syxg_{i}' for i in range(16)])
        w.writerows(rows)
    print(f'\nwrote {out}')


if __name__ == '__main__' :
    main()
