# analyze_mu80.py - analysis tools used to calibrate the MU80 conversion against the S-YXG50 tables
# (merged from analyze_drum_eg / analyze_voice_params / analyze_sample_flags / list_long_loops).
# Not needed for a conversion; run from anywhere:
#   python utility/dev/analyze_mu80.py <tool> <files...>
# Tools:
#   drum-eg       MU80 drum voices vs. the S-YXG50 drum voices of the same kit and key (drum_eg_compare.csv)
#   voice-params  converted MU80 voice elements vs. the S-YXG50 voices, byte by byte (voice_param_compare.csv)
#   sample-flags  bit 6 (0x40) of the MU80 sample format byte (sample_flags.csv)
#   long-loops    MU80 voices whose sample loops exceed 65535 samples
# Each section below keeps the description and usage of the former script.

import sys, csv, copy, math, statistics
from pathlib import Path
from collections import Counter, defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))     # the utility folder

from dataCRCs import ROMLIST
from dataenum import MU, BankToLSBMSB
from utils import calccrc32, Dejumble
import decBase, decMU80, decMU50, decMU90, decMU100, decSYXG50
import tableconvert


# ==================== drum-eg (was analyze_drum_eg.py) ====================

# analyze_drum_eg.py - compares MU80 drum voices with the S-YXG50 drum voices of the same kit and key
#
# Purpose: calibrate the drum envelope conversion (drum voice bytes 13/14/15) from real data
# instead of the current heuristic in tableconvert.TableConverter.
#
# Usage:
#   python analyze_mu80.py drum-eg yamaha_mu80.bin xq012b0-822.bin xq013b0-823.bin xq089b0-824.bin xq090b0-825.bin syxg50.dll
#
# The last argument is the S-YXG50 DLL that contains the embedded tables (the 5 MB version),
# or alternatively two files: SXGBIN41.TBL SXGWAVE4.TBL
# Writes drum_eg_compare.csv next to the first ROM and prints a summary.




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
            return ref.name, decBase.Create_Table(dec, ref.source, dec.data, waves)
        case MU.MU100 : 
            dec = decMU100.MU100.From_Bytes(Dejumble(open(prg[0],'rb').read()))
            return ref.name, decBase.Create_Table(dec, MU.MU90, dec.data, waves)
        case MU.SYXG50 : dec = decSYXG50.SYXG50.From_Bytes(open(prg[0],'rb').read())
        case _ : raise SystemExit(f'unsupported source {ref.source}')
    return ref.name, decBase.Create_Table(dec, ref.source, dec.data, waves)


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
    table = decBase.Create_Table(dec, MU.SYXG50, dec.data, [wav])
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


def main_drum_eg() :
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


# ==================== voice-params (was analyze_voice_params.py) ====================

# analyze_voice_params.py - compares converted MU80 voice elements with the S-YXG50 voices
# in the same bank / program slot, byte by byte (78-byte S-YXG50 element layout).
#
# Purpose: check the MU80 element conversion in tableconvert.fromMU80 (field mapping and value
# offsets, e.g. envelope rates) against real S-YXG50 data, like analyze_drum_eg.py did for drums.
#
# Usage:
#   python analyze_mu80.py voice-params yamaha_mu80.bin xq012b0-822.bin xq013b0-823.bin xq089b0-824.bin xq090b0-825.bin syxg50.dll
# The last argument is the 5 MB syxg50.dll with embedded tables (or: SXGBIN41.TBL SXGWAVE4.TBL).
# Writes voice_param_compare.csv next to the first ROM and prints a summary.



LABELS = {
    1:'key low', 2:'key high', 3:'vel low', 4:'vel high', 5:'LFO wave/phase', 6:'FEG velo curve',
    7:'LFO speed', 8:'vib delay', 9:'vib fade', 10:'LFO pitch depth', 11:'LFO filter depth', 12:'LFO amp depth',
    13:'PEG note shift', 14:'PEG detune', 15:'pitch scaling', 16:'pitch sc. center', 17:'PEG depth',
    18:'PEG velo level', 19:'PEG velo rate', 20:'PEG rate scaling',
    **{i:'pitch EG' for i in range(21, 31)}, **{i:'filter EG' for i in range(31, 42)},
    42:'FEG velo level', 43:'FEG velo rate', 44:'FEG rate scaling',
    **{i:'filter EG 2' for i in range(45, 55)}, **{i:'level/scaling' for i in range(55, 64)},
    64:'velocity curve', 65:'pan', 66:'AEG rate scaling', 67:'AEG RS center', 68:'AEG key-on delay',
    **{i:'amp EG' for i in range(69, 75)}, 75:'wave offset', 76:'wave offset', 77:'reso sens',
}

