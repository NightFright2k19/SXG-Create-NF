# dllpatch.py - patches a user supplied syxg50.dll for the table being built
#
# The DLL is given on the command line together with the ROMs, under any file name (it is
# recognised by its content). SXG-Create writes next to the table and wave file:
#   <name>.dll  the patched DLL, same name as the supplied one (e.g. mu800.dll)
#   <name>.ini  its settings (the DLL reads the ini with its own name), e.g. mu800.ini
# If the supplied DLL is in the output folder itself, it is replaced and the original is kept as
# <name>.orig.dll (later runs patch from that copy). The ini selects the table with
# SoftSynth=<table>.TBL, the wave file name is stored in the table header.
#
# syxg50.dll (S-YXG50, 626,688 bytes, or 5,070,848 bytes with embedded tables). The patch level
# follows the table, no switch needed:
#   "Enhanced"  MU50 / MU80 / MU90 (classic table layout)
#     * ini section [Config] and key SoftSynth (originally [SYXG50] / VoiceTable)
#     * 24-bit loop length (loops > 65,535 samples: MU90 and some MU80 voices)
#     * drum setup EG offsets (attack/decay) for ext drum voices at the same strength as for
#       internal drum keys
#     * embedded bitmaps 101 (per model, bitmaps/Bitmap101_<model>.bmp) and 105 (bitmaps/Bitmap105.bmp)
#     * names in the About dialog, string table and version info follow the model (S-YXG<n>, mu<n>, table name)
#   "Full"      MU100 / MU128 / MU1000 (big table layout)
#     * everything from "Enhanced"
#     * table size limits: 32-bit sample addresses (wave file > 64 MB; drum keys: 30 bits), 768 multisamples,
#       32-bit voice and ext voice offsets. The sound engine (incl. MMX/SSE) is unchanged.

import zlib, struct
from pathlib import Path


class DllPatchError(Exception) :
    pass


# ----------------------------------------------------------------------------- patch data
# (file offset, original bytes, patched bytes)

SYXG50_24BIT = [
    # voice setup masks start offset and loop length with 0xFFFF (and edx, 0xFFFF) -> 0xFFFFFF
    (0x1A6F0, '00', 'ff'),
    (0x1A6FC, '00', 'ff'),
]

# "Full": big table layout (MU100 / MU128 / MU1000), see buildtarget.py
SYXG50_BIG = [
    # voice map 32-bit
    (0x045E0, '66 8b 04 46 66 3d 00 80 5e 5b 73 11 8b 0d dc 52 05 10 33 d2 66 8b d0 8d 04 51 c2 10 00 8b 0d 08 53 05 10 05 00 80 00 00 33 d2 66 8b d0 8d 04 51 c2 10',
              '8b 04 86 5e 5b 90 90 90 90 90 90 90 8b 0d dc 52 05 10 8d 04 01 c2 10 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90'),
    # wavedata offsets 32-bit, up to 768 multisamples in three pages (hook)
    (0x04DF4, '0f b6 08 8b 15 04 53 05 10 0f b7 04 4a 03 05 fc 52 05 10',
              'e9 e7 a5 03 00 cc cc cc cc cc cc cc cc cc cc cc cc cc cc'),
    # wavedata offsets 32-bit, up to 768 multisamples (code cave, position independent):
    #   wave number = element byte 0, + 256 for elements in voice bank B when the offset table has
    #   more than 256 entries, + another 256 for elements behind bank B + [entry 768] when it has
    #   more than 512 entries
    (0x3F3E0, '00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00',
              '0f b6 08 56 57 e8 00 00 00 00 5e 8b be 1a 5f 01 00 8b 96 12 5f 01 00 29 fa 81 fa 00 04 00 00 76 2c 3b 86 1e 5f 01 00 72 24 81 c1 00 01 00 00 81 fa 00 08 00 00 76 16 8b 97 00 0c 00 00 03 96 1e 5f 01 00 39 d0 72 06 81 c1 00 01 00 00 8b 04 8f 03 86 12 5f 01 00 89 fa 5f 5e e9 c8 59 fc ff'),
    # drum: ext voice check +0x11
    (0x05BFE, '80 79 10 ff',
              '80 79 11 ff'),
    # drum: ext voice check +0x11
    (0x16E6F, '8a 50 10',
              '8a 50 11'),
    # drum: ext voice check +0x11
    (0x16EA5, '8a 50 10',
              '8a 50 11'),
    # drum: ext voice check +0x11
    (0x16EC4, '8a 50 10',
              '8a 50 11'),
    # drum: ext voice check +0x11
    (0x16EDB, '8a 50 10',
              '8a 50 11'),
    # ext voice index 16-bit, 32-bit offsets
    (0x0AFDA, '0f b6 42 11 8b 0d f0 52 05 10 0f b7 1c 41',
              '0f b7 42 10 8b 0d f0 52 05 10 8b 1c 81 90'),
    # wavedata format +0x0D
    (0x05C13, '8a 52 0c',
              '8a 52 0d'),
    # wavedata format +0x0D
    (0x05CB0, '8a 52 0c',
              '8a 52 0d'),
    # drum format in address MSB
    (0x05C44, '8a 51 1b',
              '8a 51 18'),
    # drum root key +0x0A
    (0x1379D, '66 0f b6 4a 12',
              '66 0f b6 4a 0a'),
    # drum setup +0x0A = 1
    (0x08325, '8a 50 0a 88 56 0a',
              'b2 01 90 88 56 0a'),
    # drum setup +0x0A = 1
    (0x08410, '8a 48 0a 88 4e 0a',
              'b1 01 90 88 4e 0a'),
    # drum sample fields
    (0x138F0, '8b 44 24 08 8b 40 30 0f b6 50 13 0f b6 48 14 c1 e2 08 03 d1 8b 4c 24 04 89 91 cc 01 00 00 0f b6 50 16 56 0f b6 70 17 c1 e2 08 03 d6 89 91 d4 01 00 00 0f b6 50 18 0f b6 70 19 c1 e2 08 03 d6 0f b6 70 1a c1 e2 08 03 d6 89 91 d0 01 00 00 8a 40 1b 88 81 cb 01 00 00 5e c2 08 00 90 90 90 90 90',
              '8b 44 24 08 8b 40 30 8b 4c 24 04 8b 50 12 0f ca c1 ea 08 89 91 cc 01 00 00 8b 50 15 0f ca c1 ea 08 89 91 d4 01 00 00 8b 50 18 0f ca 89 d0 81 e2 ff ff ff 3f 89 91 d0 01 00 00 c1 e8 18 24 c0 88 81 cb 01 00 00 c2 08 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90'),
    # wavedata fields
    (0x15620, '8b 44 24 0c 8b 40 24 0f b6 48 06 0f b6 50 07 c1 e1 08 03 ca 0f b6 50 08 c1 e1 08 03 ca 8b 54 24 04 89 8a d4 01 00 00 8a 48 0c 88 8a cb 01 00 00 0f b6 48 09 c1 e1 08 56 0f b6 70 0a 03 ce 0f b6 70 0b c1 e1 08 03 ce 89 8a d0 01 00 00',
              '8b 44 24 0c 8b 40 24 8b 54 24 04 8b 48 05 0f c9 81 e1 ff ff ff 00 89 8a d4 01 00 00 8a 48 0d 88 8a cb 01 00 00 8b 48 09 0f c9 89 8a d0 01 00 00 56 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90'),
]
BIG_CAVE_END = 0x3F3E0 + 95    # code cave at the end of .text, the section's VirtualSize is enlarged to cover it

# drum setup EG offsets (attack, decay 1, decay 2) for ext drum voices (syxg50.dll 0x10012210):
# the offset is added to the element rate, whose unit is two drum units, so the offset acted twice
# as strong as on internal drum keys. Now rate + (offset - 0x40) / 2, via three small code caves.
SYXG50_DRUMEG = [
    (0x12233, '66 0f be 52 0d 8d 44 10 c0',
              'e8 78 d1 02 00 90 90 90 90'),
    (0x3f3b0, '00 00 00 00 00 00 00 00 00 00 00 00 00 00',
              '0f b6 52 0d 0f b7 c0 8d 44 42 c0 d1 f8 c3'),
    (0x12273, '66 0f be 51 0e 8d 44 10 c0',
              'e8 48 d1 02 00 90 90 90 90'),
    (0x3f3c0, '00 00 00 00 00 00 00 00 00 00 00 00 00 00',
              '0f b6 51 0e 0f b7 c0 8d 44 42 c0 d1 f8 c3'),
    (0x122b3, '66 0f be 51 0f 8d 44 10 c0',
              'e8 18 d1 02 00 90 90 90 90'),
    (0x3f3d0, '00 00 00 00 00 00 00 00 00 00 00 00 00 00',
              '0f b6 51 0f 0f b7 c0 8d 44 42 c0 d1 f8 c3'),
]
DRUMEG_CAVE_END = 0x3F3D0 + 14

