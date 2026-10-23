# Development notes

## Folder layout

```
main.py              the converter (run this)
README.md, LICENSE, docs/   README (users) and the technical documentation
CLAUDE.md            project rules and a short code map for Claude (Claude Code)
source/              your ROM files; the original syxg50.dll (part of the repository, the templates are made from it)
templates/           plugin templates, one per model, without ROM data (made by the Autobuild workflow)
output/              generated tables, wave files, patched DLLs and inis (created on the first run)
utility/             the converter modules (decoders, table converters, table writer, sample conversion, DLL patcher)
utility/bitmaps/     panel pictures for the patched DLLs
utility/dev/         development tools, not needed for a conversion and not in the release archive
.github/workflows/   autobuild release
```

**Autobuild:** every push to `main` that changes `main.py`, the patcher, `utility` (except `utility/dev`), `source/syxg50.dll` or `templates` makes the [templates](templates.md) again (and commits them when they changed), then creates a release `autobuild-rN` (marked Latest) with the patchers for Windows, Linux and macOS, built from that commit. Older autobuilds are kept (for regression tests) and carry no label, so only the newest one, listed on top, is marked Latest. The workflow can also be started by hand (Actions, "Run workflow"). Autobuilds r14-r27 (the first ones with patchers) were deleted by the earlier workflow; the hand-started workflow `restore-autobuilds.yml` creates them again from the patchers that the Actions runs still hold. The tag `autobuild-rN` and the names of the patcher files in the release are used by the patcher's update (issue #72): keep them, or change `utility/selfupdate.py` with them.

## Patcher

The patcher is `patcher.py` (texts in `patcher_i18n.py`); it imports `main.py` and the modules in `utility` unchanged and runs each model through `main.py`'s command line (`patcher --cli <arguments>`, without a DLL, so the plugins come from the templates). The release workflow freezes it with PyInstaller on each system, with the templates in one 7z archive. `python patcher.py` starts it from the repository (Python 3.12 with Tk) and uses `templates/`. `patcher --selftest` checks that every template is there and empty.

- **Update test options:** `--update-dir <folder>` takes the release files from a folder instead of GitHub, `--update-test-version rN` makes the patcher act as that version.

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
