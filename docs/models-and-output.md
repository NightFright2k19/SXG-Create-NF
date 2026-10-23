# Models, output files and table layouts

> **MU2000** (issue #53): it has the same voice data as the MU1000 (1,635 voices, 1,027 drum voices, 2,901 samples, the same wave ROMs); every table the converter reads is byte-identical, only at other addresses. Only the element filter/level scaling is stored differently: instead of 4 break points, each element holds an index into 1,377 tables of 128 notes, which lie in the upper half of the 4 MB firmware image (at `0x23CED0`, location from TaleTN's MUTable). The tables are the MU1000's break points interpolated per note (the formula reproduces all 5,306 scalings), and the converter turns them back into break points (`utility/scaling.py`): 1,376 tables give exactly the same 128 notes; one (an element of MuteGtr#, whose MU1000 break points cross) differs on 3 notes by up to 3 steps of the cutoff scaling. The break points are not always the MU1000's own (points on a straight part of the curve are free), so the voice level trims are keyed on the scaling written out per note and apply to both. With only the MU2000 set the result is `syxg2000.dll` (S-YXG2000, table `SXGMU2KX.TBL`, wave `SXGMU2KX.UPCM`); with both sets, only the MU1000 is converted, as the plugins would sound the same. The MU2000's own extras (sampling, plug-in boards, A/D input) have no counterpart in the S-YXG50.

## Output files and table layouts

| Models | Layout | DLL patch | Table | Wave data | Wave size |
|---|---|---|---|---|---|
| MU50 | classic | "Enhanced" | `SXGMU50a1.TBL` | `SXGMU50a1.UPCM` | 6.7 MB |
| MU80 | classic | "Enhanced" | `SXGMU80a1.TBL` | `SXGMU80a1.UPCM` | 12.7 MB |
| MU90 / MU90B | classic | "Enhanced" | `SXGMU90t.TBL` | `SXGMU90.UPCM` | 13.3 MB |
| MU100 | big | "Full" | `SXGMU100X.TBL` | `SXGMU100X.UPCM` | 51.8 MB |
| MU128 | big | "Full" | `SXGMU128X.TBL` | `SXGMU128X.UPCM` | 70.8 MB |
| MU1000 | big | "Full" | `SXGMU1KX.TBL` | `SXGMU1KX.UPCM` | 87.3 MB |
| MU2000 | big | "Full" | `SXGMU2KX.TBL` | `SXGMU2KX.UPCM` | 87.3 MB |

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