# effect types the DLL does not have (it switches the block off or to Thru) -> the nearest type it has.
# The six functions that turn MSB/LSB into the internal effect number (0x100099C0 - 0x10009D36:
# reverb, chorus, variation, each set + get) read the type through a small stub that first rewrites
# MSB/LSB with a per-block table (code cave at 0x3F460, position independent):
#   reverb    12/xx Canyon -> 11/00 Tunnel
#   chorus    44/xx Symphonic -> 42/00 Celeste 1, 48/xx Phaser -> 43/00 Flanger 1, 57/xx Ensemble Detune -> 41/00 Chorus 1
#   variation 4E/01, 4E/02 Auto Wah+Dist/+OD -> 49/00 Distortion / 4A/00 Overdrive, 52/01, 52/02 Touch Wah+Dist/+OD
#             -> Distortion / Overdrive, 52/xx Touch Wah -> 4E/00 Auto Wah, 56/xx 2-Way Rotary -> 45/00 Rotary,
#             57/xx Ensemble Detune -> 44/00 Symphonic, 5D/xx Talking Modulator -> Auto Wah,
#             5F-61/00 Dist+Delay, Comp+Dist+Delay, Wah+Dist+Delay -> Distortion, 5F-61/01 (OD versions) -> Overdrive
#   left as they are (no counterpart, Thru): Pitch Change, Harmonic Enhancer, Compressor, Noise Gate, Lo-Fi
SYXG50_FX = [
    (0x099C2, '8a 90 c4 69 00 00',
              'e8 be 5a 03 00 90'),
    (0x09A97, '8a 91 af 69 00 00',
              'e8 09 5a 03 00 90'),
    (0x09ADC, '8a 91 9b 69 00 00',
              'e8 e4 59 03 00 90'),
    (0x09B80, '8a 8a c4 69 00 00',
              'e8 60 59 03 00 90'),
    (0x09C4E, '8a 81 ae 69 00 00',
              'e8 b2 58 03 00 90'),
    (0x09CA3, '8a 81 9a 69 00 00',
              'e8 7d 58 03 00 90'),
    (0x3F460, '00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00',
              '8a 07 84 c0 74 1e 3a 06 75 15 8a 67 01 80 fc ff 74 05 3a 66 01 75 08 66 8b 47 02 66 89 06 c3 83 c7 04 eb dc c3 60 8d b0 c3 69 00 00 e8 00 00 00 00 5f 81 c7 cf 00 00 00 e8 c3 ff ff ff 61 8a 90 c4 69 00 00 c3 60 8d b1 ae 69 00 00 e8 00 00 00 00 5f 81 c7 9f 00 00 00 e8 a3 ff ff ff 61 8a 91 af 69 00 00 c3 60 8d b1 9a 69 00 00 e8 00 00 00 00 5f 81 c7 77 00 00 00 e8 83 ff ff ff 61 8a 91 9b 69 00 00 c3 60 8d b2 c3 69 00 00 e8 00 00 00 00 5f 81 c7 6f 00 00 00 e8 63 ff ff ff 61 8a 8a c4 69 00 00 c3 60 8d b1 ae 69 00 00 e8 00 00 00 00 5f 81 c7 3f 00 00 00 e8 43 ff ff ff 61 8a 81 ae 69 00 00 c3 60 8d b1 9a 69 00 00 e8 00 00 00 00 5f 81 c7 17 00 00 00 e8 23 ff ff ff 61 8a 81 9a 69 00 00 c3 00 00 00 12 ff 11 00 00 00 00 00 44 ff 42 00 48 ff 43 00 57 ff 41 00 00 00 00 00 4e 01 49 00 4e 02 4a 00 52 01 49 00 52 02 4a 00 52 ff 4e 00 56 ff 45 00 57 ff 44 00 5d ff 4e 00 5f 00 49 00 5f ff 4a 00 60 00 49 00 60 ff 4a 00 61 00 49 00 61 ff 4a 00 00 00 00 00'),
    # effect return level per type (reverb and variation, system effects), code cave at 0x3F5A0: the DLL reads
    # the return level (0-127) through a stub that scales it with a per-type factor (64 = x1, result max 127).
    # Factors from the S-MU2000 (12_Effect_Test, tail 4.0-5.2 s after the dry signal, reverb types averaged
    # over the reverb and the variation block): Hall +2.5 dB, Room1 +3.5, Room2/3 +2.0, Stage1 +1.0, Stage2 +2.5,
    # Plate +1.5, White Room +3.5, Basement -1.0; variation only: Delay LCR +1.0, Delay LR +2.5, Echo +2.0,
    # Cross Delay x2, ER2 +2.5, Gate / Reverse Gate +2.0, Karaoke 1/2 -1.5/-2.5; Symphonic x1.56,
    # Rotary x1.45, Tremolo / Auto Pan x2 (total level; still short of the S-MU2000 by 0.8 / 0.9 dB)
    (0x041D6, '66 8b 96 76 69 00 00',
              'e8 fa b3 03 00 90 90'),
    (0x0A65D, '0f b7 96 80 69 00 00',
              'e8 98 4f 03 00 90 90'),
    (0x3F5A0, '00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00',
              '8a 0f 84 c9 74 2e 3a 0e 75 25 8a 6f 01 80 fd ff 74 05 3a 6e 01 75 18 0f b6 4f 02 0f af c1 83 c0 20 c1 e8 06 83 f8 7f 76 0b b8 7f 00 00 00 c3 83 c7 03 eb cc c3 60 0f b7 86 76 69 00 00 8d b6 9a 69 00 00 e8 00 00 00 00 5f 81 c7 38 00 00 00 e8 ac ff ff ff 89 44 24 14 61 c3 60 0f b7 86 80 69 00 00 8d b6 c3 69 00 00 e8 00 00 00 00 5f 81 c7 2c 00 00 00 e8 87 ff ff ff 89 44 24 14 61 c3 00 01 ff 55 02 00 60 02 ff 51 03 00 48 03 ff 55 04 ff 4c 10 ff 60 13 ff 39 00 01 ff 55 02 00 60 02 ff 51 03 00 48 03 ff 55 04 ff 4c 10 ff 60 13 ff 39 05 ff 48 06 ff 55 07 ff 51 08 ff 80 09 01 55 0a ff 51 0b ff 51 14 00 36 14 01 30 44 ff 64 45 ff 5d 46 ff 80 47 ff 80 00'),
    # the DLL computes the return level only when the return parameter changes, not on a type change: the
    # type change handler (0x10008F50) now also runs the return update of its block (reverb: group 1,
    # variation: group 6; block 0 = reverb, 1 = chorus, 2 = variation) after setting up the new type (code cave at 0x3F680)
    (0x0900E, '8b 16 53 56 ff 52 3c',
              'e8 6d 66 03 00 90 90'),
    (0x3F680, '00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00',
              '8b 16 53 56 ff 52 3c 60 0f b6 c3 85 c0 75 04 6a 01 eb 07 83 f8 02 75 08 6a 06 56 8b 16 ff 52 50 61 c3'),
]
FX_CAVE_END = 0x3F6A2

# effect fade-in after a type change: the type change handler mutes the block, and a ramp run every 10 ms
# (0x10008850) brings it back in steps of 4 (reverb 0 -> -256 at 0x10008C20: 64 steps = 0.64 s; chorus
# 0 -> -412 at 0x10008C70: 1.03 s; variation 0 -> -128 / -362 at 0x10008CD0: 0.32 / 0.9 s). Songs and games
# that set the effect types at the start lost the first second of reverb / chorus / variation. Larger
# steps (reverb 32, chorus 52, variation 40) end the ramp after 80-90 ms, the end values are unchanged.
# Measured on the emulator (type change, then notes every 100 ms against the settled type): reverb -3.6 dB
# for 0.7 s -> -0.9 dB in the first 100 ms only, chorus up to -3.5 dB for 1 s -> first 100 ms, variation
# (Chorus, system) -4.6 dB for 0.9 s -> -2.3 dB in the first 100 ms.
SYXG50_FXFADE = [
    (0x08C24, '66 83 80 d6 66 00 00 fc', '66 83 80 d6 66 00 00 e0'),
    (0x08C75, '66 83 86 d8 66 00 00 fc', '66 83 86 d8 66 00 00 cc'),
    (0x08CDF, '66 83 86 da 66 00 00 fc', '66 83 86 da 66 00 00 d8'),
]


