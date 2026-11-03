# CLAP plugins (bridge)

Issue #97. The plugins are 32-bit Windows VST2 DLLs, so a native CLAP is not possible (no source, only the patched `syxg50.dll`). The CLAP versions are **bridges**: a small CLAP file that runs the DLL in a 32-bit helper process. All three patchers write them (on Linux and macOS the helper runs under Wine); each patcher writes only the CLAP of its own system.

## What the patcher writes

```
Plugins/VST2/syxgmu50.dll ... syxg1000.dll, syxg2006le.dll     the plugins, as before
Plugins/CLAP/syxgmu50.clap ... syxg1000.clap, syxg2006le.clap  one bridge per plugin
Plugins/CLAP/sxgbridge32.exe                                   the 32-bit helper, shared; keep it next to the CLAP files
```

Copy the `.clap` files **and** `sxgbridge32.exe` to a CLAP folder of your host (Windows: `C:\Program Files\Common Files\CLAP`; Linux: `~/.clap`; macOS: `~/Library/Audio/Plug-Ins/CLAP`), and the DLLs to where the bridge finds them: `<name>.dll` in `../VST2/` (the layout above), then next to the CLAP, then one folder up. So either keep `Plugins` as it is and point the host to `Plugins/CLAP`, or copy `VST2` next to the CLAP folder.

**Linux and macOS need Wine** (any recent version that runs 32-bit programs, e.g. Wine 9): `wine` in the path, or `SXG_WINE=/path/to/wine`; the Wine prefix is the usual one (`WINEPREFIX`, default `~/.wine`). `SXG_DEBUG=1` leaves Wine's output visible when the plugin does not load. On macOS the CLAP also looks in the usual install folders (Homebrew `/opt/homebrew/bin`, `/usr/local/bin`, `/Applications/Wine *.app`, CrossOver), because a host's PATH is short; Wine for macOS is an x86-64 program, so Apple Silicon needs Rosetta 2 for it (the CLAP itself is universal). Start Wine once by hand first so that its prefix exists.

## Troubleshooting

- **The host does not load the CLAP:** the reason is written to `sxgbridge.log` in the temp folder (`%TEMP%` on Windows, `$TMPDIR` or `/tmp` elsewhere), often the only place a host does not show. Typical causes: `sxgbridge32.exe` is not in the same folder as the `.clap`, the DLL is not found (see the search order above), or (Linux / macOS) Wine is missing.
- **Where hosts look for CLAP files:** each host has its own folders. Woof! (Windows) scans only a `plugins` folder next to `Woof.exe` or in its preferences folder, and loads the first suitable `.clap` it finds. Put the `.clap`, `sxgbridge32.exe` and the DLL into that `plugins` folder (the DLL may also be one folder up or in a `VST2` folder next to `plugins`); remove the CLAP files of models you do not want, so that the right one is used.

## How it works

- `clapbridge/clap_bridge.c` (Windows) and `clap_bridge_posix.c` (Linux) are the same file under every plugin's name; the plugin is taken from the file name (`syxg1000.clap` -> `syxg1000.dll`, shown as "S-YXG MU1000"). What both share (MIDI, audio, ports, state, factory) is `clap_common.h`.
- Per plugin instance, one `sxgbridge32.exe` (`clapbridge/host32.c`) is started with the DLL. Audio, MIDI and commands go through one shared-memory block (`clapbridge/protocol.h`); one round trip per audio block. A helper that ends or hangs for more than one second makes the instance silent instead of blocking the host; the helper ends with the host (Windows: job object; Linux: the helper stops when its connection closes).
  - Windows: named events and a named file mapping.
  - Linux and macOS: the shared memory is a file (`/dev/shm`; macOS: the temp folder) that Wine maps too (Wine sees `/` as drive `Z:`), the signals travel over two loopback TCP connections (control, audio) with a random token.