CONVERTERS = {MU.MU80 : tableconvert.fromMU80(MU.MU80), MU.MU90 : tableconvert.fromMU90(MU.MU90), MU.MU50 : tableconvert.fromMU50(MU.MU50),
              MU.SYXG50 : tableconvert.fromSYXG50(MU.SYXG50)}


class _WB :   # stand-in wavebank, only .index is used by ConvertElements
    index = 0


def converted_elements(voice, source : MU) -> list[bytes] :
    v = copy.deepcopy(voice)
    CONVERTERS[source].ConvertElements(v, [_WB() for _ in v.elements], MU.SYXG50)
    return [bytes(e.data) for e in v.elements]


def voice_map(table) :
    # (bank, msb, lsb, program) -> voice
    out = {}
    for vb in table.voice_banks.values() :
        slots = [(str(vb.bank), vb.msb, vb.lsb)]
        for bank, byte in vb.aliases :
            try :
                lsb, msb = BankToLSBMSB(bank, byte)
                slots.append((str(bank), msb, lsb))
            except Exception :
                pass
        for prg, vhash in vb.voices.items() :
            v = table.Voice_pool.get(vhash)
            if v is None : continue
            for s in slots :
                out[(*s, prg)] = v
    return out


def main_voice_params() :
    args = sys.argv[1:]
    split = len(args) - 1 if args[-1].lower().endswith('.dll') else len(args) - 2
    src_files = [Path(a) for a in args[:split]]
    name, src = load_source(src_files)
    ref = load_syxg50(args[split:], src_files[0].parent)
    source_mu = next(iter(src.Voice_pool.values())).elements[0].format

    a, b = voice_map(src), voice_map(ref)
    pairs = []; seen = set()
    for k in sorted(set(a) & set(b), key=str) :
        va, vb = a[k], b[k]
        if (id(va), id(vb)) in seen : continue
        seen.add((id(va), id(vb)))
        if len(va.elements) != len(vb.elements) : continue
        pairs.append((k, va, vb))

    print(f'{name}: {len({id(v) for v in a.values()})} voices, S-YXG50: {len({id(v) for v in b.values()})} voices, '
          f'same slot + same element count: {len(pairs)} voice pairs')

    eq = [0]*78; diffs = [Counter() for _ in range(78)]; minus21 = [0]*78; big = [0]*78; n = 0; rows = []
    for k, va, vb in pairs :
        ea = converted_elements(va, source_mu)
        eb = [bytes(e.data) for e in vb.elements]
        for i, (x, y) in enumerate(zip(ea, eb)) :
            n += 1
            for j in range(1, 78) :
                eq[j] += x[j] == y[j]
                diffs[j][y[j] - x[j]] += 1
                if x[j] >= 0x21 : 
                    big[j] += 1
                    minus21[j] += y[j] == x[j] - 0x21
            rows.append([*k, va.name.strip(), i, *(f'{v:02X}' for v in x), *(f'{v:02X}' for v in y)])

    print(f'compared elements: {n}\n')
    print(' byte  label              equal   best offset        "-0x21" fits (of values >= 0x21)   other common differences')
    for j in range(1, 78) :
        best, cnt = diffs[j].most_common(1)[0]
        others = ', '.join(f'{d:+d}x{c}' for d, c in diffs[j].most_common(4)[1:])
        flag = '  <--' if best != 0 and cnt > n * 0.5 else ''
        print(f' {j:4}  {LABELS.get(j, ""):18} {100*eq[j]//n:4}%   {best:+4d} ({100*cnt//n:3}%)   {(f"{100*minus21[j]//big[j]:3}% of {big[j]:4}" if big[j] else "      -    "):>14}      {others}{flag}')

    out = src_files[0].parent / 'voice_param_compare.csv'
    with open(out, 'w', newline='', encoding='utf-8') as f :
        w = csv.writer(f)
        w.writerow(['bank', 'msb', 'lsb', 'program', 'name', 'element'] + [f'src_{i}' for i in range(78)] + [f'syxg_{i}' for i in range(78)])
        w.writerows(rows)
    print(f'\nwrote {out}')


