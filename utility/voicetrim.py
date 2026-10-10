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
# Boosts are limited: syxg50.dll caps the element level, above about 100 a louder level byte plays
# no louder (AfrcnWnd: 110 -> 127 = 0 dB). Voices that are too quiet and already at that ceiling
# (5partStr, Insects, AfrcnWnd, ...) are left out, they need another way to gain level.
#
# key: CRC32 of the source voice (14 header bytes + 84 bytes per element), value: trim in 0.1 dB.
#
# syxg50.dll plays the element level on a 40 log10 curve (measured: level 90 -> 64 = -5.9 dB,
# 90 -> 127 = +6.2 dB), so all element levels are scaled by 10 ** (-trim / 40), capped at 127.

import zlib

TRIM_DB10 = {
    0xdcba7598 :   45,   # Aah Mix
    0x9b4533f8 :   12,   # Alps
    0x24f586a5 :   13,   # Ana Tom
    0xa439c96b :  -30,   # AnaBrss2
    0x01431509 :   17,   # AnVelBr2
    0x0b36e580 :  -19,   # Bacteria
    0xf934428b :   25,   # Balafon
    0xe05eb3bf :   15,   # Balimba
    0x82f0af8c :   21,   # Big Lead
    0x0ed5956a :   -7,   # Bombay S
    0xa34ef155 :   11,   # Brook St
    0xd3c0c0ab :  -14,   # BrssSec2
    0x87370816 :  -13,   # BrssStab
    0xffadbb47 :   35,   # Brt Trem
    0x76d60118 :  -19,   # BrthTnSx
    0x2046254b :   -9,   # Burst
    0x21555869 :   28,   # ChoEP K
    0xccf9066f :   -8,   # Cubit +
    0x6c5db150 :   -6,   # DoorSqek
    0xa97b7320 :   44,   # DstCutNz
    0x3e9570b1 :   13,   # Echoes 2
    0x1814ce34 :   36,   # El Banjo
    0x3c07c7fd :  -17,   # FakeAltD
    0xbb46d001 :   18,   # Fanfare
    0xa729ec76 :   21,   # FM Koto
    0x64c394eb :   26,   # GblnTalk
    0xfe9cb13a :   -9,   # GtFeedbk
    0xcfcdedc5 :   18,   # HeinzUni
    0xc98f0522 :  -39,   # Hermit
    0xa183fc1e : -198,   # Insects
    0x940d94ab :   12,   # Marimba
    0x91d497c6 :  -13,   # Memory
    0x70ef4706 :   14,   # MutePkBa
    0xa44571d7 :   33,   # MuteStlG
    0xe349ad3c :   28,   # NylnGtDt
    0xffd6568c :   30,   # Ooh Aah
    0xa02ae1af :    8,   # Pan Pad
    0xd62363d9 :   19,   # Pi Pa
    0x3bd49424 :   32,   # Popcorn
    0x73a1dc94 :  -15,   # Raga Syn
    0xd581310f :   10,   # Real Tom
    0x3b008ca3 :  -19,   # Rev Cym2
    0xd1c98b3b :  -12,   # RevCym3
    0xcaaa5290 :  -10,   # RevSnar1
    0xe1ba9b4e :   -8,   # ScratchS
    0xb037e0ea :   11,   # Seq Bass
    0xb678de36 :   16,   # Shepherd
    0xcfaa105e :  -16,   # Shower
    0x758aae35 :   38,   # SineMrmb
    0xd6a51a84 :  -29,   # Siren
    0x60c9492f :   11,   # SlapBa1#
    0xabfc9615 :   16,   # Soft Brs
    0x398d631c :   49,   # SolidStr
    0x73276887 :   15,   # SprCyphr
    0x7d84b292 :   -9,   # SprTenor
    0x1d6a764c :  -16,   # StarDust
    0x612e94d8 :   35,   # StBrtPno
    0xf72653c5 :   30,   # Str+Brss
    0x18e95ff1 :   -8,   # Stream
    0x155f3de1 :  -52,   # Sweepy
    0x8dbb9f7a :   -9,   # SwpStOct
    0x9e832190 :    6,   # Syn Str4
    0x6396293d :   26,   # SynDrCmp
    0x99d39b03 :   13,   # SynFretl
    0x6237fe03 :    7,   # TaikoDrm
    0x51363f61 :   15,   # TechnoBa
    0xac72e116 :  -14,   # Throne
    0x02037fb2 :   34,   # Tin
    0x1f2a176e :  -52,   # Trcrtps
    0x94753af5 :  -27,   # TurnTabl
    0xe3de9e01 :  -31,   # VlnHrpDt
    0xdd1d21f8 :   30,   # Woodblok
    0xd948e7d4 :  -12,   # Xplosion
}

def Trim_Levels(raw : bytes | bytearray, levels : list[int]) -> list[int] :
    trim = TRIM_DB10.get(zlib.crc32(raw), 0) / 10
    if not trim : 
        return levels
    f = 10 ** (-trim / 40)
    return [min(127, max(1, round(l * f))) if l else 0 for l in levels]
