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

    # voice: 16-byte header (+2: layer count), then per layer a 12-byte layer record (+1: zone count) and per zone
    # 16 bytes: [key hi, key lo, vel hi, vel lo] + 12-byte zone record (+1 pan, +8 element index); traced in SGP2.DLL.
    # A layer is what S-YXG50 calls an element.
    def zones(self, v : int) -> list[dict] :
        o = struct.unpack_from('<I', self.d, self.vptr + v * 4)[0]
        n_layers = self.d[o + 2]
        o += 16
        out = []
        for layer in range(n_layers) :
            lr = self.d[o : o + 12]
            o += 12
            for _ in range(lr[1]) :
                z = self.d[o : o + 16]
                el = struct.unpack_from('<I', z, 12)[0]
                if el < self.n_el :
                    out.append(dict(el=el, khi=z[0], klo=z[1], vhi=z[2], vlo=z[3], pan=z[5], layer=layer, lr=bytes(lr)))
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
                    atk=b2[1], d1=b2[2], d2=b2[3], rel=b2[5], delay=b2[8], d1lvl=b2[9], d2lvl=b2[0x0A],
                    cutoff=self.cutoff(b3), feg_rate=b3[4], feg_levels=struct.unpack_from('<4h', b3, 0x0A),
                    level_keys=self.curve(struct.unpack_from('<H', b2, 0x0C)[0], LEVEL_KEYS))

    # 128-byte signed curves, indexed by key (or velocity - 1); B2 +0x0C = level key curve (0.74 dB per unit,
    # measured on SGP2.DLL), 0xFFFF = none
    def curve(self, c : int, idx : tuple) -> list[int] | None :
        if c == 0xFFFF : return None
        return [v - 256 if v >= 0x80 else v for v in (self.d[self.curves + c * 128 + i] for i in idx)]

    # filter cutoff in cents (SGP2.OLD 0x10011ae0 / 0x10011d50 / 0x10011e40), B3 = filter block:
    # +0x2E word base cutoff, clamped 9600..19200; +0x36 / +0x38 word = key / velocity curve (128-byte curve,
    # 0xFFFF = none), offset = signed table value * depth * 75 / 16 with depth +0x3E high / low nibble + 1.
    # Filter EG (0x1000dcd0.., active when a level is set): levels +0x0A, +0x0C.. (signed words, cents) and
    # rate +0x04 (0 = holds the start level, about 0.5 s to the next level at 0x20, twice as fast every 16
    # steps). The S-YXG50 element has one static cutoff here, so the EG level reached after 0.3 s is used.
    # Key 60 and velocity 100 stand for the element.
    def cutoff(self, b3 : bytes, key : int = 60, vel : int = 100) -> int :
        c = max(9600, min(19200, struct.unpack_from('<H', b3, 0x2E)[0]))
        l0, l1, l2, l3 = struct.unpack_from('<4h', b3, 0x0A)
        if l0 or l1 or l2 or l3 :
            frac = 0.0 if b3[4] == 0 else min(1.0, 0.3 / (0.5 * 2 ** ((0x20 - b3[4]) / 16)))
            c += int(l0 + (l1 - l0) * frac)
        for off, depth, idx in ((0x36, (b3[0x3E] >> 4) + 1, key), (0x38, (b3[0x3E] & 15) + 1, vel - 1)) :
            curve = struct.unpack_from('<H', b3, off)[0]
            if curve == 0xFFFF : continue
            v = self.d[self.curves + curve * 128 + idx]
            v = v - 256 if v >= 0x80 else v
            if v : c += int(v * depth * 75 / 16)
        return c


LEVEL_KEYS = (36, 60, 84, 108, 60)   # S-YXG50 level scaling breakpoints, then the reference key

# * S-YXG50 element defaults (78 bytes), everything not mapped below stays at these values
ELEMENT_DEFAULT = bytes.fromhex('2e007f017f81011f00000000004040003c014040403c3f3f3f3f40404040400600341830606c3e403f3f4540'
                                '423c3f030101406f4040406a183a48604043424300074248003f10111f6f00000042')
