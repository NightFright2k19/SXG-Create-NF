# S-YXG2006LE (XGLite soft synth): sxgbnw6l.tbl (voice/element data) + sxgdat6l.tbl (encrypted wave data)
# -> Table object for makeSYXG50, elements and drum voices already in the S-YXG50 layout.
# The 2006LE table has its own layout, nothing is shared with the MU / S-YXG50 decoders.
# Field meanings and calibrations: measured on both engines (SGP2.DLL and syxg50.dll) in an emulator,
# rendering notes with single bytes changed (issue #12).

import struct
from pathlib import Path

import numpy as np

from dataenum import *
from table import *


# * wave data: SGP2.OLD 0x1004c900 / 0x10002ef0
# b ^= key ^ (i & 0xff) with key = 0x5b, inverted after every byte, then swap nibbles, then swap the two bytes
# of each 16-bit word. The DLL also xors 0x5a at load time and again in every sample fetcher (cancels out).
def Decrypt_Waves(data : bytes) -> bytes :
    w = np.frombuffer(data, np.uint8)
    i = np.arange(len(w))
    a = w ^ np.where(i & 1, 0xa4, 0x5b).astype(np.uint8) ^ (i & 0xff).astype(np.uint8)
    a = ((a >> 4) | (a << 4)).astype(np.uint8)
    if len(a) & 1 : a = np.append(a, 0).astype(np.uint8)
    a = a.reshape(-1, 2)[:, ::-1].reshape(-1)
    return a[:len(w)].tobytes()


# * bank file sxgbnw6l.tbl: header "UTG VPRM", u32 section offsets at 0x18
BLOCK_SIZES = [16, 28, 36, 84]   # element blocks B0 (LFO), B1 (pitch), B2 (amp EG / level), B3 (filter)

class Bank2006() :

    def __init__(self, data : bytes) :
        self.d = data
        h = struct.unpack_from('<7I', data, 0x18)
        self.bankmap, self.prgidx, self.vptr, self.eptr, self.t28, self.curves, self.samp = h
        # the element records follow their pointer list
        self.n_el = (struct.unpack_from('<I', data, self.eptr)[0] - self.eptr) // 4

    def element_address(self, el : int) -> int :
        return struct.unpack_from('<I', self.d, self.eptr + el * 4)[0]

    # bank map [MSB][LSB] -> bank row, row * 128 + program -> voice index (0xFFFF = none)
    def voice(self, msb : int, lsb : int, prg : int) -> int | None :
        b = self.d[self.bankmap + msb * 128 + lsb]
        if b == 0xFF : return None
        v = struct.unpack_from('<H', self.d, self.prgidx + (b * 128 + prg) * 2)[0]
        return None if v == 0xFFFF else v

    # voice: 16-byte header, then 16-byte records. A zone is [key hi, key lo, vel hi, vel lo] at record +12..+15
    # plus the NEXT record's +0..+11 (+1 pan, +8 element index); traced in SGP2.DLL. Key bytes 0/0 end the list.
    def zones(self, v : int) -> list[dict] :
        o = struct.unpack_from('<I', self.d, self.vptr + v * 4)[0] + 16
        out = []
        while True :
            z = self.d[o : o + 16]
            if z[12] == 0 and z[13] == 0 : break
            nxt = self.d[o + 16 : o + 28]
            el = struct.unpack_from('<I', nxt, 8)[0]
            if el < self.n_el :
                out.append(dict(el=el, khi=z[12], klo=z[13], vhi=z[14], vlo=z[15], pan=nxt[1]))
            o += 16
        return out

    # element: 12-byte head (+6 sample index), then the four blocks, each inline (first byte < 0x80)
    # or a 4-byte BE reference 0x80000000 | element index (followed until inline)
    def block(self, el : int, k : int) -> bytes :
        while True :
            a = self.element_address(el) + 12
            for j in range(k) :
                a += 4 if self.d[a] & 0x80 else BLOCK_SIZES[j]
            if self.d[a] & 0x80 :
                el = struct.unpack_from('>I', self.d, a)[0] & 0x7FFFFFFF
                continue
            return self.d[a : a + BLOCK_SIZES[k]]

    # sample header, 20 bytes: +0 root key, +1 signed 7-bit semitones, +2 signed 7-bit 1/128 semitones,
    # +5 & 7 format (3 = 16 bit LE), +8 loop address / 4, +0x0C samples before the loop, +0x10 loop length
    def sample(self, i : int) -> dict :
        h = self.d[self.samp + i * 20 : self.samp + i * 20 + 20]
        s7 = lambda b : (b & 0x7F) - 128 if b & 0x40 else b & 0x7F
        return dict(root=h[0] & 0x7F, pitch=s7(h[1]) + s7(h[2]) / 128, fmt=h[5] & 7,
                    loop_addr=struct.unpack_from('<I', h, 8)[0] * 4,
                    pre=struct.unpack_from('<I', h, 0x0C)[0], loop=struct.unpack_from('<I', h, 0x10)[0])

    def fields(self, el : int) -> dict :
        b0, b1, b2, b3 = [self.block(el, k) for k in range(4)]
        s7 = lambda v : (v & 0x7F) - 128 if v & 0x40 else v & 0x7F
        a = self.element_address(el)
        return dict(sample=struct.unpack_from('<H', self.d, a + 6)[0],
                    lfo_rate=b0[1], lfo_pitch=b0[4], lfo_on=b0[5] < 0x80, lfo_delay=b0[8],
                    coarse=s7(b1[0x1A]), fine=s7(b1[0x1B]),
                    atk=b2[1], d1=b2[2], d2=b2[3], rel=b2[5], delay=b2[8], d1lvl=b2[9],
                    cutoff=b3[0x2D])