- **MIDI:** note port with MIDI dialect: notes, controllers, program changes, pitch bend and SysEx (XG / GS reset, parameter changes) with sample-accurate offsets. Reset sends All Notes Off and Reset All Controllers.
- **Editor:** the plugin's own panel (the panel has a fixed size). Windows: a child window in the host's window (win32). Linux: the helper opens the panel in a window of its own, the CLAP finds it (by its title) and moves it into the host's X11 window with `XReparentWindow`; a timer (CLAP timer support, 100 ms) tells Wine where the window is on the screen, so mouse clicks hit when the host window moves. X11 hosts only (no Wayland-native embedding).
  macOS: a window of another process cannot be embedded in a host's window, so the panel is a **floating** GUI (CLAP floating window): the host's editor button opens the plugin's own window (with a title bar, always on top), closing it hides it and tells the host. Hosts without floating-GUI support cannot show the panel.
- **macOS bundle:** each CLAP is a bundle `syxg1000.clap/Contents/{Info.plist, MacOS/syxg1000}` made by the patcher from the universal (arm64 + x86-64) binary and signed ad hoc with `codesign`, which Apple Silicon requires. The helper `sxgbridge32.exe` stays next to the bundles.
- **State:** the plugin's own chunk (what a VST2 host saves) is stored in the CLAP state.
- **Not done:** CLAP parameters (the plugins have none worth automating except the S-YXG2006LE's; they stay in the plugin's own panel / MIDI), voice info, latency reporting, keyboard focus handling in the Linux editor.
- Block sizes above 8192 samples are processed in pieces. Sample rate is passed on at activation.

## Building (development)

- Windows files: `make -C clapbridge` with mingw-w64 (`gcc-mingw-w64`): `sxgbridge.clap` (x86_64) and `sxgbridge32.exe` (i686, the helper for both systems).
- Linux CLAP: `make -C clapbridge linux` (gcc, `libxcb-dev`): `sxgbridge-linux.clap`. macOS CLAP: `make -C clapbridge macos` (clang on a Mac): universal `sxgbridge-macos`. In the frozen macOS patcher this file is bundled gzipped (`sxgbridge-macos.gz`): PyInstaller would otherwise thin a bare Mach-O data file to the architecture of the build machine, and the patcher's self-test (and the bundle it writes) would see a single-architecture bridge. `bridge-check.yml` freezes a small test program to catch this.
- The Autobuild workflow builds the Windows files in the `bridge` job (ubuntu, mingw-w64) the Linux CLAP in the Linux patcher's own build job (ubuntu-22.04, for an old glibc) and the macOS CLAP in the macOS patchers' jobs; every patcher bundles its system's CLAP + the helper (folder `bridge` inside the patcher). `utility/clapbridge.py` copies them. `python utility/clapbridge.py <VST2 folder> <CLAP folder>` writes the CLAP files for a folder of DLLs from a checkout. The workflow `bridge-check.yml` builds and tests the bridges on pull requests that touch `clapbridge/`.

## Tests (Wine)

`clapbridge/test/`: `fakevst.c` is a 32-bit test instrument (note, sample offset, SysEx, chunk, editor), `testhost.c` a minimal 64-bit Windows CLAP host, `testhost_posix.c` a minimal Linux / macOS CLAP host. `bash clapbridge/test/run_tests.sh` builds everything (gcc, mingw-w64, libxcb-dev, Wine, Xvfb) and runs
- the Windows bridge under Wine (embedded editor),
- the Linux bridge (editor reparented into an X11 window),
- the macOS source compiled on Linux (`-D__APPLE__`, stub header): same transport, floating editor (Wine's window must exist with the plugin's name, hide / show again, embedding refused).

With a real converted plugin run a testhost with a second argument `real` (no sample checks). The tests cover loading, activation, sample-accurate notes, pitch, SysEx, state round trip, editor and shutdown. Checked with a converted MU50 under Wine: it plays (same output on all bridges), saves state and shows its 400 x 114 panel (embedded, or floating). On macOS only the CI can check the build: `bridge-check.yml` builds the universal binary, makes a bundle like the patcher, verifies its signature and loads it (entry, factory, descriptor). **Not tested on real hardware:** macOS with Wine (shared file mapping, floating window, Rosetta), and any real CLAP host on Linux or macOS; a window manager that decorates or composites; Wayland (XWayland hosts should work).
