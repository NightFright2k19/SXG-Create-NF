# * Voices with 3 or 4 elements (MU128 engine: MU128 / MU1000 / MU2000)
#
# syxg50.dll plays at most 2 elements per voice (0x10016FA0: element count = 1 + bit 1 of the mask;
# the part keeps two element pointers, +0xE8/+0xEC), so the converter has to fit the rest into two.
# Taking the first two (the old behaviour) leaves whole key ranges silent in key-split voices (Sweet Tp:
# keys 85-127, 5partStr: 0-35, Tim'sSet: 0-59) and drops whole layers (Str+Brss: the brass).
#
# Here the elements are grouped and folded into at most two:
#   * stereo pairs (same key/velocity range, pans mirrored around the centre, e.g. 0/14) count as one
#     sound: one of them is kept, centred, same level (syxg50.dll pans with 0 dB per side at the centre:
#     hard left = -6.02 dB on the mono sum, centre = 0 dB, so a centred element equals the L/R pair); octave layers panned apart
#     (different coarse tune) are not pairs
#   * key splits: elements with disjoint key ranges and the same velocity range share one element; its
#     multisample takes each member's waves in that member's key range (coarse tune folded into the
#     wave's root note), the other parameters come from the loudest member
#   * remaining layers: the loudest ones are kept; key ranges that would fall silent are filled by
#     clipping a dropped element to the gap and folding it in
#   * layers that are still left over are dropped, their power is added to the level of the kept element
#     sounding in the same range (power ~ level^4 in syxg50.dll, see merge_wavebanks)
#   * velocity splits: the kept elements' velocity ranges are widened to close the gaps

def _rng(e, a) : return (e[a], e[a + 1])
def keys(e) : return _rng(e, 2)
def vels(e) : return _rng(e, 4)
def pan(e) : return e[67]
def level(e) : return e[57]

def overlap(a, b) : return not (a[1] < b[0] or b[1] < a[0])

# keys where an element is really heard: inside its key limits and its level KS stays within
# AUDIBLE_DROP of the element's own peak (0.6 = -8.9 dB). Key-split voices crossfade with level KS
# (5partStr: the low element fades out at 34-41, the high one fades in at 48-64), so the key limits
# alone overstate the coverage.
AUDIBLE_DROP = 0.6

def audible_keys(e) :
    lv = {x : effective_level(e, x) for x in range(e[2], e[3] + 1)}
    if not lv : return keys(e)
    top = max(lv.values())
    k = [x for x, v in lv.items() if v > 0 and v >= AUDIBLE_DROP * top]
    return (k[0], k[-1]) if k else keys(e)

class Unit :
    def __init__(self, idx, els, loudness = None) :
        self.idx = idx                    # source element indices (a stereo pair has two)
        e = els[idx[0]]
        self.keys = audible_keys(e); self.vels = vels(e)
        # rank: the sound's power (level and sample loudness, element HPF included) when known, else the level
        self.level = sum(loudness[i] for i in idx) if loudness else level(e)
        self.pair = len(idx) > 1

class Out :
    def __init__(self) :
        self.members = []                 # [(element index, key range used)]
        self.vels = None
        self.centre = False
        self.pair_mate = None             # the other side of a stereo pair (centred, its power folded in)
        self.absorbed = []                # dropped layers whose power is added to this element's level
    def key_ranges(self) : return [r for _, r in self.members]
    def fits(self, r, v) :
        return self.vels == v and not any(overlap(r, q) for q in self.key_ranges())

