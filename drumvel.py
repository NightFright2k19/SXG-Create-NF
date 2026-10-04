# * Drum velocity sensitivity (MU90 and later): "Velocity Pitch Sense" and "Velocity LPF Cutoff Sense"
#
# The MU drum setup has two per-key velocity parameters (MU90/MU100 drum voice +22/+23,
# MU1000 +21/+22, centre 0x40). syxg50.dll plays internal drum samples without any velocity
# modulation of pitch or filter, but its voice elements can do it:
#
#   pitch EG  (element +17 depth, +18 velocity level sense, +26..+30 levels)
#   filter EG (element +42 velocity level sense, +50..+54 levels)
#
# With all five levels of an EG set to the same value its output is a constant offset, and the
# velocity level sense scales that offset with the velocity (syxg50.dll 0x10016040 / 0x10013F80):
#   sense c > 0:  k = ((128 - v) * c * 36) >> 7,  offset = level * (1 - k / 256)
# (the filter EG looks the velocity up in a curve first). With c = +7 the offset grows from ~2 %
# at the lowest to 100 % at the highest velocity. Together with a fixed counter offset this gives
# the MU behaviour: no change at a reference velocity, lower pitch / cutoff below, higher above.
#
# Every internal drum key with one of the two parameters != 0x40 becomes an ext drum voice with
# one element that reproduces the internal drum playback of syxg50.dll (sample, pitch, cutoff,
# resonance, amp EG, level, velocity curve, pan) plus the two velocity EGs.
#
# Pitch: for ext drum voices syxg50.dll tracks the key 0x40 + drum setup coarse tune, not the
# played key. With note shift n the element plays wave slot n, so several drum samples share one
# multisample (blocks of notes, see Convert), and the coarse tune still works.
#
# Limits: the resonance loses its lowest bit. Keys with the special drum attack (EG rate byte >= 0x60) stay
# internal.

import os

# ---- MU behaviour, measured on the S-MU2000 (MU2000 firmware), see the drum velocity issue
# pitch: cents = VELPITCH_CENTS * (sense - 0x40) * (velocity - VELPITCH_REF)
VELPITCH_CENTS = 0.25
VELPITCH_REF = 100
# filter: syxg50 cutoff units = VELLPF_UNITS * (sense - 0x40) * (g(velocity) - g(VELLPF_REF))
VELLPF_UNITS = float(os.environ.get('DRUMVEL_LPF_UNITS', '0.5'))
VELLPF_REF = int(os.environ.get('DRUMVEL_LPF_REF', '100'))

SENSE = 7   # velocity level sense +7 (element value 0x47), the largest value that does not overflow

# ---- syxg50.dll tables
CUT = [1536, 1562, 1589, 1615, 1642, 1668, 1695, 1722, 1748, 1775, 1801, 1828, 1854, 1881, 1908, 1934, 1961, 1987, 2014, 2040, 2067, 2094, 2120, 2147, 2173, 2200, 2227, 2253, 2280, 2306, 2333, 2359, 2386, 2413, 2439, 2466, 2492, 2519, 2545, 2572, 2599, 2625, 2652, 2678, 2705, 2732, 2758, 2785, 2811, 2838, 2864, 2891, 2918, 2944, 2971, 2997, 3024, 3050, 3077, 3104, 3130, 3157, 3183, 3210, 3237, 3250, 3264, 3277, 3291, 3305, 3318, 3332, 3345, 3359, 3373, 3386, 3400, 3414, 3427, 3441, 3454, 3468, 3482, 3495, 3509, 3523, 3536, 3550, 3563, 3577, 3591, 3604, 3618, 3631, 3645, 3659, 3672, 3686, 3700, 3713, 3727, 3740, 3754, 3768, 3781, 3795, 3809, 3822, 3836, 3849, 3863, 3877, 3890, 3904, 3917, 3931, 3945, 3958, 3972, 3986, 3999, 4013, 4026, 4040, 4054, 4067, 4081, 4095]   # 0x100473D0
FEG_VEL = [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 4, 4, 5, 5, 6, 6, 6, 7, 8, 8, 9, 9, 10, 10, 11, 12, 12, 13, 14, 15, 15, 16, 17, 18, 19, 19, 20, 21, 22, 23, 24, 25, 27, 28, 29, 31, 32, 33, 35, 36, 37, 39, 40, 41, 43, 44, 45, 47, 48, 49, 51, 52, 53, 55, 56, 57, 59, 60, 61, 63, 64, 65, 67, 68, 69, 71, 72, 73, 75, 76, 77, 79, 80, 81, 83, 84, 85, 87, 88, 89, 91, 92, 93, 95, 96, 97, 99, 100, 101, 103, 104, 105, 107, 108, 109, 111, 112, 113, 115, 116, 117, 119, 120, 121, 123, 124, 125, 127]   # 0x10047650
PAN = [0, 10, 19, 28, 37, 46, 55, 64, 73, 82, 91, 100, 109, 118, 127]   # 0x100480A0

PEG_CENTS_PER_STEP = 75 / 16     # pitch EG depth 0
FEG_UNITS_PER_STEP = 32


