# SXG-Create

Converts the ROM sets of Yamaha MU-series tone generators (MU50 to MU1000, and the MU2000) into tables and wave data for the **S-YXG50** soft synthesizer (`syxg50.dll`), and patches the DLL so that it can play them as close to the original module as the S-YXG50 engine allows.

<img width="518" height="448" alt="patcher_preview" src="https://github.com/user-attachments/assets/3f20301f-ff01-4f6e-8e0d-98956f7c2eb5" />

## Table of contents

- [Changes compared to the original SXG-Create](#changes-compared-to-the-original-sxg-create)
- [Patcher](#patcher)
- [Plugin templates](#plugin-templates)
- [Quick start (Python script)](#quick-start-python-script)
- [Folder layout](#folder-layout)
- [Command line parameters](#command-line-parameters)
- [Supported models and ROM sets](#supported-models-and-rom-sets)
- [Output files and table layouts](#output-files-and-table-layouts)
- [Why the wave files got bigger](#why-the-wave-files-got-bigger)
- [DLL patching](#dll-patching)
- [S-YXG2006LE](#s-yxg2006le)
- [Setup page](#setup-page)
- [MU Basic voice maps](#mu-basic-voice-maps)
- [What the conversion does, per model](#what-the-conversion-does-per-model)
- [Verification against the S-MU2000 and the S-YXG50](#verification-against-the-s-mu2000-and-the-s-yxg50)
- [Polyphony up to 256](#polyphony-up-to-256)
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
- **MU2000** (issue #53): converted to `syxg2000.dll` (S-YXG2000) when no MU1000 set is there, from the MAME-style h/l pair or from the `mu2000_flash.bin` of tarboh's S-MU2000 ROM folder. It has the same sound data as the MU1000, so both plugins sound the same; with both sets present only the MU1000 is converted (see [Supported models](#supported-models-and-rom-sets)).
- **S-YXG2006LE** (new): Yamaha's own engine (`SGP2.OLD` / `SGP2.DLL`) is patched and its tables are used unconverted, see [S-YXG2006LE](#s-yxg2006le).
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
- **Element HPF with a static pitch EG:** where all pitch EG levels are equal (a constant transposition, e.g. Parasite: coarse tune -24, pitch EG +24), the cutoff of the HPF copies follows the pitch that is actually played. Before, it was set for the coarse-tuned key only, two octaves too high for Parasite (-13 dB at C4).
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
- **Table loading:** ini section `[<plugin id>]` (e.g. `[SYXG100]`), `[SYXG50]` or `[Config]`, table key `VoiceTable` or `SoftSynth` (issue #36), 24-bit loop length, and for "Full" all big-layout parser changes (program maps, wavedata offsets with three pages, drum voice fields, formats, root key).
- **Effects:** missing effect types mapped to the nearest available type, return levels scaled per type (calibrated against the S-MU2000) and recomputed on a type change, fade-in after a type change shortened from 0.3-1 s to 80-90 ms.
- **Drum setup EG offsets** for ext drum voices no longer act twice as strong.
- **Voice map switch** ("Full"): radio buttons "MU Tone Map" (Basic / Native) in the Setup dialog switch MU100 / MU128 / MU1000 tables between MU Native and MU Basic, saved with the host's plugin state like the other Setup options (no files written); optional start value `MUBasic=1` in the ini; works with external and embedded tables. A change takes effect immediately for new notes on all parts (no program change needed).
- **Panel controls:** a control row under the title strip (panel 400 x 114) with channel select (CHN 01-16), program (PRG) and bank select MSB / LSB of that channel, each with its own readout; hold a button to repeat, or turn the mouse wheel over a control; holding the left mouse button in the POLYPHONY field plays a preview note on that channel (see [Panel controls](#panel-controls-channel-program-bank)).
- **Polyphony up to 256:** a second synth engine inside the DLL takes the notes above 128 voices; it only renders while it has notes (plus 4 s for release and reverb) and sleeps otherwise (see [Polyphony up to 256](#polyphony-up-to-256)).
- **Setup page:** compact Polyphony slider (8-256), effect switches named with their controller ("Reverb (CC 91)", ...), Output Level -12 ... +12 dB with 0 dB in the centre, and a **Utility** box (MU50 / MU80 / MU90: a **Send Reset** box): **Send Reset** buttons MT-32 / GM / GS / XG / GM2, each sends its reset once; resets in MIDI files always pass (see [Setup page](#setup-page)).
- **MU1000 drum level:** all drum keys raised by 0.82 dB to match the S-MU2000 (drum sweep of all kits: median -0.82 -> -0.03 dB).
- **MU1000 drum level trim:** each drum voice gets its own measured level correction on top (syxg50.dll's frequency balance and level steps), see Drum keys below. Drum sweep: median deviation 0.48 -> 0.20 dB, keys more than 1 dB off 20 % -> 4 %.
- **Resources:** panel bitmap per model, names in About dialog / string table / version info (S-YXG<n>), default table name (MU50 too), conversion date and credits in the version info.

### Usage and command line

- **`--embed`:** table and wave data are stored inside the patched DLL (old `SXGBIN41.TBL` / `SXGWAVE4.TBL` removed), no ini needed.
- **`source` folder:** ROMs and the original `syxg50.dll` are read from `source` next to `main.py`, including subfolders. `syxg50.dll` is part of the repository (with the permission of its author, Evgeny Vrublevsky).
- **Plugin templates** (issue #40): the patcher no longer needs `syxg50.dll`. It carries one ready-patched plugin per model without any ROM data (`templates/*.tpl`) and only writes the converted table and wave file into it (see [Plugin templates](#plugin-templates)). The S-YXG2006LE is patched from the user's `SGP2.OLD` / `SGP2.DLL` as before.
- **Several models in one run:** all complete ROM sets found are converted (in parallel, one process per model, as many at a time as there are CPU cores and enough free memory, about 1 GB each; `--jobs N` sets the number, `--jobs 1` converts one after another), DLLs/inis named `syxg80.dll` ... `syxg1000.dll` (MU50: `syxgmu50.dll`, MU2000: `syxg2000.dll`); MU2000 is skipped when the MU1000 set is there.
- **Wildcards** (`*.bin`) are expanded by the script; `SXG_NO_PAUSE=1` skips the final key press.
- **`output` folder:** all generated files are written to `output` next to `main.py`.
- **Folder layout:** only `main.py` stays in the root; all modules are in `utility`, development tools in `utility/dev` (see [Folder layout](#folder-layout)). The table converters are merged into `tableconvert.py`, the table creation into `decBase.py`, the MU80 investigation tools into `utility/dev/analyze_mu80.py`.
- **Patcher:** releases contain a patcher with a window for Windows, Linux and macOS (Apple Silicon and Intel) in 29 languages instead of the Python files (see [Patcher](#patcher)). It runs the same converter as `main.py` and produces the same plugins.
- **Panel: channel and bank select** (issue #35): the title strip control selects the MIDI channel (CHN 01-16) and steps the program or, after a click on its label, the bank select MSB / LSB of that channel (see [Panel controls](#panel-controls-channel-program-bank)).
- **ini like the original S-YXG50** (issue #36): the converter writes `[<plugin id>]` (e.g. `[SYXG100]`) with `VoiceTable=`; `[Config]` / `SoftSynth=` of earlier versions and the original `[SYXG50]` section are read as well, so the debug panel switch of Falcosoft's MIDI Player / VST MIDI Driver works (see [The ini](#the-ini)).
- **Panel redesign** (issue #42): the panel is 24 pixels higher and has its own control row CHN / PRG / MSB / LSB with a readout each (the former PRE / MSB / LSB label switch is gone; the program control is labelled PRG); the title strip only holds the logo and the model name, which is now a picture of its own per model.
- **Panel per instance** (issue #55): the CHN / PRG / MSB / LSB row and the preview note belong to their own plugin instance. Hosts that run several instances in one process (VST MIDI Driver with ports A and B, a DAW with two tracks) showed the values of another instance and sent the steps there; now each panel shows and changes the channel settings of its own instance.
- **Drum parts on the panel** (issue #70): the PRG buttons step through the kits the engine knows instead of staying on the same kit, and the PRG digits of a drum channel are dimmed, and red digits show a channel without a valid instrument, issue #73 (see [Panel controls](#panel-controls-channel-program-bank)).
- **MT-32 button**: Send Reset also has **MT-32**, which sends Falcosoft's GS MT-32 sequence once (GS reset, MT-32 bank and programs per part), so MT-32 titles without custom sounds play on the GS banks; the S-YXG2006LE has MT-32 as the lowest Send Reset step.
- **Send Reset instead of Reset Mode** (issue #37): four buttons GM / GS / XG / GM2 send their reset once; nothing is sent at load or saved, and resets from MIDI files always pass unchanged (the earlier replace / drop rules are gone). The S-YXG2006LE has a Send Reset parameter (GM / GS / XGLite / GM2).
- **GM2 for MU50 / MU80 / MU90 / MU100** (issue #34): bank select MSB 121 (GM2 capital and variation tones, LSB 0-9) works like in the original S-YXG50, after a GM2 or an XG reset; GM2 drum programs (MSB 120) select the kits like GS (for all models, also the MU128 / MU1000, issue #71: before, their MSB 120 had no drum program map and every GM2 drum program change was ignored). Before, GM2 files stayed silent on all melodic channels (see [Conversion details](#bank-maps-gm2)).
- **Autobuild releases:** every change to `main.py`, the patcher or `utility` on `main` creates a versioned release (`autobuild-rN`) with the patchers; older autobuilds stay available for regression tests.

---

## Patcher

The easiest way: download the patcher for your system from the newest **Autobuild** release (marked Latest, on top of the Releases page; older autobuilds are kept for comparison). It is a single program file; nothing is installed.

| System | File | Start |
|---|---|---|
| Windows | `SXG-Create-NF-Patcher-rN-windows.exe` | double-click |
| Linux | `SXG-Create-NF-Patcher-rN-linux.tar.gz` | extract, then run `SXG-Create-NF-Patcher` |
| macOS (M1 and newer) | `SXG-Create-NF-Patcher-rN-macos-applesilicon.zip` | extract, then open `SXG-Create-NF-Patcher.app` |
| macOS (Intel) | `SXG-Create-NF-Patcher-rN-macos-intel.zip` | extract, then open `SXG-Create-NF-Patcher.app` |

1. Put the patcher in a folder together with your MU ROM files, and/or the three files of Yamaha's **S-YXG2006LE** (`SGP2.OLD` or `SGP2.DLL`, also one patched by SGP2VSTi 1.0.2.22 such as `S-YXG2006LE.DLL`; `sxgbnw6l.tbl`, `sxgdat6l.tbl`). Subfolders are fine, e.g. one per model; file names don't matter (detection by CRC32). **`syxg50.dll` is no longer needed:** the patcher carries ready-patched plugin templates (see [Plugin templates](#plugin-templates)).
2. Start the patcher. It lists the S-YXG2006LE first (one line, when all three files are there), then every complete ROM set it found, starting with the MU50. If it finds no ROMs, it asks for the folder; **Choose folder…** points it to another place at any time.
3. Click **Patch**. All listed models are converted, several at the same time on a multi-core CPU, and the S-YXG2006LE is patched in the same run. The plugins end up in the folder **`Plugins`** next to the patcher: one DLL per model (`syxgmu50.dll`, `syxg80.dll` ... `syxg1000.dll`, `syxg2000.dll`) with the tables inside (`--embed`), no ini or table files needed, and `syxg2006le.dll` with its two tables inside (see [S-YXG2006LE](#s-yxg2006le) for its parameters). **Open folder** shows them.

- **Language:** the system language if available, else English; the menu at the top right switches between 29 languages, each shown in its own name and sorted alphabetically by the Latin spelling of that name: العربية, Bahasa Indonesia, বাংলা, Čeština, Dansk, Deutsch, Ελληνικά, English, Español, فارسی, Français, 한국어, हिन्दी, Italiano, עברית, Magyar, Nederlands, 日本語, Polski, Português, Română, Русский, Српски, Svenska, ไทย, Tiếng Việt, Türkçe, Українська, 中文.
- **Show details** shows the converter's log (the same text the Python script prints).
- **Update** (issue #72): a moment after it has started, the patcher asks GitHub for the number of the newest Autobuild release (the redirect of the Latest page; no login, no API, nothing else is sent). If it is newer than the running one, **A newer version (rN) is available!** appears under the buttons. **Update** (left of **Show details**) then asks once (OK / Cancel), downloads the file for your system with a progress bar, checks its size and the SHA-256 that GitHub shows, lets the new version pass its own `--selftest`, and starts it; the old window closes. The new version goes into the folder of the patcher (that is where the ROMs are searched); if that folder is read-only, into your Downloads folder.
  - **Windows:** the new `SXG-Create-NF-Patcher-rN-windows.exe` is placed next to the old one, and the new patcher deletes the old one as soon as it has ended. Only a file with the official name `SXG-Create-NF-Patcher-rN-windows.exe` is deleted; a renamed copy stays.
  - **Linux:** the program file is replaced. **macOS:** the app is replaced; the old one is deleted by the new one after it has started.
  - **Not for everyone:** start the patcher with `--no-update-check` (or set `SXG_NO_UPDATE_CHECK=1`) and it does not look at the start; **Update** still checks when you click it. A patcher run from source (`python patcher.py`) does not update itself. The patcher files are not signed (see below), so the update is as trustworthy as downloading the file yourself.
  - **Test options:** `--update-dir <folder>` takes the release files from a folder instead of GitHub, `--update-test-version rN` makes the patcher act as that version.
- **Not signed:** the patcher files carry no code signature, so the system warns on the first start:
  - **Windows:** SmartScreen shows "Windows protected your PC". Click **More info**, then **Run anyway**.
  - **macOS:** Gatekeeper says the app "cannot be opened because the developer cannot be verified" (or that it is damaged). Right-click (Control-click) the app, choose **Open**, then **Open** again; on macOS 15 and newer: try to open it once, then go to **System Settings → Privacy & Security** and click **Open Anyway**. Alternatively, in Terminal: `xattr -dr com.apple.quarantine SXG-Create-NF-Patcher.app`.
  - **Linux:** if the file is not executable after extracting: `chmod +x SXG-Create-NF-Patcher`. The window needs a desktop session (X11 or Wayland with XWayland).
- **Development:** the patcher is `patcher.py` (texts in `patcher_i18n.py`); it imports `main.py` and the modules in `utility` unchanged and runs each model through `main.py`'s command line (`patcher --cli <arguments>`, without a DLL, so the plugins come from the templates). The release workflow freezes it with PyInstaller on each system, with the templates in one 7z archive. `python patcher.py` starts it from the repository (Python 3.12 with Tk) and uses `templates/`. `patcher --selftest` checks that every template is there and empty.

---

## Plugin templates

A template is the finished plugin of one model without ROM data: `syxg50.dll` with every patch of [DLL patching](#dll-patching) for that model (code, panel bitmaps, Setup page, names, version info), plus the table and wave file as embedded resources, exactly as `--embed` stores them, but filled with zeroes. On its own a template is useless. The patcher converts your ROMs and writes the table and wave file into the two placeholders; the result is the same plugin a run with `syxg50.dll` and `--embed` gives (byte for byte, apart from the date in the version info, see below).

- **Files:** `templates/syxgmu50.tpl`, `syxg80.tpl`, `syxg90.tpl`, `syxg100.tpl`, `syxg128.tpl`, `syxg1000.tpl`, `syxg2000.tpl`, named after the plugins. `templates/templates.json` holds the sizes of the two placeholders per model.
- **No ROM data:** the placeholders contain only zeroes; `python utility/template.py --check` (and `patcher --selftest`) verifies that.
- **Made by the workflow:** `utility/template.py --make` builds them from `source/syxg50.dll`. The Autobuild workflow runs it on every push to `main` that touches the converter, commits the templates to `templates/` when they changed and builds the patchers from that commit, so every Autobuild release carries templates that match its code. In the patcher they are one 7z archive (LZMA2, Ultra, largest dictionary; mostly zeroes, so it is small), read with Python's own `lzma`, so nothing has to be installed.
- **Version date:** the version info of a plugin shows the date of the last commit that changed the templates' sources (`syxg50.dll`, `dllpatch.py`, `template.py`, the bitmaps, `templates.json`), no longer the day of the conversion. The same commit always gives the same templates.
- **Placeholder sizes:** a converted table or wave file that does not have the size of its placeholder (another ROM version of a model, or a converter change since the sizes were measured) still works: the resources are rebuilt around it, which only takes a little longer, and the log says so. `python utility/template.py --measure output` takes the sizes from plugins built with `--embed` and updates `templates.json`.
- **S-YXG2006LE:** no template. Yamaha's `sgp2.dll` is not part of the repository; the patcher patches the user's `SGP2.OLD` / `SGP2.DLL` as before.

---

## Quick start (Python script)

For development, or without the patcher:
1. Download the latest **Autobuild** release (or clone the repository) and extract it.
2. Put your MU ROM files into the `source` folder. Subfolders are fine, e.g. one per model. The original `syxg50.dll` (626,688 bytes) is already there (part of the repository).
3. Run:

```
python main.py [--embed]
```

The converted files end up in the `output` folder.

- **Inputs:** ROM files in any order. SXG-Create detects the model from the CRC32 of the files, so the file names don't matter. Files larger than 64 MB in `source` are ignored.
- **Command line:** ROM files and a DLL can also be given on the command line (or dropped onto `main.py`); they are used together with the contents of `source`.
- **DLL:** one `syxg50.dll` under any file name. SXG-Create writes a patched copy plus a matching `.ini` (or, with `--embed`, a DLL that contains the table). Without a DLL (ROMs given on the command line with `--out-dir`, or `source/syxg50.dll` removed), the plugin is made from the model's [template](#plugin-templates), as the patcher does; without a template, only the table and wave file are written.
- **Output folder:** always `output` next to `main.py` (created if needed).
- **Requirements:** Python 3.12 or newer. No extra packages.

### Example (MU1000)

```
source/mu1000-v2.01-h.bin  source/mu1000-v2.01-l.bin  source/xv364a0.ic49  source/xv365a0.ic50
source/xw848a0.ic53  source/xw849a0.ic54  source/syxg50.dll (part of the repository)

python main.py
```

This writes to `output`:

```
SXGMU1KX.TBL     table
SXGMU1KX.UPCM    wave data
syxg1000.dll     patched DLL ("Full")
syxg1000.ini     [SYXG1000] VoiceTable=SXGMU1KX.TBL
```

Copy all four files into one folder.

### Example (all models, embedded)

```
source/mu50/...  source/mu80/...  source/mu90/...  source/mu100/...  source/mu128/...  source/mu1000/...  source/syxg50.dll

python main.py --embed
```

This writes `syxgmu50.dll`, `syxg80.dll`, `syxg90.dll`, `syxg100.dll`, `syxg128.dll` and `syxg1000.dll` to `output`, each a self-contained DLL with its table and wave data inside. The supplied `syxg50.dll` stays unchanged. At the end a summary lists each model as done or failed.

> **zsh / bash:** an unquoted `*.bin` that matches nothing makes zsh stop with "no matches found" before Python starts. Leave the pattern out (the `source` folder is searched anyway), quote it (`'*.bin'`) or use `source/**/*.bin`.

---

## Folder layout

```
main.py              the converter (run this)
README.md, LICENSE
CLAUDE.md            project rules and a short code map for Claude (Claude Code)
source/              your ROM files; the original syxg50.dll (part of the repository, the templates are made from it)
templates/           plugin templates, one per model, without ROM data (made by the Autobuild workflow)
output/              generated tables, wave files, patched DLLs and inis (created on the first run)
utility/             the converter modules (decoders, table converters, table writer, sample conversion, DLL patcher)
utility/bitmaps/     panel pictures for the patched DLLs
utility/dev/         development tools, not needed for a conversion and not in the release archive
.github/workflows/   autobuild release
```

**Autobuild:** every push to `main` that changes `main.py`, the patcher, `utility` (except `utility/dev`), `source/syxg50.dll` or `templates` makes the [templates](#plugin-templates) again (and commits them when they changed), then creates a release `autobuild-rN` (marked Latest) with the patchers for Windows, Linux and macOS, built from that commit. Older autobuilds are kept (for regression tests) and carry no label, so only the newest one, listed on top, is marked Latest. The workflow can also be started by hand (Actions, "Run workflow"). Autobuilds r14-r27 (the first ones with patchers) were deleted by the earlier workflow; the hand-started workflow `restore-autobuilds.yml` creates them again from the patchers that the Actions runs still hold. The tag `autobuild-rN` and the names of the patcher files in the release are used by the patcher's update (issue #72): keep them, or change `utility/selfupdate.py` with them.

---

## Command line parameters

| Parameter | Meaning |
|---|---|
| `<ROM files>` | Optional. Program ROM(s) and wave ROMs of one or more models, in any order (see [Supported models](#supported-models-and-rom-sets)), in addition to the `source` folder. Wildcards are allowed. |
| `<dll>` | Optional. A `syxg50.dll`, under any file name (`syxg50.dll`, `mu800.dll`, ...). It is recognised by its content, not its name. A DLL in the `source` folder is used if none is given on the command line. See [DLL patching](#dll-patching). Without one, the plugin is made from the model's [template](#plugin-templates). |
| `--jobs N` | **New.** Number of models converted at the same time in a multi-model run (default: CPU cores, limited by free memory; 1 = one after another). Each model's log is printed in one piece when it is done. |
| `--embed` | **New.** Puts table and wave file into the patched DLL as resources instead of writing them as files (see [Embedded tables](#embedded-tables---embed)). Needs a DLL or the model's template. |

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
| MU2000 (v2.01) | `mu2000-v2.01-h.bin`, `mu2000-v2.01-l.bin`, or `mu2000_flash.bin` (S-MU2000 ROM folder) | `xv364a0.ic49`, `xv365a0.ic50`, `xw848a0.ic53`, `xw849a0.ic54` (the MU1000's; in the S-MU2000 folder under `dump/`) | big |

File names are only examples; the files are recognised by their CRC32.

> **MU2000** (issue #53): it has the same voice data as the MU1000 (1,635 voices, 1,027 drum voices, 2,901 samples, the same wave ROMs); every table the converter reads is byte-identical, only at other addresses. Only the element filter/level scaling is stored differently: instead of 4 break points, each element holds an index into 1,377 tables of 128 notes, which lie in the upper half of the 4 MB firmware image (at `0x23CED0`, location from TaleTN's MUTable). The tables are the MU1000's break points interpolated per note (the formula reproduces all 5,306 scalings), and the converter turns them back into break points (`utility/scaling.py`): 1,376 tables give exactly the same 128 notes; one (an element of MuteGtr#, whose MU1000 break points cross) differs on 3 notes by up to 3 steps of the cutoff scaling. The break points are not always the MU1000's own (points on a straight part of the curve are free), so the voice level trims are keyed on the scaling written out per note and apply to both. With only the MU2000 set the result is `syxg2000.dll` (S-YXG2000, table `SXGMU2KX.TBL`, wave `SXGMU2KX.UPCM`); with both sets, only the MU1000 is converted, as the plugins would sound the same. The MU2000's own extras (sampling, plug-in boards, A/D input) have no counterpart in the S-YXG50.

| S-YXG2006LE | `SGP2.OLD` or `SGP2.DLL` (CRC32 `A62F256A`, `68FD2825` or `F5037F5F`), `sxgbnw6l.tbl` | `sxgdat6l.tbl` | original, not converted |

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
- **One DLL per run:** if both `<name>.dll` and its backup `<name>.orig.dll` are passed (e.g. by dropping a whole folder), `<name>.dll` is used. A DLL given on the command line wins over one in the `source` folder.

### Patch levels (chosen automatically)

| Level | Used for | Patches |
|---|---|---|
| "Enhanced" | MU50 / MU80 / MU90 | ini names, 24-bit loop length, drum EG offsets, effect types, effect return levels, effect fade-in, Setup page (layout, effect names, Output Level range, Send Reset), panel preset buttons, bitmaps, names, version info |
| "Full" | MU100 / MU128 / MU1000 | everything in "Enhanced" + table size limits (big layout) + voice map switch |

### Patch sites in `syxg50.dll` (file offset = RVA)

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
| `0x03875`, `0x30B91`, `0x30BBA`, `0x30BEF`, `0x30C5F`, `0x02B50`, `0x02BB0` + code cave `0x3F6B0`-`0x3FA20`, dialog resource 111, `.data` VirtualSize -> `0x5E40` | **Voice map switch** (Full only; see [MU Basic voice maps](#mu-basic-voice-maps)). After the table setup, the cave looks for the voice map appendix behind the table sections (`MAP2`), remembers the 8 bank/drum row pointers and points them at the appendix rows when `[Config] MUBasic=1` selects MU Basic. A checkbox (control `0x420`) is added to the Setup page; Init and Set Defaults set it, a click enables Apply, and Apply switches the rows. Since issue #26 it is hidden and driven by the "MU Tone Map" radio buttons (see the Setup page row below). `[Config] MUBasic` sets the mode only at the first table setup of the process (flag `.data` `0x56DC3`, issue #65): with embedded tables every engine start runs the table setup again (one per instance and the second engine of the polyphony patch), and before the fix each one reset the mode to the start value. The plugin state (VST chunk) carries the setting: getChunk (`0x10002B50`) returns a copy with 3 more bytes `'V','M',<mode>` (bank 33 -> 36 bytes, program 5 -> 8 bytes), setChunk (`0x10002BB0`) takes the mode from such a chunk (also before the first table setup) and passes the original size on; old 33/5-byte chunks are still accepted. Nothing is written to a file. Without an appendix the checkbox is hidden and the chunk stays unchanged. The cave code is position independent; its state lives in `.data` at `0x56DC0` (chunk copy at `0x56E00`). |
| `0x07560` + code cave `0x3FA20`-`0x3FA7B` | **Voice map switch, immediate** (Full only). The MIDI channel event entry (audio thread) compares the XG bank map row pointer (`0x100552D8`) with the last one it saw (`.data` `0x56DE8`). After a switch (Setup page or plugin state) all 16 parts re-run their program change with their current program (part `+0x6A`, handler table `0x10041BB0`[4]; *receive program change* is honoured) before the event is handled. Notes already sounding keep their voice. Position independent. |
| `0x010A0`, `0x010C0`, `0x30AF0`, `0x320EE`, `0x3233D`, `0x32407`, `0x32427`, `0x3246B` + code in the unused NOP block `0x33150`-`0x338A1` (no relocations there), bitmaps 101 / 106, `.data` VirtualSize -> `0x5E6C` | **Panel controls** (all models, issues #16, #23, #35, #42): the panel is 24 pixels higher (400 x 114): editor rect and window height (`0x3257D`, `0x326D5`), the whole-bitmap paint (`0x322DF`) and the lower part move down 24 pixels: meter screen background (`0x32233`, `0x3224F`), level meters (`0x32130`), POLYPHONY digits (`0x32186`), XG / GS lamps (`0x321DF`, `0x32208`), SETUP button picture and hit test (`0x3253E`, `0x324D6`, `0x324DB`). The control row (`utility/dev/poly/panel.asm`, section `.sxp`): eight buttons in row 31 (CHN 25 / 73, PRG 116 / 174, MSB 221 / 279, LSB 323 / 381), readouts in row 32 (CHN 46, PRG 137, MSB 242, LSB 344); WM_LBUTTONDOWN / WM_LBUTTONUP / WM_TIMER / WM_MOUSEWHEEL as before; per instance (issue #55) the panel keeps its state in a panel record of its engine (panel object `+8` = plugin `+0xB0`; 4 records x 16 bytes at `.data` `0x56F08`, claimed with `lock cmpxchg`, freed at effClose): the channel (`+7`) changes at once, PRG / MSB / LSB steps are pending (`+4`, `+5`, `+6`) and sent by the audio thread of that plugin (`panel_prog`, program change or CC 0 / CC 32 + program change, to its engine and its engine B); the readouts stay blank until that thread has processed the engine (`+0xC`). **Preview note** (issue #43): a left click in the POLYPHONY field (x 245-298, y 57-103) sets record `+0xA` and captures the mouse, the button release clears it; the wheel there changes the note (`+8`, stored XOR `0x3C` so that zeroed `.data` means 60 = C4, range 24-127). `panel_prog` calls `pp_prev` first, which compares the wanted note with the sounding one (`+9` = note + 1, channel `+0xB`) and sends note off / note on (velocity 100) to engine A only (`pv_send`; engine B renders only while the dispatcher has given it notes, issue #46). Parts: the synth (engine `+8`) keeps them in the order of channels 10, 1-9, 11-16, records of `0x11C` bytes from `+0x248` (`+0` MSB, `+1` LSB, `+2` program); engine mode `+0x63B0` (0 XG, 1 GM, 2 GM2), `+0x63AE` (0 = GS). Bitmaps: see **Bitmaps** below. |
| `0x30AF0`, `0x31142`, `0x30B4E` + code in the unused NOP block `0x2F6D3`-`0x2FB60` (and the panel cave above), gain table `0x4DF10`, dB texts `0x4E748`, vtable slots `0x40594`/`0x40598`/`0x407AC`/`0x407B0`, dialog resource 111, `.data` VirtualSize -> `0x5EB8` | **Setup page layout, Output Level, Send Reset** (all models, issues #26, #37). Dialog 111: the seven polyphony preset buttons are removed and the frames move up; the effect checkboxes read "Reverb (CC 91)", "Chorus (CC 93)", "Variation (CC 94)"; the Output Level trackbar gets tick marks (ends + centre, TBM_SETTIC 101); Full: a "Utility" frame (41 units high) holds the Send Reset push buttons (`0x42C` MT-32 26 x 15, `0x423` GM, `0x424` GS, `0x425` XG, `0x42B` GM2 20 x 15, at x 8 / 37 / 60 / 83 / 106, y 133, label `0x42A`) and the MU Tone Map radio buttons (`0x427` Basic / `0x428` Native at y 136, label `0x429`), the page is 177 units high; Enhanced (MU50 / MU80 / MU90): the frame is titled "Send Reset" and holds only the buttons (x 11 / 42 / 67 / 92 / 117, y 124; MT-32 26 units wide, the others 20), frame 31 units high, page 167 units. "Set Defaults" sits below the frame. **Output Level:** the value byte keeps its meaning (101 = 0 dB, the default), the trackbar range becomes 77-125 (`0x30B4E`), WM_HSCROLL clamps to it (`0x31142` -> cave), the gain table (128 floats) and the dB texts (6 bytes each) get -12 ... +12 dB in 0.5 dB steps (values outside the range count as -12 / +12 dB). **Page procedure** (`0x10030AF0` -> cave): a Send Reset button marks its reset pending (`.data` `0x56E40`: 1 GM, 2 GS, 3 XG, 4 GM2, 5 MT-32 = the 27 messages of `mt32.syx` one after the other; nothing stored, Apply untouched); a Tone Map click sets the hidden checkbox `0x420` and enables Apply. After WM_INITDIALOG / Set Defaults the page's own code runs first, then the Tone Map controls are set from the state; without a voice map appendix they are hidden. **Reset handling** (issue #37): the process / processReplacing wrappers (`0x100010A0` / `0x100010C0`, audio thread) send a pending reset through the engine's SysEx entry (engine = plugin `+0xB0`, vtable `+0x0C`, both engines) before the block is rendered; host resets are not looked at. For 4800 samples after it (100 ms at 48 kHz) host events and preset steps are held back in a 64 KB queue (VirtualAlloc on first use) and passed on with deltaFrames 0 in the first block after that; a block with a dropped reset alone goes through the same queue at once (pending value 6). **Plugin state:** the getChunk / setChunk slots of both AudioEffect vtables (`0x40594`/`0x407AC`, `0x40598`/`0x407B0`) point to the cave, which calls the original functions (voice map patch included) and appends / takes off `'R','P',<mode>,<extra voices>` (see Polyphony up to 256 below) (bank 33 (+3) -> 37 (40) bytes, program 5 (8) -> 9 (12)); the Reset Mode byte of earlier versions is ignored and no reset is sent; chunks without it are passed on unchanged. Copy buffer `.data` `0x56E70`, VirtualSize -> `0x5EB8`. Position independent; sources in `utility/dev/gui` (`gui.asm`, `settings.asm`, `mkgui.py`). |
| `0x01000`, `0x010A0`, `0x010C0`, `0x30B1D`, `0x30F31`, `0x320A0` + new section `.sxp` at `0x5B000` (inserted in front of `.rsrc`, which moves up by its size, two pages since #55; resource directory and data entries follow), `.data` VirtualSize -> `0x5F48` | **Polyphony up to 256** (all models, issue #14). The process / processReplacing wrappers (`0x100010A0` / `0x100010C0`) jump to `poly_procA` / `poly_procR` in `.sxp`: per plugin a slot (`.data` `0x56EC0`, 4 x 16 bytes: plugin, AEffect of engine B, samples B stays awake, event lists) is looked up; in the first block engine B is made with VSTPluginMain (`0x10003610`, own audioMaster stub answering only the version) and gets effOpen, sample rate, block size, mains on. Then `send_pending` (Send Reset, preset steps) runs as before; its resets and program steps go to both engines (`both_sysex` / `both_short`). Each block B gets A's settings through the settings object (the engine object `[plugin +0xB0]`, vtable `0x1004E110`; Set `0x10030770`; B's polyphony = the voices above 128, `.data` `0x56EB8`), the host events (`plugin +0xE0`) are split: a Note On goes to A while A has two voices free (synth `+0x64BE`), else to B while B has two free (polyphony `+0x64C0`), else to A; everything else to both. A renders, then B with the accumulating process (`vtable +0x10`) while it has voices and 4 s longer (and 250 ms after a SysEx); waking up, B takes A's control-rate counters (`plugin +0xE4..+0xEC`); asleep, B's events go through its engine entries (`+0x08` / `+0x0C`). The dispatcher (`0x10001000`) closes B on effClose. **Panel readout:** the POLYPHONY readout asks the settings object for the voices in use (Get, op 4, `0x100320A0`); `poly_count` adds engine B's voices in use. **Setup page:** trackbar range 8-256 (`0x30B1D`), WM_HSCROLL (`0x30F31` -> `poly_scroll`) keeps the settings byte up to 128 and the rest as extra voices on the page (`0x56EB9`), committed on PSN_APPLY; `.data` `0x56EB8` holds the extra voices XOR 0x80, so without a saved state (and with Set Defaults) the total is 256; the plugin state appends `'R','P',<mode>,<extra>` (older `'R','S'` chunks: extra 128). Source `utility/dev/poly/poly.asm`, generated with `utility/dev/gui/mkgui.py`. |
| `0x08C24`, `0x08C75`, `0x08CDF` | **Effect fade-in after a type change:** the handler mutes the block, and a ramp run every 10 ms brings it back in steps of 4: reverb 0.64 s, chorus 1.03 s, variation 0.32-0.9 s. Larger steps (reverb 32, chorus 52, variation 40) end the ramp after 80-90 ms; the end values are unchanged. |

**Resources**

- **Bitmaps:** bitmap 101 (the panel picture, 400 x 114 since issue #42) is built from `utility/bitmaps/Panel101.bmp` (the same for every model, with the control row) and the model name `utility/bitmaps/Name_<model>.bmp` pasted at (300, 0) (MU50 / original: S-YXG50); bitmap 106 gets `PanelButtons.bmp` (pressed buttons, dash) appended and, behind it, the dimmed digits 0-9 for the PRG field of a drum part (issue #70: made by `dllpatch.py` from `Bitmap105.bmp`, their contrast to the field is `DRUM_DIGIT_PERCENT` = 65) and the red digits for a part without an instrument (issue #73: made the same way, `NO_VOICE_PERCENT` in `dllpatch.py`); bitmap 106 is 400 x 16 then; bitmap 105 becomes `utility/bitmaps/Bitmap105.bmp`. Keep the `bitmaps` folder in `utility`. All are made by `utility/dev/gui/mkpanel.py` from the template and mockup of issue #42 (`utility/dev/gui/panel42/`). Bitmap 105 must keep the original size (110x13); any uncompressed 8-, 24- or 32-bit BMP works.
- **Names** (MU80 ... MU2000; MU50 keeps the S-YXG50 names, only its default table name is set): the About dialog and string table say S-YXG<n> instead of S-YXG50 (e.g. S-YXG1000), the internal name `xg50` becomes `mu<n>`, the default table name in the string table becomes the table just built, and the version info reads "Yamaha S-YXG<n> VSTi", "S-YXG<n>", "S-YXG<n>.DLL" and "Yamaha S-YXG<n> Portable VSTi". Hosts may list the plugin under its new name after a rescan.
- **Version info** (all models): the file version `2016,4,25,18` becomes the conversion date (`YYYY,MM,DD,0`), the FileVersion string `2016.04.25.0018` becomes `YYYY.MM.DD`, and the copyright reads "... 2016 VEG, 2026 Soundshock/NightFright".

The resource section grows by a few KB for this. The PE checksum is recalculated after patching.

The S-YXG50 sound engine itself, including its MMX/SSE paths, is not changed beyond the effect patches above. The MMX/SSE paths were checked: they read samples through a 32-bit pointer plus a 32-bit index, so they don't limit addresses.

### File names

- **`syxg50.dll` is never overwritten:** a DLL supplied as `syxg50.dll` (or `syxg50.orig.dll`) is written under the model's name: `syxgmu50.dll` (MU50, because `syxg50.dll` is the original's name), `syxg80.dll`, `syxg90.dll`, `syxg100.dll`, `syxg128.dll`, `syxg1000.dll` or `syxg2000.dll`, in single and multi-model runs, with and without `--embed`. The supplied `syxg50.dll` stays unchanged.
- **Other names are kept:** e.g. `mu800.dll` gives a patched `mu800.dll`. A name without an extension gets `.dll` added.
- **ini:** it gets the same name with `.ini` (`mu800.ini`). The DLL looks for the ini under its own name, so if you rename the DLL later, rename the ini as well.
- **DLL with another name already in the `output` folder:** it is replaced by the patched version, and the original is kept once as `<name>.orig.dll`. Later runs patch from that backup, so switching between models (Enhanced <-> Full) always starts from the original.
- **DLL in another folder** (e.g. `source`): it stays unchanged, and the patched copy is written to `output`.

### The ini

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

### Embedded tables (`--embed`)

- Table and wave file are stored in the patched DLL as `RT_RCDATA` resources under their file names, the same way the 5 MB `syxg50.dll` stores its own tables. Those old tables (`SXGBIN41.TBL`, `SXGWAVE4.TBL`) are removed first.
- The default table name in the DLL's string table is set to the new table, so the DLL finds it without an ini. No ini is written, and an existing ini of the same name is removed (an ini with a `VoiceTable` / `SoftSynth` entry would make the DLL look for an external file instead).
- A DLL supplied as `syxg50.dll` is written under the model's name (`syxgmu50.dll`, `syxg80.dll` ... `syxg1000.dll`, see [File names](#file-names)); other names are kept.
- One file to copy, at the cost of DLL size (MU1000: about 88 MB).

### How the DLL loads the table

1. **Table:** it reads `VoiceTable` (or `SoftSynth`) from `<dll name>.ini` (sections as above) and loads that file from the DLL's folder.
2. **Wave file:** the table header names the wave file, which is loaded from the same folder. Both files are read whole, so file size is not limited.
3. **Embedded:** without the key, the DLL loads the table named in its string table from its own resources (5 MB version, or a DLL made with `--embed`).

---

## S-YXG2006LE

The S-YXG2006LE engine differs from the S-YXG50 in ways a table conversion can't reproduce: its filter EG does not follow velocity, and its filter does not follow the key. SXG-Create therefore patches Yamaha's own DLL instead of converting the tables. With `SGP2.OLD` (or `SGP2.DLL`), `sxgbnw6l.tbl` and `sxgdat6l.tbl` among the inputs or in `source/` (recognised by CRC32), it writes `syxg2006le.dll` and copies the two tables unchanged (`--embed`: they go into the DLL), in addition to the MU plugins when MU ROMs and `syxg50.dll` are there as well. The patcher finds the three files the same way, lists them as **S-YXG2006LE** and writes the DLL with the tables inside to `Plugins`; it works with only these three files, with only MU ROMs and `syxg50.dll`, or with both.

Patches (`utility/sgp2patch.py`, code in `utility/dev/sgp2/params.asm`):
- **Host lock off:** the plugin only started in a host whose vendor string is `YAMAHA` (`0x2AAE` `je` → `jmp`).
- **Accepted DLLs** (issue #54): the original `SGP2.OLD` (CRC32 `A62F256A`), `SGP2.DLL` with only the host lock removed (`68FD2825`) and `SGP2.DLL` as patched by SGP2VSTi 1.0.2.22 (`F5037F5F`, often shared as `S-YXG2006LE.DLL`). SGP2VSTi also changed the debugger check at `0x4BFFB` (`74 14 8B` → `90 90 FF`); that change is undone, so all three give the same `syxg2006le.dll`.
- **Parameters** in the host's generic plugin window, in the order of the S-YXG50 plugins' Settings page, saved with the project (own chunk `SXR6` (the chunks of earlier test builds, `SXR5` / `SXR4`, are read as well); older `SXR3` / `SXR2` chunks are converted: a Reverb / Chorus Return above 0 becomes On, Master Volume starts at 0 dB; the plugin saves nothing itself). All parameters are stepped: values snap to the nearest step, the plugin reports the steps to the host (effGetParameterProperties) and sends the snapped value back (audioMasterAutomate / UpdateDisplay), so sliders jump to the step:
  - **Polyphony** 8-256 notes (default 256). The engine has 32 voices. Above 32 the plugin runs up to eight engines (32 voices each, created at mains on as needed): a new note goes to the first engine with a free voice, its note-off to the same engine, everything else (controllers, program changes, SysEx, the settings below) to all of them, and their outputs are added. An extra engine renders only while it has voices and for 192000 samples after the last one ended (release and effect tails); asleep it only takes events. Beyond the limit a new note is dropped, so sounding notes keep playing (the engine itself does the same when its voices are busy); a note held by the sustain pedal counts until the pedal is released. A higher Polyphony takes effect at the next mains on (e.g. reloading the project). A long held note (like the test tone of a polyphony test) therefore keeps sounding at any limit; the limit shows in the notes that come later.
  - **Reverb (CC 91)** and **Chorus (CC 93)**: On / Off (default On). Off sets the effect return to 0, On to the default 64. The 2006LE has no variation effect (CC 94 does nothing), so there is no Variation switch.
  - **Master Volume** -12 ... +12 dB in 0.5 dB steps (default 0 dB): gain on the plugin's output, like the Output Level of the MU plugins (processReplacing).
  - **Master Tune** -100 ... +100 cent, **Transpose** -24 ... +24 semitones.
  - Reverb, Chorus, Master Tune and Transpose are sent as parameter SysEx on change and again right after every reset, ours or one in the song (a reset sets them back to the engine defaults). After a GS reset they go out as GS system parameters (the engine ignores XG parameter SysEx in GS mode), otherwise as XG System / Effect parameters.
  - **Send Reset** (issue #37): MT-32 / GM / GS / XGLite / GM2 (MT-32 is the lowest step, GM2 the highest). It shows XGLite after loading and sends nothing then; choosing a value sends that reset once (a host parameter can't be a button: to send the shown value again, choose another one and come back). It is not restored from the plugin state. Resets and all other SysEx from the host always pass. The engine plays GM2 natively (MSB 121 / 120). The engine handles the resets itself and applies events right after one correctly, so no pause is needed.
- **Version info** (file properties): FileVersion / ProductVersion become the build date (YYYY.MM.DD, also the binary version YYYY,MM,DD,0), FileDescription / ProductName `Yamaha S-YXG2006LE`, CompanyName `Yamaha Corporation`, and the copyright line gets the credits, like the MU plugins. The resources therefore move to a new section `.rsrc2` (the original `.rsrc` is not the last section and can't grow).
- **Embedded tables:** the two table loaders (`0x4C780` file size, `0x4C7D0` read) take `SXGBNW6L.TBL` / `SXGDAT6L.TBL` from `RT_RCDATA` resources when present (new section `.rsrc2`). Otherwise they read the files from the DLL's folder.
- The code lives in a new section `.sxg` (hook at `0x2CF4` in `main`). It wraps dispatcher / process / processReplacing and has base relocations, so the DLL can be loaded at any address.

**Editor** (issue #39): the DLL has no editor of its own (its dialog resources are unused), so the patch adds one (`utility/dev/sgp2/editor.c`, a small C program compiled into the code of the new section). It looks like the panel of the MU plugins (400 x 114) and uses the DLL's own pictures of Yamaha's unused editor (the Yamaha bitmaps are not part of this repository; the patch takes them from the user's DLL), plus the control row of `bitmaps/Panel101.bmp` and the title `bitmaps/Name_XG2006LE.bmp`:
  - **Level meters:** 16 parts and L / R. L / R show the real output peaks (after Master Volume). The engine reports no part levels, so a part meter shows the velocity of its last note and falls back, more slowly while notes are held on that part.
  - **POLYPHONY:** the notes the plugin counts (as for the Polyphony limit, sustained notes included).
  - **XG / GS lamps:** XG at the start and after an XG reset, GS after a GS or MT-32 reset, none after GM / GM2 (resets from the Setup page and from the song).
  - **CHN / PRG / MSB / LSB:** as on the MU plugins: click, hold (repeat after 400 ms every 75 ms) or mouse wheel. PRG sends a program change, MSB / LSB a bank select followed by the current program change, to every engine. The values shown are what the engines got last on that channel (from the host or from the panel; after a reset the defaults of the mode: XG part 10 MSB 127, GM2 MSB 121 / part 10 120). A bank value the mode ignores shows "---" and is not sent (GM: MSB and LSB, GS: LSB). The drum handling of issue #70 (stepping to the next kit, dimmed PRG digits) is not in this editor: its PRG buttons send plain steps and the readout shows the last program sent.
  - **SETUP** opens the Setup page with the parameters above: Polyphony, Reverb / Chorus, Output Level, Master Tune, Transpose, the five Send Reset buttons, Set Defaults, OK / Cancel / Apply. It works through the plugin's own parameters, so host automation and the saved state do not change.
  - The engine state of the patch is one per DLL copy (as before), so two S-YXG2006LE instances in one process share their meters and control row values.

---

## Setup page

The **Setup** button of the panel opens the Settings page (all models):

![Settings page, MU50 and MU100](utility/dev/gui/settings_page_mu50_mu100.png)

- **Polyphony:** one slider (8-256, default 256) with its value box; the seven preset buttons are gone. Values above 128 use the second engine (see [Polyphony up to 256](#polyphony-up-to-256)); the setting is saved with the plugin state, a state saved by an earlier version loads with 256.
- **Effects:** the three switches name the controller they correspond to: **Reverb (CC 91)**, **Chorus (CC 93)**, **Variation (CC 94)**. Unticked, the block is off.
- **Output Level:** **-12 dB** (left end) to **+12 dB** (right end) in 0.5 dB steps, **0 dB** (the default) in the centre, marked by a tick. The value is saved with the plugin state as before; a level saved by an earlier version keeps 0 dB at the default, other values now follow the new steps (old +6 dB = new +12 dB).
- **Utility** box (MU100 / MU128 / MU1000; on MU50 / MU80 / MU90 the box itself is called **Send Reset** and holds only the four buttons, flush with its title):
  - **Send Reset** (left, issue #37): buttons **MT-32**, **GM**, **GS**, **XG**, **GM2** (size of the original S-YXG50's polyphony buttons, MT-32 a little wider for its label; MU100 / MU128 / MU1000 a little closer together). A click sends that reset to the synth **once**; no button is selected, nothing is sent when the plugin loads, and nothing is saved. Resets that come from the host (the reset at the beginning of a MIDI file, or the one a MIDI player sends before each song) always pass unchanged, as in the original S-YXG50.
    - GM: GM System On `F0 7E 7F 09 01 F7`
    - GS: GS reset `F0 41 10 42 12 40 00 7F 00 41 F7` (Roland GS address 40 00 7F, data 00, checksum 41)
    - XG: XG System On `F0 43 10 4C 00 00 7E 00 F7` (Yamaha XG parameter change, address 00 00 7E, data 00)
    - GM2: GM2 System On `F0 7E 7F 09 03 F7`
    - MT-32: Falcosoft's GS MT-32 sequence (`utility/dev/gui/mt32.syx`, 27 messages, 313 bytes): the GS reset, then for each part the tone number (parts 1-9: MT-32 bank MSB 127 with the MT-32 default programs, part 10: program 128 = CM-64 / MT-32 drum set, parts 11-16: bank 126) and further part settings for MT-32 playback. For MT-32 titles that use no custom instruments or other MT-32 SysEx.
    - Notes, program changes, controllers and SysEx that arrive in the 100 ms (4800 samples) after a reset sent by a button are held back and passed on in order right after that pause, so they reach the synth only after the reset has settled. The reset goes to both engines (polyphony above 128). The XG / GS lamps in the panel follow the reset.
  - **MU Tone Map** (right, MU100 / MU128 / MU1000 only): **Basic** = MU Basic voice map, **Native** = MU Native (default); takes effect with Apply / OK (see [MU Basic voice maps](#mu-basic-voice-maps)).
  - The Send Reset buttons do not enable **Apply** (they act at once). The plugin state no longer holds a reset mode; a state saved by an earlier version loads as before (its Reset Mode is ignored, the Polyphony is kept). **Set Defaults** sends no reset.
- **Monitor panel:** the S-YXG50 also has a monitor panel with part levels, polyphony and load readouts. It replaces the normal panel when `DebugPanel=1` is set in the ini (see [The ini](#the-ini)).

## Polyphony up to 256

The S-YXG50 engine has 128 voices (one voice per element, so a 2-element voice takes two). With **Polyphony** above 128 on the Setup page (the default is 256), the DLL runs a second engine for the voices above 128, much like Nuked-SC55-P256. As long as a song needs no more than 128 voices, the second engine sleeps and the output is bit-identical to a single engine:

- The second engine is made inside the DLL when the plugin starts (the host still sees one plugin) and gets every MIDI event, SysEx and reset, so it always has the song's state. Tables and wave data are shared, it only costs its own engine memory.
- A Note On goes to the first engine while it has two voices free, else to the second (up to *Polyphony* - 128 voices), else to the first, which then steals a voice as before. Note Offs, controllers, program changes, pitch bend and SysEx go to both. The outputs are added.
- The second engine renders only while it has notes, plus 4 s for release and effect tails, and for 250 ms after a SysEx (a reset only takes full effect while the engine renders). Asleep it costs next to nothing; it takes its events directly and picks up the first engine's control-rate clock when it wakes, so its notes sound like the first engine's (measured: a note on the second engine is bit-identical to the same note on the first).
- The POLYPHONY readout in the panel shows the voices of both engines (up to 256).
- Effect switches and Output Level follow the first engine. Effects are linear, so two reverbs over two halves of the notes add up to one reverb over all of them.
- Limits: exclusive groups (e.g. open / closed hi-hat) and mono parts only act within one engine; after a voice map switch the second engine takes the new map with the next program change; the setting above 128 is shared by all instances of the same DLL in one host process.

## Panel controls (channel, program, bank)

Since issue #42 the panel is 24 pixels higher (400 x 114) and has a control row of its own under the title strip (all models; earlier versions: issues #16, #23, #35):

- **CHN ◀ 01 ▶** selects the MIDI channel (01-16) for the three controls on its right.
- **PRG ◀ 001 ▶** steps the program of that channel down or up by one (001-128, wraps around; the bank stays) and shows the channel's current program, including program changes from the host. On a drum part a step goes to the next kit instead of the next number (see **Drum parts** below).
- **Drum parts** (issue #70): a drum part only has a few kits, and the engine ignores every other program change that comes from the panel (a step used to land on the same kit again, in both directions). GS and GM2 have the kits 001, 009, 017, 025, 026, 033, 041, 049, 057 and 128 (on the MU50, MU100, MU128 and MU1000); in XG the list depends on the model (MU50: 001, 002, 009, 017, 025, 026, 033, 041, 049). The PRG buttons now go on in the direction of the step until the engine takes a program, round the ends of the list, so every kit can be reached from the panel; a melodic part still steps by one. To see which channels are drum channels, the **PRG digits of a drum part are dimmed** (grey, 65 % contrast to the field; the MSB and LSB digits keep their colour). The panel reads the engine's own rhythm flag of the part, so the dimming follows every way a part becomes a drum part or stops being one:
  - GS: "use for rhythm part" on any channel, switched on and off again by sysex; channel 10 after a reset. In GS the banks 120 and 127 are only variations and do not dim.
  - XG: bank MSB 120, 126 or 127; channel 10 always, whatever its MSB (the S-YXG engines keep it as a drum part).
  - GM2: bank MSB 120, 126 or 127; MSB 121 is melodic again. GM: channel 10.
  - The engine sets the flag with the program change that follows a bank select, so the digits change with that program change.
- **No instrument** (issue #73): in XG and GM2 mode almost any bank and program combination is accepted, but only some have a voice; a channel with another one stays completely silent (like "No Instrument" on Roland devices without CTF support). The **PRG digits are then red** (a strong red, a little darker than full red), so you can see at a glance which channel has no instrument. The engine has no flag for it; the panel uses the engine's own voice lookup: it asks it for the voice of the channel's bank, LSB and program and for the voice of its silent bank (XG: SFX MSB 1), and the part has no instrument when both are the same. This also catches single empty programs, e.g. in the SFX bank (MSB 64). The result is the same on every model (checked against rendered notes: every silent combination was found, no sounding one was marked), but which banks exist differs between models, so the same MSB can be red on one model and white on another. Not in GS or GM mode, where the engine falls back on a capital tone and is never silent, and not on drum parts (they stay grey). Red means "no voice assigned", not "nothing to hear right now": a note outside the key range of a voice stays silent without it.
- **MSB ◀ 000 ▶** and **LSB ◀ 000 ▶** step the channel's bank select MSB / LSB (000-127). A step sends the bank select (CC 0 or CC 32) followed by a program change of the current program on that channel, so the new bank sounds at once; the readouts show the channel's current bank values, also when they come from the MIDI file. A bank select the engine ignores in its current mode shows as **---** and its buttons leave it alone: after a GS reset the S-YXG50 ignores bank select LSB (CC 32), after a GM reset both MSB and LSB (in XG mode, the state after loading, and after a GM2 reset both are used).
- Each button reacts to single clicks; holding it repeats the step (after 400 ms, then every 75 ms); the mouse wheel over a control steps it as well.
- After loading, the panel shows **CHN 01**; nothing of the row is saved with the plugin state (like the program itself). Before the first audio block the value readouts stay blank.
- Program and bank changes go to both engines (polyphony above 128).
- Each plugin instance has its own row (issue #55): with several instances in one host process (e.g. VST MIDI Driver ports A and B), every panel shows and changes only its own instance; up to four instances per process have a working row.
- **Preview note** (issue #43): press and hold the left mouse button anywhere in the **POLYPHONY** field (the dark box with the voice count) to hear the selected sound: it plays a note on the channel chosen with CHN (velocity 100) for as long as the button is held (releasing it outside the field works too). The mouse wheel over the field changes the pitch (next higher / lower note, C1 to G9, default C4); on a held note the new pitch sounds at once. Nothing of it is saved. The note goes to the first engine only (a note given to the sleeping second engine would keep its voice and stay in the POLYPHONY count, issue #46).
- The model name in the title strip is a picture of its own (`utility/bitmaps/Name_<model>.bmp`), the panel picture is the same for every model (`utility/bitmaps/Panel101.bmp`).
- Hosts that ask for the editor size only once may show the taller panel only after the plugin is loaded again.

![Panel with the control row CHN / PRG / MSB / LSB](utility/dev/gui/panel_preset.png)

## MU Basic voice maps

The MU100, MU128 and MU1000 have two voice maps, which the module switches with its own Voice Map setting:

| Map | Voices | PC 0 drum kit |
|---|---|---|
| MU Native | revoiced (`GrandP #`, `BriteP #`, `Strngs1#`, ...) | native Standard Kit |
| MU Basic | MU90-compatible (`GrandPno`, `BritePno`, `Strings1`, ...) | MU90 Standard Kit |

**New:** the converted table contains **both maps**, and the patched DLL switches between them like the module does:

- **Setup dialog:** open Setup in the S-YXG50 panel, pick **Basic** under **"MU Tone Map"** and press Apply/OK. **Set Defaults** returns to the start value.
- **When it takes effect:** immediately, for the next note on every part (the current programs are selected again in the new map with the next MIDI event). Notes already sounding keep their voice. Parts with *receive program change* switched off keep their voice until a reset.
- **Saving:** like the other Setup options, the setting is part of the plugin state (VST chunk) that the host saves with its project, preset or plugin settings and restores on the next load. The DLL itself writes no files. A host that does not save plugin state starts with the start value every time. Confirmed: in the **Falcosoft MIDI Player** the setting survives a restart once the VSTi settings are saved there; in the **VST MIDI Driver** it is saved with "Apply" in its configuration. Since issue #65 the restored setting also stays in place when the plugin starts playing: each synth engine the DLL starts (one per instance, plus the second engine of [Polyphony up to 256](#polyphony-up-to-256) on the first audio block) used to set the map back to the start value with embedded tables, so the VST MIDI Driver played MU Native in real time although its configuration showed Basic.
- **Start value:** MU Native. An optional `MUBasic=1` in the plugin's section (or `[Config]` / `[SYXG50]`) of `<dll name>.ini` makes MU Basic the start value (only read, never written). The start value is taken once, when the DLL sets up its first engine; later engines keep the current setting. A saved plugin state overrides it (also when the host restores it before the first engine is set up); older saved states without the setting keep the start value.
- **Embedded tables (`--embed`):** the switch works the same and needs no ini; the DLL stays a single file (no ini, no registry).
- **Other tables:** with MU50 / MU80 / MU90 tables, or MU100+ tables from earlier versions, the checkbox is hidden.

Both maps share the same samples, elements and drum voices. The appendix behind the table holds only what differs: the XG voice row, the XG drum program row and (on MU128/MU1000) the GM2 row, plus the banks and voices only the basic map has (MU100: 70 banks, no extra voices; MU128: 83 banks, 32 voices; MU1000: 86 banks, 32 voices). The wave file does not grow. GS, SFX and MSB 48 are the same in both maps. Both settings were checked to render byte-identical to separate native-only and basic-only builds (external and embedded), and the switch was confirmed in a real VST host.

> **Note:** the newer kits (e.g. the Apogee Kit on XG drum program 30) exist in both maps. A song that selects such a kit sounds different on MU100+ tables than on MU80/MU90 tables, which fall back to the Standard Kit, and the same happens on real hardware.

---

## What the conversion does, per model

### All models

- **Bank maps:** program and drum kit bank maps are rebuilt for the S-YXG50 bank map format (XG, SFX, GS; MU128/MU1000 also GM2).
<a id="bank-maps-gm2"></a>- **GM2 banks for every model** (issue #34): models without GM2 voices of their own (MU50, MU80, MU90, MU100) get the ten GM2 banks of Yamaha's own S-YXG50 table: bank select MSB 121 + LSB 0-9 plays the GM2 capital and variation tones (e.g. LSB 3, program 63 = Jump Brass, LSB 1, program 128 = Machine Gun), built from the model's own XG and GS voices (`utility/dataGM2.py`, a list of positions only); GM2 drum programs (MSB 120) select the kits like GS. As in the original S-YXG50, this works after a GM2 reset (`F0 7E 7F 09 03 F7`, which also sets the default banks MSB 121 / 120 for the GM2 file) and after an XG reset, so GM2 files play without any setting; the Send Reset button GM2 (issue #37) sends a GM2 reset by hand. Before, MSB 121 was silent after a GM2 reset and every GM2 drum program gave the standard kit.
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
- **Drum level (MU1000):** syxg50.dll plays every drum key about 0.8 dB below the S-MU2000 with the same data, for all kits, levels, velocities and EG modes (melodic voices have no such offset). The level byte is raised by 0.82 dB (x 1.048 on the 40*log10 level curve, clamped at 127). Drum sweep of all 39 XG/SFX kits (2,453 keys): median -0.82 -> -0.03 dB. Only measured for the MU1000 (the S-MU2000 has the MU1000 drum data), other models are unchanged.
- **Drum level trim per drum voice (MU1000):** syxg50.dll plays drum samples with a different frequency balance than the MU, about 1 dB less above 6 kHz and 0.3 dB more below 800 Hz, and the loss moves with the pitch of the key. So cymbals, shakers and triangles stayed 0.6-1.6 dB too quiet after the global +0.82 dB, kicks and toms up to 1.8 dB too loud (e.g. Ride 2 in the classic kits: -0.9 dB; issue #5, not caused by the level offset). A level estimate from the sample spectrum explained only part of it, so each drum voice gets its measured deviation as a trim (`drumtrim.py`, 680 of 868 drum voices, keyed by the CRC32 of their 42 source bytes; voices shared by several kits measured the same within 0.14 dB). syxg50.dll also plays the drum level byte in steps of 0.5-1 dB (levels 115-119 all at -1.7 dB, 120-124 at -0.8 dB, 125-127 at 0 dB), so the trimmed level is the byte of the nearest step. Internal keys that still need more at the top step (84 drum keys, e.g. the triangles, 80/81 at -1.5 dB) become ext drum voices whose element reproduces the internal playback (`drumvel.py`) plus a second, identical element that adds the missing gain in phase (measured: 20 x log10(1 + 1.5 x (level / 127)^2) dB). Keys with the short-decay rule (Short Guiro) stay internal, their element EG differs. Drum sweep of all 39 kits: median deviation 0.48 -> 0.20 dB, p90 1.53 -> 0.61 dB, keys more than 1 dB off 20.1 % -> 4.3 %, more than 2 dB 3.6 % -> 0.1 %; Ride 2 -0.90 -> -0.03 dB. With the boost (issue #4): p90 0.42 dB, keys more than 1 dB off 0.9 %, more than 3 dB 1 key (an SFX ext voice); keys 13/14/23/24 (+1.8..+3.2 dB before the trim) within 0.5 dB, triangles 80/81 -1.5 -> -0.2/+0.1 dB, stable within 0.5 dB at velocities 32-127.
- **Level trim per melodic voice (MU1000):** after the voice sweep (issue #3) some voices stayed several dB off on every note and at every velocity. Their wave tables are converted 1:1; the offset comes from how syxg50.dll mixes the elements (detuned or stacked copies of one wave), so it cannot be derived from the voice data (issue #6). Each voice with a median deviation of 1 dB or more gets its measured offset as a trim on the element levels (`voicetrim.py`, 66 voices, keyed by the CRC32 of the source voice; syxg50.dll plays the element level on a 40 x log10 curve), calibrated against a second measurement. Voices that are too quiet get louder element levels up to 127; what is still missing there goes into louder copies of their samples (`elemreduce.gain_wavebank`, 24 voices, e.g. Insects -7.6 -> +0.3 dB, Sweepy -5.2 -> +0.1 dB; the wave file grows by about 5 MB). A copy that would clip is scaled back to full scale, and syxg50.dll caps the output of some voices (AfrcnWnd: level 110 -> 127 = 0 dB), so 5partStr (-7 dB), AfrcnWnd, Starship and WindChim stay too quiet. Too-quiet voices, C2/C4/C6 at velocity 64/100: mean deviation 2.20 -> 1.13 dB, p90 5.20 -> 2.33 dB. Trimmed voices, C2/C4/C6 at velocity 64/100: mean deviation 1.97 -> 1.22 dB, p90 4.57 -> 2.79 dB, points more than 3 dB off 17.1 % -> 9.2 %. Note-dependent deviations (e.g. StBrtPno, Tin) remain.
- **Key-dependent trim (MU1000):** some voices drift over the keyboard (e.g. Trcrtps +1.6 dB at C1 down to -5 dB at the top, Frost -9 dB in the bass). Measured every 6 keys from 24 to 102, the 11 voices with a smooth trend get it corrected through the element level key scaling: a piecewise-linear fit with breakpoints at keys 30/54/78/102, multiplied into the element's own key scaling (`voicetrim.KEY_TRIM_DB10`). RMS deviation over the keyboard 2.6 -> 1.2 dB (Trcrtps 2.9 -> 0.6, Frost 4.2 -> 1.4, HeinzUni 2.1 -> 0.8). Jagged curves stay: they come from element pairs on the same wave (StBrtPno, NylnGtDt, VlnHrpDt, Popcorn), whose two copies add up differently from note to note in syxg50.dll; a level or key-scaling change cannot fix them (repeat measurements of these voices differ by up to 1.7 dB already).
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
- **Element HPF (element byte `+80`):** 162 elements in 128 MU1000 voices, e.g. Oboe, Muted/Jazz/Overdrive Guitar, Slap Bass, Rock Organ. Same filter and cutoff scale as the drum HPF (measured on the S-MU2000). Baked into filtered copies of the multisamples (see [Why the wave files got bigger](#why-the-wave-files-got-bigger)). The HPF copies are cut in the transposed key range (key + coarse tune), as the DLL selects waves; this matters for 18 elements with both, e.g. Sleep (+24): low-band shape against the S-MU2000 -1.9 -> +0.3 dB. A **static pitch EG** (all five PEG levels equal, no PEG velocity sensitivity) moves the played pitch away from that key without changing the wave choice, so the cutoff and the critical key range are taken at the played pitch: depth 0-3 = ±3 / 6 / 12 / 24 semitones at level 0 / 127, linear in the level (measured in the DLL). This concerns 3 MU1000 elements with an HPF: Parasite (+24, C2-C6 against the S-MU2000 -3 to -13.5 dB -> -0.5 to -1.1 dB; MU100 within 0.4 dB), Fuzzorgn (+12, upper keys up to 1.4 dB closer in spectrum) and NoisePno (+2, unchanged within 0.5 dB). Folding the static pitch EG into the coarse tune instead was tried and rejected: it changes the wave choice and made 8 of 13 such voices worse (e.g. OldPiano, CheezOrg, AsianBel).

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
| Element HPF + static pitch EG (Parasite, C2-C6) | -3 to -13.5 dB | -0.5 to -1.1 dB |
| Effect types without counterpart (e.g. Symphonic as chorus, Dist+Delay tail) | +5.0 dB / +11.8 dB | +0.3 dB / +1.8 dB |
| Effect return levels (late tail, 12_Effect_Test) | median 2.2 dB off | 0.4 dB |
| Effect onset after a type change (0.12-0.5 s, 91 types) | 3.8 dB off (3.7 dB too weak) | 1.1 dB off (0.4 dB) |
| Drum level, all MU1000 kits (39 kits, 2,453 keys) | -0.82 dB median, 0.88 dB median deviation | -0.03 dB, 0.48 dB; 1.9 % of the keys more than 3 dB off, none more than 6 dB |
| Drum level trim per drum voice (same sweep) | 0.48 dB median deviation, 20.1 % of the keys more than 1 dB off | 0.20 dB, 4.3 % (mostly keys at the top level step); Ride 2 -0.90 -> -0.03 dB |
| Level boost for keys at the top level step (same sweep) | 4.3 % of the keys more than 1 dB off, triangles -1.5 dB | 0.9 %, p90 0.42 dB; triangles within 0.2 dB |

The voices with stereo pairs measure about 2-3 dB louder in a mono recording, because the uncorrelated L/R pair of the original loses 3 dB in mono; in stereo the power is the same.

### Cross-checks between models

- **MU50 against the S-YXG50's own table** (`SXGBIN41.TBL`, Yamaha's port of the MU50 sound set): the converted voice and drum parameters are identical for all 438 XG voices and 303 drum keys. The wave tuning matches within 1-2 cents (the S-YXG50 table writes some fine tunes from the next note down, e.g. note 50 / +52 cents instead of note 49 / +209, measured as the same pitch in the DLL). Rendered in the DLL, 80 % of 1,313 notes are within 0.1 dB of the original S-YXG50, and 3 are more than 3 dB apart.
- **MU80:** its voices are revoiced against the MU50 (scattered differences, no systematic offset), so the S-YXG50 table is no reference there.
- **MU90 / MU100 / MU128 / MU1000:** all XG voices were rendered (keys 36/60/84) and compared where two models share a voice (same bank, program and name): MU128 vs MU1000 1,014 voices, MU100 vs MU128 939, MU90 vs MU100 505. The converted voice data of MU128 and MU1000 is identical for all shared voices; MU100 differs in 4 (Whistle, Ocarina, DrawOrg2, Dim&Cool: different ROM data). After the MU100 element HPF fix, every remaining level difference above 2 dB was traced to identical data played after a different preceding voice (LFO phase), not to the conversion. No clipping voices; the only silent one (Lite Org) led to the rising decay 2 fix.
- **Builds:** the multi-model run with `--embed` (MU90, MU100, MU128, MU1000 from the `source` folder) and the MU50, MU80 and MU90B sets convert without errors. Rebuilds after each change were compared byte by byte against the previous build, so that only the intended bytes changed.

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
- **Polyphony above 128:** see the limits in [Polyphony up to 256](#polyphony-up-to-256).
- **Remaining deviations:** a sweep of all 1,193 MU1000 voices (XG + SFX, C2/C4/C6, no effects) against the S-MU2000 gave a median deviation of 0.33 dB in the sustain level and 0.39 dB in the attack; 2.1 % of the notes are more than 3 dB off. About half of those depend on the note-on time in both synths (beating between elements, free-running LFO) and are not conversion errors. Stable deviations remain for the merged 3/4-element voices (e.g. 5partStr, Trcrtps), a few SFX voices with very deep pitch modulation (Insects, Sweepy) and single voices (e.g. VX El.P1, RobotClv, AfrcnWnd). Above 3.2 kHz the S-YXG50 is slightly darker (-0.3 to -0.6 dB). Release tails end at about -50 dB in the S-YXG50 (about -70 dB on the S-MU2000). A few effect types are 2-3 dB off.

---

## Using the converted DLLs

- **Host:** syxg50.dll is a 32-bit VST2 instrument. Any VST2 host works; to use it as a system MIDI device (e.g. for DOSBox or Windows games), load it through a VSTi MIDI driver.
- **Which model:** MU50 sounds like the DB50XG, SW60XG and the S-YXG50 itself, which is what most players of 1990s games heard. MU90/MU100 are good all-rounders with better samples and similar balance (MU100 = SW1000XG sound set). MU1000/MU128 have the best samples and the most voices, but are larger and partly revoiced; the "MU Tone Map" switch (Basic) in Setup gives the MU90-compatible voice set for older material.
- **GS:** GS songs play through Yamaha's GS mode, an approximation of the Roland sound set. MT-32 music needs an MT-32 emulator.

---

## Behaviour on reruns

- **Table and DLL output:** an existing table file is skipped. The DLL and ini are rewritten on every run.
- **Wave file:** if it already exists, the run stops before writing it ("already exists, exiting early"). Delete or move the old table and wave file before rebuilding the same model. With `--embed` nothing is written besides the DLL.

---

## Investigation tools

Optional, not needed for conversion, in `utility/dev` (not in the release archive).

`python utility/dev/analyze_mu80.py <tool> <files...>`

| Tool | Purpose |
|---|---|
| `drum-eg` | compares MU80 drum voices with the S-YXG50 drum voices of the same kit and key (drum EG calibration), writes `drum_eg_compare.csv` |
| `voice-params` | compares converted MU80 voice elements byte by byte with the S-YXG50 voices in the same slot, writes `voice_param_compare.csv` |
| `sample-flags` | collects evidence on bit 6 of the MU80 sample format byte, writes `sample_flags.csv` |
| `long-loops` | lists MU80 voices with loops longer than 65,535 samples |

Usage is described at the top of each section. Most take the MU80 ROMs plus the 5 MB `syxg50.dll` (or `SXGBIN41.TBL` + `SXGWAVE4.TBL`). `utility/dev/voicemap` holds the assembler sources of the voice map patch (`vmap2.asm`) and the scripts that turn them into patch bytes. `utility/dev/gui` holds the same for the Setup page (`settings.asm`) and the panel preset buttons and reset handling (`gui.asm`), `mkgui.py`, the script that draws the preset control (`mkpreset.py`, writes `bitmaps/PresetPanel.bmp` and `PresetButtons.bmp`) and screenshots.

Modules used by the conversion (in `utility`): decoders `decBase.py` (incl. table creation), `decMU50.py` ... `decMU1000.py`, `decSYXG50.py`; table converters `tableconvert.py`; table writer `makeSYXG50.py`; samples `SampleConvert.py`; `elemreduce.py` (voices with 3/4 elements, EG baking), `drumvel.py` (drum velocity sensitivity), `dllpatch.py` (DLL patcher), `convert.py`, `dataCRCs.py`, `dataenum.py`, `table.py`, `utils.py`, `buildtarget.py`. The folder `utility/bitmaps` holds the panel pictures for the DLL.

---

## Credits and license

- **Soundshock** – original [SXG-Create](https://github.com/Soundshock/SXG-Create)
- **tarboh** – [S-MU2000](https://github.com/tarboh/S-MU2000), the reference for the sound comparisons
- **TaleTN** – [MUTable](https://github.com/TaleTN/MUTable), MU series data table documentation (MU50 ext drum voice table, MU2000 scaling tables)
- **VEG** (Evgeny Vrublevsky) – [S-YXG50](https://veg.by/en/projects/syxg50/) (`syxg50.dll`, included in this repository with the author's permission)
- **Yamaha** – MU series tone generators and the S-YXG50 sound engine

DPCM delta table, DPCM limits table, and delta format decoding code based on MAME, copyright (c) MAME contributors, and related contributions by TaleTN, tarboh, and hockinsk under the BSD-3 license.

license: BSD-3-Clause

copyright-holders: Olivier Galibert