# ==================== sample-flags (was analyze_sample_flags.py) ====================

# analyze_sample_flags.py - investigates bit 6 (0x40) of the MU80 sample format byte
#
# MU80 wavedata entry byte +5 / drum voice byte +21:
#   bit 7: 1 = 16-bit PCM, 0 = ADPCM      bit 0: 17th bit of the loop length
#   bit 6: unknown -> this script collects evidence: loop lengths, loop loudness,
#          samples used with both values, drum vs. voice use, ADPCM parameters.
#
# Usage:
#   python analyze_mu80.py sample-flags yamaha_mu80.bin xq012b0-822.bin xq013b0-823.bin xq089b0-824.bin xq090b0-825.bin
# Writes sample_flags.csv next to the first ROM and prints a summary.




def rms_s16(w : bytes, start : int, n : int) -> float :
    if n <= 0 : return 0.0
    b = w[start : start + 2*n]
    if len(b) < 2 : return 0.0
    vals = [int.from_bytes(b[i:i+2], 'little', signed=True) for i in range(0, len(b) - 1, 2)]
    return math.sqrt(sum(v*v for v in vals) / len(vals))


def rms_adpcm_bytes(w : bytes, start : int, n : int) -> float :
    # rough activity measure for ADPCM: how far the delta bytes are from "no change"
    b = w[start : start + n]
    if not b : return 0.0
    return statistics.fmean((x if x < 128 else 255 - x) for x in b)


def main_sample_flags() :
    files = [Path(a) for a in sys.argv[1:]]
    crcs = {calccrc32(f) : f for f in files}
    ref = next((r for r in ROMLIST if r.source == MU.MU80 and r.Is_List_Ours(crcs)), None)
    if ref is None :
        raise SystemExit('MU80 ROM set (v1.04) not found - pass all 5 ROM files')
    prg, waves = ref.Order_Pathlists(crcs)
    dec = decMU80.MU80.From_Bytes(Dejumble(open(prg[0], 'rb').read()))
    table = decBase.Create_Table(dec, MU.MU80, dec.data, waves)
    wrom = b''.join(open(p, 'rb').read() for p in waves)   # same as convert.py
    analyze(table, dec.data, wrom, files[0].parent)


