# * Level trim per melodic voice (MU1000 voice data), measured on the S-MU2000 (issue #6).
#
# The voice sweep (issue #3: 1,119 voices x C2/C4/C6, velocity 100, sustain energy) left 44 voices
# more than 3 dB off on at least one note. Their wave tables are converted 1:1 (attenuation, key
# ranges) and the deviation stays the same over velocity, so it comes from the way syxg50.dll mixes
# the elements (detuned and stacked copies of one wave add up differently) and cannot be derived
# from the voice data. Like drumtrim.py, each voice gets its measured offset instead: the median
# deviation, S-YXG minus S-MU2000, over C2/C4/C6 (over C2/C4/C6 x velocity 32/64/100/127 for the
# 44 outliers). Only voices with |median| >= 1 dB are listed.
#
# key: CRC32 of the source voice (14 header bytes + 84 bytes per element), value: trim in 0.1 dB.
#
# syxg50.dll plays the element level on a 40 log10 curve (measured: level 90 -> 64 = -5.9 dB,
# 90 -> 127 = +6.2 dB), so all element levels are scaled by 10 ** (-trim / 40), capped at 127.

import zlib

TRIM_DB10 = {
    0xdcba7598 :   31,   # Aah Mix
    0x9b4533f8 :   12,   # Alps
    0x24f586a5 :   13,   # Ana Tom
    0xa439c96b :  -28,   # AnaBrss2
    0x01431509 :   17,   # AnVelBr2
    0x0b36e580 :   26,   # Bacteria
    0xf934428b :   25,   # Balafon
    0xe05eb3bf :   16,   # Balimba
    0x82f0af8c :   19,   # Big Lead
    0x0ed5956a :   -9,   # Bombay S
    0xa34ef155 :   14,   # Brook St
    0xd3c0c0ab :  -14,   # BrssSec2
    0x87370816 :  -12,   # BrssStab
    0xffadbb47 :   35,   # Brt Trem
    0x76d60118 :  -16,   # BrthTnSx
    0x2046254b :   -5,   # Burst
    0x21555869 :   31,   # ChoEP K
    0xccf9066f :   29,   # Cubit +
    0x6c5db150 :   -6,   # DoorSqek
    0xa97b7320 :   38,   # DstCutNz
    0x3e9570b1 :   13,   # Echoes 2
    0x1814ce34 :   34,   # El Banjo
    0x3c07c7fd :  -17,   # FakeAltD
    0xbb46d001 :   16,   # Fanfare
    0xa729ec76 :   20,   # FM Koto
    0x64c394eb :   25,   # GblnTalk
    0xfe9cb13a :  -10,   # GtFeedbk
    0xcfcdedc5 :   17,   # HeinzUni
    0xc98f0522 :  -34,   # Hermit
    0xa183fc1e : -198,   # Insects
    0x940d94ab :   15,   # Marimba
    0x91d497c6 :  -13,   # Memory
    0x70ef4706 :   19,   # MutePkBa
    0xa44571d7 :   21,   # MuteStlG
    0xe349ad3c :   27,   # NylnGtDt
    0xffd6568c :   27,   # Ooh Aah
    0xa02ae1af :    6,   # Pan Pad
    0xd62363d9 :   14,   # Pi Pa
    0x73a1dc94 :   -9,   # Raga Syn
    0xd581310f :   10,   # Real Tom
    0x3b008ca3 :  -17,   # Rev Cym2
    0xd1c98b3b :  -12,   # RevCym3
    0xcaaa5290 :  -10,   # RevSnar1
    0xe1ba9b4e :   -8,   # ScratchS
    0xb037e0ea :   13,   # Seq Bass
    0xb678de36 :   12,   # Shepherd
    0xcfaa105e :  -13,   # Shower
    0x758aae35 :   27,   # SineMrmb
    0xd6a51a84 :  -19,   # Siren
    0x60c9492f :   11,   # SlapBa1#
    0xabfc9615 :   16,   # Soft Brs
    0x398d631c :   49,   # SolidStr
    0x73276887 :   14,   # SprCyphr
    0x7d84b292 :  -10,   # SprTenor
    0x1d6a764c :  -13,   # StarDust
    0x612e94d8 :   49,   # StBrtPno
    0xf72653c5 :   29,   # Str+Brss
    0x18e95ff1 :   -9,   # Stream
    0x155f3de1 :  -52,   # Sweepy
    0x8dbb9f7a :  -10,   # SwpStOct
    0x9e832190 :    9,   # Syn Str4
    0x6396293d :   18,   # SynDrCmp
    0x99d39b03 :   12,   # SynFretl
    0x6237fe03 :    8,   # TaikoDrm
    0x51363f61 :   16,   # TechnoBa
    0xac72e116 :  -12,   # Throne
    0x02037fb2 :   47,   # Tin
    0x1f2a176e :  -86,   # Trcrtps
    0x94753af5 :  -20,   # TurnTabl
    0xe3de9e01 :  -31,   # VlnHrpDt
    0xdd1d21f8 :   23,   # Woodblok
    0xd948e7d4 :  -12,   # Xplosion
}

def Trim_Levels(raw : bytes | bytearray, levels : list[int]) -> list[int] :
    trim = TRIM_DB10.get(zlib.crc32(raw), 0) / 10
    if not trim : 
        return levels
    f = 10 ** (-trim / 40)
    return [min(127, max(1, round(l * f))) if l else 0 for l in levels]