def plan(els : list, loudness : dict | None = None) -> list :
    # loudness: {element index: power} (see element_loudness), ranks the elements; without it the level does
    # (TurnTabl: the loudest-level element has HPF 112 and is nearly silent, ranking by level kept it
    # and dropped half of the audible ones, -7 dB against the S-MU2000)
    els = [bytes(e) for e in els]
    live = [i for i, e in enumerate(els) if level(e) > 0 and e[2] <= e[3] and e[4] <= e[5]]
    # stereo pairs
    units, used = [], set()
    for i in live :
        if i in used : continue
        mate = None
        for j in live :
            if j > i and j not in used and keys(els[j]) == keys(els[i]) and vels(els[j]) == vels(els[i]) \
               and els[i][15] == els[j][15] \
               and pan(els[i]) != 7 and pan(els[i]) + pan(els[j]) == 14 :
                mate = j; break
        used.add(i)
        if mate is not None : used.add(mate); units.append(Unit([i, mate], els, loudness))
        else : units.append(Unit([i], els, loudness))
    if len(els) <= 2 or len(units) == 0 :
        return None                       # nothing to do
    order = sorted(units, key=lambda u : (-u.level, u.idx[0]))
    outs : list[Out] = []
    dropped = []
    for u in order :
        o = next((o for o in outs if o.fits(u.keys, u.vels)), None)
        if o is None and len(outs) < 2 :
            o = Out(); o.vels = u.vels; outs.append(o)
        if o is None : dropped.append(u); continue
        o.members.append((u.idx[0], u.keys))
        if u.pair : o.centre = True; o.pair_mate = u.idx[1]
    # dropped layers: fill the keys where a kept element has nothing (same velocity range; any element
    # when no kept element sounds there at all), clipped to those keys; otherwise their power goes to
    # the level of the kept element sounding in their range
    def covered_in(o, k) : return any(r[0] <= k <= r[1] for r in o.key_ranges())
    def covered(k) : return any(covered_in(o, k) for o in outs)
    top = max((u.level for u in units), default=0)
    for u in dropped :
        if loudness and u.level < SILENT * top : continue      # not heard anyway: dropped, nothing to fill
        assign = {}
        for k in range(u.keys[0], u.keys[1] + 1) :
            o = next((o for o in outs if o.vels == u.vels and not covered_in(o, k)), None)
            if o is None and not covered(k) : 
                o = min(outs, key=lambda o : (len(o.members), o.vels != u.vels))
            if o is not None : assign.setdefault(id(o), (o, []))[1].append(k)
        if not assign : 
            o = max(outs, key=lambda o : (sum(overlap(u.keys, r) for r in o.key_ranges()), o.vels == u.vels))
            o.absorbed += u.idx
            continue
        for o, ks in assign.values() :
            seg0 = ks[0]
            for a, b in zip(ks, ks[1:] + [None]) :
                if b != a + 1 : 
                    o.members.append((u.idx[0], (seg0, a)))
                    if b is not None : seg0 = b
    # velocity gaps: widen the kept ranges
    if len(outs) == 2 and outs[0].vels != outs[1].vels :
        a, b = sorted(outs, key=lambda o : o.vels[0])
        if a.vels[1] + 1 < b.vels[0] :
            mid = (a.vels[1] + b.vels[0]) // 2
            a.vels = (a.vels[0], mid); b.vels = (mid + 1, b.vels[1])
        a.vels = (min(a.vels[0], 1), a.vels[1]); b.vels = (b.vels[0], max(b.vels[1], 127))
    elif len(outs) == 1 :
        pass
    # members back to their key limits where the neighbours leave room (the audible range only decides
    # coverage; the faded-out ends keep sounding as in the original, through the baked level KS)
    for o in outs : 
        o.members.sort(key=lambda m : m[1][0])
        ms = o.members
        for n, (i, (a, b)) in enumerate(ms) :
            lo = max(els[i][2], ms[n - 1][1][1] + 1) if n else els[i][2]
            hi = min(els[i][3], ms[n + 1][1][0] - 1) if n + 1 < len(ms) else els[i][3]
            ms[n] = (i, (min(a, lo), max(b, hi)))
    return outs

def describe(els, outs) :
    s = []
    for o in outs :
        s.append(' + '.join(f'el{i}[{r[0]}-{r[1]}]' for i, r in o.members) + f' vel {o.vels[0]}-{o.vels[1]}'
                 + (' centred' if o.centre else '') + ''.join(f' +el{i} level' for i in o.absorbed))
    return ' | '.join(s)


