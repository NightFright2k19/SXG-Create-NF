# * Level trim per melodic voice (MU1000 voice data), measured on the S-MU2000 (issue #6).
#
# The voice sweep (issue #3: 1,119 voices x C2/C4/C6, velocity 100, sustain energy) left 44 voices
# more than 3 dB off on at least one note. Their wave tables are converted 1:1 (attenuation, key
# ranges) and the deviation stays the same over velocity, so it comes from the way syxg50.dll mixes
# the elements (detuned and stacked copies of one wave add up differently) and cannot be derived
# from the voice data. Like drumtrim.py, each voice gets its measured offset instead: the median
# deviation, S-YXG minus S-MU2000, over C2/C4/C6 (over C2/C4/C6 x velocity 32/64/100/127 for the
# 44 outliers), then calibrated against a second measurement with the trims applied (the level
# curve is not exact). Only voices with |median| >= 1 dB are listed.
#
# Voices that are too quiet get higher element levels, up to 127. syxg50.dll caps the output of
# some voices, above a voice-dependent level a louder byte plays no louder (AfrcnWnd: 110 -> 127 =
# 0 dB). What the levels cannot add (at 127) goes into louder copies of the voice's samples
# (elemreduce.gain_wavebank); a copy that would clip is scaled back to full scale, so samples that
# are already normalized gain nothing. Left out for that reason: 5partStr (-7 dB), AfrcnWnd, Starship,
# WindChim (-1.4..-2.4 dB), where neither level nor sample gain changed the output.
#
# key: Voice_Key of the source voice (CRC32 of the 14 header bytes + 84 bytes per element, each element
# scaling written out as its 128 notes, so MU1000 and MU2000 voice data give the same key, issue #53),
# value: trim in 0.1 dB.
#
# syxg50.dll plays the element level on a 40 log10 curve (measured: level 90 -> 64 = -5.9 dB,
# 90 -> 127 = +6.2 dB), so all element levels are scaled by 10 ** (-trim / 40), capped at 127.

import math, zlib
import scaling