def s8(b : int) -> int : return b - 256 if b > 127 else b

def peg_factor(v : int) -> float :
    return 1 - (((128 - v) * SENSE * 36) >> 7) / 256

def feg_factor(v : int) -> float :
    return 1 - (((128 - FEG_VEL[v]) * SENSE * 36) >> 7) / 256


class VelPlan :
    def __init__(self, cutoff : int) :
        self.peg_level = 0x40     # pitch EG level (all five)
        self.cents = 0            # fixed counter offset in cents
        self.feg_level = 0x40     # filter EG level (all five)
        self.cutoff = cutoff      # element cutoff byte


def plan(vel_pitch : int, vel_lpf : int, cutoff : int) -> VelPlan :
    p = VelPlan(cutoff)
    if os.environ.get('DRUMVEL_NEUTRAL') : return p
    sp = vel_pitch - 0x40
    if sp :
        slope = (peg_factor(127) - peg_factor(0)) / 127            # factor per velocity step
        x = round(VELPITCH_CENTS * sp / slope / PEG_CENTS_PER_STEP)  # level steps (x' in syxg50.dll)
        x = max(-64, min(63, x))
        if x :
            p.peg_level = 0x40 + (x - 1 if x > 0 else x)
            p.cents = round(-x * PEG_CENTS_PER_STEP * peg_factor(VELPITCH_REF))
    sl = vel_lpf - 0x40
    if sl :
        slope = (feg_factor(127) - feg_factor(64)) / 63
        y = round(VELLPF_UNITS * sl / slope / FEG_UNITS_PER_STEP)
        y = max(0, min(63, y))
        if y :
            p.feg_level = 0x40 + y
            base = CUT[cutoff] - y * FEG_UNITS_PER_STEP * feg_factor(VELLPF_REF)
            p.cutoff = min(range(128), key=lambda c : abs(CUT[c] - base))
    return p


