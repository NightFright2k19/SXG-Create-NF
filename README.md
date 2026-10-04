# SXG-Create

Converts the ROM sets of Yamaha MU-series tone generators (MU50 to MU1000) into tables and wave data for the **S-YXG50** soft synthesizer (`syxg50.dll`), and patches the DLL so that it can play them as close to the original module as the S-YXG50 engine allows.

This document is the reference for the current state of SXG-Create: what changed in this version, supported models, command line, output files, the DLL patches, what the conversion does for each model, how the results were checked against the S-MU2000, and what is still unsolved.

## Table of contents

- [What's new in this version](#whats-new-in-this-version)
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

## What's new in this version

Compared to the state of 1 October 2026. Most of the sound changes were measured against the **S-MU2000** (Yamaha's MU2000 software version, which runs the MU2000/MU1000 firmware and sound data) and against recordings of a real **MU1000**; see [Verification](#verification-against-the-s-mu2000-and-the-s-yxg50).

### Usage and command line

- **`roms` folder:** ROMs are also picked up from a folder `roms` next to `main.py`, including all subfolders (e.g. `roms/mu90`, `roms/mu1000`). `python main.py syxg50.dll` is then enough.
- **Several models in one run:** when the complete ROM sets of several models are found, all of them are converted one after the other, and the DLLs/inis are named after the model (`syxg80.dll`, `syxg90.dll`, `syxg100.dll`, `syxg128.dll`, `syxg1000.dll`; MU50: `syxgmu50.dll`). The MU2000 set is skipped when the MU1000 set is present (same sound set).
- **New switch `--embed`:** table and wave file are embedded into the patched DLL instead of being written as files. The old embedded tables of the 5 MB `syxg50.dll` (`SXGBIN41.TBL`, `SXGWAVE4.TBL`) are removed first. No ini is needed.
- **Wildcards** such as `*.bin` are expanded by SXG-Create itself (the Windows command line passes them unexpanded). A pattern without matches is skipped with a note.
- **Python 3.12** or newer is required (nested f-strings).

### DLL patches (all models)

- **Effect types without a counterpart** in the DLL (it switched them off or to Thru) now use the nearest type it has.
- **Effect return levels** are scaled per effect type, calibrated against the S-MU2000, and recomputed on a type change.
- **Effect fade-in after a type change** is shortened from 0.3-1 s to 80-90 ms.
- **Drum setup EG offsets** (attack/decay) for ext drum voices now act with the same strength as for internal drum keys (they acted twice as strong).
- **768 multisamples** in three pages (was 512) and **30-bit drum sample addresses** (was 26 bits) in the "Full" patch, needed by the larger MU128/MU1000 wave data.
- **Model identity:** panel bitmap per model, names in the About dialog, string table and version info (S-YXG<n>), default table name, conversion date and credits in the version info.

### Sound conversion

- **Element HPF** (MU100, MU128, MU1000): the per-element high-pass filter is baked into filtered copies of the multisamples, because syxg50.dll has no high-pass filter. The MU100 stores it in a byte that was not read before.
- **Drum keys:** HPF cutoff (baked), level offset, an attack mode without the DLL's built-in hold for instant attacks, and velocity pitch/filter sensitivity via generated ext drum voices.
- **Voices with 3 or 4 elements** (22 MU1000 voices): folded into the two elements the DLL can play, instead of dropping elements 3 and 4.
- **Wave start offset** of merged elements, **amp EG baking** for percussive key-split members, **HPF and coarse tune**, **rising decay 2** (notes that ended right after the attack, e.g. Lite Org), and **program maps of duplicated banks** (MU80, MSB 126/127).

Details for each point are in the sections below.

---

## Quick start

```
python main.py <ROM files...> [syxg50.dll] [--mu-basic] [--embed]
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
| `--mu-basic` | MU100 / MU128 / MU1000 only. Converts the "MU Basic" voice map instead of the native one (see [MU Basic voice maps](#mu-basic-voice-maps)). Ignored for other models, with a note. |
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

> **MU2000:** it has the same voice data as the MU1000. Its program ROM stores the element filter/level scaling as an index into a table that is missing from the dump, so SXG-Create uses the MU1000 set instead (skipped when both are present, or a message asking for the MU1000 set).

The S-YXG50's own tables and `Vampire.dll` are recognised as well, but they are not a conversion source.

---

## Output files and table layouts

| Models | Layout | DLL patch | Table | Wave data | Wave size |
|---|---|---|---|---|---|
| MU50 | classic | "Enhanced" | `SXGMU50a1.TBL` | `SXGMU50a1.UPCM` | 6.7 MB |
| MU80 | classic | "Enhanced" | `SXGMU80a1.TBL` | `SXGMU80a1.UPCM` | 12.7 MB |
| MU90 / MU90B | classic | "Enhanced" | `SXGMU90t.TBL` | `SXGMU90.UPCM` | 13.3 MB |
| MU100 | big | "Full" | `SXGMU100X.TBL` | `SXGMU100X.UPCM` | 51.8 MB |
| MU100 `--mu-basic` | big | "Full" | `SXGMU100BX.TBL` | `SXGMU100BX.UPCM` | |
| MU128 | big | "Full" | `SXGMU128X.TBL` | `SXGMU128X.UPCM` | 70.8 MB |
| MU128 `--mu-basic` | big | "Full" | `SXGMU128BX.TBL` | `SXGMU128BX.UPCM` | |
| MU1000 | big | "Full" | `SXGMU1KX.TBL` | `SXGMU1KX.UPCM` | 87.3 MB |
| MU1000 `--mu-basic` | big | "Full" | `SXGMU1KBX.TBL` | `SXGMU1KBX.UPCM` | |

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
| "Full" | MU100 / MU128 / MU1000 | everything in "Enhanced" + table size limits (big layout) |

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

**Sound (new in this version)**

| Offset | Patch |
|---|---|
| `0x12233`, `0x12273`, `0x122B3` + code caves `0x3F3B0`-`0x3F3DD` | **Drum setup EG offsets for ext drum voices** (0x10012210): the attack/decay offset is added to the element rate, whose unit is two drum units, so it acted twice as strong as on internal drum keys. Now rate + (offset - 0x40) / 2. |
| `0x099C2`, `0x09A97`, `0x09ADC`, `0x09B80`, `0x09C4E`, `0x09CA3` + code cave `0x3F460` | **Effect types without counterpart -> nearest type.** The six functions that turn MSB/LSB into the internal effect number read the type through a stub with a per-block substitution table. Reverb: Canyon -> Tunnel. Chorus: Symphonic -> Celeste 1, Phaser -> Flanger 1, Ensemble Detune -> Chorus 1. Variation: Touch Wah -> Auto Wah, Auto/Touch Wah+Dist/OD, Dist/OD+Delay, Comp+Dist/OD+Delay, Wah+Dist/OD+Delay -> Distortion / Overdrive, 2-Way Rotary -> Rotary, Ensemble Detune -> Symphonic, Talking Modulator -> Auto Wah. |
| `0x041D6`, `0x0A65D` + code cave `0x3F5A0` | **Effect return level per type** (reverb and variation as system effects): the return level (0-127) is read through a stub that scales it with a per-type factor, result capped at 127. Factors from the S-MU2000: Hall +2.5 dB, Room1 +3.5, Room2/3 +2.0, Stage1 +1.0, Stage2 +2.5, Plate +1.5, White Room +3.5, Basement -1.0; variation only: Delay LCR +1.0, Delay LR +2.5, Echo +2.0, Cross Delay x2, ER2 +2.5, Gate / Reverse Gate +2.0, Karaoke 1/2 -1.5/-2.5, Symphonic x1.56, Rotary x1.45, Tremolo / Auto Pan x2. |
| `0x0900E` + code cave `0x3F680` | **Return level update on a type change:** the DLL computed the return level only when the return parameter changed. The type change handler (0x10008F50) now also runs the return update of its block. |
| `0x08C24`, `0x08C75`, `0x08CDF` | **Effect fade-in after a type change:** the handler mutes the block, and a ramp run every 10 ms brings it back in steps of 4: reverb 0.64 s, chorus 1.03 s, variation 0.32-0.9 s. Larger steps (reverb 32, chorus 52, variation 40) end the ramp after 80-90 ms; the end values are unchanged. |

**Resources (new in this version)**

- **Bitmaps:** bitmap 101 (the panel picture) becomes `bitmaps/Bitmap101_<model>.bmp` for MU80, MU90, MU100, MU128 and MU1000 (MU50 keeps the original), bitmap 105 becomes `bitmaps/Bitmap105.bmp` for every model. Keep the `bitmaps` folder next to the scripts. Replacement pictures must have the size of the original (400x90 and 110x13); any uncompressed 8-, 24- or 32-bit BMP works. They are stored as 24-bit DIBs in place.
- **Names** (MU80 ... MU1000; MU50 keeps them): the About dialog and string table say S-YXG<n> instead of S-YXG50 (e.g. S-YXG1000), the internal name `xg50` becomes `mu<n>`, the default table name in the string table becomes the table just built, and the version info reads "Yamaha S-YXG<n> VSTi", "S-YXG<n>", "S-YXG<n>.DLL" and "Yamaha S-YXG<n> Portable VSTi". Hosts may list the plugin under its new name after a rescan.
- **Version info** (all models): the file version `2016,4,25,18` becomes the conversion date (`YYYY,MM,DD,0`), the FileVersion string `2016.04.25.0018` becomes `YYYY.MM.DD`, and the copyright reads "... 2016 VEG, 2026 Soundshock/NightFright".

The resource section grows by a few KB for this. The PE checksum is recalculated after patching.

The S-YXG50 sound engine itself, including its MMX/SSE paths, is not changed beyond the effect patches above. The MMX/SSE paths were checked: they read samples through a 32-bit pointer plus a 32-bit index, so they don't limit addresses.

### File names

- **Same name as supplied:** the patched DLL keeps the name of the supplied file, e.g. `mu800.dll` gives a patched `mu800.dll`. A name without an extension gets `.dll` added.
- **Several models in one run:** the DLLs are named after the model (`syxg80.dll` ... `syxg1000.dll`, MU50: `syxgmu50.dll`, because `syxg50.dll` is the original's name), and the supplied DLL stays unchanged.
- **ini:** it gets the same name with `.ini` (`mu800.ini`). The DLL looks for the ini under its own name, so if you rename the DLL later, rename the ini as well.
- **DLL already in the output folder:** it is replaced by the patched version, and the original is kept once as `<name>.orig.dll`. Later runs patch from that backup, so switching between models (Enhanced <-> Full) always starts from the original.
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

### Embedded tables (`--embed`)

- Table and wave file are stored in the patched DLL as `RT_RCDATA` resources under their file names, the same way the 5 MB `syxg50.dll` stores its own tables. Those old tables (`SXGBIN41.TBL`, `SXGWAVE4.TBL`) are removed first.
- The default table name in the DLL's string table is set to the new table, so the DLL finds it without an ini. No ini is written, and an existing ini of the same name is removed (an ini with a `SoftSynth` entry would make the DLL look for an external file instead).
- A DLL supplied as `syxg50.dll` is written as `syxg80.dll`, `syxg90.dll`, `syxg100.dll`, `syxg128.dll` or `syxg1000.dll`; other names are kept.
- One file to copy, at the cost of DLL size (MU1000: about 88 MB).

### How the DLL loads the table

1. **Table:** it reads `SoftSynth` from `[Config]` in `<dll name>.ini` and loads that file from the DLL's folder.
2. **Wave file:** the table header names the wave file, which is loaded from the same folder. Both files are read whole, so file size is not limited.
3. **Embedded:** without the key, the DLL loads the table named in its string table from its own resources (5 MB version, or a DLL made with `--embed`).

---

## MU Basic voice maps

The MU100, MU128 and MU1000 have two voice maps, which the module switches with its own Voice Map setting. Use `--mu-basic` to convert the second one:

| Map | Voices | PC 0 drum kit |
|---|---|---|
| Native (default) | revoiced (`GrandP #`, `BriteP #`, `Strngs1#`, ...) | native Standard Kit |
| MU Basic (`--mu-basic`) | MU90-compatible (`GrandPno`, `BritePno`, `Strings1`, ...) | MU90 Standard Kit |

`--mu-basic` switches the XG voice row, the XG drum program row and (on MU128/MU1000) the GM2 row to the basic map. GS, SFX and MSB 48 are the same in both maps. Output names get a `B` (`SXGMU1KBX.TBL`).

> **Note:** the newer kits (e.g. the Apogee Kit on XG drum program 30) exist in both maps. A song that selects such a kit sounds different on MU100+ tables than on MU80/MU90 tables, which fall back to the Standard Kit, and the same happens on real hardware.

---

## What the conversion does, per model

### All models

- **Bank maps:** program and drum kit bank maps are rebuilt for the S-YXG50 bank map format (XG, SFX, GS; MU128/MU1000 also GM2).
- **Duplicated banks (new):** a voice bank used on both the GS and the XG side is copied to the other side with its own index. The copy now also gets its program map. Before, the MU80's MSB 126/127 (which point to the GS bank) had an empty program map, so all 128 programs read the 8-byte debug label in front of the first voice as a voice (element count `0x70`).
- **Ext drum voices:** drum keys that play a full voice are placed in voice bank A, which the drum voice offsets require.
- **Drum EG rate (byte 13):** S-YXG50 = MU - `0x21`. The MU models store the rate with the offset that syxg50.dll adds itself. Without the correction, values >= `0x60` put the drum envelope into a special state, which made drums sound cut off. Calibrated against the S-YXG50 table: 245 of 253 matching MU80 drum voices, 426 of 460 MU90 drum voices.
- **LFO pitch modulation depth:** read with 6 bits instead of 5. The old mask halved the vibrato depth of voices like Siren, Ghost, Goblins and Wind.
- **24-bit loop lengths:** loops longer than 65,535 samples are written in full (they need the "Enhanced" or "Full" DLL).
- **Rising decay 2 (new, MU80 and later):** an amp EG whose decay 2 level is above its decay 1 level falls to the decay 1 level and climbs back. syxg50.dll does that too, but it ends the note as soon as the envelope is below level 64 (measured: decay 1 level 63 ends it at every key and velocity, 64 keeps it). Lite Org was only a click instead of a sustained organ; WireLead, synecho2, Bounce and Ana Echo have one such element. The decay 1 level is raised to 64 (-46 dB). The S-YXG50/MU50 data never does this.

### ADPCM loops

The MU hardware keeps decoding through a loop, carrying the decoder state from one pass into the next. A PCM table can only repeat one fixed loop. SXG-Create therefore emulates the passes until the decoder state settles, puts the transitional passes in front of the loop (lead-in) and uses the settled pass as the loop, so loops play back seamlessly.

- **Limits:** lead-in is only used while it fits the address range and the 24-bit start offset; drum samples in the classic layout are limited to a 16-bit start offset.
- **Statistics:** the run prints how many loops were already seamless, made seamless, or did not settle within 8 passes.

### MU50

- **Identical to Yamaha's own S-YXG50 table** in all voice and drum parameters (see [Verification](#verification-against-the-s-mu2000-and-the-s-yxg50)), but with the MU50's original sample data.

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

### Drum keys (MU90 and later, new)

- **HPF cutoff** (MU100 and later, drum voice byte `+21` / MU1000 `+20`): baked into a filtered copy of the drum sample. Measured on the S-MU2000: 2nd-order high-pass, Q about 1.0, cutoff at the output 2^(5.066 + 0.0591 x value) Hz (value 55 = 319 Hz, 94 = 1.57 kHz), independent of the note pitch. The sample is filtered in its own time base, so the cutoff is divided by its playback ratio.
- **Level offset** (MU100 and later, drum voice byte `+29`, signed): added to the key's level. Used by 11 keys of the MU1000/MU128 Standard Kit (e.g. Ride 1, Crash 1/2, Chinese, Ride 2, hi-hats) and 7 MU100 keys; without it the Ride 1 was 13.6 dB too loud.
- **Instant attack with equal decay rates:** syxg50.dll holds a drum key at full level for 18-120 ms before its decay starts, the MU decays after a few ms. For keys with attack `0x7F` and decay 1 = decay 2 (223 kit/key pairs in the MU1000 kits tested, e.g. Seq Click, Analog Kit hi-hat and toms) the converter selects an attack mode of the DLL without that hold (`0x60`). Seq Click: 4-7 dB too loud before, now within 1-2 dB of the S-MU2000.
- **Short decay 1 before a fast decay 2** (Hi Q, Click Noise, Short Guiro): the MU leaves decay 1 after about 1-2 dB, so these keys get the no-hold mode with one decay of the same energy (3.5-8 dB too loud before, now within 2 dB).
- **Velocity Pitch Sense / Velocity LPF Cutoff Sense:** syxg50.dll has no such drum parameters. Drum keys that use them are converted to ext drum voices whose element reproduces the drum playback of the DLL and adds the velocity dependency with constant pitch and filter EGs (`drumvel.py`). MU1000: 162 drum keys -> 158 ext drum voices.

Players that substitute "missing" programs from an instrument list (e.g. Falcosoft MIDI Player with `S-YXG50_XG-GS.ins`) replace the MU-only drum kits with the Standard Kit. Select an instrument definition for the converted model (e.g. `Yamaha_MU1000_XG.ins`).

### MU100

- **Wave ROMs:** three 32-bit pairs (MU90 pair + two new pairs), mapped to one address space.
- **Wavedata tables:** three, with their own offset tables (wave numbers 0-292 / 293-326 / 327-).
- **Voice map:** MU100 Native by default, MU Basic with `--mu-basic`.
- **Element HPF (new):** the MU100 stores the element HPF cutoff in element byte `+69` (unused on the MU90). It is the same value as byte `+80` of the MU128/MU1000 in all 1,925 elements of the voices both models have. It was not converted before, so 66 MU100 voices (86 elements, e.g. Oboe #, MuteGtr#, Wrench, Heinz, Parasite) sounded up to 13 dB too loud and dull in the low keys (Parasite up to 19 dB). Now they are filtered like on the MU128/MU1000.

### MU128 / MU1000

- **Program flash:** high/low 16-bit halves of a 32-bit bus, combined.
- **Elements:** 84-byte elements, mapped to the 78-byte S-YXG50 element almost 1:1. This was verified on 2,317 elements shared with the MU100, all 77 bytes match.
- **Drum voices:** 42 bytes in the MU90 layout, except byte 0, which moved to `+23`.
- **Voice maps:** MU Native by default, MU Basic with `--mu-basic`, plus GS, MSB 48 and GM2.
- **Element HPF (new, element byte `+80`):** 162 elements in 128 MU1000 voices, e.g. Oboe, Muted/Jazz/Overdrive Guitar, Slap Bass, Rock Organ. Same filter and cutoff scale as the drum HPF (measured on the S-MU2000). Baked into filtered copies of the multisamples (see [Why the wave files got bigger](#why-the-wave-files-got-bigger)). The HPF copies are cut in the transposed key range (key + coarse tune), as the DLL selects waves; this matters for 18 elements with both, e.g. Sleep (+24): low-band shape against the S-MU2000 -1.9 -> +0.3 dB.

### Voices with 3 or 4 elements (MU1000, new)

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
- **MU2000:** its program ROM needs a table that is not in the dump; the MU1000 set is used instead (same sound).
- **MU50 DOC bank:** the 'DOC' voice bank and drum kit are not converted. Some DOC drum voices appear to be missing data, so it would need reconstruction.
- **Remaining deviations:** most measured voices are within about ±2.5 dB of the S-MU2000; a few effect types and merged voices are 2-3 dB off. Some differences come from engine details that a table cannot change (e.g. the LFO phase).

---

## Using the converted DLLs

- **Host:** syxg50.dll is a 32-bit VST2 instrument. Any VST2 host works; to use it as a system MIDI device (e.g. for DOSBox or Windows games), load it through a VSTi MIDI driver.
- **Which model:** MU50 sounds like the DB50XG, SW60XG and the S-YXG50 itself, which is what most players of 1990s games heard. MU90/MU100 are good all-rounders with better samples and similar balance (MU100 = SW1000XG sound set). MU1000/MU128 have the best samples and the most voices, but are larger and partly revoiced; `--mu-basic` gives the MU90-compatible voice set for older material.
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
- **VEG** – [S-YXG50](https://veg.by/en/projects/syxg50/) (`syxg50.dll`)
- **Yamaha** – MU series tone generators and the S-YXG50 sound engine

DPCM delta table, DPCM limits table, and delta format decoding code based on MAME, copyright (c) MAME contributors, and related contributions by TaleTN, tarboh, and hockinsk under the BSD-3 license.

license: BSD-3-Clause

copyright-holders: Olivier Galibert
