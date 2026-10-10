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
# key: CRC32 of the source voice (14 header bytes + 84 bytes per element), value: trim in 0.1 dB.
#
# syxg50.dll plays the element level on a 40 log10 curve (measured: level 90 -> 64 = -5.9 dB,
# 90 -> 127 = +6.2 dB), so all element levels are scaled by 10 ** (-trim / 40), capped at 127.

import math, zlib

TRIM_DB10 = {
    0xa439c96b :  -22,   # AnaBrss2
    0x0b36e580 :  -20,   # Bacteria
    0x0ed5956a :  -11,   # Bombay S
    0x87370816 :  -11,   # BrssStab
    0x76d60118 :  -13,   # BrthTnSx
    0x2046254b :  -11,   # Burst
    0xccf9066f :  -13,   # Cubit +
    0x3c07c7fd :  -11,   # FakeAltD
    0xfe9cb13a :  -10,   # GtFeedbk
    0xc98f0522 :  -27,   # Hermit
    0xa183fc1e :  -79,   # Insects
    0x91d497c6 :  -14,   # Memory
    0x73a1dc94 :  -15,   # Raga Syn
    0x3b008ca3 :  -17,   # Rev Cym2
    0xd1c98b3b :  -17,   # RevCym3
    0xcfaa105e :  -13,   # Shower
    0xd6a51a84 :  -14,   # Siren
    0x1d6a764c :  -11,   # StarDust
    0x155f3de1 :  -53,   # Sweepy
    0x8dbb9f7a :  -10,   # SwpStOct
    0xcc558df6 :  -13,   # SyPadPno
    0x1f2a176e :  -21,   # Trcrtps
    0x94753af5 :  -12,   # TurnTabl
    0xe3de9e01 :  -19,   # VlnHrpDt
    0xdcba7598 :   45,   # Aah Mix
    0x9b4533f8 :   12,   # Alps
    0x24f586a5 :   13,   # Ana Tom
    0x01431509 :   17,   # AnVelBr2
    0xf934428b :   25,   # Balafon
    0xe05eb3bf :   15,   # Balimba
    0x82f0af8c :   21,   # Big Lead
    0xa34ef155 :   11,   # Brook St
    0xffadbb47 :   35,   # Brt Trem
    0x21555869 :   28,   # ChoEP K
    0xa97b7320 :   44,   # DstCutNz
    0x3e9570b1 :   13,   # Echoes 2
    0x1814ce34 :   36,   # El Banjo
    0xbb46d001 :   18,   # Fanfare
    0xa729ec76 :   21,   # FM Koto
    0x64c394eb :   26,   # GblnTalk
    0xcfcdedc5 :   18,   # HeinzUni
    0x940d94ab :   12,   # Marimba
    0x70ef4706 :   14,   # MutePkBa
    0xa44571d7 :   33,   # MuteStlG
    0xe349ad3c :   28,   # NylnGtDt
    0xffd6568c :   30,   # Ooh Aah
    0xa02ae1af :    8,   # Pan Pad
    0xd62363d9 :   19,   # Pi Pa
    0x3bd49424 :   32,   # Popcorn
    0xd581310f :   10,   # Real Tom
    0xb037e0ea :   11,   # Seq Bass
    0xb678de36 :   16,   # Shepherd
    0x758aae35 :   38,   # SineMrmb
    0x60c9492f :   11,   # SlapBa1#
    0xabfc9615 :   16,   # Soft Brs
    0x398d631c :   49,   # SolidStr
    0x73276887 :   15,   # SprCyphr
    0x612e94d8 :   35,   # StBrtPno
    0xf72653c5 :   30,   # Str+Brss
    0x9e832190 :    6,   # Syn Str4
    0x6396293d :   26,   # SynDrCmp
    0x99d39b03 :   13,   # SynFretl
    0x6237fe03 :    7,   # TaikoDrm
    0x51363f61 :   15,   # TechnoBa
    0x02037fb2 :   34,   # Tin
    0xdd1d21f8 :   30,   # Woodblok
}


def Trim_Levels(raw : bytes | bytearray, levels : list[int]) -> tuple[list[int], float] :
    # -> (element levels, gain in dB still missing at level 127: goes into louder sample copies)
    trim = TRIM_DB10.get(zlib.crc32(raw), 0) / 10
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
    0x6594c392 : (  51,  -16,   -1,   12),   # AsprateD
    0x21555869 : (  24,  -12,  -20,  -39),   # ChoEP K
    0x812ffc26 : (  41,    8,   -2,    5),   # DimChors
    0xa97b7320 : ( -35,  -25,  -10,   18),   # DstCutNz
    0x50878d88 : ( -86,  -12,   -3,   -7),   # Frost
    0xcfcdedc5 : (  -6,    1,  -19,  -44),   # HeinzUni
    0xa183fc1e : ( -32,   -5,    9,    6),   # Insects
    0xa44571d7 : (  19,  -35,  -35,    5),   # MuteStlG
    0x99787da3 : (   5,  -58,   11,   -5),   # SlapBa2#
    0x1f2a176e : (  17,   -7,  -37,  -48),   # Trcrtps
    0x9e35ea84 : (  43,   -4,  -12,    3),   # WrnchDbl
}

def Key_Trim(raw : bytes | bytearray, edata : bytearray) -> None :
    import elemreduce
    dev = KEY_TRIM_DB10.get(zlib.crc32(raw))
    if dev is None or not edata[57] : 
        return
    offs = []
    for key, d in zip(KEY_TRIM_KEYS, dev) : 
        eff = min(145.0, elemreduce.effective_level(edata, key) * 10 ** (-d / 10 / 40))
        offs.append(max(0, min(127, round((eff - edata[57]) / elemreduce.KS_LEVEL_STEPS) + 64)))
    edata[58:62] = bytes(KEY_TRIM_KEYS)
    edata[62:66] = bytes(offs)