# * one multisample out of several elements' multisamples, each used in its own key range
#   members: [(wavebank, key range, element data)], primary: element data the merged element keeps
#   - coarse tune difference -> wave root note (pitch ratio = 2^((key - root + coarse) / 12))
#   - level and level key scaling -> wave attenuation. The merged element gets the highest effective
#     level of all members and flat level KS, every member's waves are attenuated down to its own
#     level curve (split into key pieces where the curve moves by more than ATTEN_PIECE_DB).
#     Measured in syxg50.dll: wave attenuation 0.75 dB per step (8 = -6.02 dB), element level
#     40*log10(level/128) (64 = -12.04 dB), level KS offset about 2.25 level steps per unit
#     (grid level 32..127 x offset -16..+40: level 100 / offset -16 = level 64 / offset 0 = -12.0 dB;
#     effective level is not capped at 127, the top is about 145), linear between the breakpoints.
#   Filter, EG and the other element parameters come from the primary member (not compensated).
ATTEN_DB = 0.75
KS_LEVEL_STEPS = 2.25
ATTEN_PIECE_DB = 1.5

def level_ks(e, key : int) -> float :
    bp, off = list(e[58:62]), [x - 64 for x in e[62:66]]
    if key <= bp[0] : return off[0]
    for i in range(3) :
        if key <= bp[i + 1] :
            span = bp[i + 1] - bp[i]
            return off[i] if span <= 0 else off[i] + (off[i + 1] - off[i]) * (key - bp[i]) / span
    return off[3]

def effective_level(e, key : int) -> float :
    return max(0.0, min(145.0, e[57] + KS_LEVEL_STEPS * level_ks(e, key)))

def gain_db(level : float) -> float :
    import math
    return -200.0 if level <= 0 else 40 * math.log10(level / 128)

# * the merged element keeps one member's parameters (filter, EGs, LFO, ...): the member covering most
#   of the central keys (36-96), so the most played range sounds as the original; ties: the louder one.
#   (Tim'sSet: picking the louder low-key element gave the upper keys the wrong amp EG, +10 dB.)
CENTRAL_KEYS = (36, 96)
SILENT = 0.01           # loudness below 1 % (-20 dB) of the voice's loudest element: practically not heard

def primary_member(o, els, loudness : dict | None = None) -> int :
    # weighted by the member's loudness (amplitude): the louder sound keeps its EG and filter
    # (TurnTabl: a nearly silent layer covering one key more took over, -10 dB; Tim'sSet: the loud
    # low elements sound right only with their own amp EG, the quiet rhythmic high ones lose less)
    def central(r) : return max(0, min(r[1], CENTRAL_KEYS[1]) - max(r[0], CENTRAL_KEYS[0]) + 1)
    def weight(i) : return loudness[i] ** 0.25 if loudness else 1.0
    return max(o.members, key=lambda m : (central(m[1]) * weight(m[0]), els[m[0]][57], -m[0]))[0]