def analyze(table, data, wrom : bytes, outdir : Path) : 

    # which voices use which wavebank
    users = defaultdict(set)
    for v in table.Voice_pool.values() :
        for e in v.elements :
            users[e.wavebank_address].add(v.name.strip())

    rows = []
    # --- voice wavedata entries
    for wb_addr, wb in table.Wavebank_pool.items() :
        for w in wb.waves :
            raw = data[w.address_src + 5]
            rows.append(dict(kind='voice', entry=f'{w.address_src:06X}', fmt=raw, bit7=raw >> 7 & 1, bit6=raw >> 6 & 1,
                             dpcm=data[w.address_src + 11], neg=w.offset_negative, pos=w.offset_positive,
                             loop=w.loop_address_src, keys=f'{w.key_min}-{w.key_max}',
                             tune_note=w.tune_note, tune_cent=w.tune_cent, atten=w.attenuation, bank=str(wb_addr),
                             raw=data[w.address_src : w.address_src + 14].hex(' '),
                             users=', '.join(sorted(users.get(wb_addr, set())))[:120]))
    # --- drum voices with their own sample
    for addr, dv in table.DrumVoice_pool.items() :
        if dv.ext_Voice_address : continue
        raw = dv.data[21]
        rows.append(dict(kind='drum', entry=str(addr), fmt=raw, bit7=raw >> 7 & 1, bit6=raw >> 6 & 1,
                         dpcm=dv.data[27], neg=dv.offset_negative, pos=dv.offset_positive,
                         loop=dv.Sample_hash,
                         keys='', users=''))

    # loudness of body and loop
    for r in rows :
        la = r['loop']
        if r['bit7'] :
            r['rms_body'] = rms_s16(wrom, la - 2*r['neg'], r['neg'])
            r['rms_loop'] = rms_s16(wrom, la, r['pos'])
        else :
            r['rms_body'] = rms_adpcm_bytes(wrom, la - r['neg'], r['neg'])
            r['rms_loop'] = rms_adpcm_bytes(wrom, la, r['pos'])
        r['loop_rel'] = (r['rms_loop'] / r['rms_body']) if r['rms_body'] else 0.0

    # ---------------- summary
    def group(rs) :
        g = defaultdict(list)
        for r in rs : g[(r['kind'], r['fmt'] & 0xC0)].append(r)
        return g
    g = group(rows)
    print(f'{len(rows)} sample references ({sum(r["kind"]=="voice" for r in rows)} voice wave entries, '
          f'{sum(r["kind"]=="drum" for r in rows)} drum voices)\n')
    print(' kind   top bits  count   loop=0  loop<=2  loop<64  median loop   loop quiet (<5% of body)   median loop/body')
    for (kind, top), rs in sorted(g.items()) :
        pos = [r['pos'] for r in rs]
        quiet = sum(1 for r in rs if r['pos'] > 0 and r['loop_rel'] < 0.05)
        rel = [r['loop_rel'] for r in rs if r['pos'] > 0 and r['rms_body']]
        print(f' {kind:5}  {top:02X}       {len(rs):5}   {sum(p==0 for p in pos):6}  {sum(p<=2 for p in pos):7}  {sum(p<64 for p in pos):7}'
              f'  {int(statistics.median(pos)):11}   {quiet:24}   {statistics.median(rel) if rel else 0:15.2f}')

    # same sample (loop address) referenced with different bit 6
    by_loop = defaultdict(list)
    for r in rows : by_loop[(r['bit7'], r['loop'])].append(r)
    mixed = [(k, rs) for k, rs in by_loop.items() if len({r['bit6'] for r in rs}) > 1]
    print(f'\nsamples referenced with bit 6 = 0 AND bit 6 = 1: {len(mixed)}')
    diffs = Counter()
    for (b7, la), rs in mixed[:400] :
        a = [r for r in rs if r['bit6'] == 0]; b = [r for r in rs if r['bit6'] == 1]
        for x in a :
            for y in b :
                diffs[('same neg' if x['neg']==y['neg'] else 'diff neg', 'same loop len' if x['pos']==y['pos'] else 'diff loop len',
                       f"{x['kind']}/{y['kind']}")] += 1
    for k, c in diffs.most_common(10) : print(f'   {c:4}x  {k}')
    for (b7, la), rs in mixed[:12] :
        print(f'   loop {la:07X}: ' + ' | '.join(f"{r['kind']} fmt {r['fmt']:02X} neg {r['neg']} loop {r['pos']} {r['users'][:30]}" for r in rs[:4]))

    # multisamples (wavebanks) that contain a bit-6 entry: all zones side by side
    banks = defaultdict(list)
    for r in rows : 
        if r['kind'] == 'voice' : banks[r['bank']].append(r)
    flagged = [b for b, rs in banks.items() if any(r['bit6'] for r in rs)]
    print(f'\nmultisamples containing a bit-6 zone: {len(flagged)}  (tune note = byte +1, cent = +2, atten = +0)')
    for b in flagged : 
        rs = banks[b]
        print(f'  [{rs[0]["users"][:60]}]')
        for r in rs : 
            print(f"     keys {r['keys']:>8}  fmt {r['fmt']:02X}  tune {r['tune_note']:3}/{r['tune_cent']:3}  atten {r['atten']:3}"
                  f"  loopaddr {r['loop']:07X}  neg {r['neg']:6} loop {r['pos']:6}   raw {r['raw']}")

    print('\nADPCM parameter byte (+11 / drum +27) per group, most common:')
    for (kind, top), rs in sorted(g.items()) :
        print(f'   {kind:5} {top:02X}: ' + ', '.join(f'{d:02X}x{c}' for d, c in Counter(r['dpcm'] for r in rs).most_common(6)))

    out = outdir / 'sample_flags.csv'
    with open(out, 'w', newline='', encoding='utf-8') as f :
        cols = ['kind','entry','fmt','bit7','bit6','dpcm','neg','pos','loop','keys','tune_note','tune_cent','atten','rms_body','rms_loop','loop_rel','raw','users']
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore'); w.writeheader()
        for r in rows :
            r = dict(r); r['fmt'] = f"{r['fmt']:02X}"; r['dpcm'] = f"{r['dpcm']:02X}"; r['loop'] = f"{r['loop']:X}"
            r['rms_body'] = round(r['rms_body'], 1); r['rms_loop'] = round(r['rms_loop'], 1); r['loop_rel'] = round(r['loop_rel'], 3)
            w.writerow(r)
    print(f'\nwrote {out}')


