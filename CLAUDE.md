# CLAUDE.md – SXG-Create-NF

Guidance for Claude (Claude Code or chat) working in this repository. The README covers what users need; the technical reference is in `docs/` (see its table "More documentation"); this file is the short map.

## Binding project rules for changes and documentation

These rules apply permanently to all tasks and changes in this repository.
Apply them proactively, without needing to be reminded.

### 1. Documentation on every change

- For every change, check whether `README.md`, the matching file in `docs/` (technical details) and/or the Autobuild Release Notes
  need to be updated. The release notes are the `body` of the "Create GitHub
  release" step in `.github/workflows/build.yml`.
- Add a row to `docs/versions.md` (version history) for every change that ends up in a release; plain language, one line, newest on top.
- Required documentation changes belong in the same change (the same PR).
- Never skip a documentation update without checking first. State the result of
  the check (updated, or not needed and why) in the PR.

### 2. Changes to the plugin GUI, the Setup page or the patcher

Applies to the plugin panel and its controls (`utility/dev/poly/panel.asm`,
`utility/dev/gui/mkpanel.py`, `utility/bitmaps/`, the panel patches in
`utility/dllpatch.py`), the Setup page (dialog 111, `utility/dev/gui/settings.asm`,
`gui.asm`), the S-YXG2006LE parameters shown to the user, and the patcher window
(`patcher.py`, `patcher_i18n.py`).

- Before implementing, create preview screenshots (mockup or rendering) and
  present them for approval.
- Do not start the implementation until the screenshots have been explicitly
  approved.
- After implementing, check whether existing screenshots in the README
  (`utility/dev/gui/*.png` and embedded images such as the patcher preview) are
  outdated, and update them if needed.

### 3. Binding nature

- If it is unclear whether something has been approved, ask before implementing.

## What this is

SXG-Create-NF converts the ROMs of Yamaha MU tone generators (MU50 … MU1000) into tables and wave data for the **S-YXG50** soft synth and patches `syxg50.dll` (626,688 bytes) so it plays them like the module. It also patches Yamaha's **S-YXG2006LE** (`SGP2.OLD` / `SGP2.DLL` + `sxgbnw6l.tbl` / `sxgdat6l.tbl`, used unconverted) into a host-independent plugin. Releases ship a GUI **patcher** (Windows, Linux, macOS Apple Silicon / Intel) built from the same Python code.

## Layout