# * S-YXG50 element defaults (78 bytes), everything not mapped below stays at these values
ELEMENT_DEFAULT = bytes.fromhex('2e007f017f81011f00000000004040003c014040403c3f3f3f3f40404040400600341830606c3e403f3f4540'
                                '423c3f030101406f4040406a183a48604043424300074248003f10111f6f00000042')
# S-YXG50 drum voice defaults (30 bytes), used with an ext voice (+16..)
DRUMVOICE_DEFAULT = bytes.fromhex('3c467f00407f7f7f0000017f025b4938ffff442e0800000058001000' '01fd')

clamp = lambda v, lo=0, hi=127 : max(lo, min(hi, int(round(v))))

# 2006LE element fields -> S-YXG50 element bytes
def To_SYXG50_Element(f : dict, vlo : int = 1, vhi : int = 127) -> bytearray :
    e = bytearray(ELEMENT_DEFAULT)
    e[1], e[2], e[3], e[4] = 0, 127, vlo, vhi
    if f['lfo_on'] :
        e[7] = clamp(f['lfo_rate'] / 2, 0, 63)          # LFO speed, both exponential
        e[8] = clamp(f['lfo_delay'] / 2)                 # vibrato delay
        e[10] = clamp(f['lfo_pitch'] * 0.26 / 0.84)      # pitch depth: 0.26 vs 0.84 cent/step
    else :
        e[10] = 0
    e[13] = clamp(64 + f['coarse'])                     # note shift, 1 semitone/step
    e[14] = clamp(64 + f['fine'] * 0.77)                 # detune: 0.77 vs ~1 cent/step
    e[33] = clamp(52 + (max(f['cutoff'], 16) - 32) * 0.15, 0, 64)   # cutoff, matched by spectral centroid
    e[55] = 78                                           # element level, ~0.17 dB/step
    e[68] = clamp(f['delay'] / 4, 0, 63)                 # key-on delay
    # amp EG rates: both exponential, S-YXG50 needs half the steps per octave
    e[69] = 63 if f['atk'] & 0x80 else clamp(f['atk'] / 2, 0, 63)
    e[70] = clamp(f['d1'] / 2, 0, 63)
    e[71] = clamp(f['d2'] / 2, 0, 63)
    e[72] = clamp(f['rel'] / 2, 0, 63)
    e[73] = clamp(127 - min(f['d1lvl'] * 1.5, 48) / 0.67)   # decay-1 level, ~0.67 dB/step below 127
    return e

# S-YXG50 wave entry: +1 tune note acts like a root key, +2 signed cents (raises the pitch)
def Wave_Tune(s : dict) -> tuple[int, int] :
    t = s['root'] - s['pitch']
    n = round(t)
    return n & 0xFF, round((n - t) * 100) & 0xFF

# MSB 119 (2006LE only) has no bank row in S-YXG50: its LSBs go to free XG LSBs (MSB 0)
MSB119_LSB = {0 : 48, 1 : 49, 2 : 50, 3 : 51, 4 : 52, 5 : 53, 6 : 54, 7 : 55, 8 : 56, 9 : 57, 16 : 58, 24 : 59, 32 : 60}