# * amp EG baked into the samples (key splits whose members have different amp EGs; Tim'sSet and TurnTabl:
#   the percussive high elements got the sustained EG of the loud low ones, +9..+27 dB). Only where one of
#   the two EGs goes silent (one-shot copies): baking sustained differences (EG_BAKE_SUSTAINED) made
#   5partStr (-4.5 dB) and Sweet Tp (up to -16 dB on single keys) worse than the kept EG alone and added
#   15 MB of sample copies. A member whose own EG
#   differs from the kept one by more than EG_BAKE_DB gets sample copies with the difference
#   (own - kept, in dB over time) multiplied in, played as one-shots that end where its own EG goes
#   silent. Time in the sample runs with the playback ratio, so the copies are made per EG_BAKE_SPAN keys.
#   DLL amp EG, measured on the emulator (MU element bytes: +71 attack, +72 decay 1 rate, +73 decay 2
#   rate, +75 decay 1 level, +76 decay 2 level; S-YXG50 element -2):
#     rate r: 16.2 * 2^((r - 20) / 4) dB/s (6: 1.5, 12: 4.1, 20: 16.2, 30: ~97 dB/s), 0 = hold
#     level L: -0.735 dB * (127 - L) (112: -10.3, 96: -22.3, 64: -46.4 dB); below about -49 dB silent
EG_BAKE = True
EG_BAKE_SUSTAINED = False
EG_BAKE_DB = 3.0
EG_BAKE_SPAN = 6
EG_BAKE_SUSTAIN_T = 1.5          # s, longest baked part in front of a kept loop
EG_BAKE_MAX_DB = 12.0             # boost limit where the kept EG is lower (the copy is scaled down if it would clip)
EG_SILENT_DB = -49.0
EG_STEP = 0.005                     # s, envelope table resolution
EG_MAX_T = 6.0                      # s, longest baked envelope

def eg_slope(rate : int) -> float :
    return 0.0 if rate == 0 else 16.2 * 2 ** ((rate - 20) / 4)

def eg_level_db(level : int) -> float :
    return -0.735 * (127 - level)

def eg_curve(e, t_max : float = EG_MAX_T) -> list :
    # dB over time (EG_STEP grid) of an element's amp EG while the key is held; None = silent
    ar, d1r, d2r, d1l, d2l = e[71], e[72], e[73], e[75], e[76]
    out, lvl, stage = [], (0.0 if ar >= 60 else EG_SILENT_DB), (1 if ar >= 60 else 0)
    l1, l2 = eg_level_db(d1l), eg_level_db(d2l)
    for i in range(int(t_max / EG_STEP) + 1) :
        out.append(lvl if lvl > EG_SILENT_DB else None)
        if stage == 0 :
            lvl += eg_slope(ar) * EG_STEP
            if lvl >= 0 : lvl, stage = 0.0, 1
        elif stage == 1 :
            sl = eg_slope(d1r) * EG_STEP
            lvl = max(l1, lvl - sl) if l1 < lvl else min(l1, lvl + sl)
            if lvl == l1 or sl == 0 : stage = 2
        else :
            sl = eg_slope(d2r) * EG_STEP
            lvl = max(l2, lvl - sl) if l2 < lvl else min(l2, lvl + sl)
    return out

def eg_bake_curve(own, kept) :
    """(gain dB per EG_STEP, loop gain dB or None) to multiply into the member's sample, or None if the
       EGs agree within EG_BAKE_DB. One-shot (loop gain None) when either EG goes silent: it ends there.
       When both sustain, only the part until both EGs are steady is baked and the loop keeps playing
       with the final gain (at most EG_BAKE_SUSTAIN_T, then the gain at that point)."""
    a, b = eg_curve(own), eg_curve(kept)
    def ends(c) :           # first step after the attack where the EG is silent
        on = False
        for i, v in enumerate(c) :
            if v is not None : on = True
            elif on : return i
        return len(c)
    lo = EG_SILENT_DB - 20
    gain = lambda x, y : min(EG_BAKE_MAX_DB, (x if x is not None else lo) - (y if y is not None else EG_SILENT_DB))
    end = min(ends(a), ends(b))
    if end < len(a) :
        return [gain(x, y) for x, y in zip(a[:max(1, end)], b[:max(1, end)])], None
    if not EG_BAKE_SUSTAINED : return None
    steady = max((i for i in range(1, len(a)) if a[i] != a[i - 1] or b[i] != b[i - 1]), default=0) + 1
    steady = min(steady, int(EG_BAKE_SUSTAIN_T / EG_STEP))
    g = [gain(x, y) for x, y in zip(a[:steady + 1], b[:steady + 1])]
    if max(abs(v) for v in g) <= EG_BAKE_DB : return None
    return g, g[-1]

PITCH_SCALE = {0 : 1.0, 1 : 0.5, 2 : 0.25, 3 : 0.125}

