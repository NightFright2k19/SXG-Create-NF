# Version history

What changed in each Autobuild release, newest first. Releases are numbered `r<N>` and can be downloaded from the [Releases](https://github.com/NightFright2k19/SXG-Create-NF/releases) page; the number in the patcher's file name tells you which one you have. Numbers in brackets are issues / pull requests. The full list of features is in [Changes compared to the original SXG-Create](changes.md).

Releases before r14 were not kept. Releases that only touched the build or the documentation say so.

| Release | Date | Changes |
|---|---|---|
| r58 | 2026-10-31 | MU100: the same two fixes as for MU1000: the 12 further MSB 48 banks (LSB 8-120, e.g. 48/8 Ping) now play (#89), and the wave fine tune is converted, so 25 waves play in tune, e.g. Flute # above C#5 was up to 33 cents off (#90). |
| r57 | 2026-10-31 | MU128 / MU1000: the MSB 48 banks with an LSB (48/8 Ping, 48/16 CheapOsc, 48/48 RandmRun and so on, 12 more banks) now play; before, every LSB played bank 48/0 and most presets were silent (#89). The MU1000 wave file grows by 2.7 MB. |
| r56 | 2026-10-31 | MU1000 / MU128: the fine tune of waves (wavedata byte `+8`, 1/1024 octave) is now converted, so the 71 waves that use it play in tune; e.g. Flute # above F5 was up to 31 cents off, Native voices only (#90). |
| r55 | 2026-10-30 | Ports A-D: the port select command `F5 nn` plays up to four ports of 16 channels (own engine per port, SysEx routing incl. GS modes, port selector in the panel); the plugins are called `S-YXGM<n>` internally (#74). |
| r54 | 2026-10-28 | Patcher: the update check no longer fails with "certificate verify failed" when the system lacks a GitHub root certificate; the Mozilla certificates (certifi) are used as well (#84). |
| r54 | 2026-10-28 | GS mode: PRG digits turn red for bank MSB 126 with a program from 65 up, which has no voice (#73). |
| r54 | 2026-10-28 | Patcher: link "What's new?" at the bottom of the window; version history added. |
| r50 | 2026-10-21 | Build only: workflow cleanup, no change to the patcher or the plugins. |
| r49 | 2026-10-21 | The port select command `F5 nn` is now ignored instead of switching the instance's channels (#74). |
| r48 | 2026-10-21 | PRG digits turn red when a channel has no valid instrument (#73). |
| r47 | 2026-10-21 | The patcher updates itself from the newest release (#72). |
| r46 | 2026-10-21 | Drum parts: the digits follow the engine's own drum flag instead of the bank (#70). |
| r45 | 2026-10-20 | PRG control on drum parts steps to the next kit the engine takes; the digits are dimmed (#70). |
| r44 | 2026-10-20 | Fixed GM2 drum program changes on MU128 / MU1000 (#71). |
| r43 | 2026-10-20 | S-YXG2006LE: answers the host's name queries. |
| r42 | 2026-10-20 | The alternate Modern skin was removed again (#69). |
| r41 | 2026-10-19 | S-YXG2006LE gets an editor with panel, Setup page, meters and control row (#39). |
| r40 | 2026-10-19 | New patcher icon. |
| r39 | 2026-10-18 | Patcher: the model list has a new order (#67). |
| r38 | 2026-10-18 | The MU Tone Map setting is kept when the plugin starts playing (#65, #66). |
| r37 | 2026-10-18 | Modern skin: meter floor dash and glass strips on the displays (#64). |
| r36 | 2026-10-18 | MU2000 support: `syxg2000.dll` (S-YXG2000) (#53, #62). |
| r35 | 2026-10-18 | The skin switch writes only an ini that already exists (#63). |
| r34 | 2026-10-18 | Fixed plugins crashing when the DLL is loaded at another address (#61). |
| r33 | 2026-10-18 | Modern panel skin, switched with a click on the YAMAHA logo (#52, #60). |
| r32 | 2026-10-18 | The S-YXG2006LE DLL patched by SGP2VSTi 1.0.2.22 is accepted (#54, #59). |
| r31 | 2026-10-18 | Panel controls work per instance, so several instances in one host no longer interfere (#55, #57). |
| r30 | 2026-10-18 | Build only: the newest release is marked as Latest. |
| r29 | 2026-10-18 | Build only: older releases are kept; project rules added. |
| r28 | 2026-10-16 | Several models are converted in parallel on multi-core CPUs (#50). |
| r27 | 2026-10-16 | The patcher builds plugins from ready-patched templates, `syxg50.dll` is no longer needed (#40, #49). |
| r26 | 2026-10-16 | Polyphony 256 is safe when a host processes instances in parallel threads (#48). |
| r25 | 2026-10-16 | The preview note goes to engine A only, so it no longer sticks in the polyphony count (#46, #47). |
| r24 | 2026-10-16 | Preview note: hold the left mouse button in the POLYPHONY field to hear the selected channel (#43, #44). |
| r23 | 2026-10-15 | Panel redesign: 400 x 114 with a control row CHN / PRG / MSB / LSB and the model name as a picture (#42). |
| r22 | 2026-10-15 | MT-32 reset button (#41). |
| r21 | 2026-10-14 | Send Reset: one-shot GM / GS / XG / GM2 buttons replace the Reset Mode; host resets always pass (#37). |
| r20 | 2026-10-14 | ini: the plugin uses its own section and `VoiceTable` like the original S-YXG50 (#36). |
| r19 | 2026-10-14 | Documentation only: S-YXG2006LE instructions. |
| r18 | 2026-10-14 | S-YXG2006LE: parameters in S-YXG50 order, Polyphony 256 with 8 engines, patcher support (#12). |
| r17 | 2026-10-14 | Panel: channel select and bank select MSB / LSB next to the program control (#35). |
| r16 | 2026-10-13 | Patcher: 29 languages, sorted alphabetically. |
| r15 | 2026-10-13 | GM2 banks (MSB 120 / 121) for models without GM2 voices of their own (#34). |
| r14 | 2026-10-13 | First release that was kept. |
