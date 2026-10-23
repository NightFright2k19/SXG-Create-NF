# Python script and command line

For development, or for conversions without the patcher.

## Quick start

1. Download the latest **Autobuild** release (or clone the repository) and extract it.
2. Put your MU ROM files into the `source` folder. Subfolders are fine, e.g. one per model. The original `syxg50.dll` (626,688 bytes) is already there (part of the repository).
3. Run:

```
python main.py [--embed]
```

The converted files end up in the `output` folder.

- **Inputs:** ROM files in any order. SXG-Create detects the model from the CRC32 of the files, so the file names don't matter. Files larger than 64 MB in `source` are ignored.
- **Command line:** ROM files and a DLL can also be given on the command line (or dropped onto `main.py`); they are used together with the contents of `source`.
- **DLL:** one `syxg50.dll` under any file name. SXG-Create writes a patched copy plus a matching `.ini` (or, with `--embed`, a DLL that contains the table). Without a DLL (ROMs given on the command line with `--out-dir`, or `source/syxg50.dll` removed), the plugin is made from the model's [template](templates.md#plugin-templates), as the patcher does; without a template, only the table and wave file are written.
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

## Command line parameters

| Parameter | Meaning |
|---|---|
| `<ROM files>` | Optional. Program ROM(s) and wave ROMs of one or more models, in any order (see [Supported models](../README.md#supported-models-and-rom-sets)), in addition to the `source` folder. Wildcards are allowed. |
| `<dll>` | Optional. A `syxg50.dll`, under any file name (`syxg50.dll`, `mu800.dll`, ...). It is recognised by its content, not its name. A DLL in the `source` folder is used if none is given on the command line. See [DLL patching](dll-patching.md#dll-patching). Without one, the plugin is made from the model's [template](templates.md#plugin-templates). |
| `--jobs N` | **New.** Number of models converted at the same time in a multi-model run (default: CPU cores, limited by free memory; 1 = one after another). Each model's log is printed in one piece when it is done. |
| `--embed` | **New.** Puts table and wave file into the patched DLL as resources instead of writing them as files (see [Embedded tables](dll-patching.md#embedded-tables---embed)). Needs a DLL or the model's template. |

The table layout and the DLL patch level are chosen automatically from the detected model. `--out-dir` and `--dll-name` exist as well, but only for the per-model runs that `main.py` starts itself in a multi-model conversion.

The script waits for a key press at the end (so a drag & drop window stays open). Set the environment variable `SXG_NO_PAUSE=1` to skip that, e.g. in batch files.

## Behaviour on reruns

- **Table and DLL output:** an existing table file is skipped. The DLL and ini are rewritten on every run.
- **Wave file:** if it already exists, the run stops before writing it ("already exists, exiting early"). Delete or move the old table and wave file before rebuilding the same model. With `--embed` nothing is written besides the DLL.