def Create_Table(bank_data : bytes, wave_len : int, wave_roms : list[Path]) -> Table :
    B = Bank2006(bank_data)
    samples : dict[str | int, Sample] = {}
    wavebanks : dict[str | int, WaveBank] = {}
    voices : dict[str | int, Voice] = {}
    voice_banks : dict[int | str, VoiceBank] = {}

    def get_sample(i : int) -> dict :
        s = B.sample(i)
        assert s['fmt'] == 3, f'S-YXG2006LE: sample {i} has unknown format {s["fmt"]}'
        AddToSampleList(samples, Sample(s['loop_addr'], s['pre'], s['loop'], s['loop_addr'], SampleFormat.S16,
                                        encoding_parameters=0, format=MU.SYXG50, address_book={i}))
        return s

    def make_voice(v : int) -> str | None :
        key = f'v{v}'
        if key in voices : return key
        layers : dict[tuple[int, int], list[dict]] = {}
        for z in B.zones(v) :
            layers.setdefault((z['vlo'], z['vhi']), []).append(z)
        if not layers : return None
        elements = []
        for (vlo, vhi), zs in sorted(layers.items())[:2] :    # S-YXG50: two elements at most
            zs.sort(key=lambda z : z['klo'])
            waves = []
            for z in zs :
                s = get_sample(B.fields(z['el'])['sample'])
                tn, tc = Wave_Tune(s)
                waves.append(Wave('', s['pre'], s['loop'], s['loop_addr'], attenuation=0,
                                  tune_note=tn, tune_cent=tc, key_min=z['klo'], key_max=z['khi']))
            waves[0].key_min, waves[-1].key_max = 0, 0x7F
            wbkey = 'wb_' + '_'.join(f'{w.loop_address_src}:{w.key_min}-{w.key_max}' for w in waves)
            for w in waves : w.address_src = f'{wbkey}#{w.key_min}'
            wavebanks.setdefault(wbkey, WaveBank(wbkey, waves))
            # element parameters: the zones of one layer share them, except tuning (in the wave entries)
            f = B.fields(zs[len(zs) // 2]['el'])
            elements.append(Element(wbkey, To_SYXG50_Element(f, vlo, vhi), MU.SYXG50, waveID=len(wavebanks)))
        voices[key] = Voice(key, 100, '', elements, MU.SYXG50)
        return key

    # (S-YXG50 bank, bank row index, 2006LE MSB, 2006LE LSB)
    rows = [(Bank.XG, l, 0, l) for l in range(128)] + [(Bank.SFX, 64, 64, 0)] \
         + [(Bank.XG, x, 119, l) for l, x in MSB119_LSB.items()] + [(Bank.GM2, l, 121, l) for l in range(128)]
    for bank, idx, msb, lsb in rows :
        vb = None
        for prg in range(128) :
            v = B.voice(msb, lsb, prg)
            k = make_voice(v) if v is not None else None
            if k is None : continue
            if vb is None :
                l, m = BankToLSBMSB(bank, idx)
                vb = VoiceBank(f'{bank}_{idx}', bank, l, m, voices={}, aliases=[], seqID=len(voice_banks))
            vb.voices[prg] = k
        if vb is None : continue
        # unused programs: same program of the bank's base row, as on the XG banks of the MU models
        base = voice_banks.get(f'{bank}_0')
        for prg in range(128) :
            if prg not in vb.voices :
                vb.voices[prg] = (base.voices.get(prg) if base and base is not vb else None) or next(iter(vb.voices.values()))
        voice_banks[vb.prg_address] = vb

    # * drums: each key is an ext voice (one element, fixed pitch) behind an S-YXG50 drum voice
    drumvoices : dict[str | int, DrumVoice] = {}
    drumkits : dict[int | str, DrumKit] = {}

    def drum_voice(z : dict) -> str :
        f = B.fields(z['el'])
        s = get_sample(f['sample'])
        tn, tc = Wave_Tune(s)
        wbkey = f'wb_d{s["loop_addr"]}_{tn}_{tc}'
        data = To_SYXG50_Element(f)
        data[15], data[16] = 5, 60      # pitch scaling: fixed pitch (2006LE drums don't follow the key)
        data[55] = 127                  # level, measured against the 2006LE kits
        key = f'dz{wbkey}_{bytes(data).hex()}'
        if key not in voices :
            wavebanks.setdefault(wbkey, WaveBank(wbkey, [Wave(f'{wbkey}#0', s['pre'], s['loop'], s['loop_addr'],
                                 attenuation=0, tune_note=tn, tune_cent=tc, key_min=0, key_max=0x7F)]))
            voices[key] = Voice(key, 100, '', [Element(wbkey, data, MU.SYXG50, waveID=0)], MU.SYXG50)
        return key

    for bank, msb in ((Bank.XG_DRUMS, 127), (Bank.SFX_DRUMS, 126), (Bank.GM2_DRUMS, 120)) :
        for prg in range(128) :
            v = B.voice(msb, 0, prg)
            if v is None : continue
            kit = DrumKit(f'kit{msb}_{prg}', bank, prg, {}, {}, aliases=[], seqID=len(drumkits))
            for z in B.zones(v) :
                if z['vhi'] != 127 : continue     # top velocity layer
                vk = drum_voice(z)
                dk = f'd{vk}_p{z["pan"]}'        # keymap offsets are 16 bit: share drum voices
                if dk not in drumvoices :
                    dv = bytearray(DRUMVOICE_DEFAULT)
                    dv[1], dv[4] = 0x7F, z['pan'] & 0x7F
                    drumvoices[dk] = DrumVoice(dv, 0, vk, 0, 0, format=MU.SYXG50, address_book=set())
                for key in range(z['klo'], z['khi'] + 1) :
                    kit.drumvoices[key] = dk
                kit.voices[vk] = vk
            drumkits[kit.keymap_address] = kit

    return Table('SXG2006LE', MU.SYXG50, Sample_pool=samples, Wavebank_pool=wavebanks, Voice_pool=voices,
                 DrumVoice_pool=drumvoices, drumkits=drumkits, voice_banks=voice_banks,
                 waveroms=wave_roms, waveroms_byte_len=wave_len)