# * voice map switch (MU100 / MU128 / MU1000, "Full" level): the table carries both voice maps of the model
#   (MU Native in the normal bank map / drum program rows, MU Basic in an appendix behind the wave data, see
#   makeSYXG50.Voice_Map_Appendix). The Settings page gets a checkbox "MU Basic voice map" (id 0x420):
#   - table setup (0x10003870 -> 0x100043D0): afterwards the cave looks for the appendix ('MAP2'), saves the
#     eight row pointers (drum programs GS/XG/SFX/GM2 0x100552D0/CC/F8/E8, bank maps GS/MSB/XG/GM2
#     0x100552D8/D4/E4/E0), reads [Config] MUBasic from the DLL's ini (default: the table's default) and points
#     the rows at the appendix when the Basic map is on
#   - Settings page (0x10030AF0): WM_INITDIALOG / Set Defaults set the checkbox (hidden without an appendix;
#     Set Defaults = the start value), a click marks the page changed, PSN_APPLY switches the rows.
#     Nothing is written to a file: the ini is only read (optional [Config] MUBasic=1 as start value).
#   - plugin state (VST chunk, saved by the host with its project / preset / settings): getChunk (0x10002B50)
#     returns a copy with 3 more bytes 'V','M',mode (bank 0x21 -> 0x24, program 5 -> 8 bytes); setChunk
#     (0x10002BB0) takes the mode from such a chunk and passes the original size on. Old 0x21 / 5 byte
#     chunks are still accepted and keep the start value.
#   The switch takes effect immediately (SYXG50_VMAPNOW below) for new notes.
#   State in the .data section behind its used part (0x10056DC0, chunk copy at 0x10056E00, VirtualSize
#   enlarged to 0x5E40). All code is position independent (call/pop), generated from vmap2.asm with
#   mkvmap4.py (keystone).
SYXG50_VOICEMAP = [
    (0x03875, 'e8 56 0b 00 00',
              'e8 36 be 03 00'),
    (0x30B91, 'e8 6a 06 00 00',
              'e8 e6 ec 00 00'),
    (0x30C5F, 'e8 9c 05 00 00',
              'e8 1c ec 00 00'),
    (0x30BEF, '0f b7 44 24 14 3d f6 03 00 00 8b 74 24 0c',
              'e9 f6 ec 00 00 90 90 90 90 90 90 90 90 90'),
    (0x30BBA, '8b 4c 24 08 8b 41 08',
              'e9 4a ed 00 00 90 90'),
    (0x02B50, '56 8b f1 8b 56 18',
              'e9 10 ce 03 00 90'),
    (0x02BB0, '8b c1 8a 4c 24 0c',
              'e9 10 ce 03 00 90'),
    (0x3F6B0, '00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00',
              '8b 44 24 04 50 e8 16 4d fc ff 60 e8 00 00 00 00 5d 81 ed c0 f6 03 10 8b 74 24 24 31 c0 8d 7e 20 b9 11 00 00 00 03 07 83 c7 04 e2 f9 8d 7c 06 64 c6 85 c1 6d 05 10 00 81 3f 4d 41 50 32 0f 85 9b 00 00 00 89 bd c4 6d 05 10 8b 85 d0 52 05 10 89 85 c8 6d 05 10 8b 85 cc 52 05 10 89 85 cc 6d 05 10 8b 85 f8 52 05 10 89 85 d0 6d 05 10 8b 85 e8 52 05 10 89 85 d4 6d 05 10 8b 85 d8 52 05 10 89 85 d8 6d 05 10 8b 85 d4 52 05 10 89 85 dc 6d 05 10 8b 85 e4 52 05 10 89 85 e0 6d 05 10 8b 85 e0 52 05 10 89 85 e4 6d 05 10 c6 85 c1 6d 05 10 01 0f b6 47 04 50 8d 85 18 fa 03 10 50 8d 85 ec 19 05 10 50 e8 84 39 ff ff 85 c0 0f 95 c0 88 85 c0 6d 05 10 88 85 c2 6d 05 10 e8 04 00 00 00 61 c2 04 00 60 e8 00 00 00 00 5d 81 ed 98 f7 03 10 80 bd c1 6d 05 10 01 0f 85 ce 00 00 00 80 bd c0 6d 05 10 00 74 65 8b b5 c4 6d 05 10 8d 46 08 89 85 d0 52 05 10 8d 86 88 00 00 00 89 85 cc 52 05 10 8d 86 08 01 00 00 89 85 f8 52 05 10 8d 86 88 01 00 00 89 85 e8 52 05 10 8d 86 08 02 00 00 89 85 d8 52 05 10 8d 86 88 02 00 00 89 85 d4 52 05 10 8d 86 08 03 00 00 89 85 e4 52 05 10 8d 86 88 03 00 00 89 85 e0 52 05 10 eb 60 8b 85 c8 6d 05 10 89 85 d0 52 05 10 8b 85 cc 6d 05 10 89 85 cc 52 05 10 8b 85 d0 6d 05 10 89 85 f8 52 05 10 8b 85 d4 6d 05 10 89 85 e8 52 05 10 8b 85 d8 6d 05 10 89 85 d8 52 05 10 8b 85 dc 6d 05 10 89 85 d4 52 05 10 8b 85 e0 6d 05 10 89 85 e4 52 05 10 8b 85 e4 6d 05 10 89 85 e0 52 05 10 61 c3 31 c0 eb 05 b8 01 00 00 00 50 ff 74 24 0c ff 74 24 0c e8 6d 19 ff ff 58 60 e8 00 00 00 00 5d 81 ed 9a f8 03 10 8b 5c 24 24 89 c7 68 20 04 00 00 53 ff 95 78 01 04 10 80 bd c1 6d 05 10 01 74 0b 6a 00 50 ff 95 b0 01 04 10 eb 1f 0f b6 85 c0 6d 05 10 85 ff 74 07 0f b6 85 c2 6d 05 10 50 68 20 04 00 00 53 ff 95 d0 01 04 10 61 c2 08 00 0f b7 44 24 14 8b 74 24 0c 3d 20 04 00 00 75 05 e9 22 14 ff ff 3d f6 03 00 00 e9 f4 12 ff ff 60 e8 00 00 00 00 5d 81 ed 0f f9 03 10 80 bd c1 6d 05 10 01 75 39 8b 5c 24 2c 68 20 04 00 00 53 ff 95 78 01 04 10 6a 00 6a 00 68 f0 00 00 00 50 ff 95 74 01 04 10 83 f8 01 0f 94 c0 3a 85 c0 6d 05 10 74 0b 88 85 c0 6d 05 10 e8 3a fe ff ff 61 8b 4c 24 08 8b 41 08 e9 5c 12 ff ff ff 74 24 08 ff 74 24 08 e8 48 00 00 00 60 e8 00 00 00 00 5d 81 ed 78 f9 03 10 80 bd c1 6d 05 10 01 75 2e 89 c1 83 f9 21 77 27 8b 54 24 24 8b 32 8d bd 00 6e 05 10 89 3a f3 a4 c6 07 56 c6 47 01 4d 8a 8d c0 6d 05 10 88 4f 02 83 c0 03 89 44 24 1c 61 c2 08 00 56 89 ce 8b 56 18 e9 91 31 fc ff 60 e8 00 00 00 00 5d 81 ed cb f9 03 10 80 bd c1 6d 05 10 01 75 31 8b 44 24 28 83 f8 08 74 05 83 f8 24 75 23 8b 74 24 24 66 81 7c 06 fd 56 4d 75 16 83 6c 24 28 03 8a 44 06 ff 24 01 88 85 c0 6d 05 10 e8 86 fd ff ff 61 89 c8 8a 4c 24 0c e9 9e 31 fc ff 4d 55 42 61 73 69 63 00'),
]
VMAP_CAVE_END = 0x3FA20
# * voice map switch takes effect immediately: the MIDI channel event entry (0x10007560, audio thread) compares the
#   XG bank map row pointer (0x100552D8) with the last one it saw (0x10056DE8). When the row was switched (Settings
#   page / plugin state), all 16 parts re-run their program change with their current program (part +0x6A, handler
#   table 0x10041BB0[4], honours "receive program change"), before the event is handled. Notes already sounding keep
#   their voice. Generated from vmapnow.asm (keystone), position independent.
SYXG50_VMAPNOW = [
    (0x07560, '8a 44 24 08 3c 10', 'e9 bb 84 03 00 90'),
    (0x3FA20, ' '.join(['00'] * 91),
              '60 e8 00 00 00 00 5d 81 ed 26 fa 03 10 8b 85 d8 52 05 10 8b 95 e8 6d 05 10 39 d0 74 32 89 85 e8 6d 05 10 '
              '85 d2 74 28 8b 74 24 24 31 db 69 fb 1c 01 00 00 8d bc 3e e0 01 00 00 6a 00 0f b6 47 6a 50 57 56 ff 95 c0 '
              '1b 04 10 43 83 fb 10 72 de 61 8a 44 24 08 3c 10 e9 eb 7a fc ff'),
]
VMAPNOW_CAVE_END = 0x3FA7B
VMAP_DATA_END = 0x56E40
VMAP_CONTROL_ID = 0x420
VMAP_CONTROL_TEXT = 'MU Basic voice map'

def data_virtual_size(data : bytearray, minimum : int) :
    for h, vs, va, rs, rp in sections(data) :
        if data[h : h + 5] == b'.data' :
            if va + vs < minimum :
                nxt = min(v for _, _, v, _, _ in sections(data) if v > va)
                assert minimum <= nxt
                struct.pack_into('<I', data, h + 8, minimum - va)
            return
    raise DllPatchError('.data section not found')

def add_voicemap_checkbox(raw : bytes) -> bytes :
    # DLGTEMPLATEEX of the Settings page (dialog 111): one more item, an auto checkbox left of "Set Defaults"
    if struct.unpack_from('<HH', raw, 0) != (1, 0xFFFF) : raise DllPatchError('dialog 111 is not a DLGTEMPLATEEX')
    if struct.pack('<I', VMAP_CONTROL_ID) + b'\xff\xff\x80\x00' in raw : return raw       # already there
    n = struct.unpack_from('<H', raw, 16)[0]
    out = bytearray(raw)
    while len(out) % 4 : out.append(0)
    out += struct.pack('<IIIhhhhI', 0, 0, 0x50010003, 10, 142, 160, 10, VMAP_CONTROL_ID)
    out += b'\xff\xff\x80\x00' + VMAP_CONTROL_TEXT.encode('utf-16le') + b'\0\0' + b'\0\0'
    struct.pack_into('<H', out, 16, n + 1)
    return bytes(out)

def apply_voicemap(data : bytearray) :
    apply(data, SYXG50_VOICEMAP, 'voice map switch (MU Native / MU Basic, Settings page)')
    text_virtual_size(data, VMAP_CAVE_END)
    apply(data, SYXG50_VMAPNOW, 'voice map switch: immediate (re-selects the programs of all parts)')
    text_virtual_size(data, VMAPNOW_CAVE_END)
    data_virtual_size(data, VMAP_DATA_END)
    entry = resource_entries(data, RT_DIALOG).get(111)
    if entry is None : raise DllPatchError('dialog 111 not found in the DLL')
    old = resource_data(data, entry); new = add_voicemap_checkbox(old)
    if new != old : replace_resource_data(data, entry, new)