def pitch_key(e, key : float) -> float :
    # the key the DLL picks the wave (and the pitch) by: center + floor((key - center) * scale) + coarse
    import math
    c = e[18]
    return c + math.floor((key - c) * PITCH_SCALE.get(e[17] & 7, 0.0)) + (e[15] - 0x40)

def pitch_exact(e, key : float) -> float :
    # pitch in semitones (relative to the wave root): not rounded
    c = e[18]
    return c + (key - c) * PITCH_SCALE.get(e[17] & 7, 0.0) + (e[15] - 0x40)

# * wave start offset (MU element +77 = S-YXG50 +75): playback starts this many x 128 samples into the
#   wave (measured on the emulator, 8- and 16-bit alike; +78 / S-YXG50 +76 has no effect in syxg50.dll).
#   It is an element parameter, so merged members with different offsets would all get the primary's
#   (Tim'sSet: the percussive el0 started 2,560 samples late and lost its attack). Instead the merged
#   element gets offset 0 and each member's offset moves the start of its own waves (offset_negative of
#   the wave rows; the sample data stays as it is).
START_OFFSET_UNIT = 128

def start_offset_wavebank(wavebank, units : int) :
    import copy
    if not units : return wavebank
    waves = []
    for w in wavebank.waves :
        nw = copy.copy(w)
        nw.offset_negative = max(0, w.offset_negative - units * START_OFFSET_UNIT)
        waves.append(nw)
    return type(wavebank)(f'{wavebank.address_src}_so{units}', waves)

def merge_wavebanks(members : list, primary, address : str, samples : dict | None = None, new_samples : dict | None = None) :
    import copy
    from table import WaveBank
    top = max(effective_level(e, k) for _, (k0, k1), e in members for k in range(k0, k1 + 1))
    # syxg50.dll picks the wave by the pitch-scaled key plus the coarse tune:
    #   center + (key - center) * scale + coarse, scale by element +17 (S-YXG50 +15): 0 = 100 %, 1 = 50 %,
    #   2 = 25 %, 3 = 12.5 %, 4 and up = 0 (center: +18), measured with per-wave attenuations on the emulator
    # (Tim'sSet: coarse -12 made keys 60-71 play the low element's wave; with 25 % scaling and coarse -31
    # every key played the first wave). The merged waves are placed by the kept element's mapping, each
    # member's waves chosen by its own; the root note is corrected per piece for the pitch difference.
    # Pitch scaling below 100 % in the kept element made the placement unreliable (the measured mapping
    # did not follow the model at 25 %), so a merged element always plays at 100 % (element +17 = 0, set
    # by the caller): wave = key + coarse exactly; the members' own pitch scaling goes into the root
    # note, per key where a member scales below 100 %.
    co_p = primary[15] - 0x40
    sel_p = lambda k : k + co_p
    pit_p = lambda k : k + co_p
    waves = []
    for wb, (k0, k1), e in sorted(members, key=lambda m : m[1][0]) :
        sel_m = lambda k, e=e : pitch_key(e, k)
        bake = eg_bake_curve(e, primary) if EG_BAKE and samples is not None and e is not primary else None
        if bake is not None and any(getattr(samples.get(w.loop_address_src), 'reverse', False) for w in wb.waves) : bake = None
        if bake is not None and bake[1] is not None and any(w.offset_positive == 0 for w in wb.waves) : bake = (bake[0], None)
        def wave_of(k) :
            x = sel_m(k)
            return next((n for n, w in enumerate(wb.waves) if x <= w.key_max), len(wb.waves) - 1)
        att = {k : gain_db(top) - gain_db(effective_level(e, k)) for k in range(k0, k1 + 1)}
        # pieces: same member wave, attenuation within ATTEN_PIECE_DB, baked EG: at most EG_BAKE_SPAN keys
        pieces, p0 = [], k0
        span = EG_BAKE_SPAN if bake is not None else 999
        if PITCH_SCALE.get(e[17] & 7, 0.0) != 1.0 : span = 1                 # root note per key
        for k in range(k0 + 1, k1 + 2) :
            if k > k1 or wave_of(k) != wave_of(p0) or k - p0 >= span \
               or max(att[j] for j in range(p0, k + 1)) - min(att[j] for j in range(p0, k + 1)) > ATTEN_PIECE_DB :
                pieces.append((p0, k - 1)); p0 = k
        for q0, q1 in pieces :
            w = wb.waves[wave_of(q0)]
            r1 = max(0, min(0x7F, sel_p(q1)))            # in the merged element's mapping
            if waves and r1 <= waves[-1].key_max : continue    # keys that map onto the previous piece
            kr = (q0 + q1) / 2
            nw = copy.copy(w)
            nw.key_min, nw.key_max = max(0, min(0x7F, sel_p(q0))), r1
            nw.tune_note = round(w.tune_note + pit_p(kr) - pitch_exact(e, kr))
            assert 0 <= nw.tune_note <= 0xFF, (address, nw.tune_note)
            mean = sum(att[k] for k in range(q0, q1 + 1)) / (q1 - q0 + 1)
            nw.attenuation = min(0x7F, w.attenuation + max(0, round(mean / ATTEN_DB)))
            if bake is not None :
                ratio = 2 ** ((pitch_exact(e, kr) - w.tune_note) / 12)   # member's own playback ratio
                es = Env_Sample(samples[w.loop_address_src], w, bake[0], bake[1], ratio)
                new_samples[es.address_src] = es
                nw.loop_address_src = es.address_src
                nw.offset_negative, nw.offset_positive = es.offset_negative, es.offset_positive
            waves.append(nw)
    assert waves
    # contiguous, full range (key low is implied from the previous wave's key high on write)
    waves[0].key_min = 0
    for p, n in zip(waves, waves[1:]) : n.key_min = p.key_max + 1
    waves[-1].key_max = 0x7F
    return WaveBank(address, waves), round(top)