def Voice_Key(raw : bytes | bytearray) -> int :
    out = bytearray(raw[:14])
    for k in range((len(raw) - 14) // 84) :
        e = raw[14 + 84 * k : 98 + 84 * k]
        notes = lambda b : bytes(x & 0xFF for x in scaling.Table_From_Bytes(b))
        out += e[:36] + notes(e[36:44]) + e[44:58] + notes(e[58:66]) + e[66:]
    return zlib.crc32(out)

TRIM_DB10 = {
    0xb9293da6 :  -22,   # AnaBrss2
    0xdf4b84ed :  -20,   # Bacteria
    0xbf9fd8df :  -11,   # Bombay S
    0xa55c46e6 :  -11,   # BrssStab
    0x136877b0 :  -13,   # BrthTnSx
    0x299e4e0e :  -11,   # Burst
    0x0c41c065 :  -13,   # Cubit +
    0x529d0ac5 :  -11,   # FakeAltD
    0x1616a73e :  -10,   # GtFeedbk
    0xff7d075a :  -27,   # Hermit
    0x34e20653 :  -79,   # Insects
    0xef71bc66 :  -14,   # Memory
    0x646aba5c :  -15,   # Raga Syn
    0x479a6de2 :  -17,   # Rev Cym2
    0x0b0a3d91 :  -17,   # RevCym3
    0x42ca50ff :  -13,   # Shower
    0x226d3a40 :  -14,   # Siren
    0x53f40951 :  -11,   # StarDust
    0x71d8ff13 :  -53,   # Sweepy
    0xdf758790 :  -10,   # SwpStOct
    0xae991585 :  -13,   # SyPadPno
    0x4402ea76 :  -21,   # Trcrtps
    0xae81bd0f :  -12,   # TurnTabl
    0xd1c51648 :  -19,   # VlnHrpDt
    0x43b31d76 :   45,   # Aah Mix
    0x55e6ab6a :   12,   # Alps
    0x909e5334 :   13,   # Ana Tom
    0x56d43f73 :   17,   # AnVelBr2
    0x445e9f7d :   25,   # Balafon
    0x3500fd0c :   15,   # Balimba
    0x2464e7fc :   21,   # Big Lead
    0xe803ed79 :   11,   # Brook St
    0xe4953e62 :   35,   # Brt Trem
    0x098c002a :   28,   # ChoEP K
    0x378d340a :   44,   # DstCutNz
    0xe9c8f9ac :   13,   # Echoes 2
    0xcf00bd84 :   36,   # El Banjo
    0x24386751 :   18,   # Fanfare
    0x1e49dd4f :   21,   # FM Koto
    0x2a6e14e1 :   26,   # GblnTalk
    0x67005b08 :   18,   # HeinzUni
    0xbc1d86df :   12,   # Marimba
    0xd6d1a7da :   14,   # MutePkBa
    0x5f9ab9ab :   33,   # MuteStlG
    0xdbe65fbc :   28,   # NylnGtDt
    0xaab23b56 :   30,   # Ooh Aah
    0xe01ed9d0 :    8,   # Pan Pad
    0xd2c40123 :   19,   # Pi Pa
    0x04dbf036 :   32,   # Popcorn
    0x02c7c5a2 :   10,   # Real Tom
    0xcc6389f6 :   11,   # Seq Bass
    0xabfaabdc :   16,   # Shepherd
    0x5688f343 :   38,   # SineMrmb
    0x1297626d :   11,   # SlapBa1#
    0x30396843 :   16,   # Soft Brs
    0x19b55d86 :   49,   # SolidStr
    0x93f1dc29 :   15,   # SprCyphr
    0xeda1f664 :   35,   # StBrtPno
    0xd306e311 :   30,   # Str+Brss
    0xdc8064ff :    6,   # Syn Str4
    0x03948d32 :   26,   # SynDrCmp
    0x5d9f5f84 :   13,   # SynFretl
    0x0ea45dae :    7,   # TaikoDrm
    0x1652aa4c :   15,   # TechnoBa
    0x8b87e01f :   34,   # Tin
    0x0cf2ea72 :   30,   # Woodblok
}


def Trim_Levels(raw : bytes | bytearray, levels : list[int]) -> tuple[list[int], float] :
    # -> (element levels, gain in dB still missing at level 127: goes into louder sample copies)
    trim = TRIM_DB10.get(Voice_Key(raw), 0) / 10
    if not trim or not any(levels) : 
        return levels, 0.0
    f = 10 ** (-trim / 40)
    new = [min(127, max(1, round(l * f))) if l else 0 for l in levels]
    top = max(levels)
    missing = -trim - 40 * math.log10(max(new) / top)
    return new, round(missing, 1) if missing >= 0.3 else 0.0


# * key-dependent part (issue #6): voices whose deviation runs smoothly over the keyboard (measured every
# 6 keys from 24 to 102, after the trims above) get it corrected through the element level key scaling.
# Fitted piecewise linear at KEY_TRIM_KEYS; only voices where the fit removes at least 1 dB rms and 40 %
# of the deviation are listed. Jagged curves (element pairs on the same wave, e.g. StBrtPno, NylnGtDt:
# the two copies add up differently from note to note) cannot be fixed this way.
# The new key scaling keeps the element's own curve (elemreduce.effective_level) and multiplies the
# correction in, with its breakpoints at KEY_TRIM_KEYS.
#
# key as above, value: deviation in 0.1 dB at KEY_TRIM_KEYS (S-YXG minus S-MU2000)
KEY_TRIM_KEYS = (30, 54, 78, 102)
KEY_TRIM_DB10 = {
    0xf164d22b : (  51,  -16,   -1,   12),   # AsprateD
    0x098c002a : (  24,  -12,  -20,  -39),   # ChoEP K
    0x3f210359 : (  41,    8,   -2,    5),   # DimChors
    0x378d340a : ( -35,  -25,  -10,   18),   # DstCutNz
    0xeff6c7fc : ( -86,  -12,   -3,   -7),   # Frost
    0x67005b08 : (  -6,    1,  -19,  -44),   # HeinzUni
    0x34e20653 : ( -32,   -5,    9,    6),   # Insects
    0x5f9ab9ab : (  19,  -35,  -35,    5),   # MuteStlG
    0x50aa86b0 : (   5,  -58,   11,   -5),   # SlapBa2#
    0x4402ea76 : (  17,   -7,  -37,  -48),   # Trcrtps
    0x4a2982c7 : (  43,   -4,  -12,    3),   # WrnchDbl
}

def Key_Trim(raw : bytes | bytearray, edata : bytearray) -> None :
    import elemreduce
    dev = KEY_TRIM_DB10.get(Voice_Key(raw))
    if dev is None or not edata[57] : 
        return
    offs = []
    for key, d in zip(KEY_TRIM_KEYS, dev) : 
        eff = min(145.0, elemreduce.effective_level(edata, key) * 10 ** (-d / 10 / 40))
        offs.append(max(0, min(127, round((eff - edata[57]) / elemreduce.KS_LEVEL_STEPS) + 64)))
    edata[58:62] = bytes(KEY_TRIM_KEYS)
    edata[62:66] = bytes(offs)
