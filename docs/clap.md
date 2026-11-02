# CLAP plugins (bridge)

Issue #97. The plugins are 32-bit Windows VST2 DLLs, so a native CLAP is not possible (no source, only the patched `syxg50.dll`). The CLAP versions are **bridges**: a small 64-bit CLAP file that runs the DLL in a 32-bit helper process. Only the Windows patcher writes them for now; native bridges for Linux (through Wine) and macOS are a later step.

## What the patcher writes (Windows)

```
Plugins\VST2\syxgmu50.dll ... syxg1000.dll, syxg2006le.dll     the plugins, as before
Plugins\CLAP\syxgmu50.clap ... syxg1000.clap, syxg2006le.clap  one bridge per plugin
Plugins\CLAP\sxgbridge32.exe                                    the 32-bit helper, shared; keep it next to the CLAP files
```

Copy the `.clap` files **and** `sxgbridge32.exe` to a CLAP folder of your host (e.g. `C:\Program Files\Common Files\CLAP`), and the DLLs to where the host (or the bridge) finds them: the bridge looks for `<name>.dll` in `..\VST2\` (the layout above), then next to the CLAP, then one folder up. So either keep `Plugins` as it is and point the host to `Plugins\CLAP`, or copy `VST2` next to the CLAP folder. The patcher on Linux and macOS is unchanged (DLLs in `Plugins`).

## How it works

- `clapbridge/clap_bridge.c` is the same file under every plugin's name; the plugin is taken from the file name (`syxg1000.clap` -> `syxg1000.dll`, shown as "S-YXG MU1000").
- Per plugin instance, one `sxgbridge32.exe` (`clapbridge/host32.c`) is started with the DLL. Audio, MIDI and commands go through one shared-memory block and four events (`clapbridge/protocol.h`). One round trip per audio block, no copies beyond the block itself. A helper that ends or hangs for more than one second makes the instance silent instead of blocking the host; the helper ends with the host (job object).
- **MIDI:** note port with MIDI dialect: notes, controllers, program changes, pitch bend and SysEx (XG / GS reset, parameter changes) with sample-accurate offsets. Reset sends All Notes Off and Reset All Controllers.
- **Editor:** the plugin's own panel (win32, embedded in the host's window; the panel has a fixed size). The Setup page of the DLL works as usual.
- **State:** the plugin's own chunk (what a VST2 host saves) is stored in the CLAP state.
- **Not done:** CLAP parameters (the plugins have none worth automating except the S-YXG2006LE's; they stay in the plugin's own panel / MIDI), voice info, latency reporting.
- Block sizes above 8192 samples are processed in pieces. Sample rate is passed on at activation.

## Building (development)

`make -C clapbridge` with mingw-w64 (`gcc-mingw-w64`): `sxgbridge.clap` (x86_64) and `sxgbridge32.exe` (i686). The Autobuild workflow does this in the `bridge` job and bundles both files with the Windows patcher (`bridge` folder inside it); `utility/clapbridge.py` copies them. `python utility/clapbridge.py <VST2 folder> <CLAP folder>` writes the CLAP files for a folder of DLLs from a checkout.

## Tests (Wine)

`clapbridge/test/`: `fakevst.c` is a 32-bit test instrument (note, sample offset, SysEx, chunk, editor), `testhost.c` a minimal 64-bit CLAP host. Build both with mingw-w64 and run `wine64 testhost.exe <path>\fake.clap` (plugin `fake.dll` in `..\VST2`; with a real converted plugin add a second argument `real`). The test covers loading, activation, sample-accurate notes, pitch, SysEx, state round trip, editor embedding and shutdown. Checked with a converted MU50 under Wine: it plays, saves state and shows its 400 x 114 panel inside the host window. Not tested with a real Windows CLAP host yet.