def amp_eg(d : bytes) -> tuple[int, int, int] | None :
    # internal drum amp EG of syxg50.dll (0x100123CB, XG mode) -> element rates (0x10012210)
    x = d[13]
    if x >= 0x60 and d[14] == d[15] : x = 0x5E   # no-hold mode of an instant attack (cnv_fromMU90)
    if x >= 0x60 : return None             # special attack mode, not reproducible with an element
    R = 2 * (x >> 1) + 0x21
    attack = 0x3F if R >= 0x7F else max(1, min(0x3E, (R + 1) // 2))
    decay1 = max(1, min(0x3F, (d[14] + 1) // 2))
    decay2 = d[15] >> 1
    return attack, decay1, decay2


def make_element(wave_index : int, note : int, d : bytes, vp : VelPlan, eg : tuple[int, int, int]) -> bytes :
    e = bytearray(78)
    e[0] = wave_index
    e[1], e[2], e[3], e[4] = 0, 0x7F, 1, 0x7F
    e[7] = 0x20
    e[13] = note                         # note shift: tracked key (0x40 + coarse tune) -> wave slot
    e[14] = 0x40                         # detune
    e[15] = 0                            # pitch scaling 100 %
    e[16] = 0x40
    e[17] = 0                            # pitch EG depth
    e[18] = 0x40 + SENSE if vp.peg_level != 0x40 else 0x40
    e[19] = e[20] = 0x40
    e[21:26] = bytes([0x3C, 0x3F, 0x3F, 0x3F, 0x3F])
    e[26:31] = bytes([vp.peg_level] * 5)
    e[31] = d[12] >> 1                   # resonance (syxg50.dll doubles it for ext drum voices)
    e[32] = 0
    e[33] = vp.cutoff
    e[34:38] = bytes([0x18, 0x30, 0x48, 0x60]); e[38:42] = bytes([0x40] * 4)
    e[42] = 0x40 + SENSE if vp.feg_level != 0x40 else 0x40
    e[43] = e[44] = 0x40
    e[45:50] = bytes([0x3C, 0x3F, 0x3F, 0x3F, 0x3F])
    e[50:55] = bytes([vp.feg_level] * 5)
    e[55] = 0x7F
    e[56:60] = bytes([0x18, 0x30, 0x48, 0x60]); e[60:64] = bytes([0x40] * 4)
    e[64] = 1                            # velocity curve 1 = drum velocity curve (0x100477D8)
    e[65] = 7                            # pan: the ext drum voice keeps the drum key's pan, 7 = no offset
    e[66] = 0x40; e[67] = 0x3C; e[68] = 0
    e[69], e[70], e[71] = eg
    e[72] = 0x28                         # release: drum keys use 0x50
    e[73] = 0x7D; e[74] = 0x00           # EG levels of drum keys (0x100139A0)
    e[77] = 0x40
    return bytes(e)


def Convert(table, extvoiceIDX, waveIDX, page : int, big : bool, free_multisamples : int, write_wavedata, write_voice) -> None :
    # page 1/2: the voices go to bank B and use the second/third multisample page (big layout with paging)
    from table import Voice, Element, WaveBank, Wave
    from dataenum import MU
    if os.environ.get('DRUMVEL_OFF') : return
    jobs = []
    skipped = 0
    for dv in table.DrumVoice_pool.values() :
        if dv.ext_Voice_address : continue
        vp, vl = getattr(dv, 'vel_pitch', 0x40), getattr(dv, 'vel_lpf', 0x40)
        if vp == 0x40 and vl == 0x40 : continue
        d = bytes(dv.data)
        eg = amp_eg(d)
        if eg is None : skipped += 1; continue
        p = plan(vp, vl, d[11])
        root = d[10] if big else d[18]            # root key: big layout +0x0A, classic +0x12
        semis = 0x40 + s8(d[29]) - root          # syxg50.dll 0x10013760 (XG mode)
        total = semis * 100 + (d[1] - 0x40) + p.cents
        q = round(total / 100)
        sample = dv.get_sample(table.Sample_pool)
        lead = getattr(sample, 'lead_in', 0)
        wkey = (sample.address_src, dv.offset_negative - lead, dv.offset_positive, q, total - 100 * q)
        jobs.append((dv, d, p, eg, wkey, sample))
    if not jobs : return

    # pack the waves. The drum setup coarse tune shifts the key the element tracks (syxg50.dll
    # passes 0x40 + coarse offset as the key), so each sample gets a block of 2R+1 notes with one
    # common tune note: coarse tune up to +-R semitones then plays the same sample R semitones
    # higher/lower, like an internal drum key. R depends on the free multisample numbers.
    nwaves = len({j[4] for j in jobs})
    R = 12                           # one octave covers practically all drum setup tunings
    while R > 0 and -(-nwaves // (128 // (2 * R + 1))) > free_multisamples : R -= 1
    B = 2 * R + 1
    nblocks = 128 // B
    packs : list[dict] = []          # block -> (wkey, sample)
    where : dict = {}                # wkey -> (pack, centre note)
    for dv, d, p, eg, wkey, sample in jobs :
        if wkey in where : continue
        q = wkey[3]
        ok = [j for j in range(nblocks) if 0 <= j * B + R - q <= 127]
        assert ok, f'drum pitch out of range ({q} semitones)'
        for i, pk in enumerate(packs + [{}]) :
            free = [j for j in ok if j not in pk]
            if free :
                if i == len(packs) : packs.append(pk)
                j = min(free, key=lambda j : abs(j * B + R - q - 64))
                pk[j] = (wkey, sample); where[wkey] = (i, j * B + R); break

    wavebanks = []
    for i, pk in enumerate(packs) :
        waves, samples = [], []
        used = sorted(pk)
        for n in range(128) :
            j = min(n // B, nblocks - 1)
            src = j if j in pk else min(used, key=lambda u : abs(u - j))
            (s_addr, neg, pos, q, r), sample = pk[src]
            tune = src * B + R - q
            assert 0 <= tune <= 127
            waves.append(Wave(f'drumvel{i}_{n}', neg, pos, s_addr, attenuation=0,
                              tune_note=tune, tune_cent=r & 0xFF, key_min=n, key_max=n if n < 127 else 0x7F))
            samples.append(sample)
        wb = WaveBank(f'drumvel{i}', waves)
        try :
            idx = next(waveIDX)
        except StopIteration :
            idx = 999
        if idx >= 256 * (page + 1) :
            print('drum velocity: no free multisample number left, drum velocity sensitivity not converted')
            for w in wavebanks : del table.Wavebank_pool[w.address_src]
            return
        setattr(wb, ('index', 'index1', 'index2')[page], idx)
        wb.out_data = write_wavedata(wb, samples)
        table.Wavebank_pool[wb.address_src] = wb
        wavebanks.append(wb)

    voices : dict[bytes, Voice] = {}
    for dv, d, p, eg, wkey, sample in jobs :
        pi, n = where[wkey]
        wb = wavebanks[pi]
        edata = make_element(getattr(wb, ('index', 'index1', 'index2')[page]) - 256 * page, n, d, p, eg)
        voice = voices.get(edata)
        if voice is None :
            voice = Voice(f'drumvel_v{len(voices)}', 0x7F, 'DrumVel', [Element(wb.address_src, edata, MU.SYXG50, waveID=-1)], MU.SYXG50)
            voice.converted = True
            voice.page = page
            voice.data = write_voice(voice)
            voice.extvoice_index = next(extvoiceIDX)
            table.Voice_pool[voice.address_src] = voice
            voices[edata] = voice
        dv.ext_Voice_address = voice.address_src
        dv.extvoice_index = voice.extvoice_index
        out = bytearray(d)
        out[16:18] = voice.extvoice_index.to_bytes(2, 'little' if big else 'big')
        out[18:30] = bytes(12)
        dv.data = bytes(out)

    print(f'drum velocity: {len(jobs)} drum keys -> {len(voices)} ext drum voices, '
          f'{len(where)} waves in {len(packs)} multisamples (coarse tune range +-{R})' + (f', {skipped} kept internal (special attack)' if skipped else ''))
