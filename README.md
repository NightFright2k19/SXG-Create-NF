# SXG-Create

Converts the ROM sets of Yamaha MU-series tone generators (MU50 to MU1000) into tables and wave data for the **S-YXG50** soft synthesizer (`syxg50.dll`), and patches the DLL so that it can play them as close to the original module as the S-YXG50 engine allows.

This document is the reference for the current state of SXG-Create: what changed in this version, supported models, command line, output files, the DLL patches, what the conversion does for each model, how the results were checked against the S-MU2000, and what is still unsolved.

## Table of contents

- [Changes compared to the original SXG-Create](#changes-compared-to-the-original-sxg-create)
- [Quick start](#quick-start)
- [Command line parameters](#command-line-parameters)
- [Supported models and ROM sets](#supported-models-and-rom-sets)
- [Output files and table layouts](#output-files-and-table-layouts)
- [Why the wave files got bigger](#why-the-wave-files-got-bigger)
- [DLL patching](#dll-patching)
- [MU Basic voice maps](#mu-basic-voice-maps)
- [What the conversion does, per model](#what-the-conversion-does-per-model)
- [Verification against the S-MU2000 and the S-YXG50](#verification-against-the-s-mu2000-and-the-s-yxg50)
- [Known limitations and unsolved problems](#known-limitations-and-unsolved-problems)
- [Using the converted DLLs](#using-the-converted-dlls)
- [Behaviour on reruns](#behaviour-on-reruns)
- [Investigation tools](#investigation-tools)
- [Credits and license](#credits-and-license)

---

## Changes compared to the original SXG-Create

This fork extends [Soundshock's SXG-Create](https://github.com/Soundshock/SXG-Create), which converted the MU50 and MU80 (MU90 work in progress) into classic S-YXG50 tables and left the DLL setup to the user. Below is the complete list of changes, grouped by topic. Most of the sound changes were measured against the **S-MU2000** (Yamaha's MU2000 software version, which runs the MU2000/MU1000 firmware and sound data) and against recordings of a real **MU1000**; see [Verification](#verification-against-the-s-mu2000-and-the-s-yxg50). Details for each point are in the sections further down.

### New models

- **MU90 / MU90B** completed (was work in progress): word-interleaved wave ROMs (two 16-bit halves of a 32-bit bus), all four sample formats (16 bit, 12 bit, 8 bit, ADPCM), 42-byte drum voices, the bank map order XG (LSB) / SFX (MSB) / GS, and the MU90B program ROM.
- **MU100** (new): three 32-bit wave ROM pairs in one address space, three wavedata tables with their own offset tables, 32-bit voice program maps, MU100 Native and MU Basic voice maps.
- **MU128 and MU1000** (new): program flash from high/low 16-bit halves, 84-byte elements (mapped almost 1:1, verified on 2,317 elements shared with the MU100), 42-byte drum voices with byte 0 moved to `+23`, voice maps MU Native / MU Basic, GS, MSB 48 and GM2.
- **MU2000** detected, but not converted: it has the same sound data as the MU1000, so the MU1000 set is used instead (see [Supported models](#supported-models-and-rom-sets)).
- **MU Basic voice map** for MU100 / MU128 / MU1000: the MU90-compatible map is built into the same table as the native one and can be switched in the Setup dialog (MU Native is the default). The earlier `--mu-basic` switch was removed.

### Table formats

- **Big table layout** for MU100 / MU128 / MU1000: 32-bit voice, ext voice and wavedata offsets, 32-bit sample addresses, 24-bit drum start offset and loop length, **768 multisamples** in three pages of 256, **30-bit drum sample addresses**. The classic layout stays for MU50 / MU80 / MU90.
- **24-bit loop lengths** (both layouts): loops longer than 65,535 samples (MU80 pads, MU90) are written in full instead of being clamped.
- **Ext drum voices** are placed in voice bank A (the DLL reads their offsets as 16 bit from bank A).
- **Duplicated voice banks** (GS <-> XG side) get their own program map. The MU80's MSB 126/127 pointed to an empty map, so all 128 programs read the 8-byte debug label in front of the first voice as a voice.
- **MU50 ext drum voices** are read from the program ROM's own table (location from TaleTN's MUTable) instead of a hand-made list. Two entries of that list were wrong: the GS-mode C/M Kit keys 81 / 102 and SFX Set keys 57 / 78 played SynMalet and Bird 2 instead of FootStep and Tweet.

### Sample conversion

- **ADPCM loops** are made seamless: the decoder state is emulated through the loop passes until it settles, the transitional passes go in front of the loop (lead-in), the settled pass becomes the loop.
- **Reverse flag** (MU90 and later): samples the hardware plays backwards are reversed (toms of the standard kits, MelodTom, Real Tom; Rev Tom / Rev Kick).
- **Long drum bodies** in the classic layout (four XG open hi-hats with 70,626 samples): the loop start is moved earlier instead of cutting off the attack.
- **MU80 format bit 6** (`0xC0` vs `0x80`): investigated, no audible meaning; both are 16-bit PCM.

### Voices and elements

- **LFO pitch modulation depth** read with 6 bits instead of 5 (MU80 / MU90 and later); the old mask halved the vibrato of voices like Siren, Ghost, Goblins, Wind.
- **Element HPF** (MU100: element byte `+69`, MU128/MU1000: `+80`): baked into filtered copies of the multisamples, every 6 keys in the low range; the copies follow the coarse-tuned key range. 66 MU100 voices and 128 MU1000 voices use it (e.g. Oboe, muted/jazz/overdrive guitars, slap bass, rock organ); without it they were up to 13-19 dB too loud and dull in the low keys.
- **Voices with 3 or 4 elements** (22 MU1000 voices): folded into the two elements the DLL can play instead of dropping elements 3 and 4 (stereo pairs, key splits, layers; `elemreduce.py`), incl. per-member wave start offsets and baked amp EGs for percussive key-split members.
- **Rising decay 2** (MU80 and later): decay 1 level raised to 64 where decay 2 rises again, because the DLL ends notes below that level (Lite Org, WireLead, synecho2, Bounce, Ana Echo).

### Drum keys

- **Drum EG rate** (byte 13): the original's MU80 rule S-YXG50 = MU - `0x21` was checked against the S-YXG50 table (245 of 253 MU80 drum voices) and extended to the MU90 and later (426 of 460).
- **HPF cutoff** (MU100 and later): baked into a filtered copy of the drum sample.
- **Level offset** (MU100 and later, byte `+29`): added to the key's level (MU1000 Ride 1 was 13.6 dB too loud).
- **Instant attack with equal decay rates** and **short decay 1 before a fast decay 2** (MU90 and later): converted to an attack mode of the DLL without its 18-120 ms hold (Seq Click, Hi Q, Click Noise, Short Guiro: 3.5-8 dB too loud before, now within 1-2 dB).
- **Velocity pitch / LPF cutoff sensitivity** (MU90 and later): reproduced with generated ext drum voices (`drumvel.py`).

### DLL patching (new)

- SXG-Create patches a supplied `syxg50.dll` (626,688 bytes or the 5 MB version, any file name) and writes a matching ini; the original is kept as `<name>.orig.dll`. Patch level follows the table: **"Enhanced"** (classic) or **"Full"** (big layout). Already-patched DLLs are accepted and checked patch by patch.
- **Table loading:** ini section/key `[Config]` / `SoftSynth`, 24-bit loop length, and for "Full" all big-layout parser changes (program maps, wavedata offsets with three pages, drum voice fields, formats, root key).
- **Effects:** missing effect types mapped to the nearest available type, return levels scaled per type (calibrated against the S-MU2000) and recomputed on a type change, fade-in after a type change shortened from 0.3-1 s to 80-90 ms.
- **Drum setup EG offsets** for ext drum voices no longer act twice as strong.
- **Voice map switch** ("Full"): checkbox "MU Basic voice map" in the Setup dialog switches MU100 / MU128 / MU1000 tables between MU Native and MU Basic, saved with the host's plugin state like the other Setup options (no files written); optional start value `MUBasic=1` in the ini; works with external and embedded tables. A change takes effect immediately for new notes on all parts (no program change needed).
- **Resources:** panel bitmap per model, names in About dialog / string table / version info (S-YXG<n>), default table name (MU50 too), conversion date and credits in the version info.

### Usage and command line

- **`--embed`:** table and wave data are stored inside the patched DLL (old `SXGBIN41.TBL` / `SXGWAVE4.TBL` removed), no ini needed.
- **`roms` folder:** ROMs are also read from `roms` next to `main.py`, including subfolders.
- **Several models in one run:** all complete ROM sets found are converted, DLLs/inis named `syxg80.dll` ... `syxg1000.dll` (MU50: `syxgmu50.dll`); MU2000 is skipped when the MU1000 set is there.
- **Wildcards** (`*.bin`) are expanded by the script; `SXG_NO_PAUSE=1` skips the final key press.
- **Output folder** next to the program ROM, or next to the DLL / `main.py` for ROMs from the `roms` folder.
- **Investigation tools** added: `analyze_drum_eg.py`, `analyze_voice_params.py`, `analyze_sample_flags.py`, `list_long_loops.py`.

---

## Quick start

```
python main.py <ROM files...> [syxg50.dll] [--embed]
```

You can also drag & drop all files onto `main.py`.

- **Inputs:** ROM files in any order. SXG-Create detects the model from the CRC32 of the files, so the file names don't matter.
- **`roms` folder:** ROMs in a folder `roms` next to `main.py` (any subfolders) are used as well. Files larger than 64 MB in it are ignored.
- **Optional DLL:** one `syxg50.dll` under any file name. SXG-Create writes a patched copy plus a matching `.ini` (or, with `--embed`, a DLL that contains the table).
- **Output folder:** next to the (first) program ROM given on the command line. For ROMs from the `roms` folder: next to the DLL, or next to `main.py` when no DLL is given.
- **Requirements:** Python 3.12 or newer. No extra packages.

### Example (MU1000)

```
python main.py mu1000-v2.01-h.bin mu1000-v2.01-l.bin xv364a0.ic49 xv365a0.ic50 xw848a0.ic53 xw849a0.ic54 syxg50.dll
```

This writes:

```
SXGMU1KX.TBL     table
SXGMU1KX.UPCM    wave data
syxg50.dll       patched DLL ("Full"); the original is kept as syxg50.orig.dll
syxg50.ini       SoftSynth=SXGMU1KX.TBL
```

Copy all four files into one folder.

### Example (all models from the `roms` folder, embedded)

```
roms/mu50/...  roms/mu80/...  roms/mu90/...  roms/mu100/...  roms/mu128/...  roms/mu1000/...

python main.py syxg50.dll --embed
```

This writes `syxgmu50.dll`, `syxg80.dll`, `syxg90.dll`, `syxg100.dll`, `syxg128.dll` and `syxg1000.dll`, each a self-contained DLL with its table and wave data inside. The supplied `syxg50.dll` stays unchanged. At the end a summary lists each model as done or failed.

> **zsh / bash:** an unquoted `*.bin` that matches nothing makes zsh stop with "no matches found" before Python starts. Leave the pattern out (the `roms` folder is searched anyway), quote it (`'*.bin'`) or use `roms/**/*.bin`.

---

## Command line parameters

| Parameter | Meaning |
|---|---|
| `<ROM files>` | Program ROM(s) and wave ROMs of one or more models, in any order (see [Supported models](#supported-models-and-rom-sets)). Optional if the `roms` folder holds them. Wildcards are allowed. |
| `<dll>` | Optional. A `syxg50.dll`, under any file name (`syxg50.dll`, `mu800.dll`, ...). It is recognised by its content, not its name. A DLL in the `roms` folder is used if none is given on the command line. See [DLL patching](#dll-patching). |
| `--embed` | **New.** Puts table and wave file into the patched DLL as resources instead of writing them as files (see [Embedded tables](#embedded-tables---embed)). Needs a DLL. |

The table layout and the DLL patch level are chosen automatically from the detected model. `--out-dir` and `--dll-name` exist as well, but only for the per-model runs that `main.py` starts itself in a multi-model conversion.

The script waits for a key press at the end (so a drag & drop window stays open). Set the environment variable `SXG_NO_PAUSE=1` to skip that, e.g. in batch files.

---

## Supported models and ROM sets

| Model | Program ROM(s) | Wave ROMs | Table layout |
|---|---|---|---|
| MU50 (xr174c0 v1.05) | `xr174c0.ic7` | `xq057c0.ic18`, `xq058c0.ic19` | classic |
| MU80 (xq556a0 v1.04) | `yamaha_mu80.bin` / `xq556a0.ic8` | `xq012b0-822.bin`, `xq013b0-823.bin`, `xq089b0-824.bin`, `xq090b0-825.bin` | classic |
| MU90 (xs519d0 v1.01) | `xs519d0.ic9` | `xs518a0.ic22`, `xs743a0.ic23` | classic |
| MU90B (xt040c0 v1.01) | `xt040c0.ic9` | `xs518a0.ic22`, `xs743a0.ic23` | classic |
| MU100 (xu50720 v1.11) | `xu50720.ic11` | `xs518b0.ic34`, `xs743b0.ic35`, `xt445a0-828.ic36`, `xt461a0-829.ic37`, `xt462a0.ic39`, `xt463a0.ic38` | big |
| MU128 (v2.00) | `mu128-v2.00-h.bin`, `mu128-v2.00-l.bin` | `xv364a0.ic53`, `xv365a0.ic54`, `xv366a0.ic57`, `xv376a0.ic58` | big |
| MU1000 (v2.01) | `mu1000-v2.01-h.bin`, `mu1000-v2.01-l.bin` | `xv364a0.ic49`, `xv365a0.ic50`, `xw848a0.ic53`, `xw849a0.ic54` | big |
| MU2000 (v2.01) | detected, but not converted | | |

File names are only examples; the files are recognised by their CRC32.

> **MU2000:** it has the same voice data as the MU1000 (1,635 voices, 1,027 drum voices, 2,901 samples, the same wave ROMs). Only the element filter/level scaling is stored differently: instead of 4 break points, each element holds an index into 1,377 tables of 128 notes, which lie in the upper half of the 4 MB firmware image (at `0x23CED0`, location from TaleTN's MUTable). An earlier version of this README said this table was missing from the ROM dump; that was wrong. The tables are the MU1000's break points interpolated per note, so they convert back to break points (1,376 of 1,377 exactly, one within 1 step on one note). A test conversion of the MU2000 set rendered bit-identically to the MU1000 conversion (464 voices, 6,496 notes) with a byte-identical wave file. Since the result is the same, SXG-Create uses the MU1000 set (the MU2000 set is skipped when both are present, otherwise a message asks for the MU1000 set).

The S-YXG50's own tables and `Vampire.dll` are recognised as well, but they are not a conversion source.

---

## Output files and table layouts

| Models | Layout | DLL patch | Table | Wave data | Wave size |
|---|---|---|---|---|---|
| MU50 | classic | "Enhanced" | `SXGMU50a1.TBL` | `SXGMU50a1.UPCM` | 6.7 MB |
| MU80 | classic | "Enhanced" | `SXGMU80a1.TBL` | `SXGMU80a1.UPCM` | 12.7 MB |
| MU90 / MU90B | classic | "Enhanced" | `SXGMU90t.TBL` | `SXGMU90.UPCM` | 13.3 MB |
| MU100 | big | "Full" | `SXGMU100X.TBL` | `SXGMU100X.UPCM` | 51.8 MB |
| MU128 | big | "Full" | `SXGMU128X.TBL` | `SXGMU128X.UPCM` | 70.8 MB |
| MU1000 | big | "Full" | `SXGMU1KX.TBL` | `SXGMU1KX.UPCM` | 87.3 MB |

The MU100, MU128 and MU1000 tables contain both voice maps (native and MU Basic); the wave file is the same as for the native map alone. Earlier versions wrote a separate `...BX` set with the old `--mu-basic` switch; these files are no longer needed, and `--mu-basic` is ignored with a note.

With `--embed`, the DLL contains both files and is correspondingly large (MU90 14 MB, MU100 53 MB, MU128 72 MB, MU1000 88 MB).

Classic tables also get a `<table>.TBL.rehex-meta` file, a debug description of the table.

### Classic layout (MU50 / MU80 / MU90)

This is the original S-YXG50 table format:

- 16-bit voice and ext voice offsets.
- 24-bit sample addresses, so at most 16 MB of wave data.
- At most 256 multisamples.
- Samples as unsigned 16 bit or 8 bit.

The one extension is 24-bit loop lengths, which the "Enhanced" DLL patch enables (some MU80 and MU90 loops are longer than 65,535 samples).

### Big layout (MU100 / MU128 / MU1000)

This needs the "Full" DLL patch. Compared to the classic layout:

| Field | Classic | Big |
|---|---|---|
| Voice program maps | 16 bit, bank A/B encoded | 32-bit LE byte offset from voice bank A |
| Wavedata offset table | 16 bit | 32-bit LE |
| Ext drum voice offsets | 16 bit (bank A only) | 32-bit LE |
| Multisamples | 256 | **768** in three pages of 256 (see below) |
| Wavedata sample address | 24 bit at `+0x09`, format at `+0x0C` | 32 bit at `+0x09`, format at `+0x0D` |
| Drum voice ext index | `+0x10..+0x11` BE | `+0x10..+0x11` LE (`+0x11 = 0xFF`: internal sample) |
| Drum voice root key | `+0x12` | `+0x0A` |
| Drum voice start / loop length | 16 / 16 bit | 24 / 24 bit (`+0x12`, `+0x15`) |
| Drum voice sample address | 24 bit at `+0x18`, format at `+0x1B` | **30 bit** at `+0x18` (max. 1 GB), top two bits = format |
| Sample data | U16 / U8 | U16 / U8 (unchanged) |

**Multisample pages:** an element stores its wave number in one byte. The converter assigns each voice to a page so that all multisamples of the voice are in that page: page 0 voices go to voice bank A, page 1 voices to bank B, page 2 voices to the end of bank B. The DLL adds 256 for elements in bank B, and another 256 for elements behind the page 2 start, which is stored in wavedata offset entry 768. A multisample used by voices of two pages gets an entry in both (same data). The log shows the split, e.g. MU1000: `496 -> 3 pages: 256 (bank A) + 256 (bank B) + 47 (bank B, page 2), 63 shared`.

> Classic tables only run on an "Enhanced" DLL, and big tables only on a "Full" DLL.

---

## Why the wave files got bigger

The MU100, MU128 and MU1000 wave files grew by 18-36 MB. Almost all of it is the **element HPF**:

- The MU100 and later have a 2nd-order high-pass filter per voice element (and per drum key). syxg50.dll has no high-pass filter at all, so the only way to reproduce it is to filter the sample data itself.
- The cutoff is a fixed frequency in Hz, but a sample plays at many different pitches. A sample filtered once would have the right cutoff only at its root key. So each wave gets its own filtered copy every 6 keys in its low key range (where the cutoff is near or above the fundamental), which keeps the cutoff within about 3 semitones of the real one. Higher keys, where the filter only removes inaudible lows, share one copy.
- MU1000: 1,475 filtered copies (1,425 for voice elements, 50 for drum keys), about +33 MB and 90 more multisamples. MU128: 1,291 copies. MU100: 1,027 copies.

Smaller additions:

- **Amp EG baking** for two merged MU1000 voices (Tim'sSet, TurnTabl): 1.9 MB.
- **ADPCM lead-in** (already in the previous version): a few tens of thousands of samples.

Drum velocity sensitivity and the folded 3-/4-element voices reuse existing sample data.

The classic tables (MU50 / MU80 / MU90) did not grow, because those models have no HPF.

---

## DLL patching

If a DLL is among the input files, SXG-Create patches it for the table being built.

### Accepted DLLs

Any input file that starts with `MZ` is taken as the DLL and identified by its content:

| CRC32 | File |
|---|---|
| `38A60E61` | `syxg50.dll`, 626,688 bytes |
| `80EFA471` | `syxg50.dll`, 5,070,848 bytes (with embedded tables) |

- **Already-patched DLLs:** a DLL with the right size but an unknown CRC (one that already carries these patches) is accepted and checked patch by patch. Every patch must find either its original bytes or the patched bytes, otherwise the DLL is rejected. So a DLL patched by an older version gets the new patches on top.
- **Other DLLs:** these are rejected, including `YMF-754Hi.dll`.
- **5 MB version:** this one works too. Its embedded (classic) table is not used, because the ini names the external table; with `--embed` its tables are replaced.
- **One DLL per run:** if both `<name>.dll` and its backup `<name>.orig.dll` are passed (e.g. by dropping a whole folder), `<name>.dll` is used. A DLL given on the command line wins over one in the `roms` folder.

### Patch levels (chosen automatically)

| Level | Used for | Patches |
|---|---|---|
| "Enhanced" | MU50 / MU80 / MU90 | ini names, 24-bit loop length, drum EG offsets, effect types, effect return levels, effect fade-in, bitmaps, names, version info |
| "Full" | MU100 / MU128 / MU1000 | everything in "Enhanced" + table size limits (big layout) + voice map switch |

### Patch sites in `syxg50.dll` (file offset = RVA)

**Table loading**

| Offset | Patch | Level |
|---|---|---|
| `0x519EC` | ini section `SYXG50` -> `Config` | both |
| `0x519F4` | ini key `VoiceTable` -> `SoftSynth` | both |
| `0x1A6F0`, `0x1A6FC` | key-on masks for start offset / loop length: 16 -> 24 bit | both |
| `0x045E0` | voice program maps: 32-bit byte offsets | Full |
| `0x04DF4` + code cave `0x3F3E0` | wavedata offset table 32-bit + **768 multisamples** (three pages, see above); `.text` VirtualSize enlarged to cover the cave | Full |
| `0x05BFE`, `0x16E6F`, `0x16EA5`, `0x16EC4`, `0x16EDB` | drum voice: internal sample if `+0x11 == 0xFF` | Full |
| `0x0AFDA` | ext drum voice index 16-bit LE, 32-bit offset table | Full |
| `0x05C13`, `0x05CB0` | wavedata format byte at `+0x0D` | Full |
| `0x05C44` | drum format bits from the top byte of the sample address | Full |
| `0x1379D` | drum root key at `+0x0A` | Full |
| `0x08325`, `0x08410` | drum setup default byte `+0x0A` (rcv note on) = 1 | Full |
| `0x138F0` | drum voice sample fields: start 24 bit, loop length 24 bit, address **30 bit** + format | Full |
| `0x15620` | wavedata entry: loop length 24 bit, address 32 bit, format `+0x0D` | Full |

**Sound**

| Offset | Patch |
|---|---|
| `0x12233`, `0x12273`, `0x122B3` + code caves `0x3F3B0`-`0x3F3DD` | **Drum setup EG offsets for ext drum voices** (0x10012210): the attack/decay offset is added to the element rate, whose unit is two drum units, so it acted twice as strong as on internal drum keys. Now rate + (offset - 0x40) / 2. |
| `0x099C2`, `0x09A97`, `0x09ADC`, `0x09B80`, `0x09C4E`, `0x09CA3` + code cave `0x3F460` | **Effect types without counterpart -> nearest type.** The six functions that turn MSB/LSB into the internal effect number read the type through a stub with a per-block substitution table. Reverb: Canyon -> Tunnel. Chorus: Symphonic -> Celeste 1, Phaser -> Flanger 1, Ensemble Detune -> Chorus 1. Variation: Touch Wah -> Auto Wah, Auto/Touch Wah+Dist/OD, Dist/OD+Delay, Comp+Dist/OD+Delay, Wah+Dist/OD+Delay -> Distortion / Overdrive, 2-Way Rotary -> Rotary, Ensemble Detune -> Symphonic, Talking Modulator -> Auto Wah. |
| `0x041D6`, `0x0A65D` + code cave `0x3F5A0` | **Effect return level per type** (reverb and variation as system effects): the return level (0-127) is read through a stub that scales it with a per-type factor, result capped at 127. Factors from the S-MU2000: Hall +2.5 dB, Room1 +3.5, Room2/3 +2.0, Stage1 +1.0, Stage2 +2.5, Plate +1.5, White Room +3.5, Basement -1.0; variation only: Delay LCR +1.0, Delay LR +2.5, Echo +2.0, Cross Delay x2, ER2 +2.5, Gate / Reverse Gate +2.0, Karaoke 1/2 -1.5/-2.5, Symphonic x1.56, Rotary x1.45, Tremolo / Auto Pan x2. |
| `0x0900E` + code cave `0x3F680` | **Return level update on a type change:** the DLL computed the return level only when the return parameter changed. The type change handler (0x10008F50) now also runs the return update of its block. |
| `0x03875`, `0x30B91`, `0x30BBA`, `0x30BEF`, `0x30C5F`, `0x02B50`, `0x02BB0` + code cave `0x3F6B0`-`0x3FA20`, dialog resource 111, `.data` VirtualSize -> `0x5E40` | **Voice map switch** (Full only; see [MU Basic voice maps](#mu-basic-voice-maps)). After the table setup, the cave looks for the voice map appendix behind the table sections (`MAP2`), remembers the 8 bank/drum row pointers and points them at the appendix rows when `[Config] MUBasic=1` selects MU Basic. A checkbox (control `0x420`) is added to the Setup page; Init and Set Defaults set it, a click enables Apply, and Apply switches the rows. The plugin state (VST chunk) carries the setting: getChunk (`0x10002B50`) returns a copy with 3 more bytes `'V','M',<mode>` (bank 33 -> 36 bytes, program 5 -> 8 bytes), setChunk (`0x10002BB0`) takes the mode from such a chunk and passes the original size on; old 33/5-byte chunks are still accepted. Nothing is written to a file. Without an appendix the checkbox is hidden and the chunk stays unchanged. The cave code is position independent; its state lives in `.data` at `0x56DC0` (chunk copy at `0x56E00`). |
| `0x07560` + code cave `0x3FA20`-`0x3FA7B` | **Voice map switch, immediate** (Full only). The MIDI channel event entry (audio thread) compares the XG bank map row pointer (`0x100552D8`) with the last one it saw (`.data` `0x56DE8`). After a switch (Setup page or plugin state) all 16 parts re-run their program change with their current program (part `+0x6A`, handler table `0x10041BB0`[4]; *receive program change* is honoured) before the event is handled. Notes already sounding keep their voice. Position independent. |
| `0x08C24`, `0x08C75`, `0x08CDF` | **Effect fade-in after a type change:** the handler mutes the block, and a ramp run every 10 ms brings it back in steps of 4: reverb 0.64 s, chorus 1.03 s, variation 0.32-0.9 s. Larger steps (reverb 32, chorus 52, variation 40) end the ramp after 80-90 ms; the end values are unchanged. |

**Resources**

- **Bitmaps:** bitmap 101 (the panel picture) becomes `bitmaps/Bitmap101_<model>.bmp` for MU80, MU90, MU100, MU128 and MU1000 (MU50 keeps the original), bitmap 105 becomes `bitmaps/Bitmap105.bmp` for every model. Keep the `bitmaps` folder next to the scripts. Replacement pictures must have the size of the original (400x90 and 110x13); any uncompressed 8-, 24- or 32-bit BMP works. They are stored as 24-bit DIBs in place.
- **Names** (MU80 ... MU1000; MU50 keeps the S-YXG50 names, only its default table name is set): the About dialog and string table say S-YXG<n> instead of S-YXG50 (e.g. S-YXG1000), the internal name `xg50` becomes `mu<n>`, the default table name in the string table becomes the table just built, and the version info reads "Yamaha S-YXG<n> VSTi", "S-YXG<n>", "S-YXG<n>.DLL" and "Yamaha S-YXG<n> Portable VSTi". Hosts may list the plugin under its new name after a rescan.
- **Version info** (all models): the file version `2016,4,25,18` becomes the conversion date (`YYYY,MM,DD,0`), the FileVersion string `2016.04.25.0018` becomes `YYYY.MM.DD`, and the copyright reads "... 2016 VEG, 2026 Soundshock/NightFright".

The resource section grows by a few KB for this. The PE checksum is recalculated after patching.

The S-YXG50 sound engine itself, including its MMX/SSE paths, is not changed beyond the effect patches above. The MMX/SSE paths were checked: they read samples through a 32-bit pointer plus a 32-bit index, so they don't limit addresses.

### File names

- **`syxg50.dll` is never overwritten:** a DLL supplied as `syxg50.dll` (or `syxg50.orig.dll`) is written under the model's name: `syxgmu50.dll` (MU50, because `syxg50.dll` is the original's name), `syxg80.dll`, `syxg90.dll`, `syxg100.dll`, `syxg128.dll` or `syxg1000.dll`, in single and multi-model runs, with and without `--embed`. The supplied `syxg50.dll` stays unchanged.
- **Other names are kept:** e.g. `mu800.dll` gives a patched `mu800.dll`. A name without an extension gets `.dll` added.
- **ini:** it gets the same name with `.ini` (`mu800.ini`). The DLL looks for the ini under its own name, so if you rename the DLL later, rename the ini as well.
- **DLL with another name already in the output folder:** it is replaced by the patched version, and the original is kept once as `<name>.orig.dll`. Later runs patch from that backup, so switching between models (Enhanced <-> Full) always starts from the original.
- **DLL in another folder:** it stays unchanged, and the patched copy is written to the output folder.

### The ini

The ini is written on every run (not with `--embed`) and points to the table that was just built (CRLF line endings):

```ini
[Config]
SoftSynth=SXGMU1KX.TBL
Process=1
XGLite=0
DebugPanel=0
DisableGUI=0
```

| Key | Meaning |
|---|---|
| `SoftSynth` | Table file to load, relative to the DLL's folder. The wave file name is stored in the table header, so it doesn't need an entry. |
| `Process` | Processing switch of the S-YXG50 (left at 1) |
| `XGLite` | XG Lite mode (0 = off) |
| `DebugPanel` | 1 = show the debug panel instead of the normal panel |
| `DisableGUI` | 1 = no GUI window |
| `MUBasic` | **New**, optional, MU100 / MU128 / MU1000 only: start value of the voice map (1 = MU Basic, 0 = MU Native, default 0). Only read, never written; a setting saved by the host overrides it. |

### Embedded tables (`--embed`)

- Table and wave file are stored in the patched DLL as `RT_RCDATA` resources under their file names, the same way the 5 MB `syxg50.dll` stores its own tables. Those old tables (`SXGBIN41.TBL`, `SXGWAVE4.TBL`) are removed first.
- The default table name in the DLL's string table is set to the new table, so the DLL finds it without an ini. No ini is written, and an existing ini of the same name is removed (an ini with a `SoftSynth` entry would make the DLL look for an external file instead).
- A DLL supplied as `syxg50.dll` is written under the model's name (`syxgmu50.dll`, `syxg80.dll` ... `syxg1000.dll`, see [File names](#file-names)); other names are kept.
- One file to copy, at the cost of DLL size (MU1000: about 88 MB).

### How the DLL loads the table

1. **Table:** it reads `SoftSynth` from `[Config]` in `<dll name>.ini` and loads that file from the DLL's folder.
2. **Wave file:** the table header names the wave file, which is loaded from the same folder. Both files are read whole, so file size is not limited.
3. **Embedded:** without the key, the DLL loads the table named in its string table from its own resources (5 MB version, or a DLL made with `--embed`).

---

## MU Basic voice maps

The MU100, MU128 and MU1000 have two voice maps, which the module switches with its own Voice Map setting:

| Map | Voices | PC 0 drum kit |
|---|---|---|
| MU Native | revoiced (`GrandP #`, `BriteP #`, `Strngs1#`, ...) | native Standard Kit |
| MU Basic | MU90-compatible (`GrandPno`, `BritePno`, `Strings1`, ...) | MU90 Standard Kit |

**New:** the converted table contains **both maps**, and the patched DLL switches between them like the module does:

- **Setup dialog:** open Setup in the S-YXG50 panel, tick **"MU Basic voice map"** and press Apply/OK. **Set Defaults** returns to the start value.
- **When it takes effect:** immediately, for the next note on every part (the current programs are selected again in the new map with the next MIDI event). Notes already sounding keep their voice. Parts with *receive program change* switched off keep their voice until a reset.
- **Saving:** like the other Setup options, the setting is part of the plugin state (VST chunk) that the host saves with its project, preset or plugin settings and restores on the next load. The DLL itself writes no files. A host that does not save plugin state starts with the start value every time. Confirmed: in the **Falcosoft MIDI Player** the setting survives a restart once the VSTi settings are saved there; in the **VST MIDI Driver** it is saved with "Apply" in its configuration.
- **Start value:** MU Native. An optional `MUBasic=1` in `[Config]` of `<dll name>.ini` makes MU Basic the start value (only read, never written). A saved plugin state overrides it; older saved states without the setting keep the start value.
- **Embedded tables (`--embed`):** the switch works the same and needs no ini; the DLL stays a single file (no ini, no registry).
- **Other tables:** with MU50 / MU80 / MU90 tables, or MU100+ tables from earlier versions, the checkbox is hidden.

Both maps share the same samples, elements and drum voices. The appendix behind the table holds only what differs: the XG voice row, the XG drum program row and (on MU128/MU1000) the GM2 row, plus the banks and voices only the basic map has (MU100: 70 banks, no extra voices; MU128: 83 banks, 32 voices; MU1000: 86 banks, 32 voices). The wave file does not grow. GS, SFX and MSB 48 are the same in both maps. Both settings were checked to render byte-identical to separate native-only and basic-only builds (external and embedded), and the switch was confirmed in a real VST host.

> **Note:** the newer kits (e.g. the Apogee Kit on XG drum program 30) exist in both maps. A song that selects such a kit sounds different on MU100+ tables than on MU80/MU90 tables, which fall back to the Standard Kit, and the same happens on real hardware.

---

## What the conversion does, per model

### All models

- **Bank maps:** program and drum kit bank maps are rebuilt for the S-YXG50 bank map format (XG, SFX, GS; MU128/MU1000 also GM2).
- **Duplicated banks:** a voice bank used on both the GS and the XG side is copied to the other side with its own index. The copy now also gets its program map. Before, the MU80's MSB 126/127 (which point to the GS bank) had an empty program map, so all 128 programs read the 8-byte debug label in front of the first voice as a voice (element count `0x70`).
- **Ext drum voices:** drum keys that play a full voice are placed in voice bank A, which the drum voice offsets require.
- **Drum EG rate (byte 13):** S-YXG50 = MU - `0x21`. The MU models store the rate with the offset that syxg50.dll adds itself. Without the correction, values >= `0x60` put the drum envelope into a special state, which made drums sound cut off. Calibrated against the S-YXG50 table: 245 of 253 matching MU80 drum voices, 426 of 460 MU90 drum voices.
- **LFO pitch modulation depth:** read with 6 bits instead of 5. The old mask halved the vibrato depth of voices like Siren, Ghost, Goblins and Wind.
- **24-bit loop lengths:** loops longer than 65,535 samples are written in full (they need the "Enhanced" or "Full" DLL).
- **Rising decay 2 (MU80 and later):** an amp EG whose decay 2 level is above its decay 1 level falls to the decay 1 level and climbs back. syxg50.dll does that too, but it ends the note as soon as the envelope is below level 64 (measured: decay 1 level 63 ends it at every key and velocity, 64 keeps it). Lite Org was only a click instead of a sustained organ; WireLead, synecho2, Bounce and Ana Echo have one such element. The decay 1 level is raised to 64 (-46 dB). The S-YXG50/MU50 data never does this.

### ADPCM loops

The MU hardware keeps decoding through a loop, carrying the decoder state from one pass into the next. A PCM table can only repeat one fixed loop. SXG-Create therefore emulates the passes until the decoder state settles, puts the transitional passes in front of the loop (lead-in) and uses the settled pass as the loop, so loops play back seamlessly.

- **Limits:** lead-in is only used while it fits the address range and the 24-bit start offset; drum samples in the classic layout are limited to a 16-bit start offset.
- **Statistics:** the run prints how many loops were already seamless, made seamless, or did not settle within 8 passes.

### MU50

- **Identical to Yamaha's own S-YXG50 table** in all voice and drum parameters (see [Verification](#verification-against-the-s-mu2000-and-the-s-yxg50)), but with the MU50's original sample data.
- **Default table name:** the MU50 DLL keeps the S-YXG50 names, but its string table now names `SXGMU50a1.TBL` instead of `SXGBIN41.TBL`. Before, a MU50 DLL that was started without a `SoftSynth` entry (embedded with `--embed`, or a host that does not find the ini) looked for the missing `SXGBIN41.TBL` and failed to load.
- **Ext drum voices** (drum keys that play a normal voice, e.g. the SFX kits): the MU50 program ROM has a table of 87 voice addresses at `0x3B3CA` (32-bit, byte-swapped ROM); SXG-Create used a hand-reconstructed list before. The two disagreed on two entries that the MU50 kits use: ext voice 10 is FootStep (was SynMalet) and 31 is Tweet (was Bird 2), used by the TG300B C/M Kit (GS drum program 128, keys 81 / 102) and the TG300B SFX Set (program 57, keys 57 / 78). A rebuilt MU50 table differs from the previous one in exactly these 4 keys; all 52,224 voice slots and the other 25,371 drum keys are unchanged.

### MU80

- **Format bit 6 (`0x40`, `0xC0` vs `0x80`):** investigated and found to have no audible meaning the table format could express. Both values are treated as 16-bit PCM.
- **Long loops:** a few synth pads loop over more than 65,535 samples; with the 24-bit loop length of the "Enhanced" patch they loop as on the MU80.

### MU90 / MU90B

- **Wave ROMs:** `xs518a0` and `xs743a0` are the two 16-bit halves of one 32-bit data bus and are interleaved word by word. Loop addresses count 32-bit words.
- **Sample formats:** 16 bit, 12 bit (LE bit stream), 8 bit and ADPCM, all converted.
- **Reverse flag:** wavedata `+8` / drum voice `+34`, bit 7. The hardware plays such samples backwards from the loop address, and the converter reverses the data (one-shot). This fixes e.g. the toms of the standard kits, MelodTom and Real Tom, and also gives Rev Tom / Rev Kick.
- **42-byte drum voices:** converted to the 30-byte S-YXG50 layout. The extra EQ bytes are dropped.
- **Long drum bodies (classic layout):** four XG open hi-hats have a 70,626-sample body, more than the 16-bit drum start offset allows. Instead of cutting the attack, the loop start is moved earlier by the excess, so the sound starts at its real beginning.
- **Bank map order:** XG (LSB), SFX (MSB), GS.

### Drum keys (MU90 and later)

- **HPF cutoff** (MU100 and later, drum voice byte `+21` / MU1000 `+20`): baked into a filtered copy of the drum sample. Measured on the S-MU2000: 2nd-order high-pass, Q about 1.0, cutoff at the output 2^(5.066 + 0.0591 x value) Hz (value 55 = 319 Hz, 94 = 1.57 kHz), independent of the note pitch. The sample is filtered in its own time base, so the cutoff is divided by its playback ratio.
- **Level offset** (MU100 and later, drum voice byte `+29`, signed): added to the key's level. Used by 11 keys of the MU1000/MU128 Standard Kit (e.g. Ride 1, Crash 1/2, Chinese, Ride 2, hi-hats) and 7 MU100 keys; without it the Ride 1 was 13.6 dB too loud.
- **Instant attack with equal decay rates:** syxg50.dll holds a drum key at full level for 18-120 ms before its decay starts, the MU decays after a few ms. For keys with attack `0x7F` and decay 1 = decay 2 (223 kit/key pairs in the MU1000 kits tested, e.g. Seq Click, Analog Kit hi-hat and toms) the converter selects an attack mode of the DLL without that hold (`0x60`). Seq Click: 4-7 dB too loud before, now within 1-2 dB of the S-MU2000.
- **Short decay 1 before a fast decay 2** (Hi Q, Click Noise, Short Guiro): the MU leaves decay 1 after about 1-2 dB, so these keys get the no-hold mode with one decay of the same energy (3.5-8 dB too loud before, now within 2 dB).
- **Velocity Pitch Sense / Velocity LPF Cutoff Sense:** syxg50.dll has no such drum parameters. Drum keys that use them are converted to ext drum voices whose element reproduces the drum playback of the DLL and adds the velocity dependency with constant pitch and filter EGs (`drumvel.py`). MU1000: 162 drum keys -> 158 ext drum voices.

Players that substitute "missing" programs from an instrument list (e.g. Falcosoft MIDI Player with `S-YXG50_XG-GS.ins`) replace the MU-only drum kits with the Standard Kit. Select an instrument definition for the converted model (e.g. `Yamaha_MU1000_XG.ins`).

### MU100

- **Wave ROMs:** three 32-bit pairs (MU90 pair + two new pairs), mapped to one address space.
- **Wavedata tables:** three, with their own offset tables (wave numbers 0-292 / 293-326 / 327-).
- **Voice maps:** MU100 Native and MU Basic in one table, switchable in the Setup dialog (default MU Native).
- **Element HPF:** the MU100 stores the element HPF cutoff in element byte `+69` (unused on the MU90). It is the same value as byte `+80` of the MU128/MU1000 in all 1,925 elements of the voices both models have. It was not converted before, so 66 MU100 voices (86 elements, e.g. Oboe #, MuteGtr#, Wrench, Heinz, Parasite) sounded up to 13 dB too loud and dull in the low keys (Parasite up to 19 dB). Now they are filtered like on the MU128/MU1000.

### MU128 / MU1000

- **Program flash:** high/low 16-bit halves of a 32-bit bus, combined.
- **Elements:** 84-byte elements, mapped to the 78-byte S-YXG50 element almost 1:1. This was verified on 2,317 elements shared with the MU100, all 77 bytes match.
- **Drum voices:** 42 bytes in the MU90 layout, except byte 0, which moved to `+23`.
- **Voice maps:** MU Native and MU Basic in one table, switchable in the Setup dialog (default MU Native), plus GS, MSB 48 and GM2.
- **Element HPF (element byte `+80`):** 162 elements in 128 MU1000 voices, e.g. Oboe, Muted/Jazz/Overdrive Guitar, Slap Bass, Rock Organ. Same filter and cutoff scale as the drum HPF (measured on the S-MU2000). Baked into filtered copies of the multisamples (see [Why the wave files got bigger](#why-the-wave-files-got-bigger)). The HPF copies are cut in the transposed key range (key + coarse tune), as the DLL selects waves; this matters for 18 elements with both, e.g. Sleep (+24): low-band shape against the S-MU2000 -1.9 -> +0.3 dB.

### Voices with 3 or 4 elements (MU1000)

syxg50.dll plays at most 2 elements per voice. Taking the first two (as before) left whole key ranges silent (Sweet Tp above key 84, 5partStr below key 36, Tim'sSet below key 60) and dropped whole layers (the brass of Str+Brss). `elemreduce.py` now folds the 22 affected voices (e.g. Sweet Tp, 5partStr, Tim'sSet, Str+Brss, 4 Way EP, TurnTabl, SolidStr, Symphnc, Temple, Trcrtps) into two elements. The log lists the result for each voice, e.g. `Tim'sSet el3[0-59] + el0[60-127] | el2[0-59] + el1[60-127]`.

- **Ranking by loudness:** level, sample loudness from the wave ROM (incl. element HPF) and the amp EG key-on delay (measured in the DLL: 4 = 69 ms, 8 = 309 ms, 15 = 3.5 s; TurnTabl's loudest-level element starts after 3.5 s and is never heard).
- **Stereo pairs** (same range, mirrored pans) become one centred element. The louder side is kept and its level matched to the pair's power (pan law measured in the DLL).
- **Key splits** share one element: its multisample takes each element's waves in that element's keys. The DLL picks the wave by key + coarse tune, so the wave ranges are moved into the kept element's transposition and the coarse tune difference goes into the root note (pitch scaling of merged elements is set to 100 % and compensated per key). Level and level key scaling (incl. crossfades) go into the wave attenuation. Filter, EGs and LFO come from the member with the most (loudness-weighted) keys in 36-96.
- **Dropped layers** fill the keys where a kept element is silent; otherwise their power goes to the level of the kept element. Practically silent layers are dropped.
- **Wave start offset** (element byte `+77`, S-YXG50 `+75`; measured: playback starts 128 samples later per step, 8- and 16-bit alike): it belongs to the element, so in a merged element the primary member's offset applied to all members. Tim'sSet's percussive upper element started 2,560 samples late and lost its attack. Merged elements now get offset 0, and each member's own offset moves the start of its own wave rows (no extra sample data). Affects Tim'sSet and TurnTabl.
- **Amp EG of key-split members:** where a member's own amp EG goes silent (percussive) but the kept EG sustains, the member gets sample copies with its own envelope multiplied in, played as one-shots (`elemreduce.Env_Sample`, every 6 keys because the time in the sample runs with the pitch). Tim'sSet and TurnTabl, 1.9 MB. Tim'sSet keys 60 and up: +20 to +33 dB before, now -2 to -3 dB against the S-MU2000. Sustained EG differences are deliberately not baked (see [Known limitations](#known-limitations-and-unsolved-problems)).

---

## Verification against the S-MU2000 and the S-YXG50

### Method

- **Reference:** the **S-MU2000** (Yamaha's software MU2000, same firmware and sound data as the MU2000/MU1000) as a VST, and recordings of a real **MU1000**. Dedicated test MIDI files were played on both and on syxg50.dll with the converted tables (drum kits and levels, drum EGs, drum HPF and velocity, element HPF, voices with 3/4 elements, all effect types).
- **syxg50.dll** was run in an x86 emulator (Unicorn) so that every measurement could be repeated with modified tables or DLL patches, and so that internal DLL behaviour (EG rates and levels, pan law, key-on delays, effect routines) could be measured directly.
- Levels were compared per note (RMS in fixed windows, after aligning the recordings), plus spectral shape for filters and pitch for tuning.

### Results

| Area | Before | Now |
|---|---|---|
| Drum level offset (MU1000 Ride 1) | +13.6 dB | 0.1-1.5 dB on all 11 keys |
| Instant-attack drums (Seq Click) | 4-7 dB too loud | within 1-2 dB |
| Short decay drums (Hi Q, Click Noise, Short Guiro) | 3.5-8 dB too loud | within 2 dB |
| Voices with 3/4 elements (11_Element_Test, 22 voices) | -2 to -19 dB median, silent key ranges | within about ±2.5 dB for 21 of 22 voices |
| Tim'sSet, keys 60 and up | +20 to +33 dB | -2 to -3 dB |
| Element HPF + coarse tune (Sleep, low band) | -1.9 dB | +0.3 dB |
| Effect types without counterpart (e.g. Symphonic as chorus, Dist+Delay tail) | +5.0 dB / +11.8 dB | +0.3 dB / +1.8 dB |
| Effect return levels (late tail, 12_Effect_Test) | median 2.2 dB off | 0.4 dB |
| Effect onset after a type change (0.12-0.5 s, 91 types) | 3.8 dB off (3.7 dB too weak) | 1.1 dB off (0.4 dB) |

The voices with stereo pairs measure about 2-3 dB louder in a mono recording, because the uncorrelated L/R pair of the original loses 3 dB in mono; in stereo the power is the same.

### Cross-checks between models

- **MU50 against the S-YXG50's own table** (`SXGBIN41.TBL`, Yamaha's port of the MU50 sound set): the converted voice and drum parameters are identical for all 438 XG voices and 303 drum keys. The wave tuning matches within 1-2 cents (the S-YXG50 table writes some fine tunes from the next note down, e.g. note 50 / +52 cents instead of note 49 / +209, measured as the same pitch in the DLL). Rendered in the DLL, 80 % of 1,313 notes are within 0.1 dB of the original S-YXG50, and 3 are more than 3 dB apart.
- **MU80:** its voices are revoiced against the MU50 (scattered differences, no systematic offset), so the S-YXG50 table is no reference there.
- **MU90 / MU100 / MU128 / MU1000:** all XG voices were rendered (keys 36/60/84) and compared where two models share a voice (same bank, program and name): MU128 vs MU1000 1,014 voices, MU100 vs MU128 939, MU90 vs MU100 505. The converted voice data of MU128 and MU1000 is identical for all shared voices; MU100 differs in 4 (Whistle, Ocarina, DrawOrg2, Dim&Cool: different ROM data). After the MU100 element HPF fix, every remaining level difference above 2 dB was traced to identical data played after a different preceding voice (LFO phase), not to the conversion. No clipping voices; the only silent one (Lite Org) led to the rising decay 2 fix.
- **Builds:** the multi-model run with `--embed` (MU90, MU100, MU128, MU1000 from the `roms` folder) and the MU50, MU80 and MU90B sets convert without errors. Rebuilds after each change were compared byte by byte against the previous build, so that only the intended bytes changed.

---

## Known limitations and unsolved problems

These are limits of the S-YXG50 engine, or changes that were tried and rejected because they made things worse or were too risky.

- **Insertion effects** (MU80 and later): not converted. syxg50.dll has reverb, chorus and one variation block; the MU's insertion effect blocks (e.g. distortion on a single part) have no place in it. Adding them would mean extending the DLL's effect routing and DSP code, which was judged too risky for the gain.
- **Effect types without counterpart** stay Thru: Pitch Change, Harmonic Enhancer, Compressor, Noise Gate, Lo-Fi. The DLL has nothing close enough to substitute.
- **Effect switching:** a type change still mutes the block for 80-90 ms. The DLL mutes the block while it sets up the new type, and the ramp back was shortened rather than removed.
- **Two elements per voice:** the 22 MU1000 voices with 3 or 4 elements are approximations. Stereo pairs become mono, layers are folded into levels, and members of a key split share the filter, LFO and (except for percussive members) the amp EG of one element.
- **Sustained amp EG differences in merged voices are not baked:** baking them into the samples was implemented and measured, but made 5partStr (-4.5 dB) and Sweet Tp (up to -16 dB on single keys) worse than keeping one EG, and added 15 MB. Only percussive members are baked.
- **HPF as baked copies:** the filter cutoff is exact only every 6 keys (within about 3 semitones), it cannot follow real-time changes, and it costs wave data. The DLL has no high-pass filter to do it properly.
- **Rising decay 2:** the dip is limited to -46 dB (decay 1 level 64), because the DLL ends notes below that level; Bounce and Ana Echo have shallower gaps between their repeats than on the hardware.
- **Drum attack without hold for MU50/MU80:** the MU90+ correction is not applied to MU50/MU80. Yamaha's own MU50-based S-YXG50 table uses the hold, and whether the real MU50/MU80 decay immediately like the MU90 could not be verified without recordings.
- **MU2000:** not converted directly. Its scaling tables are in the ROM and convert back to the MU1000's break points (a test build sounded identical to the MU1000), but as the result is the same, the MU1000 set is used instead.
- **MU50 DOC bank:** the 'DOC' voice bank and drum kit are not converted. Some DOC drum voices appear to be missing data, so it would need reconstruction.
- **Remaining deviations:** a sweep of all 1,193 MU1000 voices (XG + SFX, C2/C4/C6, no effects) against the S-MU2000 gave a median deviation of 0.33 dB in the sustain level and 0.39 dB in the attack; 2.1 % of the notes are more than 3 dB off. About half of those depend on the note-on time in both synths (beating between elements, free-running LFO) and are not conversion errors. Stable deviations remain for the merged 3/4-element voices (e.g. 5partStr, Trcrtps), a few SFX voices with very deep pitch modulation (Parasite, Insects, Sweepy) and single voices (e.g. VX El.P1, RobotClv, AfrcnWnd). Above 3.2 kHz the S-YXG50 is slightly darker (-0.3 to -0.6 dB). Release tails end at about -50 dB in the S-YXG50 (about -70 dB on the S-MU2000). A few effect types are 2-3 dB off.

---

## Using the converted DLLs

- **Host:** syxg50.dll is a 32-bit VST2 instrument. Any VST2 host works; to use it as a system MIDI device (e.g. for DOSBox or Windows games), load it through a VSTi MIDI driver.
- **Which model:** MU50 sounds like the DB50XG, SW60XG and the S-YXG50 itself, which is what most players of 1990s games heard. MU90/MU100 are good all-rounders with better samples and similar balance (MU100 = SW1000XG sound set). MU1000/MU128 have the best samples and the most voices, but are larger and partly revoiced; the "MU Basic voice map" checkbox in Setup gives the MU90-compatible voice set for older material.
- **GS:** GS songs play through Yamaha's GS mode, an approximation of the Roland sound set. MT-32 music needs an MT-32 emulator.

---

## Behaviour on reruns

- **Table and DLL output:** an existing table file is skipped. The DLL and ini are rewritten on every run.
- **Wave file:** if it already exists, the run stops before writing it ("already exists, exiting early"). Delete or move the old table and wave file before rebuilding the same model. With `--embed` nothing is written besides the DLL.

---

## Investigation tools

Optional, not needed for conversion.

| Script | Purpose |
|---|---|
| `analyze_drum_eg.py` | compares MU80 drum voices with the S-YXG50 drum voices of the same kit and key (drum EG calibration), writes `drum_eg_compare.csv` |
| `analyze_voice_params.py` | compares converted MU80 voice elements byte by byte with the S-YXG50 voices in the same slot, writes `voice_param_compare.csv` |
| `analyze_sample_flags.py` | collects evidence on bit 6 of the MU80 sample format byte, writes `sample_flags.csv` |
| `list_long_loops.py` | lists MU80 voices with loops longer than 65,535 samples |

Usage is described at the top of each script. Most take the MU80 ROMs plus the 5 MB `syxg50.dll` (or `SXGBIN41.TBL` + `SXGWAVE4.TBL`).

New modules used by the conversion: `elemreduce.py` (voices with 3/4 elements, EG baking) and `drumvel.py` (drum velocity sensitivity). The folder `bitmaps` holds the panel pictures for the DLL.

---

## Credits and license

- **Soundshock** – original [SXG-Create](https://github.com/Soundshock/SXG-Create)
- **tarboh** – [S-MU2000](https://github.com/tarboh/S-MU2000), the reference for the sound comparisons
- **TaleTN** – [MUTable](https://github.com/TaleTN/MUTable), MU series data table documentation (MU50 ext drum voice table, MU2000 scaling tables)
- **VEG** – [S-YXG50](https://veg.by/en/projects/syxg50/) (`syxg50.dll`)
- **Yamaha** – MU series tone generators and the S-YXG50 sound engine

DPCM delta table, DPCM limits table, and delta format decoding code based on MAME, copyright (c) MAME contributors, and related contributions by TaleTN, tarboh, and hockinsk under the BSD-3 license.

license: BSD-3-Clause

copyright-holders: Olivier Galibert