# ==================== long-loops (was list_long_loops.py) ====================

# list_long_loops.py - lists MU80 voices whose sample loops exceed 65535 samples
# (the old S-YXG50 16-bit limit).
# Usage: python analyze_mu80.py long-loops yamaha_mu80.bin xq012b0-822.bin xq013b0-823.bin xq089b0-824.bin xq090b0-825.bin



LIMIT = 0xFFFF


def main_long_loops():
    files = [Path(a) for a in sys.argv[1:]]
    crcs = {calccrc32(f): f for f in files}

    ref = next((r for r in ROMLIST if r.source == MU.MU80 and r.Is_List_Ours(crcs)), None)
    if ref is None:
        print('MU80 ROM set (v1.04) not found - pass all 5 ROM files.')
        return
    prg, waves = ref.Order_Pathlists(crcs)

    dec = decMU80.MU80.From_Bytes(Dejumble(open(prg[0], 'rb').read()))
    table = decBase.Create_Table(dec, MU.MU80, dec.data, waves)

    # wavebank address -> voices using it (bank, msb, lsb, program, name)
    users: dict = {}
    for vb in table.voice_banks.values():
        for program, vhash in vb.voices.items():
            voice = table.Voice_pool.get(vhash)
            if voice is None:
                continue
            lsb, msb = vb.lsb, vb.msb
            for e in voice.elements:
                users.setdefault(e.wavebank_address, set()).add(
                    (str(vb.bank), msb, lsb, program, voice.name.strip()))

    rows = []
    for wb_addr, wb in table.Wavebank_pool.items():
        for w in wb.waves:
            if w.offset_positive > LIMIT:
                s = table.Sample_pool.get(w.loop_address_src)
                sname = s.get_a_name() if s is not None else '?'
                rows.append((w.offset_positive, w.offset_negative, w.key_min, w.key_max,
                             sname, sorted(users.get(wb_addr, set()))))

    drum_rows = [(d.offset_positive, d) for d in table.DrumVoice_pool.values()
                 if d.offset_positive > LIMIT]

    if not rows and not drum_rows:
        print('No loops longer than 65535 samples found.')
        return

    rows.sort(key=lambda r: -r[0])
    print(f'{len(rows)} wave entries with loop > {LIMIT} samples:\n')
    for loop, body, kmin, kmax, sname, vs in rows:
        print(f'sample "{sname}"  loop={loop:,}  body={body:,}  keys {kmin}-{kmax}  '
              f'(old DLL played only {LIMIT / loop:.0%} of the loop)')
        if not vs:
            print('    (not used by a normal voice)')
        for bank, msb, lsb, program, name in vs:
            print(f'    {bank:<5} MSB={msb:<3} LSB={lsb:<3} PC={program:<3} (Prog {program + 1:>3})  "{name}"')
        print()

    for loop, d in drum_rows:
        print(f'drum voice at {d.address_src}: loop={loop:,}')


TOOLS = {'drum-eg' : main_drum_eg, 'voice-params' : main_voice_params, 'sample-flags' : main_sample_flags, 'long-loops' : main_long_loops}

if __name__ == '__main__' :
    if len(sys.argv) < 2 or sys.argv[1] not in TOOLS :
        print('usage: python analyze_mu80.py {' + '|'.join(TOOLS) + '} <files...>')
        sys.exit(1)
    tool = sys.argv.pop(1)
    TOOLS[tool]()