- `main.py` – command line converter (finds ROMs / DLLs by CRC32 in its arguments or `source/`, writes `output/` or `--out-dir`; `--embed` puts tables into the DLL; multi-model runs re-invoke itself per model, in parallel: `--jobs N`, default CPU cores limited by free memory; without a DLL the plugin comes from the model's template).
- `source/syxg50.dll` – the original DLL, part of the repository (with its author's permission); `templates/*.tpl` + `templates.json` – one ready-patched plugin per model with zero-filled table / wave placeholders, made by `utility/template.py --make` (the Autobuild workflow regenerates and commits them itself, so `git pull` before pushing to `main`).
- `patcher.py`, `patcher_i18n.py` – Tkinter window around `main.py` (29 languages, `--cli` runs `main.py`, `--selftest` checks the templates; no DLL row since #40, the templates ship as one 7z archive read with `lzma`). Frozen with PyInstaller in `.github/workflows/build.yml`.
- `utility/selfupdate.py` – the patcher's self-update (#72, stdlib only): the number of the newest release comes from the redirect of `releases/latest` (not the API: 60 requests an hour per IP), the file `SXG-Create-NF-Patcher-r<N>-<system>` from `releases/download/autobuild-r<N>/` (https and GitHub hosts only), then size / SHA-256 / `--selftest --selftest-out` of the new file, replacement per system, restart with `PYINSTALLER_RESET_ENVIRONMENT=1`. **The tag `autobuild-r<N>`, the asset names in `build.yml` and `--selftest-out` are a contract with it: change them together.** Options `--no-update-check`, `--update-dir`, `--update-test-version`, `--after-update`; texts `upd_*` in `patcher_i18n.py`. To test a frozen build, build with `patcher_version.py` (`VERSION = 'r900'` and `'r901'`) and put the newer file into a folder for `--update-dir`; build the test copy from `git ls-files -co` (a new module is not tracked yet).
- `utility/` – converter modules: `dec*.py` (ROM decoders), `makeSYXG50.py` (table writer, incl. GM2 banks from `dataGM2.py`), `dataCRCs.py` (known ROMs), `dllpatch.py` (all patches of `syxg50.dll`), `template.py` (make / fill / check templates), `sgp2patch.py` + `sgp2code.py` (S-YXG2006LE), `bitmaps/` (panel / Setup bitmaps).
- `utility/dev/` – sources of the generated machine code, not imported at run time:
  - `gui/gui.asm` (audio-thread side: pending reset, event queue), `gui/settings.asm` (Settings page, chunk), `gui/mkgui.py` (assembles GUI + poly code, prints the lists for `dllpatch.py`), `gui/mkpanel.py` (panel bitmaps of #42; `mkpreset.py` is the older preset-control script).
  - `poly/poly.asm` (second engine, polyphony 256), `poly/panel.asm` (CHN / PRG / MSB / LSB panel controls, preview note), `poly/ini.asm` (ini lookup) – section `.sxp` at `0x1005B000`.
  - `sgp2/params.asm` + `sgp2/editor.c` + `sgp2/mksgp2.py` (S-YXG2006LE parameters, engines, editor in C, section `.sxg`).
  - `voicemap/` (MU Basic / Native voice maps).

## Rules that matter

- **Generated code:** after changing `gui.asm`, `settings.asm`, `poly.asm`, `panel.asm` or `ini.asm`, regenerate **all** lists in `dllpatch.py` together (`SYXG50_GUI`, `GUI_CAVE_END`, `SYXG50_GUI_CHUNK`, `SYXG50_POLY`, `POLY_CODE`, `INI_ID_OFFSET`, `POLY_DATA_END`) with `mkgui.py` – gui.asm and the .sxp code call each other, partial updates jump to wrong addresses. For S-YXG2006LE run `mksgp2.py params.asm > ../../sgp2code.py` (write to a temp file first; `.set` constants are substituted literally); it also compiles `editor.c` (the editor, #39) with `gcc -m32` and links it with GNU `ld` into the code (behind label `ed_blob`, 64-byte aligned; mksgp2.py checks the link address), so it needs a Linux gcc / binutils that produce 32-bit ELF (dev only, the generated `sgp2code.py` is committed).
- **Code must be position independent** (call/pop, `ebp` = load delta); absolute addresses as `[ebp + 0x1005xxxx]`.
- **No shared state between instances:** hosts may process several instances in parallel threads. Never keep per-instance values in a process-wide `.data` variable between calls (bug fixed in #48: global current slot); look up the slot from the plugin pointer, claim slots with `lock cmpxchg`. Test parallel instances under Wine (workbench `p256_test/thr.c`).
- **Never enlarge the engine:** the original engine stays at 128 voices (clamp at `0x100056D0` untouched); more polyphony means more unmodified engine instances. Every new buffer gets an explicit bounds check.
- **Windows API calls clobber eax / ecx / edx** (the emulator's stubs don't): save registers around SelectObject / BitBlt etc.
- **Never trust object layouts seen only in the emulator.** The emulator heap and its CPU (no SSE) differ from Windows / Wine: settings object = `[plugin +0xB0]`, not an offset; the S-YXG2006LE voice manager can't be found reliably at all. Check pointers via fields and test under Wine (`vhost.exe`, `host.exe`).
- **Test GUI / reset features in every engine mode** (XG, GS, GM, GM2).
- Python 3.12, standard library only (the patcher must freeze cleanly). Use `sys.exit`, not `exit`.
- Comments and README in English; commit messages: Summary + Description bullets, English.
- Don't write Yamaha data into the repository (position lists like `dataGM2.py` are fine).

## Behaviour to keep (current decisions)

- Plugins start in XG / XGLite with pass-through for all resets and SysEx (like the original S-YXG50). **Send Reset** buttons (GM / GS / XG / GM2; S-YXG2006LE: parameter GM / GS / XGLite / GM2) send a reset once; nothing is sent at load or saved (#37).
- Polyphony default 256 (MU plugins: second engine; S-YXG2006LE: up to 8 engines of 32 voices, notes counted by the plugin, sustain-held notes count).
- ini: keys looked up in `[Config]`, `[SYXG50]`, `[<plugin id>]` (e.g. `[SYXG100]`); table key `VoiceTable` or `SoftSynth`; the converter writes `[<plugin id>]` + `VoiceTable` (#36). The S-YXG2006LE reads no ini.
- Panel (#42): 400 x 114, control row `CHN ◀ 01 ▶  PRG ◀ 001 ▶  MSB ◀ 000 ▶  LSB ◀ 000 ▶` under the title strip (ignored bank values show `---`); bitmap 101 = `Panel101.bmp` + `Name_<model>.bmp`, made by `utility/dev/gui/mkpanel.py`.
- Send Reset buttons: MT-32 (Falcosoft's GS MT-32 sequence, `utility/dev/gui/mt32.syx`) / GM / GS / XG / GM2 (#37, #41).
- Preview note (#43, #46): holding the left mouse button in the POLYPHONY field (x 245-298, y 57-103) plays a note on the CHN channel, wheel = pitch (C1-G9, default C4); it goes to engine A only.
- Patcher users need only ROMs (and the S-YXG2006LE files); `syxg50.dll` is no longer asked for (#40). Plugins from a filled template must be byte-identical to `syxg50.dll` + `--embed`.

## Typical commands

```sh
python3 -m py_compile main.py patcher.py patcher_i18n.py utility/*.py
SXG_NO_PAUSE=1 python3 main.py <roms…> [syxg50.dll] [--embed] [--out-dir DIR] [--jobs N]
python3 utility/template.py --make --check     # rebuild / verify templates
python3 utility/dev/gui/mkgui.py syxg50.dll gui.asm settings.asm ../poly/poly.asm   # in utility/dev/gui
python3 patcher.py            # window from the repository (needs Tk)
python3 patcher.py --selftest
```

The maintainer's workbench (`SXG-Create_workbench.zip`) holds the ROMs, DLLs, emulator (`vstemu/`, `syxg2006le/emu2006.py`), Wine test hosts and test scripts; `HANDOFF_SXG-Create.md` has the session history.