# S-YXG50 drum voice defaults (30 bytes), used with an ext voice (+16..)
DRUMVOICE_DEFAULT = bytes.fromhex('3c467f00407f7f7f0000017f025b4938ffff442e0800000058001000' '01fd')

clamp = lambda v, lo=0, hi=127 : max(lo, min(hi, int(round(v))))

# 2006LE element fields -> S-YXG50 element bytes
# amp EG target levels (decay 1 / decay 2), measured on a sustained voice (organ, key 60) in both engines.
# 2006LE B2+09 / B2+0A: drop in dB below the peak; from about 0x8C on the EG decays to silence.
EG06_DROP = [(0, 0.0), (8, 0.5), (16, 1.6), (24, 2.6), (32, 5.7), (40, 8.5), (48, 11.6), (56, 14.5), (64, 17.7),
             (72, 20.5), (80, 23.7), (88, 26.5), (96, 29.7), (104, 32.6), (112, 35.7), (120, 38.6), (128, 41.7), (136, 44.6)]
# S-YXG50 +73 / +74: below 64 the EG decays to silence
EG50_DROP = [(127, 0.0), (120, 0.6), (116, 2.8), (112, 6.3), (108, 8.9), (104, 12.4), (100, 14.9), (96, 18.4),
             (92, 20.9), (88, 24.4), (84, 26.9), (80, 30.4), (76, 32.9), (72, 36.4), (68, 39.0), (64, 42.4)]

def EG_Level(v : int) -> int :
    if v >= 0x8C : return 0
    drop = np.interp(v, *zip(*EG06_DROP))
    levels, drops = zip(*EG50_DROP)
    return clamp(np.interp(drop, drops, levels), 64, 127)

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
    # cutoff: fitted on 25 voices against the 2006LE render (level and spectral centroid at keys 36..96);
    # the 2006LE filter tracks the key more gently than the static S-YXG50 one, hence the flat slope
    e[33] = clamp(46 + 0.3 * (f['cutoff'] - 14400) / 100, 24, 64)
    # filter EG: element +46..+48 rates to the levels +51..+53 (sustain), +50 start level, +49 / +54 release.
    # e[33] above holds the 2006LE cutoff at 0.3 s, heard with the default levels (+51 = 0x6F), so the 2006LE
    # EG levels go in as offsets to that point: one level step is about one cutoff step (~333 cents); the
    # S-YXG50 rate needs ~8.6 steps per doubling (2006LE: 16), 0x20 = 0.5 s on both sides after the shift
    # level key scaling: breakpoints +56..+59, offsets +60..+63 (~0.8 dB per step), relative to key 60
    if f.get('level_keys') :
        c = f['level_keys']
        e[56:60] = bytes(LEVEL_KEYS[:4])
        e[60:64] = bytes([clamp(64 + (v - c[4]) * 0.74 / 0.8) for v in c[:4]])
    lv = f.get('feg_levels', (0, 0, 0, 0))
    if any(lv) :
        r = f['feg_rate']
        frac = 0.0 if r == 0 else min(1.0, 0.3 / (0.5 * 2 ** ((0x20 - r) / 16)))
        at03 = lv[0] + (lv[1] - lv[0]) * frac
        L = [clamp(0x6F + (l - at03) * 0.3 / 100) for l in lv]
        e[50:54] = bytes(L)
        e[54] = L[3]
        e[46] = e[47] = e[48] = 0 if r == 0 else clamp(28.6 + (r - 0x20) * 8.6 / 16, 1, 63)
    e[55] = 78                                           # element level, ~0.17 dB/step
    e[68] = clamp(f['delay'] / 4, 0, 63)                 # key-on delay
    # amp EG rates: both exponential, S-YXG50 needs half the steps per octave
    e[69] = 63 if f['atk'] & 0x80 else clamp(f['atk'] / 2, 0, 63)
    e[70] = clamp(f['d1'] / 2, 0, 63)
    e[71] = clamp(f['d2'] / 2, 0, 63)
    e[72] = clamp(f['rel'] / 2, 0, 63)
    e[73] = EG_Level(f['d1lvl'])                         # decay-1 / decay-2 target levels
    e[74] = EG_Level(f.get('d2lvl', 0xFF))
    return e

