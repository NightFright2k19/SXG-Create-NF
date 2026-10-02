# list_long_loops.py - lists MU80 voices whose sample loops exceed 65535 samples
# (the old S-YXG50 16-bit limit). Place next to main.py in the SXG-Create folder.
# Usage: python list_long_loops.py yamaha_mu80.bin xq012b0-822.bin xq013b0-823.bin xq089b0-824.bin xq090b0-825.bin

from sys import argv
from pathlib import Path

from dataCRCs import ROMLIST
from dataenum import MU
from utils import calccrc32, Dejumble
import decode
import decMU80

LIMIT = 0xFFFF


def main():
    files = [Path(a) for a in argv[1:]]
    crcs = {calccrc32(f): f for f in files}

    ref = next((r for r in ROMLIST if r.source == MU.MU80 and r.Is_List_Ours(crcs)), None)
    if ref is None:
        print('MU80 ROM set (v1.04) not found - pass all 5 ROM files.')
        return
    prg, waves = ref.Order_Pathlists(crcs)

    dec = decMU80.MU80.From_Bytes(Dejumble(open(prg[0], 'rb').read()))
    table = decode.Create_Table(dec, MU.MU80, dec.data, waves)

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


if __name__ == '__main__':
    main()