# * Settings page (dialog 111, all models):
#   - the effect switches name their controller: "Reverb (CC 91)", "Chorus (CC 93)", "Variation (CC 94)"
#     (wider, spread over the "Effects" frame)
#   - "Reset" drop-down (combo box id 0x421, GS / XG, default GS): picking an entry sends that reset, GS reset
#     F0 41 10 42 12 40 00 7F 00 41 F7 or XG System On F0 43 10 4C 00 00 7E 00 F7. MU50 / MU80 / MU90: in the
#     place of the voice map switch of the big models; MU100 / MU128 / MU1000: right of "MU Basic voice map".
#     The page (0x10030AF0) fills the list on WM_INITDIALOG and on CBN_SELENDOK marks the reset as pending
#     (.data 0x10056E40, selection kept in 0x10056E41). The process / processReplacing wrappers (0x100010A0 /
#     0x100010C0, audio thread) send a pending reset through the SysEx entry of the engine (the same path as
#     a SysEx event from the host) before the block is rendered.
# * Panel (all models): preset buttons in the title strip, program down / up on MIDI channel 1 (part 1), with a
#   3-digit readout 001-128 and the label "PRESET". The buttons (WM_LBUTTONDOWN / UP of the panel window
#   0x10032260) add a pending step (.data 0x10056E42), the audio thread sends the program change (current
#   program of part 1 +- 1, wrapping 128 -> 1) through the engine's short message entry, the same path as a
#   host event; the bank stays. The readout is drawn on WM_PAINT and in the panel's idle redraw from the
#   program of part 1 (byte +0x366 of the synth object, engine +8). Static parts (buttons, readout frame,
#   label) are pasted into bitmap 101 from bitmaps/PresetPanel.bmp, the pressed buttons
#   (bitmaps/PresetButtons.bmp) are appended to bitmap 106 (SETUP button) on its right. Both pictures come from dev/gui/mkpreset.py.
# Generated from dev/gui/gui.asm with dev/gui/mkgui.py (keystone), position independent.
SYXG50_GUI = [
    (0x010C0, '8b 44 24 04 8b 48 40', 'e9 bb e9 03 00 90 90'),
    (0x010A0, '8b 44 24 04 8b 48 40', 'e9 ec e9 03 00 90 90'),
    (0x30AF0, '8b 44 24 0c 83 c0 b2', 'e9 a9 f2 00 00 90 90'),
    (0x3246B, '8b 74 24 54 8a 86 8c 00 00 00', 'e9 b5 d6 00 00 90 90 90 90 90'),
    (0x32427, '8b 74 24 54 8a 86 8c 00 00 00', 'e9 80 d7 00 00 90 90 90 90 90'),
    (0x3233D, '8d 4c 24 10 51', 'e9 ac d8 00 00'),
    (0x320EE, '5b 8b 8d 88 00 00 00', 'e9 0e db 00 00 90 90'),
    (0x3FA80, ' '.join(['00'] * 1045),
              'e8 1d 00 00 00 8b 44 24 04 8b 48 40 e9 36 16 fc ff e8 0c 00 00 00 8b 44 24 04 8b 48 40 e9 05 16 fc ff 60 e8 00 00 00 00 5d 81 ed a8 fa 03 10 8b 54 24 28 8b 4a 40 8b 89 b0 00 00 00 89 8d 44 6e 05 10 85 c9 74 5d 31 c0 86 85 40 6e 05 10 85 c0 74 1e 83 f8 01 75 0a 8d b5 7b fe 03 10 6a 0b eb 08 8d b5 86 fe 03 10 6a 09 56 51 8b 11 ff 52 0c 8b 8d 44 6e 05 10 31 c0 86 85 42 6e 05 10 84 c0 74 21 0f be c0 8b 51 08 0f b6 92 66 03 00 00 01 d0 83 e0 7f c1 e0 08 0d c0 00 00 00 50 51 8b 11 ff 52 08 61 c3 8b 44 24 64 0f bf c8 c1 f8 10 83 f8 01 7c 69 83 f8 10 7d 64 ba 01 00 00 00 81 f9 a4 00 00 00 7c 57 81 f9 b3 00 00 00 7c 15 ba 02 00 00 00 81 f9 dd 00 00 00 7c 42 81 f9 ec 00 00 00 7d 3a 60 e8 00 00 00 00 5d 81 ed 69 fb 03 10 88 95 43 6e 05 10 b0 01 80 fa 01 75 02 f6 d8 f0 00 85 42 6e 05 10 8b 5c 24 78 53 ff 95 a4 01 04 10 53 e8 7c 00 00 00 61 e9 16 29 ff ff 8b 74 24 54 8a 86 8c 00 00 00 e9 c9 28 ff ff 60 e8 00 00 00 00 5d 81 ed b2 fb 03 10 80 bd 43 6e 05 10 00 74 1c c6 85 43 6e 05 10 00 ff 95 a0 01 04 10 ff 74 24 78 e8 3b 00 00 00 61 e9 d5 28 ff ff 61 8b 74 24 54 8a 86 8c 00 00 00 e9 43 28 ff ff ff 74 24 10 e8 d1 00 00 00 8d 4c 24 10 51 e9 41 27 ff ff 5b 57 e8 c0 00 00 00 8b 8d 88 00 00 00 e9 e2 24 ff ff 60 e8 00 00 00 00 5d 81 ed 19 fc 03 10 ff 74 24 24 ff 95 a8 01 04 10 85 c0 74 50 89 c6 56 ff 95 1c 00 04 10 85 c0 74 38 89 c7 0f b6 9d 43 6e 05 10 b8 01 00 00 00 b9 a4 00 00 00 ba a0 00 00 00 e8 2a 00 00 00 b8 02 00 00 00 b9 dd 00 00 00 ba af 00 00 00 e8 16 00 00 00 57 ff 95 24 00 04 10 56 ff 74 24 28 ff 95 ac 01 04 10 61 c2 04 00 51 52 39 d8 75 19 ff b5 38 53 05 10 57 ff 95 20 00 04 10 5a 59 68 20 00 cc 00 6a 00 52 eb 17 ff b5 20 53 05 10 57 ff 95 20 00 04 10 5a 59 68 20 00 cc 00 6a 01 51 57 6a 0f 6a 0f 6a 01 51 56 ff 95 18 00 04 10 c3 60 e8 00 00 00 00 5d 81 ed ce fc 03 10 8b 74 24 24 56 ff 95 1c 00 04 10 85 c0 0f 84 97 00 00 00 89 c7 ff b5 3c 53 05 10 57 ff 95 20 00 04 10 8b 8d 44 6e 05 10 85 c9 75 25 b8 0a 00 00 00 b9 b9 00 00 00 e8 73 00 00 00 b8 0a 00 00 00 b9 c3 00 00 00 e8 64 00 00 00 b8 0a 00 00 00 eb 48 8b 49 08 0f b6 99 66 03 00 00 43 89 d8 31 d2 b9 64 00 00 00 f7 f1 b9 b9 00 00 00 e8 3d 00 00 00 89 d8 31 d2 b9 0a 00 00 00 f7 f1 31 d2 f7 f1 89 d0 b9 c3 00 00 00 e8 22 00 00 00 89 d8 31 d2 b9 0a 00 00 00 f7 f1 89 d0 b9 cd 00 00 00 e8 0b 00 00 00 57 ff 95 24 00 04 10 61 c2 04 00 6b c0 0a 68 20 00 cc 00 6a 00 50 57 6a 0d 6a 0a 6a 02 51 56 ff 95 18 00 04 10 c3 8b 44 24 0c 3d 10 01 00 00 74 67 3d 11 01 00 00 0f 85 bf 00 00 00 66 81 7c 24 10 21 04 0f 85 b2 00 00 00 66 83 7c 24 12 09 75 3f 60 e8 00 00 00 00 5d 81 ed cf fd 03 10 68 21 04 00 00 ff 74 24 2c ff 95 78 01 04 10 6a 00 6a 00 68 47 01 00 00 50 ff 95 74 01 04 10 83 f8 01 77 0d 88 85 41 6e 05 10 40 88 85 40 6e 05 10 61 b8 01 00 00 00 c2 14 00 60 e8 00 00 00 00 5d 81 ed 16 fe 03 10 68 21 04 00 00 ff 74 24 2c ff 95 78 01 04 10 89 c3 8d 85 8f fe 03 10 50 6a 00 68 43 01 00 00 53 ff 95 74 01 04 10 8d 85 92 fe 03 10 50 6a 00 68 43 01 00 00 53 ff 95 74 01 04 10 6a 00 0f b6 85 41 6e 05 10 50 68 4e 01 00 00 53 ff 95 74 01 04 10 61 8b 44 24 0c 83 c0 b2 e9 7c 0c ff ff f0 41 10 42 12 40 00 7f 00 41 f7 f0 43 10 4c 00 00 7e 00 f7 47 53 00 58 47 00'),
]
GUI_CAVE_END = 0x3FE95
GUI_DATA_END = 0x56E48
RESET_CONTROL_ID = 0x421
EFFECT_SWITCHES = {      # id: (text, x, width); y = 80, height 10 as before
    0x3FB : ('Reverb (CC 91)', 12, 66),
    0x3FC : ('Chorus (CC 93)', 84, 66),
    0x3FD : ('Variation (CC 94)', 156, 72),
}

KNOWN = {
    # CRC32 of the original file -> (kind, description)
    '38A60E61' : ('syxg50', 'syxg50.dll, external tables (626,688 bytes)'),
    '80EFA471' : ('syxg50', 'syxg50.dll, embedded tables (5,070,848 bytes)'),
}

# ini section and key: [SYXG50] VoiceTable -> [Config] SoftSynth
SYXG50_INI = [
    (0x519EC, '53 59 58 47 35 30 00',             '43 6f 6e 66 69 67 00'),           # "SYXG50" -> "Config"
    (0x519F4, '56 6f 69 63 65 54 61 62 6c 65 00', '53 6f 66 74 53 79 6e 74 68 00 00'), # "VoiceTable" -> "SoftSynth"
]

SIZES = {626688 : 'syxg50', 5070848 : 'syxg50'}

INI_TEMPLATE = (
    '[Config]\r\n'
    'SoftSynth={table}\r\n'
    'Process=1\r\n'
    'XGLite=0\r\n'
    'DebugPanel=0\r\n'
    'DisableGUI=0\r\n'
)


