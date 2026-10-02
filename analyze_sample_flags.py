# analyze_sample_flags.py - investigates bit 6 (0x40) of the MU80 sample format byte
#
# MU80 wavedata entry byte +5 / drum voice byte +21:
#   bit 7: 1 = 16-bit PCM, 0 = ADPCM      bit 0: 17th bit of the loop length
#   bit 6: unknown -> this script collects evidence: loop lengths, loop loudness,
#          samples used with both values, drum vs. voice use, ADPCM parameters.
#
# Usage (in the SXG-Create folder):
#   python analyze_sample_flags.py yamaha_mu80.bin xq012b0-822.bin xq013b0-823.bin xq089b0-824.bin xq090b0-825.bin
# Writes sample_flags.csv next to the first ROM and prints a summary.

import sys, csv, math, statistics
from pathlib import Path
from collections import Counter, defaultdict

from dataCRCs import ROMLIST
from dataenum import MU
from utils import calccrc32, Dejumble
import decode, decMU80


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


def main() :
    files = [Path(a) for a in sys.argv[1:]]
    crcs = {calccrc32(f) : f for f in files}
    ref = next((r for r in ROMLIST if r.source == MU.MU80 and r.Is_List_Ours(crcs)), None)
    if ref is None :
        raise SystemExit('MU80 ROM set (v1.04) not found - pass all 5 ROM files')
    prg, waves = ref.Order_Pathlists(crcs)
    dec = decMU80.MU80.From_Bytes(Dejumble(open(prg[0], 'rb').read()))
    table = decode.Create_Table(dec, MU.MU80, dec.data, waves)
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


if __name__ == '__main__' :
    main()
