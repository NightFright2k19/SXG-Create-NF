# analyze_voice_params.py - compares converted MU80 voice elements with the S-YXG50 voices
# in the same bank / program slot, byte by byte (78-byte S-YXG50 element layout).
#
# Purpose: check the MU80 element conversion in cnv_fromMU80.py (field mapping and value
# offsets, e.g. envelope rates) against real S-YXG50 data, like analyze_drum_eg.py did for drums.
#
# Usage (in the SXG-Create folder):
#   python analyze_voice_params.py yamaha_mu80.bin xq012b0-822.bin xq013b0-823.bin xq089b0-824.bin xq090b0-825.bin syxg50.dll
# The last argument is the 5 MB syxg50.dll with embedded tables (or: SXGBIN41.TBL SXGWAVE4.TBL).
# Writes voice_param_compare.csv next to the first ROM and prints a summary.

import sys, csv, copy
from pathlib import Path
from collections import Counter

from dataenum import MU, BankToLSBMSB
import cnv_fromMU80, cnv_fromMU50, cnv_fromMU90, cnv_fromSYXG50
from analyze_drum_eg import load_source, load_syxg50

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

CONVERTERS = {MU.MU80 : cnv_fromMU80.fromMU80(MU.MU80), MU.MU90 : cnv_fromMU90.fromMU90(MU.MU90), MU.MU50 : cnv_fromMU50.fromMU50(MU.MU50),
              MU.SYXG50 : cnv_fromSYXG50.fromSYXG50(MU.SYXG50)}


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


def main() :
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


if __name__ == '__main__' :
    main()