# ----------------------------------------------------------------------------- helpers

def crc(data : bytes) -> str :
    return f'{zlib.crc32(data) & 0xFFFFFFFF:08X}'

def pe_checksum_offset(data : bytes) -> int :
    pe = struct.unpack_from('<I', data, 0x3C)[0]
    assert data[pe:pe+4] == b'PE\0\0', 'not a PE file'
    return pe + 24 + 64      # optional header + 64 = CheckSum

def pe_checksum(data : bytes) -> int :
    # the standard PE checksum (same as Windows' CheckSumMappedFile)
    off = pe_checksum_offset(data)
    buf = bytearray(data)
    buf[off:off+4] = b'\0\0\0\0'
    if len(buf) % 2 : buf += b'\0'
    s = 0
    for (w,) in struct.iter_unpack('<H', buf) :
        s += w
        s = (s & 0xFFFF) + (s >> 16)
    s = (s & 0xFFFF) + (s >> 16)
    return (s + len(data)) & 0xFFFFFFFF

def text_virtual_size(data : bytearray, minimum : int) :
    # the code cave lies behind the .text VirtualSize: Windows would zero it when loading
    pe = struct.unpack_from('<I', data, 0x3C)[0]
    sec = pe + 24 + struct.unpack_from('<H', data, pe + 20)[0]
    assert data[sec:sec+5] == b'.text'
    vsize, va, raw = struct.unpack_from('<III', data, sec + 8)
    need = minimum - va          # minimum is an RVA (= file offset in .text)
    if vsize < need :
        assert need <= raw
        struct.pack_into('<I', data, sec + 8, raw)

def apply(data : bytearray, patches, label : str) :
    # all-or-nothing: every patch must find its original bytes (or be applied already)
    todo = []
    for off, old, new in patches :
        old = bytes.fromhex(old); new = bytes.fromhex(new)
        cur = bytes(data[off:off+len(old)])
        if cur == new :
            continue
        if cur != old :
            raise DllPatchError(f'{label}: unexpected bytes at 0x{off:X} ({cur.hex(" ")}), is this the right DLL version?')
        todo.append((off, new))
    for off, new in todo :
        data[off:off+len(new)] = new
    state = 'applied' if todo else 'already applied'
    print(f'  {label}: {state}')


# ----------------------------------------------------------------------------- bitmaps
# Embedded bitmaps (RT_BITMAP) replaced from the bitmaps folder next to this script:
#   101  Bitmap101_<model>.bmp  (the panel picture, one per converted model: MU80 ... MU1000;
#        models without a file keep the original)
#   105  Bitmap105.bmp          (same for all models)
# The new picture must have the size of the original; it is written in the original's format
# (24-bit DIB), so the resource keeps its size and stays in place.
BITMAP_DIR = Path(__file__).resolve().parent / 'bitmaps'
RT_BITMAP = 2

def find_resources(data : bytes | bytearray, rtype : int) -> dict[int, tuple[int, int]] :
    # -> {resource id: (file offset, size)} of the first language entry of each resource
    pe = struct.unpack_from('<I', data, 0x3C)[0]
    nsec = struct.unpack_from('<H', data, pe + 6)[0]
    opt = pe + 24
    magic = struct.unpack_from('<H', data, opt)[0]
    ddir = opt + (96 if magic == 0x10B else 112)
    rsrc_rva = struct.unpack_from('<I', data, ddir + 2 * 8)[0]
    sec0 = opt + struct.unpack_from('<H', data, pe + 20)[0]
    secs = [struct.unpack_from('<IIII', data, sec0 + 40 * i + 8) for i in range(nsec)]   # vsize, va, rawsize, rawptr
    def off(rva) :
        for vs, va, rs, rp in secs :
            if va <= rva < va + max(vs, rs) : return rp + rva - va
        raise DllPatchError(f'RVA 0x{rva:X} outside the sections')
    base = off(rsrc_rva)
    def entries(d) :
        n = sum(struct.unpack_from('<HH', data, d + 12))
        return [struct.unpack_from('<II', data, d + 16 + 8 * i) for i in range(n)]
    out = {}
    for name, ptr in entries(base) :
        if name != rtype or not ptr & 0x80000000 : continue
        for rid, p2 in entries(base + (ptr & 0x7FFFFFFF)) :
            if rid & 0x80000000 or not p2 & 0x80000000 : continue
            langs = entries(base + (p2 & 0x7FFFFFFF))
            if not langs : continue
            rva, size = struct.unpack_from('<II', data, base + langs[0][1])
            out[rid] = (off(rva), size)
    return out

