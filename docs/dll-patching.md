# DLL patching

If a DLL is among the input files, SXG-Create patches it for the table being built.

## Accepted DLLs

Any input file that starts with `MZ` is taken as the DLL and identified by its content:

| CRC32 | File |
|---|---|
| `38A60E61` | `syxg50.dll`, 626,688 bytes |
| `80EFA471` | `syxg50.dll`, 5,070,848 bytes (with embedded tables) |

- **Already-patched DLLs:** a DLL with the right size but an unknown CRC (one that already carries these patches) is accepted and checked patch by patch. Every patch must find either its original bytes or the patched bytes, otherwise the DLL is rejected. So a DLL patched by an older version gets the new patches on top.
- **Other DLLs:** these are rejected, including `YMF-754Hi.dll`.
- **5 MB version:** this one works too. Its embedded (classic) table is not used, because the ini names the external table; with `--embed` its tables are replaced.
- **One DLL per run:** if both `<name>.dll` and its backup `<name>.orig.dll` are passed (e.g. by dropping a whole folder), `<name>.dll` is used. A DLL given on the command line wins over one in the `source` folder.

## Patch levels (chosen automatically)

| Level | Used for | Patches |
|---|---|---|
| "Enhanced" | MU50 / MU80 / MU90 | ini names, 24-bit loop length, drum EG offsets, effect types, effect return levels, effect fade-in, port select ignored, Setup page (layout, effect names, Output Level range, Send Reset), panel preset buttons, bitmaps, names, version info |
| "Full" | MU100 / MU128 / MU1000 | everything in "Enhanced" + table size limits (big layout) + voice map switch |

## Patch sites in `syxg50.dll` (file offset = RVA)

**Table loading**

