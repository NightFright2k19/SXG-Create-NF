# Changes compared to the original SXG-Create

This fork extends [Soundshock's SXG-Create](https://github.com/Soundshock/SXG-Create), which converted the MU50 and MU80 (MU90 work in progress) into classic S-YXG50 tables and left the DLL setup to the user. Below is the complete list of changes, grouped by topic. Most of the sound changes were measured against the **S-MU2000** (Yamaha's MU2000 software version, which runs the MU2000/MU1000 firmware and sound data) and against recordings of a real **MU1000**; see [Verification](verification.md#verification-against-the-s-mu2000-and-the-s-yxg50). Details for each point are in the sections further down.

## New models

- **MU90 / MU90B** completed (was work in progress): word-interleaved wave ROMs (two 16-bit halves of a 32-bit bus), all four sample formats (16 bit, 12 bit, 8 bit, ADPCM), 42-byte drum voices, the bank map order XG (LSB) / SFX (MSB) / GS, and the MU90B program ROM.
- **MU100** (new): three 32-bit wave ROM pairs in one address space, three wavedata tables with their own offset tables, 32-bit voice program maps, MU100 Native and MU Basic voice maps.
- **MU128 and MU1000** (new): program flash from high/low 16-bit halves, 84-byte elements (mapped almost 1:1, verified on 2,317 elements shared with the MU100), 42-byte drum voices with byte 0 moved to `+23`, voice maps MU Native / MU Basic, GS, MSB 48 and GM2.
- **MU2000** (issue #53): converted to `syxg2000.dll` (S-YXG2000) when no MU1000 set is there, from the MAME-style h/l pair or from the `mu2000_flash.bin` of tarboh's S-MU2000 ROM folder. It has the same sound data as the MU1000, so both plugins sound the same; with both sets present only the MU1000 is converted (see [Supported models](../README.md#supported-models-and-rom-sets)).
- **S-YXG2006LE** (new): Yamaha's own engine (`SGP2.OLD` / `SGP2.DLL`) is patched and its tables are used unconverted, see [S-YXG2006LE](../README.md#s-yxg2006le).
- **MU Basic voice map** for MU100 / MU128 / MU1000: the MU90-compatible map is built into the same table as the native one and can be switched in the Setup dialog (MU Native is the default). The earlier `--mu-basic` switch was removed.

## Table formats

- **Big table layout** for MU100 / MU128 / MU1000: 32-bit voice, ext voice and wavedata offsets, 32-bit sample addresses, 24-bit drum start offset and loop length, **768 multisamples** in three pages of 256, **30-bit drum sample addresses**. The classic layout stays for MU50 / MU80 / MU90.
- **24-bit loop lengths** (both layouts): loops longer than 65,535 samples (MU80 pads, MU90) are written in full instead of being clamped.
- **Ext drum voices** are placed in voice bank A (the DLL reads their offsets as 16 bit from bank A).
- **Duplicated voice banks** (GS <-> XG side) get their own program map. The MU80's MSB 126/127 pointed to an empty map, so all 128 programs read the 8-byte debug label in front of the first voice as a voice.
- **MU50 ext drum voices** are read from the program ROM's own table (location from TaleTN's MUTable) instead of a hand-made list. Two entries of that list were wrong: the GS-mode C/M Kit keys 81 / 102 and SFX Set keys 57 / 78 played SynMalet and Bird 2 instead of FootStep and Tweet.

## Sample conversion

- **ADPCM loops** are made seamless: the decoder state is emulated through the loop passes until it settles, the transitional passes go in front of the loop (lead-in), the settled pass becomes the loop.
- **Reverse flag** (MU90 and later): samples the hardware plays backwards are reversed (toms of the standard kits, MelodTom, Real Tom; Rev Tom / Rev Kick).
- **Long drum bodies** in the classic layout (four XG open hi-hats with 70,626 samples): the loop start is moved earlier instead of cutting off the attack.
- **MU80 format bit 6** (`0xC0` vs `0x80`): investigated, no audible meaning; both are 16-bit PCM.

## Voices and elements

- **LFO pitch modulation depth** read with 6 bits instead of 5 (MU80 / MU90 and later); the old mask halved the vibrato of voices like Siren, Ghost, Goblins, Wind.
- **Element HPF** (MU100: element byte `+69`, MU128/MU1000: `+80`): baked into filtered copies of the multisamples, every 6 keys in the low range; the copies follow the coarse-tuned key range. 66 MU100 voices and 128 MU1000 voices use it (e.g. Oboe, muted/jazz/overdrive guitars, slap bass, rock organ); without it they were up to 13-19 dB too loud and dull in the low keys.
- **Element HPF with a static pitch EG:** where all pitch EG levels are equal (a constant transposition, e.g. Parasite: coarse tune -24, pitch EG +24), the cutoff of the HPF copies follows the pitch that is actually played. Before, it was set for the coarse-tuned key only, two octaves too high for Parasite (-13 dB at C4).
- **Voices with 3 or 4 elements** (22 MU1000 voices): folded into the two elements the DLL can play instead of dropping elements 3 and 4 (stereo pairs, key splits, layers; `elemreduce.py`), incl. per-member wave start offsets and baked amp EGs for percussive key-split members.
- **Rising decay 2** (MU80 and later): decay 1 level raised to 64 where decay 2 rises again, because the DLL ends notes below that level (Lite Org, WireLead, synecho2, Bounce, Ana Echo).

## Drum keys

- **Drum EG rate** (byte 13): the original's MU80 rule S-YXG50 = MU - `0x21` was checked against the S-YXG50 table (245 of 253 MU80 drum voices) and extended to the MU90 and later (426 of 460).
- **HPF cutoff** (MU100 and later): baked into a filtered copy of the drum sample.
- **Level offset** (MU100 and later, byte `+29`): added to the key's level (MU1000 Ride 1 was 13.6 dB too loud).
- **Instant attack with equal decay rates** and **short decay 1 before a fast decay 2** (MU90 and later): converted to an attack mode of the DLL without its 18-120 ms hold (Seq Click, Hi Q, Click Noise, Short Guiro: 3.5-8 dB too loud before, now within 1-2 dB).
- **Velocity pitch / LPF cutoff sensitivity** (MU90 and later): reproduced with generated ext drum voices (`drumvel.py`).

## DLL patching (new)

- SXG-Create patches a supplied `syxg50.dll` (626,688 bytes or the 5 MB version, any file name) and writes a matching ini; the original is kept as `<name>.orig.dll`. Patch level follows the table: **"Enhanced"** (classic) or **"Full"** (big layout). Already-patched DLLs are accepted and checked patch by patch.
- **Table loading:** ini section `[<plugin id>]` (e.g. `[SYXG100]`), `[SYXG50]` or `[Config]`, table key `VoiceTable` or `SoftSynth` (issue #36), 24-bit loop length, and for "Full" all big-layout parser changes (program maps, wavedata offsets with three pages, drum voice fields, formats, root key).
- **Effects:** missing effect types mapped to the nearest available type, return levels scaled per type (calibrated against the S-MU2000) and recomputed on a type change, fade-in after a type change shortened from 0.3-1 s to 80-90 ms.
- **Drum setup EG offsets** for ext drum voices no longer act twice as strong.
- **Port select `F5 nn`** (issue #74): the plugin used to drop every message after `F5 02` or higher (even after a reset). Since r49 `F5` is ignored and all messages stay on channels 1-16; the experimental multi-port build plays ports B-D on their own engines, routes XG parts 17-64 / GS block B (with the SC-88Pro mode 1 / mode 2 rules) to the right port and is named `S-YXGM<n>`; a click on the `PORT A` label in the title strip switches the panel (meters, POLYPHONY, CHN / PRG / MSB / LSB, preview note) to the next port with an engine (see [Ports B-D](gui.md#ports-b-d-f5-nn)).
- **Voice map switch** ("Full"): radio buttons "MU Tone Map" (Basic / Native) in the Setup dialog switch MU100 / MU128 / MU1000 tables between MU Native and MU Basic, saved with the host's plugin state like the other Setup options (no files written); optional start value `MUBasic=1` in the ini; works with external and embedded tables. A change takes effect immediately for new notes on all parts (no program change needed).
- **Panel controls:** a control row under the title strip (panel 400 x 114) with channel select (CHN 01-16), program (PRG) and bank select MSB / LSB of that channel, each with its own readout; hold a button to repeat, or turn the mouse wheel over a control; holding the left mouse button in the POLYPHONY field plays a preview note on that channel (see [Panel controls](gui.md#panel-controls-channel-program-bank)).
- **Polyphony up to 256:** a second synth engine inside the DLL takes the notes above 128 voices; it only renders while it has notes (plus 4 s for release and reverb) and sleeps otherwise (see [Polyphony up to 256](gui.md#polyphony-up-to-256)).
- **Setup page:** compact Polyphony slider (8-256), effect switches named with their controller ("Reverb (CC 91)", ...), Output Level -12 ... +12 dB with 0 dB in the centre, and a **Utility** box (MU50 / MU80 / MU90: a **Send Reset** box): **Send Reset** buttons MT-32 / GM / GS / XG / GM2, each sends its reset once; resets in MIDI files always pass (see [Setup page](gui.md#setup-page)).
- **MU1000 drum level:** all drum keys raised by 0.82 dB to match the S-MU2000 (drum sweep of all kits: median -0.82 -> -0.03 dB).
- **MU1000 drum level trim:** each drum voice gets its own measured level correction on top (syxg50.dll's frequency balance and level steps), see Drum keys below. Drum sweep: median deviation 0.48 -> 0.20 dB, keys more than 1 dB off 20 % -> 4 %.
- **Resources:** panel bitmap per model, names in About dialog / string table / version info (S-YXG<n>), default table name (MU50 too), conversion date and credits in the version info.

## Usage and command line

- **`--embed`:** table and wave data are stored inside the patched DLL (old `SXGBIN41.TBL` / `SXGWAVE4.TBL` removed), no ini needed.
- **`source` folder:** ROMs and the original `syxg50.dll` are read from `source` next to `main.py`, including subfolders. `syxg50.dll` is part of the repository (with the permission of its author, Evgeny Vrublevsky).
- **Plugin templates** (issue #40): the patcher no longer needs `syxg50.dll`. It carries one ready-patched plugin per model without any ROM data (`templates/*.tpl`) and only writes the converted table and wave file into it (see [Plugin templates](templates.md#plugin-templates)). The S-YXG2006LE is patched from the user's `SGP2.OLD` / `SGP2.DLL` as before.
- **Several models in one run:** all complete ROM sets found are converted (in parallel, one process per model, as many at a time as there are CPU cores and enough free memory, about 1 GB each; `--jobs N` sets the number, `--jobs 1` converts one after another), DLLs/inis named `syxg80.dll` ... `syxg1000.dll` (MU50: `syxgmu50.dll`, MU2000: `syxg2000.dll`); MU2000 is skipped when the MU1000 set is there.
- **Wildcards** (`*.bin`) are expanded by the script; `SXG_NO_PAUSE=1` skips the final key press.
- **`output` folder:** all generated files are written to `output` next to `main.py`.
- **Folder layout:** only `main.py` stays in the root; all modules are in `utility`, development tools in `utility/dev` (see [Folder layout](development.md#folder-layout)). The table converters are merged into `tableconvert.py`, the table creation into `decBase.py`, the MU80 investigation tools into `utility/dev/analyze_mu80.py`.
- **Patcher:** releases contain a patcher with a window for Windows, Linux and macOS (Apple Silicon and Intel) in 29 languages instead of the Python files (see [Patcher](../README.md#patcher)). It runs the same converter as `main.py` and produces the same plugins.
- **Panel: channel and bank select** (issue #35): the title strip control selects the MIDI channel (CHN 01-16) and steps the program or, after a click on its label, the bank select MSB / LSB of that channel (see [Panel controls](gui.md#panel-controls-channel-program-bank)).
- **ini like the original S-YXG50** (issue #36): the converter writes `[<plugin id>]` (e.g. `[SYXG100]`) with `VoiceTable=`; `[Config]` / `SoftSynth=` of earlier versions and the original `[SYXG50]` section are read as well, so the debug panel switch of Falcosoft's MIDI Player / VST MIDI Driver works (see [The ini](dll-patching.md#the-ini)).
- **Panel redesign** (issue #42): the panel is 24 pixels higher and has its own control row CHN / PRG / MSB / LSB with a readout each (the former PRE / MSB / LSB label switch is gone; the program control is labelled PRG); the title strip only holds the logo and the model name, which is now a picture of its own per model.
- **Panel per instance** (issue #55): the CHN / PRG / MSB / LSB row and the preview note belong to their own plugin instance. Hosts that run several instances in one process (VST MIDI Driver with ports A and B, a DAW with two tracks) showed the values of another instance and sent the steps there; now each panel shows and changes the channel settings of its own instance.
- **Drum parts on the panel** (issue #70): the PRG buttons step through the kits the engine knows instead of staying on the same kit, and the PRG digits of a drum channel are dimmed, and red digits show a channel without a valid instrument, issue #73 (see [Panel controls](gui.md#panel-controls-channel-program-bank)).
- **MT-32 button**: Send Reset also has **MT-32**, which sends Falcosoft's GS MT-32 sequence once (GS reset, MT-32 bank and programs per part), so MT-32 titles without custom sounds play on the GS banks; the S-YXG2006LE has MT-32 as the lowest Send Reset step.
- **Send Reset instead of Reset Mode** (issue #37): four buttons GM / GS / XG / GM2 send their reset once; nothing is sent at load or saved, and resets from MIDI files always pass unchanged (the earlier replace / drop rules are gone). The S-YXG2006LE has a Send Reset parameter (GM / GS / XGLite / GM2).
- **GM2 for MU50 / MU80 / MU90 / MU100** (issue #34): bank select MSB 121 (GM2 capital and variation tones, LSB 0-9) works like in the original S-YXG50, after a GM2 or an XG reset; GM2 drum programs (MSB 120) select the kits like GS (for all models, also the MU128 / MU1000, issue #71: before, their MSB 120 had no drum program map and every GM2 drum program change was ignored). Before, GM2 files stayed silent on all melodic channels (see [Conversion details](conversion.md#bank-maps-gm2)).
- **Autobuild releases:** every change to `main.py`, the patcher or `utility` on `main` creates a versioned release (`autobuild-rN`) with the patchers; older autobuilds stay available for regression tests.