def bmp_to_dib24(bmp : bytes) -> tuple[int, int, bytes] :
    # uncompressed 8/24/32-bit BMP file -> (width, height, 24-bit DIB with BITMAPINFOHEADER)
    if bmp[:2] != b'BM' : raise DllPatchError('not a BMP file')
    pix_off = struct.unpack_from('<I', bmp, 10)[0]
    hsize, w, h, planes, bpp, comp = struct.unpack_from('<IiiHHI', bmp, 14)
    if comp not in (0, 3) or bpp not in (8, 24, 32) : raise DllPatchError(f'unsupported BMP ({bpp} bit, compression {comp})')
    ncol = struct.unpack_from('<I', bmp, 46)[0] or (256 if bpp == 8 else 0)
    pal = [bmp[14 + hsize + 4 * i : 14 + hsize + 4 * i + 3] for i in range(ncol)] if bpp == 8 else []
    rows = abs(h)
    src_stride = ((w * bpp + 31) // 32) * 4
    dst_stride = ((w * 24 + 31) // 32) * 4
    out = bytearray()
    for r in range(rows) :
        y = r if h > 0 else rows - 1 - r          # DIB rows bottom-up
        line = bmp[pix_off + y * src_stride : pix_off + (y + 1) * src_stride]
        if bpp == 8 : px = b''.join(pal[i] for i in line[:w])
        elif bpp == 24 : px = line[:3 * w]
        else : px = b''.join(line[4 * i : 4 * i + 3] for i in range(w))
        out += px + b'\0' * (dst_stride - 3 * w)
    hdr = struct.pack('<IiiHHIIiiII', 40, w, abs(h), 1, 24, 0, len(out), 3780, 3780, 0, 0)
    return w, abs(h), hdr + bytes(out)

def bitmap_files(model : str | None) -> dict[int, Path] :
    files = {105 : BITMAP_DIR / 'Bitmap105.bmp'}
    if model : files[101] = BITMAP_DIR / f'Bitmap101_{model}.bmp'
    return {rid : f for rid, f in files.items() if f.exists()}

def apply_bitmaps(data : bytearray, model : str | None) :
    files = bitmap_files(model)
    if not files :
        return
    res = find_resources(data, RT_BITMAP)
    done = []
    for rid, path in sorted(files.items()) :
        if rid not in res : raise DllPatchError(f'bitmap {rid} not found in the DLL')
        off, size = res[rid]
        ow, oh = struct.unpack_from('<ii', data, off + 4)
        w, h, dib = bmp_to_dib24(path.read_bytes())
        if (w, h) != (ow, abs(oh)) : raise DllPatchError(f'{path.name}: {w}x{h}, the DLL bitmap {rid} is {ow}x{abs(oh)}')
        if len(dib) != size : raise DllPatchError(f'{path.name}: {len(dib)} bytes as 24-bit DIB, bitmap {rid} has {size}')
        data[off : off + size] = dib
        done.append(f'{rid} ({path.name})')
    print(f'  bitmaps: {", ".join(done)}')


# ----------------------------------------------------------------------------- names
# The DLL's names follow the converted model (dialog 112 "About", string table 1, version info):
#   S-YXG50 -> S-YXG<n>, xg50 -> mu<n>, default table SXGBIN41.TBL -> the table just built,
#   version info: Yamaha S-YXG<n> VSTi, S-YXG<n>, S-YXG<n>.DLL, Yamaha S-YXG<n> Portable VSTi.
# MU50 keeps the original names except the default table name (an unknown model keeps everything).
MODEL_NUMBER = {'MU80' : '80', 'MU90' : '90', 'MU100' : '100', 'MU128' : '128', 'MU1000' : '1000'}

def Model_Dll_Name(model : str) -> str : 
    # multi-model conversion: one DLL per model, named after it (MU50: syxgmu50.dll, syxg50.dll is the original)
    n = MODEL_NUMBER.get(model)
    return f'syxg{n}.dll' if n else f'syxg{model.lower()}.dll'

RT_DIALOG, RT_STRING, RT_VERSION = 5, 6, 16

def resource_entries(data : bytes | bytearray, rtype : int) -> dict[int, int] :
    # -> {resource id: file offset of its IMAGE_RESOURCE_DATA_ENTRY} (first language)
    pe = struct.unpack_from('<I', data, 0x3C)[0]
    opt = pe + 24
    ddir = opt + (96 if struct.unpack_from('<H', data, opt)[0] == 0x10B else 112)
    rsrc_rva = struct.unpack_from('<I', data, ddir + 16)[0]
    base = rva_to_offset(data, rsrc_rva)
    def entries(d) :
        n = sum(struct.unpack_from('<HH', data, d + 12))
        return [struct.unpack_from('<II', data, d + 16 + 8 * i) for i in range(n)]
    out = {}
    for name, ptr in entries(base) :
        if name != rtype or not ptr & 0x80000000 : continue
        for rid, p2 in entries(base + (ptr & 0x7FFFFFFF)) :
            if rid & 0x80000000 or not p2 & 0x80000000 : continue
            langs = entries(base + (p2 & 0x7FFFFFFF))
            if langs : out[rid] = base + langs[0][1]
    return out

def sections(data) :
    pe = struct.unpack_from('<I', data, 0x3C)[0]
    nsec = struct.unpack_from('<H', data, pe + 6)[0]
    sec0 = pe + 24 + struct.unpack_from('<H', data, pe + 20)[0]
    return [(sec0 + 40 * i,) + struct.unpack_from('<IIII', data, sec0 + 40 * i + 8) for i in range(nsec)]   # hdr, vsize, va, rawsize, rawptr

def rva_to_offset(data, rva) :
    for h, vs, va, rs, rp in sections(data) :
        if va <= rva < va + max(vs, rs) : return rp + rva - va
    raise DllPatchError(f'RVA 0x{rva:X} outside the sections')

def resource_data(data, entry : int) -> bytes :
    rva, size = struct.unpack_from('<II', data, entry)
    off = rva_to_offset(data, rva)
    return bytes(data[off : off + size])

def replace_resource_data(data : bytearray, entry : int, new : bytes) :
    # same size or smaller: in place; larger: appended to .rsrc (the last section), which grows
    rva, size = struct.unpack_from('<II', data, entry)
    if len(new) <= size :
        off = rva_to_offset(data, rva)
        data[off : off + len(new)] = new
        struct.pack_into('<I', data, entry + 4, len(new))
        return
    secs = sections(data)
    h, vs, va, rs, rp = secs[-1]
    if data[h : h + 5] != b'.rsrc' or rp + rs != len(data) :
        raise DllPatchError('.rsrc is not the last section, resources cannot grow')
    pe = struct.unpack_from('<I', data, 0x3C)[0]; opt = pe + 24
    salign, falign = struct.unpack_from('<II', data, opt + 32)
    pos = (vs + 7) & ~7                       # new data behind the used part of .rsrc
    end = pos + len(new)
    if end > rs :
        grow = ((end - rs + falign - 1) // falign) * falign
        data += bytes(grow)
        rs += grow
    data[rp + pos : rp + end] = new
    struct.pack_into('<II', data, h + 8, max(vs, end), va)
    struct.pack_into('<I', data, h + 16, rs)
    struct.pack_into('<I', data, opt + 56, ((va + max(vs, end) + salign - 1) // salign) * salign)   # SizeOfImage
    ddir = opt + (96 if struct.unpack_from('<H', data, opt)[0] == 0x10B else 112)
    struct.pack_into('<I', data, ddir + 20, max(vs, end))                # resource directory size
    struct.pack_into('<II', data, entry, va + pos, len(new))

# --- RT_STRING: 16 counted UTF-16 strings
def edit_string_table(raw : bytes, fn) -> bytes :
    out = bytearray(); p = 0
    for _ in range(16) :
        n = struct.unpack_from('<H', raw, p)[0]; p += 2
        txt = raw[p : p + 2 * n].decode('utf-16le'); p += 2 * n
        new = fn(txt) if n else txt
        out += struct.pack('<H', len(new)) + new.encode('utf-16le')
    return bytes(out)

# --- RT_DIALOG (DLGTEMPLATEEX)
def edit_dialog(raw : bytes, fn) -> bytes :
    if struct.unpack_from('<HH', raw, 0) != (1, 0xFFFF) : raise DllPatchError('dialog is not a DLGTEMPLATEEX')
    out = bytearray(raw[:26]); p = 26
    nitems = struct.unpack_from('<H', raw, 16)[0]
    style = struct.unpack_from('<I', raw, 12)[0]
    def sz_or_ord(edit) :
        nonlocal p
        w = struct.unpack_from('<H', raw, p)[0]
        if w == 0xFFFF : r = raw[p : p + 4]; p += 4; return r
        end = p
        while struct.unpack_from('<H', raw, end)[0] : end += 2
        txt = raw[p : end].decode('utf-16le'); p = end + 2
        if edit : txt = fn(txt)
        return txt.encode('utf-16le') + b'\0\0'
    def align() :
        nonlocal p
        while len(out) % 4 : out.append(0)
        p = (p + 3) & ~3
    out += sz_or_ord(False); out += sz_or_ord(False); out += sz_or_ord(True)   # menu, class, title
    if style & 0x40 :                          # DS_SETFONT: point size, weight, italic, charset, face
        out += raw[p : p + 6]; p += 6; out += sz_or_ord(False)
    for _ in range(nitems) :
        align()
        out += raw[p : p + 24]; p += 24
        out += sz_or_ord(False); out += sz_or_ord(True)
        n = struct.unpack_from('<H', raw, p)[0]
        out += raw[p : p + 2 + n]; p += 2 + n
    return bytes(out)

# --- RT_DIALOG items: parsed into dicts and written back (DLGTEMPLATEEX)
def dialog_items(raw : bytes) -> tuple[bytes, list[dict]] :
    # -> (header incl. title / font, items); item: style, exstyle, help, x, y, cx, cy, id, cls, text, extra (raw)
    if struct.unpack_from('<HH', raw, 0) != (1, 0xFFFF) : raise DllPatchError('dialog is not a DLGTEMPLATEEX')
    p = 26
    def sz_or_ord() :
        nonlocal p
        w = struct.unpack_from('<H', raw, p)[0]
        if w == 0xFFFF : r = struct.unpack_from('<H', raw, p + 2)[0]; p += 4; return r
        end = p
        while struct.unpack_from('<H', raw, end)[0] : end += 2
        txt = raw[p : end].decode('utf-16le'); p = end + 2
        return txt
    sz_or_ord(); sz_or_ord(); sz_or_ord()
    if struct.unpack_from('<I', raw, 12)[0] & 0x40 : p += 6; sz_or_ord()
    head = raw[:p]; items = []
    for _ in range(struct.unpack_from('<H', raw, 16)[0]) :
        p = (p + 3) & ~3
        hid, ex, style, x, y, cx, cy, cid = struct.unpack_from('<IIIhhhhI', raw, p); p += 24
        cls = sz_or_ord(); text = sz_or_ord()
        n = struct.unpack_from('<H', raw, p)[0]; extra = raw[p + 2 : p + 2 + n]; p += 2 + n
        items.append(dict(help = hid, exstyle = ex, style = style, x = x, y = y, cx = cx, cy = cy, id = cid,
                          cls = cls, text = text, extra = extra))
    return head, items

def build_dialog(head : bytes, items : list[dict]) -> bytes :
    out = bytearray(head)
    struct.pack_into('<H', out, 16, len(items))
    def sz_or_ord(v) :
        return struct.pack('<HH', 0xFFFF, v) if isinstance(v, int) else v.encode('utf-16le') + b'\0\0'
    for it in items :
        while len(out) % 4 : out.append(0)
        out += struct.pack('<IIIhhhhI', it['help'], it['exstyle'], it['style'], it['x'], it['y'], it['cx'], it['cy'], it['id'])
        out += sz_or_ord(it['cls']) + sz_or_ord(it['text']) + struct.pack('<H', len(it['extra'])) + it['extra']
    return bytes(out)

def edit_settings_page(raw : bytes, full : bool) -> bytes :
    # dialog 111: effect switch names, "Reset" label + drop-down (see SYXG50_GUI)
    head, items = dialog_items(raw)
    ids = [it['id'] for it in items]
    for it in items :
        if it['id'] in EFFECT_SWITCHES :
            it['text'], it['x'], it['cx'] = EFFECT_SWITCHES[it['id']]
        if it['id'] == VMAP_CONTROL_ID :
            it['cx'] = 80                       # room for the Reset drop-down on its right
    if RESET_CONTROL_ID not in ids :
        x = 98 if full else 10
        label = dict(help = 0, exstyle = 0, style = 0x50020000, x = x, y = 143, cx = 24, cy = 10, id = 0xFFFFFFFF,
                     cls = 0x82, text = 'Reset', extra = b'')
        combo = dict(help = 0, exstyle = 0, style = 0x50210003, x = x + 24, y = 141, cx = 36, cy = 40,
                     id = RESET_CONTROL_ID, cls = 0x85, text = '', extra = b'')
        items += [label, combo]
    return build_dialog(head, items)

PRESET_PANEL_POS = (160, 1)            # PresetPanel.bmp in bitmap 101
PRESET_BUTTONS_X = 160                 # PresetButtons.bmp appended to bitmap 106 (160 x 16 -> 190 x 16)

def dib_rows(dib : bytes) -> tuple[int, int, int, list[bytearray]] :
    # 24-bit DIB -> (width, height, header size, rows top-down without padding)
    hs, w, h, _, bpp = struct.unpack_from('<IiiHH', dib, 0)
    if bpp != 24 : raise DllPatchError(f'bitmap is {bpp} bit, expected 24')
    stride = ((w * 24 + 31) // 32) * 4; rows = abs(h)
    out = [bytearray(dib[hs + r * stride : hs + r * stride + 3 * w]) for r in range(rows)]
    if h > 0 : out.reverse()
    return w, rows, hs, out

def rows_to_dib(w : int, rows : list) -> bytes :
    stride = ((w * 24 + 31) // 32) * 4
    body = b''.join(bytes(r) + b'\0' * (stride - 3 * w) for r in reversed(rows))
    return struct.pack('<IiiHHIIiiII', 40, w, len(rows), 1, 24, 0, len(body), 3780, 3780, 0, 0) + body

def apply_preset_bitmaps(data : bytearray) :
    # bitmap 101: the static part of the preset control; bitmap 106: pressed buttons appended on the right
    res = find_resources(data, RT_BITMAP)
    off, size = res[101]
    w, h, hs, rows = dib_rows(bytes(data[off : off + size]))
    pw, ph, panel = bmp_to_dib24((BITMAP_DIR / 'PresetPanel.bmp').read_bytes())
    _, _, _, prows = dib_rows(panel)
    x, y = PRESET_PANEL_POS
    for r in range(ph) : rows[y + r][3 * x : 3 * (x + pw)] = prows[r]
    new = rows_to_dib(w, rows)
    if len(new) != size : raise DllPatchError('bitmap 101 changed size')
    data[off : off + size] = new
    entry = resource_entries(data, RT_BITMAP).get(106)
    old = resource_data(data, entry)
    w, h, hs, rows = dib_rows(old)
    if w == PRESET_BUTTONS_X :
        bw, bh, btn = bmp_to_dib24((BITMAP_DIR / 'PresetButtons.bmp').read_bytes())
        _, _, _, brows = dib_rows(btn)
        rows = [rows[r] + (brows[r] if r < bh else rows[r][-3:] * bw) for r in range(h)]
        replace_resource_data(data, entry, rows_to_dib(w + bw, rows))

def apply_gui(data : bytearray, full : bool) :
    apply(data, SYXG50_GUI, 'Settings page reset drop-down, panel preset buttons')
    apply_preset_bitmaps(data)
    text_virtual_size(data, GUI_CAVE_END)
    data_virtual_size(data, GUI_DATA_END)
    entry = resource_entries(data, RT_DIALOG).get(111)
    if entry is None : raise DllPatchError('dialog 111 not found in the DLL')
    old = resource_data(data, entry); new = edit_settings_page(old, full)
    if new != old : replace_resource_data(data, entry, new)
    print('  Settings page: effect switches named with their CC numbers')

# --- RT_VERSION: VS_VERSIONINFO tree
def _vi_parse(raw, p) :
    length, vlen, vtype = struct.unpack_from('<HHH', raw, p)
    end = p + length; q = p + 6; k = q
    while struct.unpack_from('<H', raw, k)[0] : k += 2
    key = raw[q : k].decode('utf-16le'); q = (k + 2 + 3) & ~3
    vbytes = vlen * 2 if vtype == 1 else vlen
    value = raw[q : q + vbytes]; q = (q + vbytes + 3) & ~3
    kids = []
    while q < end :
        kid, q2 = _vi_parse(raw, q); kids.append(kid); q = (q2 + 3) & ~3
    return [key, vtype, value, kids], end

def _vi_build(node) -> bytes :
    key, vtype, value, kids = node
    b = bytearray(6) + key.encode('utf-16le') + b'\0\0'
    while len(b) % 4 : b.append(0)
    b += value
    vlen = len(value) // 2 if vtype == 1 else len(value)
    for kid in kids :
        while len(b) % 4 : b.append(0)
        b += _vi_build(kid)
    struct.pack_into('<HHH', b, 0, len(b), vlen, vtype)
    return bytes(b)

def edit_version(raw : bytes, fn) -> bytes :
    root, _ = _vi_parse(raw, 0)
    def walk(node) :
        key, vtype, value, kids = node
        if vtype == 1 and value :
            txt = value.decode('utf-16le').rstrip('\0')
            new = fn(key, txt)
            if new != txt : node[2] = new.encode('utf-16le') + b'\0\0'
        for k in kids : walk(k)
    walk(root)
    return _vi_build(root)

def apply_names(data : bytearray, model : str | None, table_name : str | None) :
    n = MODEL_NUMBER.get(model or '')
    if not n :
        # MU50 keeps the S-YXG50 names, but the default table name in the string table must still be the
        # table just built: without a SoftSynth entry in the ini (--embed, or a host that starts the DLL
        # without finding its ini) the DLL loads that name, and SXGBIN41.TBL does not exist any more
        if model and table_name :
            entry = resource_entries(data, RT_STRING).get(1)
            if entry is None : raise DllPatchError('string table 1 not found in the DLL')
            old = resource_data(data, entry)
            new = edit_string_table(old, lambda t : table_name if t.upper().endswith('.TBL') else t)
            if new != old : replace_resource_data(data, entry, new)
            print(f'  names (S-YXG50 kept): default table {table_name}')
        return
    sx = f'S-YXG{n}'
    def text(t) : return t.replace('S-YXG50', sx)
    def strings(t) :
        if t == 'xg50' : return f'mu{n}'
        if table_name and t.upper().endswith('.TBL') : return table_name
        return text(t)
    VERSION = {
        'FileDescription'  : ('Yamaha S-YXG50 VSTi (4MB)', 'Yamaha S-YXG50 VSTi', f'Yamaha {sx} VSTi'),
        'InternalName'     : ('S-YXG50-4MB', 'S-YXG50', sx),
        'OriginalFilename' : ('S-YXG50-4MB.DLL', 'S-YXG50.DLL', f'{sx}.DLL'),
        'ProductName'      : ('Yamaha S-YXG50 Portable VSTi', None, f'Yamaha {sx} Portable VSTi'),
    }
    def version(key, t) :
        if key in VERSION and t in VERSION[key][:2] : return VERSION[key][2]
        return t
    done = []
    for rtype, rid, edit, label in ((RT_DIALOG, 112, lambda r : edit_dialog(r, text), 'dialog 112'),
                                     (RT_STRING, 1, lambda r : edit_string_table(r, strings), 'string table 1'),
                                     (RT_VERSION, 1, lambda r : edit_version(r, version), 'version info')) :
        entry = resource_entries(data, rtype).get(rid)
        if entry is None : raise DllPatchError(f'{label} not found in the DLL')
        old = resource_data(data, entry)
        new = edit(old)
        if new != old :
            replace_resource_data(data, entry, new)
            done.append(label)
    print(f'  names ({sx}): ' + (', '.join(done) if done else 'already applied'))


# version info: build date and credits (all models)
#   fixed file version 2016,4,25,18     -> YYYY,MM,DD,0 (conversion date; binary, so 2026,10,3,0)
#   FileVersion        2016.04.25.0018  -> YYYY.MM.DD
#   LegalCopyright     ..., 2016 VEG    -> ..., 2016 VEG, 2026 Soundshock/NightFright
CREDITS = '2016 VEG, 2026 Soundshock/NightFright'

def apply_version_date(data : bytearray, today = None) :
    import datetime
    d = today or datetime.date.today()
    entry = resource_entries(data, RT_VERSION).get(1)
    if entry is None : raise DllPatchError('version info not found in the DLL')
    old = resource_data(data, entry)
    def strings(key, t) :
        t = t.replace('2016.04.25.0018', f'{d.year:04}.{d.month:02}.{d.day:02}')
        if '2016 VEG' in t and CREDITS not in t : t = t.replace('2016 VEG', CREDITS)
        return t
    new = bytearray(edit_version(old, strings))
    # VS_FIXEDFILEINFO right after the root key (L"VS_VERSION_INFO", padded): dwFileVersionMS/LS
    fixed = 6 + len('VS_VERSION_INFO\0') * 2
    fixed = (fixed + 3) & ~3
    assert struct.unpack_from('<I', new, fixed)[0] == 0xFEEF04BD
    struct.pack_into('<HHHH', new, fixed + 8, d.month, d.year, 0, d.day)     # MS = (year, month), LS = (day, 0)
    if bytes(new) != old :
        replace_resource_data(data, entry, bytes(new))
    print(f'  version: {d.year},{d.month},{d.day},0 / {d.year:04}.{d.month:02}.{d.day:02}, credits')


# ----------------------------------------------------------------------------- embedded tables
# --embed: table and wave file go into the DLL as RT_RCDATA resources named with their full file
# names (as in the 5 MB syxg50.dll: SXGBIN41.TBL / SXGWAVE4.TBL). syxg50.dll looks for the table
# name (ini [Config] SoftSynth, without ini: string table entry 7, see apply_names) as RT_RCDATA
# resource first and only then as a file; the wave file name comes from the table header.
RT_RCDATA = 10

def read_resources(data) -> list :
    # -> [(type, name, lang, codepage, bytes)], type/name: int id or str
    pe = struct.unpack_from('<I', data, 0x3C)[0]
    opt = pe + 24
    ddir = opt + (96 if struct.unpack_from('<H', data, opt)[0] == 0x10B else 112)
    base = rva_to_offset(data, struct.unpack_from('<I', data, ddir + 16)[0])
    def entries(d) :
        n = sum(struct.unpack_from('<HH', data, d + 12))
        return [struct.unpack_from('<II', data, d + 16 + 8 * i) for i in range(n)]
    def name(v) :
        if not v & 0x80000000 : return v
        o = base + (v & 0x7FFFFFFF); n = struct.unpack_from('<H', data, o)[0]
        return bytes(data[o + 2 : o + 2 + 2 * n]).decode('utf-16le')
    out = []
    for t, p1 in entries(base) :
        for n, p2 in entries(base + (p1 & 0x7FFFFFFF)) :
            for l, p3 in entries(base + (p2 & 0x7FFFFFFF)) :
                rva, size, cp, _ = struct.unpack_from('<IIII', data, base + p3)
                off = rva_to_offset(data, rva)
                out.append((name(t), name(n), l, cp, bytes(data[off : off + size])))
    return out

def build_resources(res : list, va : int) -> bytes :
    # IMAGE_RESOURCE_DIRECTORY tree: directories, then name strings, data entries and data
    def key(k) : return (0, k.upper()) if isinstance(k, str) else (1, k)
    tree = {}
    for t, n, l, cp, b in res : tree.setdefault(t, {}).setdefault(n, {})[l] = (cp, b)
    dirs = bytearray(); strings = bytearray(); dentries = bytearray(); blobs = bytearray()
    fix_str, fix_dir, fix_dat = [], [], []      # (position in dirs, index)
    def size_dir(d) : return 16 + 8 * len(d)
    # breadth-first layout
    level1 = sorted(tree, key=key)
    total_dirs = size_dir(level1) + sum(size_dir(tree[t]) for t in level1) + sum(size_dir(tree[t][n]) for t in level1 for n in tree[t])
    str_list = []; data_list = []
    def emit_dir(keys) :
        pos = len(dirs)
        named = [k for k in keys if isinstance(k, str)]
        dirs.extend(struct.pack('<IIHHHH', 0, 0, 0, 0, len(named), len(keys) - len(named)))
        for k in keys :
            dirs.extend(bytes(8))
        return pos
    root = emit_dir(level1)
    tpos = {t : emit_dir(sorted(tree[t], key=key)) for t in level1}
    npos = {(t, n) : emit_dir(sorted(tree[t][n])) for t in level1 for n in sorted(tree[t], key=key)}
    assert len(dirs) == total_dirs
    str_off = {}
    def sref(k) :
        if k not in str_off :
            str_off[k] = len(strings)
            strings.extend(struct.pack('<H', len(k)) + k.encode('utf-16le'))
            if len(strings) % 2 : strings.append(0)
        return str_off[k]
    def set_entry(dpos, i, k, target, is_dir) :
        e = dpos + 16 + 8 * i
        nm = (0x80000000 | (total_dirs + sref(k))) if isinstance(k, str) else k
        struct.pack_into('<II', dirs, e, nm, (0x80000000 | target) if is_dir else target)
    for i, t in enumerate(level1) : set_entry(root, i, t, tpos[t], True)
    for t in level1 :
        for i, n in enumerate(sorted(tree[t], key=key)) : set_entry(tpos[t], i, n, npos[(t, n)], True)
    while len(strings) % 4 : strings.append(0)
    dentry_base = total_dirs + len(strings)
    nde = sum(len(tree[t][n]) for t in tree for n in tree[t])
    data_base = dentry_base + 16 * nde
    data_base = (data_base + 7) & ~7
    k = 0
    for t in level1 :
        for n in sorted(tree[t], key=key) :
            for i, l in enumerate(sorted(tree[t][n])) :
                cp, b = tree[t][n][l]
                set_entry(npos[(t, n)], i, l, dentry_base + 16 * k, False)
                rva = va + data_base + len(blobs)
                dentries.extend(struct.pack('<IIII', rva, len(b), cp, 0))
                blobs.extend(b)
                while len(blobs) % 8 : blobs.append(0)
                k += 1
    out = bytes(dirs) + bytes(strings) + bytes(dentries)
    out += bytes(data_base - len(out))
    return out + bytes(blobs)

def embed_files(data : bytearray, files : list[tuple[str, bytes]]) -> bytearray :
    # files: [(resource name, bytes)] -> RT_RCDATA, language neutral; existing RCDATA tables
    # (the 5 MB syxg50.dll's SXGBIN41.TBL / SXGWAVE4.TBL) are replaced
    def is_table(r) : return r[0] == RT_RCDATA and isinstance(r[1], str) and r[1].upper().endswith(('.TBL', '.UPCM'))
    old = [r for r in read_resources(data) if is_table(r)]
    res = [r for r in read_resources(data) if not is_table(r)]
    if old : 
        print('  removed old tables: ' + ', '.join(f'{r[1]} ({len(r[4]):,} bytes)' for r in old))
    for name, b in files :
        res.append((RT_RCDATA, name.upper(), 0, 0, b))
    secs = sections(data)
    h, vs, va, rs, rp = secs[-1]
    if data[h : h + 5] != b'.rsrc' or rp + rs != len(data) :
        raise DllPatchError('.rsrc is not the last section, the tables cannot be embedded')
    rsrc = build_resources(res, va)
    pe = struct.unpack_from('<I', data, 0x3C)[0]; opt = pe + 24
    salign, falign = struct.unpack_from('<II', data, opt + 32)
    raw = ((len(rsrc) + falign - 1) // falign) * falign
    out = bytearray(data[:rp]) + rsrc + bytes(raw - len(rsrc))
    struct.pack_into('<I', out, h + 8, len(rsrc))          # VirtualSize
    struct.pack_into('<I', out, h + 16, raw)               # SizeOfRawData
    struct.pack_into('<I', out, opt + 56, ((va + len(rsrc) + salign - 1) // salign) * salign)   # SizeOfImage
    ddir = opt + (96 if struct.unpack_from('<H', out, opt)[0] == 0x10B else 112)
    struct.pack_into('<II', out, ddir + 16, va, len(rsrc))
    print(f'  embedded: ' + ', '.join(f'{n} ({len(b):,} bytes)' for n, b in files))
    return out


# ----------------------------------------------------------------------------- API

def Is_Dll(path : Path) -> bool :
    # a PE file (MZ header) among the input files
    with open(path, 'rb') as f :
        head = f.read(2)
    return head == b'MZ'

def Identify(path : Path) -> str :
    # -> description; raises DllPatchError if the file is not a syxg50.dll
    data = path.read_bytes()
    c = crc(data)
    if c in KNOWN :
        return KNOWN[c][1]
    # patched DLLs: .rsrc may have grown by a few 4 KB pages (names, see apply_names)
    if not any(0 <= len(data) - n <= 0x10000 and (len(data) - n) % 0x1000 == 0 for n in SIZES) :
        raise DllPatchError(f'{path.name}: not a supported syxg50.dll (CRC32 {c}, {len(data):,} bytes), '
                            'expected syxg50.dll with 626,688 or 5,070,848 bytes')
    # a file that already carries (some of) the patches: checked patch by patch
    return f'{path.name}, not an original syxg50.dll (CRC32 {c}), checking patch by patch'

def Patch(path : Path, full : bool, model : str | None = None, table_name : str | None = None,
          embed : list[tuple[str, bytes]] | None = None) -> bytes :
    # full = False: "Enhanced" (classic table layout), True: "Full" (big table layout)
    data = bytearray(path.read_bytes())
    Identify(path)
    print(f'patching {path.name}: ' + ('"Full" (loop length + table size limits)' if full else '"Enhanced" (loop length)'))
    apply(data, SYXG50_INI, 'ini [Config] / SoftSynth')
    apply(data, SYXG50_24BIT, '24-bit loop length')
    apply(data, SYXG50_DRUMEG, 'drum setup EG offsets for ext drum voices')
    text_virtual_size(data, DRUMEG_CAVE_END)
    apply(data, SYXG50_FX, 'effect types without counterpart -> nearest type')
    text_virtual_size(data, FX_CAVE_END)
    apply(data, SYXG50_FXFADE, 'effect fade-in after a type change: 0.3-1 s -> 80-90 ms')
    if full :
        if len(data) == 5070848 :
            print('  note: 5 MB syxg50.dll, its embedded (classic) tables are not used, the ini selects the table')
        apply(data, SYXG50_BIG, 'table size limits (big layout)')
        text_virtual_size(data, BIG_CAVE_END)
        apply_voicemap(data)
    apply_bitmaps(data, model)
    apply_gui(data, full)
    apply_names(data, model, table_name)
    apply_version_date(data)
    if embed :
        data = embed_files(data, embed)
    struct.pack_into('<I', data, pe_checksum_offset(data), pe_checksum(data))
    return bytes(data)

def Write(dll_path : Path, out_dir : str, table_name : str, full : bool, model : str | None = None,
          embed : list[tuple[str, bytes]] | None = None, dll_name : str | None = None) :
    # the patched DLL keeps the name of the supplied DLL (any name, e.g. mu800.dll), the ini gets the
    # same name with .ini (the DLL looks for <its own name>.ini). The ini selects the table.
    # A DLL supplied as syxg50.dll (or its backup syxg50.orig.dll) is written under the model's name
    # (syxgmu50.dll, syxg80.dll ... syxg1000.dll, see Model_Dll_Name), with and without --embed, so the
    # original syxg50.dll is never overwritten; other names are kept.
    # embed (--embed): table and wave file go into the DLL (see embed_files), and no
    # ini is needed: the DLL finds the table by the name in its string table (an old ini of that name
    # is removed, it would point the DLL elsewhere).
    # dll_name: fixed output name (multi-model conversion: syxg<n>.dll, with and without --embed)
    import os, shutil
    name = dll_path.name if dll_path.suffix else dll_path.name + '.dll'
    if name.lower().endswith('.orig.dll') : name = name[:-9] + '.dll'
    if name.lower() == 'syxg50.dll' and (model in MODEL_NUMBER or model == 'MU50') :
        name = Model_Dll_Name(model)
    if dll_name : 
        name = dll_name
    stem = Path(name).stem
    out = Path(out_dir) / name
    src = dll_path
    if out.exists() and os.path.samefile(out, dll_path) :
        # the supplied DLL sits in the output folder: keep the original as <name>.orig.dll and
        # always patch from that copy (so a rerun with another layout starts from the original again)
        backup = out.with_name(f'{stem}.orig{out.suffix}')
        if not backup.exists() :
            shutil.copy2(dll_path, backup)
            print(f'dllpatch: original saved as {backup}')
        src = backup
    else :
        # renamed output (syxg50.dll -> syxg<n>.dll): patch from <supplied name>.orig.dll if an earlier run left one
        orig = dll_path.with_name(f'{dll_path.stem}.orig{dll_path.suffix}')
        if orig.exists() and not dll_path.name.lower().endswith('.orig.dll') : src = orig
    data = Patch(src, full, model, table_name, embed)
    ini = out.with_name(f'{stem}.ini')
    state = 'replaced' if out.exists() else 'wrote'
    out.write_bytes(data)
    print(f'dllpatch: {state} {out}, CRC32 {crc(data)}' + (f', {len(data):,} bytes' if embed else ''))
    if embed :
        if ini.exists() :
            ini.unlink()
            print(f'dllpatch: removed {ini} (not needed with embedded tables)')
    else :
        state = 'replaced' if ini.exists() else 'wrote'
        ini.write_bytes(INI_TEMPLATE.format(table=table_name).encode('ascii'))
        print(f'dllpatch: {state} {ini}')
