# SXG-Create
MU in S-YXG50. Table Creation and AWM2 Data Table Investigation

# Installation & Usage
Requirements: Python 3.8 or newer

Basic usage: Drag & Drop your roms onto **main.py**

## Supplying a DLL

Add your own `syxg50.dll` to the ROM files (drag & drop or command line). Any file name works, the DLL is recognised by its content:

```
python main.py <roms...> syxg50.dll
python main.py <roms...> mu800.dll
```

The table layout and the DLL patch level follow the model automatically, no switch needed:

| Models | Table layout | DLL patch | Output |
|---|---|---|---|
| MU50 / MU80 / MU90 | classic | "Enhanced": 24-bit loop length | `<name>.TBL`, `<name>.UPCM` |
| MU100 / MU128 / MU1000 | big (32-bit addresses, 512 multisamples) | "Full": loop length + table size limits | `<name>X.TBL`, `<name>X.UPCM` |

Next to the table, SXG-Create writes a patched copy of the DLL under the same name and an ini with the matching name, e.g. `mu800.dll` + `mu800.ini`. The DLL reads the ini with its own name, so if you rename the DLL later, rename the ini too. Copy table, wave file, DLL and ini into one folder.

If the supplied DLL is already in the output folder (the folder of the ROMs), it is replaced by the patched one. The original is kept as `<name>.orig.dll`, and later runs patch from that copy again, so a run for another model always starts from the original. The ini is rewritten on every run and points to the table just built:

```
[Config]
SoftSynth=SXGMU1KX.TBL
Process=1
XGLite=0
DebugPanel=0
DisableGUI=0
```

Accepted DLLs: `syxg50.dll` with 626,688 bytes, or the 5,070,848-byte version with embedded tables, whose embedded table is then not used. DLLs that already carry these patches are accepted too. A table only works with a DLL patched for its layout: "Enhanced" for MU50 to MU90 tables, "Full" for MU100 and later.

Switch: `--mu-basic` (MU100 / MU128 / MU1000) converts the MU Basic voice map instead of the native one.

The easiest way to make use of the tables is with Veg's VST2 engine. 
Make sure the table & wave files are in the same folder as the dll and specify the table's name in the included ini. Embedded tables may have to be removed first, which can be done with ResourceExtractor

Everything is moving very quickly right now with XG preservation so keep an eye out for alternative engines!

# Compatibility

| model   | support | waves | Sample Formats   | XG Voices | XG Kits | GS Voices  | FX Passes |
|---------|---------|-------|------------------|-----------|---------|------------|-----------|
| S-YXG50 | --      | 4.1MB | U16 / U8         | 480       | 11      | 579        | 3         |
| MU50    | Yes     | 4MB   | S12/ADPCM/S8     | 480       | 11      | 579        | 3         |
| MU80    | Yes     | 8MB   | S16 / ADPCM      | 537       | 11      | 614        | 5         |
| MU90    | WIP     | 8MB   | S16/S12/ADPCM/S8 | 586       | 20      | 614        | 5         |

MU50 and MU80 are the most similar models to S-YXG50 and will work best

MU90 (**WIP** - currently not working): Believe or not it will fit inside S-YXG50, but there will be some loss to the conversion because of the larger data tables (+12 bytes for drums, 1 additional mysterious byte for voice wavedata)


# Limitations:

Tables run within S-YXG50 are going to be limited to the S-YXG50 engine's capabilities: 3 effects passes with 11/11/43 chorus/reverb/variation effects, no A/D input. This is analogous to the MU50, but a bit less capable than what the MU80 can do.

MU50: The 'DOC' voice bank & drum kit are not preserved. It may be possible to remap them somewhere, but some of the DOC kit's drum voices appear to be missing crucial data for some reason, so it might take some reconstruction.

MU80: A few of the synth pads are simply too long to fit in the S-YXG50's 16-bit loop offset. For now they are clamped, and there may be a slight click when they loop.

MU80: The demo song ("Out Of The Muse") does not sound right, probably due to the missing effects.


# 

DPCM delta table, DPCM limits table, and delta format decoding code based on Mame, copyright (c) MAME contributors, and related contributions by TaleTN, tarboh, and hockinsk under BSD-3 license

license:BSD-3-Clause

copyright-holders:Olivier Galibert