| Offset | Patch | Level |
|---|---|---|
| `0x519EC` | ini section `SYXG50` -> `Config` | both |
| `0x330FC`, `0x3311C` + code in section `.sxp` (`dev/poly/ini.asm`) | ini lookup (issue #36): each key is read from `[Config]`, then `[SYXG50]`, then `[<plugin id>]` (`ini_id` in the code, set per model); the table from `VoiceTable` or `SoftSynth`. The original strings `SYXG50` / `VoiceTable` (`0x519EC`, `0x519F4`) stay as they are. | both |
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
| `0x03875`, `0x30B91`, `0x30BBA`, `0x30BEF`, `0x30C5F`, `0x02B50`, `0x02BB0` + code cave `0x3F6B0`-`0x3FA20`, dialog resource 111, `.data` VirtualSize -> `0x5E40` | **Voice map switch** (Full only; see [MU Basic voice maps](gui.md#mu-basic-voice-maps)). After the table setup, the cave looks for the voice map appendix behind the table sections (`MAP2`), remembers the 8 bank/drum row pointers and points them at the appendix rows when `[Config] MUBasic=1` selects MU Basic. A checkbox (control `0x420`) is added to the Setup page; Init and Set Defaults set it, a click enables Apply, and Apply switches the rows. Since issue #26 it is hidden and driven by the "MU Tone Map" radio buttons (see the Setup page row below). `[Config] MUBasic` sets the mode only at the first table setup of the process (flag `.data` `0x56DC3`, issue #65): with embedded tables every engine start runs the table setup again (one per instance and the second engine of the polyphony patch), and before the fix each one reset the mode to the start value. The plugin state (VST chunk) carries the setting: getChunk (`0x10002B50`) returns a copy with 3 more bytes `'V','M',<mode>` (bank 33 -> 36 bytes, program 5 -> 8 bytes), setChunk (`0x10002BB0`) takes the mode from such a chunk (also before the first table setup) and passes the original size on; old 33/5-byte chunks are still accepted. Nothing is written to a file. Without an appendix the checkbox is hidden and the chunk stays unchanged. The cave code is position independent; its state lives in `.data` at `0x56DC0` (chunk copy at `0x56E00`). |
| `0x07560` + code cave `0x3FA20`-`0x3FA7B` | **Voice map switch, immediate** (Full only). The MIDI channel event entry (audio thread) compares the XG bank map row pointer (`0x100552D8`) with the last one it saw (`.data` `0x56DE8`). After a switch (Setup page or plugin state) all 16 parts re-run their program change with their current program (part `+0x6A`, handler table `0x10041BB0`[4]; *receive program change* is honoured) before the event is handled. Notes already sounding keep their voice. Position independent. |
| `0x010A0`, `0x010C0`, `0x30AF0`, `0x320EE`, `0x3233D`, `0x32407`, `0x32427`, `0x3246B` + code in the unused NOP block `0x33150`-`0x338A1` (no relocations there), bitmaps 101 / 106, `.data` VirtualSize -> `0x5E6C` | **Panel controls** (all models, issues #16, #23, #35, #42): the panel is 24 pixels higher (400 x 114): editor rect and window height (`0x3257D`, `0x326D5`), the whole-bitmap paint (`0x322DF`) and the lower part move down 24 pixels: meter screen background (`0x32233`, `0x3224F`), level meters (`0x32130`), POLYPHONY digits (`0x32186`), XG / GS lamps (`0x321DF`, `0x32208`), SETUP button picture and hit test (`0x3253E`, `0x324D6`, `0x324DB`). The control row (`utility/dev/poly/panel.asm`, section `.sxp`): eight buttons in row 31 (CHN 25 / 73, PRG 116 / 174, MSB 221 / 279, LSB 323 / 381), readouts in row 32 (CHN 46, PRG 137, MSB 242, LSB 344); WM_LBUTTONDOWN / WM_LBUTTONUP / WM_TIMER / WM_MOUSEWHEEL as before; per instance (issue #55) the panel keeps its state in a panel record of its engine (panel object `+8` = plugin `+0xB0`; 4 records x 16 bytes at `.data` `0x56F08`, claimed with `lock cmpxchg`, freed at effClose): the channel (`+7`) changes at once, PRG / MSB / LSB steps are pending (`+4`, `+5`, `+6`) and sent by the audio thread of that plugin (`panel_prog`, program change or CC 0 / CC 32 + program change, to its engine and its engine B); the readouts stay blank until that thread has processed the engine (`+0xC`). **Preview note** (issue #43): a left click in the POLYPHONY field (x 245-298, y 57-103) sets record `+0xA` and captures the mouse, the button release clears it; the wheel there changes the note (`+8`, stored XOR `0x3C` so that zeroed `.data` means 60 = C4, range 24-127). `panel_prog` calls `pp_prev` first, which compares the wanted note with the sounding one (`+9` = note + 1, channel `+0xB`) and sends note off / note on (velocity 100) to engine A only (`pv_send`; engine B renders only while the dispatcher has given it notes, issue #46). Parts: the synth (engine `+8`) keeps them in the order of channels 10, 1-9, 11-16, records of `0x11C` bytes from `+0x248` (`+0` MSB, `+1` LSB, `+2` program); engine mode `+0x63B0` (0 XG, 1 GM, 2 GM2), `+0x63AE` (0 = GS). Bitmaps: see **Bitmaps** below. |
| `0x30AF0`, `0x31142`, `0x30B4E` + code in the unused NOP block `0x2F6D3`-`0x2FB60` (and the panel cave above), gain table `0x4DF10`, dB texts `0x4E748`, vtable slots `0x40594`/`0x40598`/`0x407AC`/`0x407B0`, dialog resource 111, `.data` VirtualSize -> `0x5EB8` | **Setup page layout, Output Level, Send Reset** (all models, issues #26, #37). Dialog 111: the seven polyphony preset buttons are removed and the frames move up; the effect checkboxes read "Reverb (CC 91)", "Chorus (CC 93)", "Variation (CC 94)"; the Output Level trackbar gets tick marks (ends + centre, TBM_SETTIC 101); Full: a "Utility" frame (41 units high) holds the Send Reset push buttons (`0x42C` MT-32 26 x 15, `0x423` GM, `0x424` GS, `0x425` XG, `0x42B` GM2 20 x 15, at x 8 / 37 / 60 / 83 / 106, y 133, label `0x42A`) and the MU Tone Map radio buttons (`0x427` Basic / `0x428` Native at y 136, label `0x429`), the page is 177 units high; Enhanced (MU50 / MU80 / MU90): the frame is titled "Send Reset" and holds only the buttons (x 11 / 42 / 67 / 92 / 117, y 124; MT-32 26 units wide, the others 20), frame 31 units high, page 167 units. "Set Defaults" sits below the frame. **Output Level:** the value byte keeps its meaning (101 = 0 dB, the default), the trackbar range becomes 77-125 (`0x30B4E`), WM_HSCROLL clamps to it (`0x31142` -> cave), the gain table (128 floats) and the dB texts (6 bytes each) get -12 ... +12 dB in 0.5 dB steps (values outside the range count as -12 / +12 dB). **Page procedure** (`0x10030AF0` -> cave): a Send Reset button marks its reset pending (`.data` `0x56E40`: 1 GM, 2 GS, 3 XG, 4 GM2, 5 MT-32 = the 27 messages of `mt32.syx` one after the other; nothing stored, Apply untouched); a Tone Map click sets the hidden checkbox `0x420` and enables Apply. After WM_INITDIALOG / Set Defaults the page's own code runs first, then the Tone Map controls are set from the state; without a voice map appendix they are hidden. **Reset handling** (issue #37): the process / processReplacing wrappers (`0x100010A0` / `0x100010C0`, audio thread) send a pending reset through the engine's SysEx entry (engine = plugin `+0xB0`, vtable `+0x0C`, both engines) before the block is rendered; host resets are not looked at. For 4800 samples after it (100 ms at 48 kHz) host events and preset steps are held back in a 64 KB queue (VirtualAlloc on first use) and passed on with deltaFrames 0 in the first block after that; a block with a dropped reset alone goes through the same queue at once (pending value 6). **Plugin state:** the getChunk / setChunk slots of both AudioEffect vtables (`0x40594`/`0x407AC`, `0x40598`/`0x407B0`) point to the cave, which calls the original functions (voice map patch included) and appends / takes off `'R','P',<mode>,<extra voices>` (see Polyphony up to 256 below) (bank 33 (+3) -> 37 (40) bytes, program 5 (8) -> 9 (12)); the Reset Mode byte of earlier versions is ignored and no reset is sent; chunks without it are passed on unchanged. Copy buffer `.data` `0x56E70`, VirtualSize -> `0x5EB8`. Position independent; sources in `utility/dev/gui` (`gui.asm`, `settings.asm`, `mkgui.py`). |
| `0x01000`, `0x010A0`, `0x010C0`, `0x30B1D`, `0x30F31`, `0x320A0` + new section `.sxp` at `0x5B000` (inserted in front of `.rsrc`, which moves up by its size, two pages since #55; resource directory and data entries follow), `.data` VirtualSize -> `0x5F48` | **Polyphony up to 256** (all models, issue #14). The process / processReplacing wrappers (`0x100010A0` / `0x100010C0`) jump to `poly_procA` / `poly_procR` in `.sxp`: per plugin a slot (`.data` `0x56EC0`, 4 x 16 bytes: plugin, AEffect of engine B, samples B stays awake, event lists) is looked up; in the first block engine B is made with VSTPluginMain (`0x10003610`, own audioMaster stub answering only the version) and gets effOpen, sample rate, block size, mains on. Then `send_pending` (Send Reset, preset steps) runs as before; its resets and program steps go to both engines (`both_sysex` / `both_short`). Each block B gets A's settings through the settings object (the engine object `[plugin +0xB0]`, vtable `0x1004E110`; Set `0x10030770`; B's polyphony = the voices above 128, `.data` `0x56EB8`), the host events (`plugin +0xE0`) are split: a Note On goes to A while A has two voices free (synth `+0x64BE`), else to B while B has two free (polyphony `+0x64C0`), else to A; everything else to both. A renders, then B with the accumulating process (`vtable +0x10`) while it has voices and 4 s longer (and 250 ms after a SysEx); waking up, B takes A's control-rate counters (`plugin +0xE4..+0xEC`); asleep, B's events go through its engine entries (`+0x08` / `+0x0C`). The dispatcher (`0x10001000`) closes B on effClose. **Panel readout:** the POLYPHONY readout asks the settings object for the voices in use (Get, op 4, `0x100320A0`); `poly_count` adds engine B's voices in use. **Setup page:** trackbar range 8-256 (`0x30B1D`), WM_HSCROLL (`0x30F31` -> `poly_scroll`) keeps the settings byte up to 128 and the rest as extra voices on the page (`0x56EB9`), committed on PSN_APPLY; `.data` `0x56EB8` holds the extra voices XOR 0x80, so without a saved state (and with Set Defaults) the total is 256; the plugin state appends `'R','P',<mode>,<extra>` (older `'R','S'` chunks: extra 128). Source `utility/dev/poly/poly.asm`, generated with `utility/dev/gui/mkgui.py`. Port engines (`F5 02`-`04`, issue #74): the slot's list block (VirtualAlloc 0x8000 bytes instead of 0x4000) holds the current port (+0x3008), the last reset SysEx (+0x3040), three pseudo-slots (+0x3010, same layout as a slot) and three event lists (+0x4000, +0x5010, +0x6020). `route` takes `F5 nn` out of the event list, sends the channel messages of port 2-4 to that port's list only, SysEx and system messages to all lists, and a reset selects port 1 again; the engine is made at the first `F5` with `create_inst` (as B) and gets A's settings every block (`sync_p`, polyphony 128), then renders after B with the same sleep rules. |
| `0x08C24`, `0x08C75`, `0x08CDF` | **Effect fade-in after a type change:** the handler mutes the block, and a ramp run every 10 ms brings it back in steps of 4: reverb 0.64 s, chorus 1.03 s, variation 0.32-0.9 s. Larger steps (reverb 32, chorus 52, variation 40) end the ramp after 80-90 ms; the end values are unchanged. |
| `0x03723` | **Port select `F5 nn` ignored** (issue #74): the synth's short message method (0x10003700) stored `nn - 1` as port and added port × 16 to the channel of every later message, and the channel method drops channels ≥ 16, so after `F5 02` or higher every message was lost, even after a reset, until an `F5 01`. `F5` now always selects port 1 (the branch for `nn` = 0 / 0x7F), so all messages stay on channels 1-16, as in the S-YXG2006LE. More than 16 channels are not supported (they play on port 1). |

**Resources**

- **Bitmaps:** bitmap 101 (the panel picture, 400 x 114 since issue #42) is built from `utility/bitmaps/Panel101.bmp` (the same for every model, with the control row) and the model name `utility/bitmaps/Name_<model>.bmp` pasted at (300, 0) (MU50 / original: S-YXG50); bitmap 106 gets `PanelButtons.bmp` (pressed buttons, dash) appended and, behind it, the dimmed digits 0-9 for the PRG field of a drum part (issue #70: made by `dllpatch.py` from `Bitmap105.bmp`, their contrast to the field is `DRUM_DIGIT_PERCENT` = 65) and the red digits for a part without an instrument (issue #73: made the same way, `NO_VOICE_PERCENT` in `dllpatch.py`); bitmap 106 is 400 x 16 then; bitmap 105 becomes `utility/bitmaps/Bitmap105.bmp`. Keep the `bitmaps` folder in `utility`. All are made by `utility/dev/gui/mkpanel.py` from the template and mockup of issue #42 (`utility/dev/gui/panel42/`). Bitmap 105 must keep the original size (110x13); any uncompressed 8-, 24- or 32-bit BMP works.
- **Names** (MU80 ... MU2000; MU50 keeps the S-YXG50 names, only its default table name is set): the About dialog and string table say S-YXG<n> instead of S-YXG50 (e.g. S-YXG1000), the internal name `xg50` becomes `mu<n>`, the default table name in the string table becomes the table just built, and the version info reads "Yamaha S-YXG<n> VSTi", "S-YXG<n>", "S-YXG<n>.DLL" and "Yamaha S-YXG<n> Portable VSTi". Hosts may list the plugin under its new name after a rescan.
- **Version info** (all models): the file version `2016,4,25,18` becomes the conversion date (`YYYY,MM,DD,0`), the FileVersion string `2016.04.25.0018` becomes `YYYY.MM.DD`, and the copyright reads "... 2016 VEG, 2026 Soundshock/NightFright".

The resource section grows by a few KB for this. The PE checksum is recalculated after patching.

The S-YXG50 sound engine itself, including its MMX/SSE paths, is not changed beyond the effect patches above. The MMX/SSE paths were checked: they read samples through a 32-bit pointer plus a 32-bit index, so they don't limit addresses.

## File names

- **`syxg50.dll` is never overwritten:** a DLL supplied as `syxg50.dll` (or `syxg50.orig.dll`) is written under the model's name: `syxgmu50.dll` (MU50, because `syxg50.dll` is the original's name), `syxg80.dll`, `syxg90.dll`, `syxg100.dll`, `syxg128.dll`, `syxg1000.dll` or `syxg2000.dll`, in single and multi-model runs, with and without `--embed`. The supplied `syxg50.dll` stays unchanged.
- **Other names are kept:** e.g. `mu800.dll` gives a patched `mu800.dll`. A name without an extension gets `.dll` added.
- **ini:** it gets the same name with `.ini` (`mu800.ini`). The DLL looks for the ini under its own name, so if you rename the DLL later, rename the ini as well.
- **DLL with another name already in the `output` folder:** it is replaced by the patched version, and the original is kept once as `<name>.orig.dll`. Later runs patch from that backup, so switching between models (Enhanced <-> Full) always starts from the original.
- **DLL in another folder** (e.g. `source`): it stays unchanged, and the patched copy is written to `output`.

## The ini

The ini is written on every run (not with `--embed`) and points to the table that was just built (CRLF line endings):

```ini
[SYXG1000]
VoiceTable=SXGMU1KX.TBL
Process=1
XGLite=0
DebugPanel=0
DisableGUI=0
```

The section is the plugin's own name in capitals, the DLL name without `.dll`: `[SYXGMU50]`, `[SYXG80]`, `[SYXG90]`, `[SYXG100]`, `[SYXG128]`, `[SYXG1000]`, `[SYXG2000]`. Two other sections are read as well, so older and original ini files keep working (issue #36):

- `[Config]` with `SoftSynth=` (written by SXG-Create before; still read and checked first),
- `[SYXG50]`, the section of the original S-YXG50. Falcosoft's MIDI Player and VST MIDI Driver write `DebugPanel` there when you switch the debug view with their UI button; it is read before the plugin's own section, so that switch works with these plugins as well.

Each key is looked up in `[Config]`, then `[SYXG50]`, then `[<plugin id>]`; the first section that has it wins. The table key can be `VoiceTable` (as in the original S-YXG50) or `SoftSynth`. The S-YXG2006LE reads no ini (its settings are VST parameters).

| Key | Meaning |
|---|---|
| `VoiceTable` (or `SoftSynth`) | Table file to load, relative to the DLL's folder. The wave file name is stored in the table header, so it doesn't need an entry. |
| `Process` | Processing switch of the S-YXG50 (left at 1) |
| `XGLite` | XG Lite mode (0 = off) |
| `DebugPanel` | 1 = show the monitor panel instead of the normal panel: part levels 1-16, polyphony, TG load (total / setup / wave / synth), effect load (total / reverb / chorus / variation), output, CPU load (TG / driver) and a Setup button. All readouts work (checked under Wine with notes playing). |
| `DisableGUI` | 1 = no GUI window |
| `MUBasic` | **New**, optional, MU100 / MU128 / MU1000 only: start value of the voice map (1 = MU Basic, 0 = MU Native, default 0). Only read, never written; a setting saved by the host overrides it. |

## Embedded tables (`--embed`)

- Table and wave file are stored in the patched DLL as `RT_RCDATA` resources under their file names, the same way the 5 MB `syxg50.dll` stores its own tables. Those old tables (`SXGBIN41.TBL`, `SXGWAVE4.TBL`) are removed first.
- The default table name in the DLL's string table is set to the new table, so the DLL finds it without an ini. No ini is written, and an existing ini of the same name is removed (an ini with a `VoiceTable` / `SoftSynth` entry would make the DLL look for an external file instead).
- A DLL supplied as `syxg50.dll` is written under the model's name (`syxgmu50.dll`, `syxg80.dll` ... `syxg1000.dll`, see [File names](#file-names)); other names are kept.
- One file to copy, at the cost of DLL size (MU1000: about 88 MB).

## How the DLL loads the table

1. **Table:** it reads `VoiceTable` (or `SoftSynth`) from `<dll name>.ini` (sections as above) and loads that file from the DLL's folder.
2. **Wave file:** the table header names the wave file, which is loaded from the same folder. Both files are read whole, so file size is not limited.
3. **Embedded:** without the key, the DLL loads the table named in its string table from its own resources (5 MB version, or a DLL made with `--embed`).