def flatten_level(edata : bytearray, level : int, keep_ks : bool = False) -> None :
    """merged element: level = the highest member level, flat level KS (baked into the waves)
       keep_ks: the element's own KS curve stays, shifted by the level above 127"""
    edata[57] = max(1, min(127, level))
    extra = round(max(0, level - 127) / KS_LEVEL_STEPS)       # above 127: positive KS (DLL goes to ~145)
    if keep_ks : 
        edata[62:66] = bytes([min(127, x + extra) for x in edata[62:66]])
    else : 
        edata[62:66] = bytes([64 + extra] * 4)

def absorb_level(level : float, extra_levels : list) -> float :
    """level that gives the power of all these layers together (gain = 40*log10(level/128))"""
    return (level ** 4 + sum(x ** 4 for x in extra_levels)) ** 0.25

# * multisample loudness (mean power of the waves sounding in the central keys, wave attenuation
#   included), from the source wave ROM. Used to weigh stereo pairs and dropped layers.
def wavebank_power(wavebank, samples : dict, waverom, keys = (48, 84)) -> float | None :
    import copy, array, sys
    from SampleConvert import ConvertSample
    from dataenum import MU, SampleFormat, get_SampleFormat_Target
    if waverom is None : return None
    p, n = 0.0, 0
    for w in wavebank.waves :
        if w.key_max < keys[0] or w.key_min > keys[1] : continue
        s = copy.deepcopy(samples[w.loop_address_src])
        s.lead_in = 0; s.adpcm_loop_len = 0
        s.out_sample_type = get_SampleFormat_Target(s.sample_type, MU.MU90, MU.SYXG50)
        try : 
            data = ConvertSample(s, waverom, MU.MU90, MU.SYXG50)
        except Exception : 
            return None
        if s.out_sample_type == SampleFormat.U16 : 
            a = array.array('H', data[:len(data) // 2 * 2])
            if sys.byteorder != 'little' : a.byteswap()
            x = [v - 32768 for v in a]
        else : 
            x = [(v - 128) * 256 for v in data]
        if not x : continue
        n_keys = min(w.key_max, keys[1]) - max(w.key_min, keys[0]) + 1
        p += n_keys * (sum(v * v for v in x) / len(x)) * 10 ** (-w.attenuation * ATTEN_DB / 10)
        n += n_keys
    return p / n if n else None

# syxg50.dll element pan (0..14): the far side's gain in dB, the near side stays at 0 dB
# (measured on the emulator, pans 0..7; 8..14 mirrored)
_PAN_FAR_DB = (None, None, -16.61, -10.59, -9.35, -6.02, -3.33, 0.0)

def pan_power(pan : int) -> float :
    """mean power over both channels of an element at this pan, centre = 1, hard = 0.5"""
    far = _PAN_FAR_DB[min(pan, 14 - pan)] if 0 <= pan <= 14 else 0.0
    return (1 + (0.0 if far is None else 10 ** (far / 10))) / 2

def element_power(e, wave_power : float) -> float :
    return (e[57] / 128) ** 4 * wave_power * pan_power(e[67])

def matched_level(kept_power : float, target_power : float, level : int) -> float :
    """level for the kept (centred) element so that it carries the power of all the source elements"""
    return level * (target_power / kept_power) ** 0.25

# amp EG key-on delay (MU element +70, 0..15), measured in syxg50.dll: 2 = 10 ms, 4 = 69 ms, 8 = 309 ms,
# 15 = 3.5 s (about x1.43 per step). An element that starts after the note is usually over counts less.
def key_on_delay_ms(e) -> float :
    d = e[70] & 0x0F
    return 0.0 if d < 2 else 69 * 1.43 ** (d - 4)

def element_loudness(e, wave_power : float | None) -> float | None :
    """power of an element's sound (level, multisample loudness incl. element HPF, key-on delay), for ranking
       (TurnTabl: the element with the highest level has delay 15 = 3.5 s and HPF 112, it is never heard)"""
    if wave_power is None : return None
    audible = max(0.02, 1 - key_on_delay_ms(e) / 1000)
    return (e[57] / 128) ** 4 * wave_power * audible


ENV_KEY_SHIFT = 56
_env_ids : dict = {}
ENV_LOOP = 16                       # samples of silence the baked one-shot loops on
ENV_FS = 44100

def Env_Sample(sample, wave, gain_db : list, loop_db, ratio : float) :
    """copy of a sample with the gain curve (dB per EG_STEP of real time) multiplied in: a one-shot that
       ends in ENV_LOOP samples of silence (loop_db None), or the wave's own loop run on until the curve
       ends and then kept, scaled by loop_db"""
    import copy, math
    key = (sample.address_src, wave.offset_negative, wave.offset_positive, tuple(round(g, 1) for g in gain_db),
           None if loop_db is None else round(loop_db, 1), round(ratio, 3))
    if key not in _env_ids : _env_ids[key] = len(_env_ids) + 1
    s = copy.copy(sample)
    s.address_book = set(sample.address_book); s.names = set(sample.names)
    s.env_bake = (tuple(gain_db), loop_db, ratio)
    s.src_neg, s.src_pos = wave.offset_negative, wave.offset_positive
    n = math.ceil(len(gain_db) * EG_STEP * ratio * ENV_FS)
    if loop_db is None :
        if wave.offset_positive == 0 : n = min(n, wave.offset_negative)     # one-shot: it ends by itself
        s.offset_negative, s.offset_positive = max(1, min(n, 1 << 21)), ENV_LOOP
    else :                          # body + whole loop passes covering the curve, then the loop
        k = max(0, math.ceil((n - wave.offset_negative) / wave.offset_positive))
        s.offset_negative, s.offset_positive = wave.offset_negative + k * wave.offset_positive, wave.offset_positive
    s.address_src = sample.address_src + (_env_ids[key] << ENV_KEY_SHIFT)
    return s
