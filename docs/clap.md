# CLAP plugins (bridge)

Issue #97. The plugins are 32-bit Windows VST2 DLLs, so a native CLAP is not possible (no source, only the patched `syxg50.dll`). The CLAP versions are **bridges**: a small CLAP file that runs the DLL in a 32-bit helper process. The Windows and Linux patchers write them (on Linux the helper runs under Wine); each patcher writes only the CLAP of its own system. macOS has none yet (an Intel/Rosetta Wine bridge would need its own window handling).

## What the patcher writes (Windows and Linux)

```
Plugins/VST2/syxgmu50.dll ... syxg1000.dll, syxg2006le.dll     the plugins, as before
Plugins/CLAP/syxgmu50.clap ... syxg1000.clap, syxg2006le.clap  one bridge per plugin
Plugins/CLAP/sxgbridge32.exe                                   the 32-bit helper, shared; keep it next to the CLAP files
```

Copy the `.clap` files **and** `sxgbridge32.exe` to a CLAP folder of your host (Windows: `C:\Program Files\Common Files\CLAP`; Linux: `~/.clap`), and the DLLs to where the bridge finds them: `<name>.dll` in `../VST2/` (the layout above), then next to the CLAP, then one folder up. So either keep `Plugins` as it is and point the host to `Plugins/CLAP`, or copy `VST2` next to the CLAP folder. The macOS patcher is unchanged (DLLs in `Plugins`).

**Linux needs Wine** (any recent version that runs 32-bit programs, e.g. Wine 9): `wine` in the path, or `SXG_WINE=/path/to/wine`; the Wine prefix is the usual one (`WINEPREFIX`, default `~/.wine`). `SXG_DEBUG=1` leaves Wine's output visible when the plugin does not load.

## Troubleshooting

- **The host does not load the CLAP:** the reason is written to `sxgbridge.log` in the temp folder (`%TEMP%` on Windows, `$TMPDIR` or `/tmp` elsewhere), often the only place a host does not show. Typical causes: `sxgbridge32.exe` is not in the same folder as the `.clap`, the DLL is not found (see the search order above), or (Linux / macOS) Wine is missing.
- **Where hosts look for CLAP files:** each host has its own folders. Woof! (Windows) scans only a `plugins` folder next to `Woof.exe` or in its preferences folder, and loads the first suitable `.clap` it finds. Put the `.clap`, `sxgbridge32.exe` and the DLL into that `plugins` folder (the DLL may also be one folder up or in a `VST2` folder next to `plugins`); remove the CLAP files of models you do not want, so that the right one is used.

## How it works

- `clapbridge/clap_bridge.c` (Windows) and `clap_bridge_linux.c` (Linux) are the same file under every plugin's name; the plugin is taken from the file name (`syxg1000.clap` -> `syxg1000.dll`, shown as "S-YXG MU1000"). What both share (MIDI, audio, ports, state, factory) is `clap_common.h`.
- Per plugin instance, one `sxgbridge32.exe` (`clapbridge/host32.c`) is started with the DLL. Audio, MIDI and commands go through one shared-memory block (`clapbridge/protocol.h`); one round trip per audio block. A helper that ends or hangs for more than one second makes the instance silent instead of blocking the host; the helper ends with the host (Windows: job object; Linux: the helper stops when its connection closes).
  - Windows: named events and a named file mapping.
  - Linux: the shared memory is a file in `/dev/shm` that Wine maps too (Wine sees `/` as drive `Z:`), the signals travel over two loopback TCP connections (control, audio) with a random token.
- **MIDI:** note port with MIDI dialect: notes, controllers, program changes, pitch bend and SysEx (XG / GS reset, parameter changes) with sample-accurate offsets. Reset sends All Notes Off and Reset All Controllers.
- **Editor:** the plugin's own panel (the panel has a fixed size). Windows: a child window in the host's window (win32). Linux: the helper opens the panel in a window of its own, the CLAP finds it (by its title) and moves it into the host's X11 window with `XReparentWindow`; a timer (CLAP timer support, 100 ms) tells Wine where the window is on the screen, so mouse clicks hit when the host window moves. X11 hosts only (no Wayland-native embedding).
- **State:** the plugin's own chunk (what a VST2 host saves) is stored in the CLAP state.
- **Not done:** CLAP parameters (the plugins have none worth automating except the S-YXG2006LE's; they stay in the plugin's own panel / MIDI), voice info, latency reporting, keyboard focus handling in the Linux editor.
- Block sizes above 8192 samples are processed in pieces. Sample rate is passed on at activation. S-YXG50 only plays correctly at 11025, 22050, 44100, 48000 and 96000 Hz (at any other rate it renders at about 44100 Hz, so the pitch is wrong: 32000 Hz sounds about 28 % too low). For every other host rate (e.g. 32000 Hz in Woof!) the helper therefore runs the plugin at 44100 Hz and resamples its output to the host rate (cubic interpolation); MIDI event positions are converted accordingly. The 2 to 3 samples of look-ahead of the interpolation are the only latency added.

## Building (development)

- Windows files: `make -C clapbridge` with mingw-w64 (`gcc-mingw-w64`): `sxgbridge.clap` (x86_64) and `sxgbridge32.exe` (i686, the helper for both systems).
- Linux CLAP: `make -C clapbridge linux` (gcc, `libxcb-dev`): `sxgbridge-linux.clap`.
- The Autobuild workflow builds the Windows files in the `bridge` job (ubuntu, mingw-w64) and the Linux CLAP in the Linux patcher's own build job (ubuntu-22.04, for an old glibc); the Windows patcher bundles `sxgbridge.clap` + the helper, the Linux patcher `sxgbridge-linux.clap` + the helper (folder `bridge` inside the patcher). `utility/clapbridge.py` copies them. `python utility/clapbridge.py <VST2 folder> <CLAP folder>` writes the CLAP files for a folder of DLLs from a checkout.

## Tests (Wine)

`clapbridge/test/`: `fakevst.c` is a 32-bit test instrument (note, sample offset, SysEx, chunk, editor), `testhost.c` a minimal 64-bit Windows CLAP host, `testhost_linux.c` a minimal Linux (X11) CLAP host. Build with mingw-w64 / gcc and run
- Windows bridge under Wine: `wine64 testhost.exe <path>\fake.clap` (plugin `fake.dll` in `..\VST2`, helper next to the CLAP);
- Linux bridge: `DISPLAY=:99 ./testhost_linux <path>/fake.clap` (Xvfb is enough; `SHOT=file.png` saves a screenshot of the screen).

With a real converted plugin add a second argument `real`. The tests cover loading, activation, sample-accurate notes, pitch, SysEx, state round trip, editor embedding and shutdown. Checked with a converted MU50 under Wine: it plays (same output on both bridges), saves state and shows its 400 x 114 panel inside the host window. Not tested with a real CLAP host on Windows or Linux yet, nor Linux with a window manager that decorates or composites, nor Wayland (XWayland hosts should work).
