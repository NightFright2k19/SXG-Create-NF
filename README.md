# SXG-Create

Converts the ROM sets of Yamaha MU-series tone generators into tables and wave data for the **S-YXG50** soft synthesizer (`syxg50.dll`), and optionally patches the DLL and writes a matching `.ini`.

This document is the reference for the current state of SXG-Create: supported models, command line, output files, the automatic DLL patching, and what the conversion does for each model.

## Table of contents

- [Quick start](#quick-start)
- [Command line parameters](#command-line-parameters)
- [Supported models and ROM sets](#supported-models-and-rom-sets)
- [Output files and table layouts](#output-files-and-table-layouts)
- [DLL patching and ini creation](#dll-patching-and-ini-creation)
- [MU Basic voice maps](#mu-basic-voice-maps)
- [What the conversion does, per model](#what-the-conversion-does-per-model)
- [Behaviour on reruns](#behaviour-on-reruns)
- [Investigation tools](#investigation-tools)
- [Testing status](#testing-status)

---

## Quick start

```
python main.py <ROM files...> [syxg50.dll] [--mu-basic]
```

You can also drag & drop all files onto `main.py`.

- **Inputs:** ROM files in any order. SXG-Create detects the model from the CRC32 of the files, so the file names don't matter.
- **Optional DLL:** one `syxg50.dll` under any file name. SXG-Create writes a patched copy of it plus a matching `.ini`.
- **Output folder:** all output goes to the folder of the (first) program ROM.
- **Requirements:** Python 3.12 or newer (`dataCRCs.py` uses nested f-strings). No extra packages.

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

---

## Command line parameters

| Parameter | Meaning |
|---|---|
| `<ROM files>` | Program ROM(s) and wave ROMs of one model, in any order (see [Supported models](#supported-models-and-rom-sets)). Required. |
| `<dll>` | Optional. A `syxg50.dll`, under any file name (`syxg50.dll`, `mu800.dll`, ...). It is recognised by its content, not its name. See [DLL patching](#dll-patching-and-ini-creation). |
| `--mu-basic` | MU100 / MU128 / MU1000 only. Converts the "MU Basic" voice map instead of the native one (see [MU Basic voice maps](#mu-basic-voice-maps)). Ignored for other models, with a note. |

There are no other switches. The table layout and the DLL patch level are chosen automatically from the detected model (see [Output files and table layouts](#output-files-and-table-layouts)).

---

## Supported models and ROM sets

| Model | Program ROM(s) | Wave ROMs | Table layout |
|---|---|---|---|
| MU50 (xr174c0 v1.05) | `xr174c0.ic7` | `xq057c0.ic18`, `xq058c0.ic19` | classic |
| MU80 (xq556a0 v1.04) | `yamaha_mu80.bin` | `xq012b0-822.bin`, `xq013b0-823.bin`, `xq089b0-824.bin`, `xq090b0-825.bin` | classic |
| MU90 (xs519d0 v1.01) | `xs519d0.ic9` | `xs518a0.ic22`, `xs743a0.ic23` | classic |
| MU90B (xt040c0 v1.01) | `xt040c0.ic9` | `xs518a0.ic22`, `xs743a0.ic23` | classic |
| MU100 (xu50720 v1.11) | `xu50720.ic11` | `xs518b0.ic34`, `xs743b0.ic35`, `xt445a0-828.ic36`, `xt461a0-829.ic37`, `xt462a0.ic39`, `xt463a0.ic38` | big |
| MU128 (v2.00) | `mu128-v2.00-h.bin`, `mu128-v2.00-l.bin` | `xv364a0.ic53`, `xv365a0.ic54`, `xv366a0.ic57`, `xv376a0.ic58` | big |
| MU1000 (v2.01) | `mu1000-v2.01-h.bin`, `mu1000-v2.01-l.bin` | `xv364a0.ic49`, `xv365a0.ic50`, `xw848a0.ic53`, `xw849a0.ic54` | big |
| MU2000 (v2.01) | detected, but not converted | | |

> **MU2000:** it has the same voice data as the MU1000. Its program ROM stores the element filter/level scaling as an index into a table that is missing from the dump, so SXG-Create stops with a message to use the MU1000 ROM set instead, which gives the same sound set.

The S-YXG50's own tables and `Vampire.dll` are recognised as well, but they are not a conversion source.

---

## Output files and table layouts

The layout follows the model:

| Models | Layout | DLL patch | Table | Wave data | Wave size |
|---|---|---|---|---|---|
| MU50 | classic | "Enhanced" | `SXGMU50a1.TBL` | `SXGMU50a1.UPCM` | |
| MU80 | classic | "Enhanced" | `SXGMU80a1.TBL` | `SXGMU80a1.UPCM` | |
| MU90 / MU90B | classic | "Enhanced" | `SXGMU90t.TBL` | `SXGMU90.UPCM` | 13.3 MB |
| MU100 | big | "Full" | `SXGMU100X.TBL` | `SXGMU100X.UPCM` | 32.4 MB |
| MU100 `--mu-basic` | big | "Full" | `SXGMU100BX.TBL` | `SXGMU100BX.UPCM` | |
| MU128 | big | "Full" | `SXGMU128X.TBL` | `SXGMU128X.UPCM` | 38.4 MB |
| MU128 `--mu-basic` | big | "Full" | `SXGMU128BX.TBL` | `SXGMU128BX.UPCM` | |
| MU1000 | big | "Full" | `SXGMU1KX.TBL` | `SXGMU1KX.UPCM` | 51.2 MB |
| MU1000 `--mu-basic` | big | "Full" | `SXGMU1KBX.TBL` | `SXGMU1KBX.UPCM` | |

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
| Multisamples | 256 | 512 (voices in bank B use wave numbers 256-511) |
| Wavedata sample address | 24 bit at `+0x09`, format at `+0x0C` | 32 bit at `+0x09`, format at `+0x0D` |
| Drum voice ext index | `+0x10..+0x11` BE | `+0x10..+0x11` LE (`+0x11 = 0xFF`: internal sample) |
| Drum voice root key | `+0x12` | `+0x0A` |
| Drum voice start / loop length | 16 / 16 bit | 24 / 24 bit (`+0x12`, `+0x15`) |
| Drum voice sample address | 24 bit at `+0x18`, format at `+0x1B` | 26 bit at `+0x18` (max. 64 MB), top two bits = format |
| Sample data | U16 / U8 | U16 / U8 (unchanged) |

> Classic tables only run on an "Enhanced" DLL, and big tables only on a "Full" DLL.

---

## DLL patching and ini creation

If a DLL is among the input files, SXG-Create patches it for the table being built.

### Accepted DLLs

Any input file that starts with `MZ` is taken as the DLL and identified by its content:

| CRC32 | File |
|---|---|
| `38A60E61` | `syxg50.dll`, 626,688 bytes |
| `80EFA471` | `syxg50.dll`, 5,070,848 bytes (with embedded tables) |

- **Already-patched DLLs:** a DLL with the right size but an unknown CRC (one that already carries these patches) is accepted and checked patch by patch. Every patch must find either its original bytes or the patched bytes, otherwise the DLL is rejected.
- **Other DLLs:** these are rejected, including `YMF-754Hi.dll`.
- **5 MB version:** this one works too. Its embedded (classic) table is simply not used, because the ini always names the external table.
- **One DLL per run:** if both `<name>.dll` and its backup `<name>.orig.dll` are passed (e.g. by dropping a whole folder), `<name>.dll` is used.

### Patch levels (chosen automatically)

| Level | Used for | Patches |
|---|---|---|
| "Enhanced" | MU50 / MU80 / MU90 | ini names, 24-bit loop length |
| "Full" | MU100 / MU128 / MU1000 | everything in "Enhanced" + table size limits (big layout) |

The patch sites in `syxg50.dll` (file offset = RVA):

| Offset | Patch | Level |
|---|---|---|
| `0x519EC` | ini section `SYXG50` -> `Config` | both |
| `0x519F4` | ini key `VoiceTable` -> `SoftSynth` | both |
| `0x1A6F0`, `0x1A6FC` | key-on masks for start offset / loop length: 16 -> 24 bit | both |
| `0x045E0` | voice program maps: 32-bit byte offsets | Full |
| `0x04DF4` + code cave `0x3F360` | wavedata offset table 32-bit + 512 multisamples (wave number + 256 for elements in bank B when the table has more than 256 entries); `.text` VirtualSize enlarged to cover the cave | Full |
| `0x05BFE`, `0x16E6F`, `0x16EA5`, `0x16EC4`, `0x16EDB` | drum voice: internal sample if `+0x11 == 0xFF` | Full |
| `0x0AFDA` | ext drum voice index 16-bit LE, 32-bit offset table | Full |
| `0x05C13`, `0x05CB0` | wavedata format byte at `+0x0D` | Full |
| `0x05C44` | drum format bits from the top byte of the sample address | Full |
| `0x1379D` | drum root key at `+0x0A` | Full |
| `0x08325`, `0x08410` | drum setup default byte `+0x0A` (rcv note on) = 1 | Full |
| `0x138F0` | drum voice sample fields: start 24 bit, loop length 24 bit, address 26 bit + format | Full |
| `0x15620` | wavedata entry: loop length 24 bit, address 32 bit, format `+0x0D` | Full |

The PE checksum is recalculated after patching.

Only the table loading code changes. The S-YXG50 sound engine, including its MMX/SSE paths, stays as it is. Those paths were checked: they read samples through a 32-bit pointer plus a 32-bit index, so they don't limit addresses.

### File names

- **Same name as supplied:** the patched DLL keeps the name of the supplied file, e.g. `mu800.dll` gives a patched `mu800.dll`. A name without an extension gets `.dll` added.
- **ini:** it gets the same name with `.ini` (`mu800.ini`). The DLL looks for the ini under its own name, so if you rename the DLL later, rename the ini as well.
- **DLL already in the output folder:** this is the usual case, because it lies next to the ROMs. It is replaced by the patched version, and the original is kept once as `<name>.orig.dll`. Later runs patch from that backup, so switching between models (Enhanced <-> Full) always starts from the original.
- **DLL in another folder:** it stays unchanged, and the patched copy is written to the output folder.

### The ini

The ini is written on every run and always points to the table that was just built (CRLF line endings):

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

### How the DLL loads the table

1. **Table:** it reads `SoftSynth` from `[Config]` in `<dll name>.ini` and loads that file from the DLL's folder.
2. **Wave file:** the table header names the wave file, which is loaded from the same folder. Both files are read whole, so file size is not limited.
3. **Fallback:** without the key, the DLL falls back to its embedded table (5 MB version only).

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
- **Ext drum voices:** drum keys that play a full voice are placed in voice bank A, which the drum voice offsets require.
- **Drum EG rate (byte 13):** S-YXG50 = MU - `0x21`. The MU models store the rate with the offset that syxg50.dll adds itself. Without the correction, values >= `0x60` put the drum envelope into a special state, which made drums sound cut off. Calibrated against the S-YXG50 table: 245 of 253 matching MU80 drum voices, 426 of 460 MU90 drum voices.
- **LFO pitch modulation depth:** now read with 6 bits instead of 5. The old mask halved the vibrato depth of voices like Siren, Ghost, Goblins and Wind.
- **24-bit loop lengths:** loops longer than 65,535 samples are written in full (they need the "Enhanced" or "Full" DLL).

### ADPCM loops

The MU hardware keeps decoding through a loop, carrying the decoder state from one pass into the next. A PCM table can only repeat one fixed loop. SXG-Create therefore emulates the passes until the decoder state settles, puts the transitional passes in front of the loop (lead-in) and uses the settled pass as the loop, so loops play back seamlessly.

- **Limits:** lead-in is only used while it fits the address range (16 MB classic, 64 MB big) and the 24-bit start offset; drum samples in the classic layout are limited to a 16-bit start offset.
- **Statistics:** the run prints how many loops were already seamless, made seamless, or did not settle within 8 passes.

### MU80

- **Format bit 6 (`0x40`, `0xC0` vs `0x80`):** investigated and found to have no audible meaning the table format could express. Both values are treated as 16-bit PCM.

### MU90 / MU90B

- **Wave ROMs:** `xs518a0` and `xs743a0` are the two 16-bit halves of one 32-bit data bus and are interleaved word by word. Loop addresses count 32-bit words.
- **Sample formats:** 16 bit, 12 bit (LE bit stream), 8 bit and ADPCM, all converted.
- **Reverse flag:** wavedata `+8` / drum voice `+34`, bit 7. The hardware plays such samples backwards from the loop address, and the converter reverses the data (one-shot). This fixes e.g. the toms of the standard kits, MelodTom and Real Tom, and also gives Rev Tom / Rev Kick.
- **42-byte drum voices:** converted to the 30-byte S-YXG50 layout. The extra EQ bytes are dropped.
- **Long drum bodies (classic layout):** four XG open hi-hats have a 70,626-sample body, more than the 16-bit drum start offset allows. Instead of cutting the attack, the loop start is moved earlier by the excess, so the sound starts at its real beginning.
- **Bank map order:** XG (LSB), SFX (MSB), GS.

### MU100

- **Wave ROMs:** three 32-bit pairs (MU90 pair + two new pairs), mapped to one address space.
- **Wavedata tables:** three, with their own offset tables (wave numbers 0-292 / 293-326 / 327-).
- **Voice map:** MU100 Native by default, MU Basic with `--mu-basic`.

### MU128 / MU1000

- **Program flash:** high/low 16-bit halves of a 32-bit bus, combined.
- **Elements:** 84-byte elements, mapped to the 78-byte S-YXG50 element almost 1:1. This was verified on 2,317 elements shared with the MU100, all 77 bytes match. Voices with 3 or 4 elements keep their first two, the S-YXG50 maximum.
- **Drum voices:** 42 bytes in the MU90 layout, except byte 0, which moved to `+23`.
- **Voice maps:** MU Native by default, MU Basic with `--mu-basic`, plus GS, MSB 48 and GM2.

---

## Behaviour on reruns

- **Table and DLL output:** an existing table file is skipped. The DLL and ini are rewritten on every run.
- **Wave file:** if it already exists, the run stops before writing it ("already exists, exiting early"). Delete or move the old table and wave file before rebuilding the same model.

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

---

## Testing status

- **Byte-identical rebuilds:** tables, wave files and patched DLLs were compared against earlier builds and match.
- **Emulation:** all "Full" parser patches were emulated with test data (Unicorn).
- **Big-layout samples:** every sample in the MU100/MU128/MU1000 big tables was compared bit for bit with an independent 16-bit build.
- **Not tested yet:** the big layout ("Full" DLL) in a real host. Feedback on MU100+ tables, especially drums with 8-bit samples and voices on page 2 (wave numbers >= 256), is welcome.
