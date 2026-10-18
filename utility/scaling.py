# * Element scaling of the MU128 engine (MU128 / MU1000 / MU2000), issue #53
# The MU1000 stores the filter cutoff and level key scaling of an element as 4 break points + 4 offsets
# (element +36..+43 and +58..+65, offsets with centre 64). The MU2000 (same voice data otherwise) stores
# FF 00 00 00 00 00 plus a 16-bit index into 1,377 tables of 128 signed notes (firmware 0x23CED0 in the
# dejumbled image, see TaleTN's MUTable). Table() is the formula the MU2000 tables were made with: it
# reproduces all 5,306 scalings of the MU2000 from the MU1000 break points. Inverse() goes back to break
# points for the S-YXG50 element (same format as the MU1000); it is not always the MU1000's own choice
# (break points on a straight part of the curve are free), but always gives the same 128 notes.
import math

DEFAULT_BP = (24, 48, 72, 96)

def Table(bp, of) -> list[int] :
    # segments bp[i]..bp[i+1] linear (truncated toward zero), then n >= bp3 -> of3, last n <= bp0 -> of0
    t = [0] * 128
    for i in range(3) :
        a, b = bp[i], bp[i + 1]
        if b <= a : continue
        for n in range(a, b + 1) : t[n] = of[i] + math.trunc((of[i + 1] - of[i]) * (n - a) / (b - a))
    for n in range(bp[3], 128) : t[n] = of[3]
    for n in range(0, bp[0] + 1) : t[n] = of[0]
    return t

def Table_From_Bytes(b : bytes | bytearray) -> list[int] :
    # 8 element bytes (4 break points, 4 offsets with centre 64) -> 128 notes
    return Table(list(b[0:4]), [x - 64 for x in b[4:8]])

def _segment_ok(t, a, b, tb = None) -> bool :
    tb = t[b] if tb is None else tb
    ta, d, n_ = t[a], tb - t[a], b - a
    for n in range(a + 1, min(b, 128)) :
        q = d * (n - a)
        if t[n] != ta + (q // n_ if q >= 0 else -((-q) // n_)) : return False
    return True

def Inverse(t : list[int]) -> tuple[list[int], list[int], int] :
    # 128 notes -> (break points, offsets, notes that differ); prefers break points near the defaults
    def fits(bp, of) : return Table(bp, of) == t
    of = [t[x] for x in DEFAULT_BP]
    if fits(DEFAULT_BP, of) : return list(DEFAULT_BP), of, 0
    lo = 0
    while lo < 127 and t[lo + 1] == t[0] : lo += 1
    hi = 127
    while hi > 0 and t[hi - 1] == t[127] : hi -= 1
    if hi <= lo : return list(DEFAULT_BP), [t[0]] * 4, 0
    ends = {}
    def e(x) :
        if x not in ends : ends[x] = [b for b in range(x + 1, 128) if _segment_ok(t, x, b)]
        return ends[x]
    best, score = None, 1 << 30
    def consider(bp, of = None) :
        nonlocal best, score
        of = of or [t[x] for x in bp]
        s = sum(abs(x - y) for x, y in zip(bp, DEFAULT_BP))
        if s < score and fits(bp, of) : best, score = (list(bp), list(of)), s
    for a in range(lo, -1, -1) :
        for b in e(a) :
            if b >= hi : consider((a, b, b, b))
            for c in e(b) :
                if c >= hi : consider((a, b, c, c))
                for d in e(c) :
                    if d >= hi : consider((a, b, c, d))
    if best : return best[0], best[1], 0
    # bp2 = bp3 = 127: the end value of the last segment is never played (n >= 127 -> of3)
    for a in range(lo, -1, -1) :
        for b in e(a) + [a] :
            for v in range(-64, 64) :
                if _segment_ok(t, b, 127, v) : consider((a, b, 127, 127), [t[a], t[b], v, t[127]])
    if best : return best[0], best[1], 0
    # not reachable with ascending break points (MU1000 data with crossed break points): closest fit
    # over the points where the slope changes
    pts = sorted({0, 127} | {n for n in range(1, 127) if t[n + 1] - t[n] != t[n] - t[n - 1]} | set(DEFAULT_BP))
    from itertools import combinations
    err = 1 << 30
    for bp in combinations(pts, 4) :
        of = [t[x] for x in bp]
        d = sum(x != y for x, y in zip(Table(bp, of), t))
        if d < err : best, err = (list(bp), of), d
    return best[0], best[1], err