# 2006LE layer record (12 bytes, measured on SGP2.DLL): +2 coarse tune (7-bit signed semitones), +5 fine
# tune (7-bit signed, 1/128 semitone), +3/+4 pitch key scaling centre/amount, +6 attenuation (0.375 dB/step), +7 pan (0x40 = center)
def Apply_Layer(e : bytearray, lr : bytes, zone_pan : int = 0x40) -> None :
    s7 = lambda b : (b & 0x7F) - 128 if b & 0x40 else b & 0x7F
    e[13] = clamp(e[13] + s7(lr[2]))
    e[15] = min(lr[4] & 7, 5)                        # pitch key scaling, same codes: 0 = 100 %, 1 = 50 %, 2 = 20 %, 3 = 10 %, 4 = 5 %, 5 = fixed
    e[16] = lr[3] & 0x7F                             # its centre key
    e[14] = clamp(e[14] + s7(lr[5]) * 100 / 128 * 0.77)
    e[55] = clamp(e[55] * 10 ** (-0.375 * lr[6] / 40), 1)           # S-YXG50 level: amplitude ~ (level / 127)^2
    pan = (lr[7] - 0x40) + (zone_pan - 0x40)
    e[65] = clamp(7 + pan * 7 / 64, 0, 14)                           # S-YXG50 element pan 0..14, 7 = center

# S-YXG50 wave entry: +1 tune note acts like a root key, +2 signed cents (raises the pitch)
def Wave_Tune(s : dict) -> tuple[int, int] :
    t = s['root'] - s['pitch']
    n = round(t)
    return n & 0xFF, round((n - t) * 100) & 0xFF

# MSB 119 (2006LE only) has no bank row in S-YXG50: its LSBs go to free XG LSBs (MSB 0)
# MSB 118 (2006LE only, drum kits playable as voices, one zone per key): XG LSB 61
MSB118_LSB = 61
MSB119_LSB = {0 : 48, 1 : 49, 2 : 50, 3 : 51, 4 : 52, 5 : 53, 6 : 54, 7 : 55, 8 : 56, 9 : 57, 16 : 58, 24 : 59, 32 : 60}


# drum kits, measured against the 2006LE (every key 13..84 of every kit, velocity 100): the 2006LE plays
# XG/SFX kits on keys 13..84 and GM2 kits on 27..87 only; levels ran about 2.8 dB hot at element level 127
# SFX voices (MSB 64) ran 6.8 dB quiet (median over 39 voices x 3 keys)
SFX_TRIM = 6.8
# per-voice level trim in dB (2006LE voice index), measured: GM bank voices at keys 36/60/84, velocity 100, dry,
# level over the first 1.5 s against the 2006LE render (emulator sweep); applied to every bank that uses the voice
VOICE_TRIM = {31: 4.6, 34: -4.9, 35: 3.8, 36: 1.7, 37: -6.4, 38: -2.5, 39: 3.5, 40: 2.0, 41: -8.2, 42: -2.4, 44: 1.7, 45:
              2.1, 46: 3.5, 48: 1.9, 49: -3.5, 50: 2.0, 51: -3.4, 52: -3.5, 53: -4.9, 54: -2.0, 56: 5.4, 60:
              -3.4, 62: -4.8, 63: 2.4, 64: -4.2, 65: -7.2, 66: 2.7, 67: 3.4, 68: 3.1, 69: -8.7, 71: 5.3, 72:
              5.3, 73: 2.9, 74: 3.0, 75: 4.2, 82: 6.8, 84: 3.5, 102: -5.8, 103: -1.7, 117: 4.0, 126: -5.2,
              127: 3.5, 128: -2.8, 130: 2.6, 131: 4.1, 132: 3.8, 134: 6.4, 135: 7.4, 141: 4.9, 147: 6.1, 148:
              6.1, 149: 2.3, 150: 2.1, 151: -3.7, 152: 1.5, 159: 1.6, 160: 7.6, 167: 1.4, 171: 4.0, 180: 1.9,
              181: -4.6, 182: 5.3, 184: 6.6, 185: 5.8, 198: -1.5, 200: 1.1, 201: -1.9, 202: -1.2, 203: 2.0,
              204: 3.3, 205: 5.8, 206: 3.3, 207: 3.9, 208: 5.3, 209: 2.1, 210: 4.8, 211: 4.8, 213: -2.1, 286:
              -2.4, 296: 3.3, 317: 5.7, 321: -3.9, 326: 2.0, 327: -5.3, 332: 1.3, 333: 8.7, 335: -4.8, 336:
              2.4, 338: -3.1, 339: 2.2, 354: -1.3, 359: 2.8, 361: 2.1, 363: -9.6, 368: 1.5, 374: -1.9, 376:
              3.4, 379: 2.2, 387: 2.9, 389: 2.9, 392: 8.0, 402: -1.1, 403: -3.6, 444: -2.1}
DRUM_KEYS = {127 : (13, 84), 126 : (13, 84), 120 : (27, 87)}
DRUM_LEVEL = 108
DRUM_KIT_TRIM = {(126, 0) : -8.4, (126, 1) : -3.4, (120, 56) : -5.1}    # dB, the SFX kits ran hotter still

def Create_Table(bank_data : bytes, wave_len : int, wave_roms : list[Path]) -> Table :
    B = Bank2006(bank_data)
    samples : dict[str | int, Sample] = {}
    wavebanks : dict[str | int, WaveBank] = {}
    voices : dict[str | int, Voice] = {}
    voice_banks : dict[int | str, VoiceBank] = {}

    def get_sample(i : int) -> dict :
        s = B.sample(i)
        assert s['fmt'] == 3, f'S-YXG2006LE: sample {i} has unknown format {s["fmt"]}'
        # the S-YXG50 engine loops from the sample after the loop address: point it at the last body sample
        sm = Sample(s['loop_addr'] - 2, max(0, s['pre'] - 1), s['loop'], s['loop_addr'] - 2, SampleFormat.S16,
                    encoding_parameters=0, format=MU.SYXG50, address_book={i})
        sm.wrap_guard = True     # the data after the loop end is the next sample
        AddToSampleList(samples, sm)
        return s

    def make_voice(v : int, trim_db : float = 0.0) -> str | None :
        trim_db += VOICE_TRIM.get(v, 0.0)
        key = f'v{v}' + (f'_t{trim_db}' if trim_db else '')
        if key in voices : return key
        # a 2006LE layer is an S-YXG50 element; a layer with velocity splits needs one element per split
        layers : dict[tuple[int, int, int], list[dict]] = {}
        zones = B.zones(v)
        kitlike = len({z['layer'] for z in zones}) > 2     # MSB 118: a drum kit as a voice, one layer per key
        for z in zones :
            layers.setdefault((0 if kitlike else z['layer'], z['vlo'], z['vhi']), []).append(z)
        if not layers : return None
        # S-YXG50: two elements at most. Prefer the ones that sound at velocity 100, one per layer
        order = sorted(layers, key=lambda k : (not k[1] <= 100 <= k[2], k[0], k[1]))
        picked = []
        for k in order :
            if len(picked) < 2 and k[0] not in {p[0] for p in picked} : picked.append(k)
        for k in order :
            if len(picked) < 2 and k not in picked : picked.append(k)
        elements = []
        for k in sorted(picked) :
            layer, vlo, vhi = k
            zs = sorted(layers[k], key=lambda z : z['klo'])
            waves = []
            for z in zs :
                s = get_sample(B.fields(z['el'])['sample'])
                tn, tc = Wave_Tune(s)
                waves.append(Wave('', max(0, s['pre'] - 1), s['loop'], s['loop_addr'] - 2, attenuation=0,
                                  tune_note=tn, tune_cent=tc, key_min=z['klo'], key_max=z['khi']))
            waves[0].key_min, waves[-1].key_max = 0, 0x7F
            wbkey = 'wb_' + '_'.join(f'{w.loop_address_src}:{w.key_min}-{w.key_max}' for w in waves)
            for w in waves : w.address_src = f'{wbkey}#{w.key_min}'
            wavebanks.setdefault(wbkey, WaveBank(wbkey, waves))
            # element parameters: the zones of one layer share them (mostly), except tuning (in the wave
            # entries); take the zone around middle C
            zc = min(zs, key=lambda z : 0 if z['klo'] <= 60 <= z['khi'] else min(abs(z['klo'] - 60), abs(z['khi'] - 60)))
            e = To_SYXG50_Element(B.fields(zc['el']), vlo, vhi)
            e[55] = clamp(e[55] * 10 ** (trim_db / 40))
            Apply_Layer(e, zs[0]['lr'], zc['pan'])
            elements.append(Element(wbkey, e, MU.SYXG50, waveID=len(wavebanks)))
        voices[key] = Voice(key, 100, '', elements, MU.SYXG50)
        return key

    # silent voice: one element whose velocity range is empty (127..0), never sounds
    def silent() -> str :
        if 'silent' not in voices :
            wb = next(iter(wavebanks))
            e = To_SYXG50_Element(dict(lfo_on=False, coarse=0, fine=0, cutoff=19200, delay=0, atk=0x80, d1=0, d2=0,
                                       rel=127, d1lvl=0), 127, 0)
            voices['silent'] = Voice('silent', 100, '', [Element(wb, e, MU.SYXG50, waveID=0)], MU.SYXG50)
        return 'silent'

    # (S-YXG50 bank, bank row index, 2006LE MSB, 2006LE LSB)
    rows = [(Bank.XG, l, 0, l) for l in range(128)] + [(Bank.SFX, 64, 64, 0)] \
         + [(Bank.XG, x, 119, l) for l, x in MSB119_LSB.items()] + [(Bank.GM2, l, 121, l) for l in range(128)] \
         + [(Bank.XG, MSB118_LSB, 118, 0)]
    for bank, idx, msb, lsb in rows :
        vb = None
        for prg in range(128) :
            v = B.voice(msb, lsb, prg)
            k = make_voice(v, SFX_TRIM if bank == Bank.SFX else 0.0) if v is not None else None
            if k is None : continue
            if vb is None :
                l, m = BankToLSBMSB(bank, idx)
                vb = VoiceBank(f'{bank}_{idx}', bank, l, m, voices={}, aliases=[], seqID=len(voice_banks))
            vb.voices[prg] = k
        if vb is None : continue
        # unused programs: same program of the bank's base row, as on the XG banks of the MU models;
        # SFX (MSB 64) programs without a voice stay silent, as on the 2006LE
        base = voice_banks.get(f'{bank}_0')
        for prg in range(128) :
            if prg not in vb.voices :
                vb.voices[prg] = silent() if bank == Bank.SFX else \
                    (base.voices.get(prg) if base and base is not vb else None) or next(iter(vb.voices.values()))
        if (bank, idx) == (Bank.XG, 0) : vb.aliases.append((Bank.SFX, 0))     # MSB row: MSB 0 -> XG bank by LSB
        voice_banks[vb.prg_address] = vb

    # silent bank (SFX MSB 1, bank row 0 as on the MU models): the MSB row entry of every MSB without a bank
    # stays 0 and points to it, so in XG mode such parts are mute as on the 2006LE (VoodooChild: MSB 42).
    # [Config] BankFallback=1 in the ini gives the usual S-YXG50 behaviour, see dllpatch.SYXG50_BANKFALLBACK.
    # XG LSBs without a bank: the MSB 0 voices (XG bank row 0 is the silent bank now)
    xg0 = next(vb for vb in voice_banks.values() if vb.bank == Bank.XG and vb.lsb == 0)
    used = {vb.lsb for vb in voice_banks.values() if vb.bank == Bank.XG}
    xg0.aliases += [(Bank.XG, l) for l in range(128) if l not in used]
    # GS mode (after a GS reset the S-YXG50 reads the GS bank row): every MSB plays the capital voices, as on the
    # 2006LE. Without a GS row it would fall back to XG bank row 0, the silent bank.
    voice_banks['GS_0'] = VoiceBank('GS_0', Bank.GS, 0, 0, voices=dict(xg0.voices),
                                    aliases=[(Bank.GS, m) for m in range(1, 128)], seqID=len(voice_banks))
    sb = VoiceBank('silent', Bank.SFX, 0, 1, voices={p : silent() for p in range(128)}, aliases=[], seqID=0)
    voice_banks = {'silent' : sb, **voice_banks}

    # * drums: each key is an ext voice (one element, fixed pitch) behind an S-YXG50 drum voice
    drumvoices : dict[str | int, DrumVoice] = {}
    drumkits : dict[int | str, DrumKit] = {}

    def drum_voice(z : dict, trim_db : float = 0.0) -> str :
        f = B.fields(z['el'])
        s = get_sample(f['sample'])
        tn, tc = Wave_Tune(s)
        wbkey = f'wb_d{s["loop_addr"]}_{tn}_{tc}'
        data = To_SYXG50_Element(f)
        data[55] = clamp(DRUM_LEVEL * 10 ** (trim_db / 40))   # level, measured against the 2006LE kits
        Apply_Layer(data, z['lr'])      # per-key tuning and level (the pan goes to the drum voice)
        data[15], data[16] = 5, 60      # pitch scaling: fixed pitch (2006LE drums don't follow the key)
        # the 2006LE ends a sustaining drum sound (crash cymbals) with its note-off and release, the S-YXG50 drum
        # voice ignores note-offs: decay 2 takes the release rate down to silence instead
        if data[74] or (f['d2'] == 0 and data[73]) :
            data[71], data[74] = clamp(f['rel'] / 2, 0, 63), 0
        data[65] = 7
        key = f'dz{wbkey}_{bytes(data).hex()}'
        if key not in voices :
            wavebanks.setdefault(wbkey, WaveBank(wbkey, [Wave(f'{wbkey}#0', max(0, s['pre'] - 1), s['loop'], s['loop_addr'] - 2,
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
                lo, hi = DRUM_KEYS[msb]
                if z['khi'] < lo or z['klo'] > hi : continue
                vk = drum_voice(z, DRUM_KIT_TRIM.get((msb, prg), 0.0))
                pan = clamp(z['lr'][7] + z['pan'] - 0x40)
                dk = f'd{vk}_p{pan}'             # keymap offsets are 16 bit: share drum voices
                if dk not in drumvoices :
                    dv = bytearray(DRUMVOICE_DEFAULT)
                    dv[1], dv[4] = 0x7F, pan
                    drumvoices[dk] = DrumVoice(dv, 0, vk, 0, 0, format=MU.SYXG50, address_book=set())
                for key in range(max(lo, z['klo']), min(hi, z['khi']) + 1) :
                    kit.drumvoices[key] = dk
                kit.voices[vk] = vk
            drumkits[kit.keymap_address] = kit
            if msb == 127 :     # GS mode (after a GS reset) reads the GS kit row: same kits, as on the 2006LE
                gk = DrumKit(f'kitGS_{prg}', Bank.GS_DRUMS, prg, dict(kit.drumvoices), dict(kit.voices), aliases=[], seqID=len(drumkits))
                drumkits[gk.keymap_address] = gk

    return Table('SXG2006LE', MU.SYXG50, Sample_pool=samples, Wavebank_pool=wavebanks, Voice_pool=voices,
                 DrumVoice_pool=drumvoices, drumkits=drumkits, voice_banks=voice_banks,
                 waveroms=wave_roms, waveroms_byte_len=wave_len)
