# Panel, Setup page, polyphony and voice maps

Full description of the plugin GUI. The README has the short version.

## Setup page

The **Setup** button of the panel opens the Settings page (all models):

![Settings page, MU50 and MU100](../utility/dev/gui/settings_page_mu50_mu100.png)

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
- **Monitor panel:** the S-YXG50 also has a monitor panel with part levels, polyphony and load readouts. It replaces the normal panel when `DebugPanel=1` is set in the ini (see [The ini](dll-patching.md#the-ini)).

## Polyphony up to 256

The S-YXG50 engine has 128 voices (one voice per element, so a 2-element voice takes two). With **Polyphony** above 128 on the Setup page (the default is 256), the DLL runs a second engine for the voices above 128, much like Nuked-SC55-P256. As long as a song needs no more than 128 voices, the second engine sleeps and the output is bit-identical to a single engine:

- The second engine is made inside the DLL when the plugin starts (the host still sees one plugin) and gets every MIDI event, SysEx and reset, so it always has the song's state. Tables and wave data are shared, it only costs its own engine memory.
- A Note On goes to the first engine while it has two voices free, else to the second (up to *Polyphony* - 128 voices), else to the first, which then steals a voice as before. Note Offs, controllers, program changes, pitch bend and SysEx go to both. The outputs are added.
- The second engine renders only while it has notes, plus 4 s for release and effect tails, and for 250 ms after a SysEx (a reset only takes full effect while the engine renders). Asleep it costs next to nothing; it takes its events directly and picks up the first engine's control-rate clock when it wakes, so its notes sound like the first engine's (measured: a note on the second engine is bit-identical to the same note on the first).
- The POLYPHONY readout in the panel shows the voices of both engines (up to 256).
- Effect switches and Output Level follow the first engine. Effects are linear, so two reverbs over two halves of the notes add up to one reverb over all of them.
- Limits: exclusive groups (e.g. open / closed hi-hat) and mono parts only act within one engine; after a voice map switch the second engine takes the new map with the next program change; the setting above 128 is shared by all instances of the same DLL in one host process.

## Ports B-D (`F5 nn`)

The original S-YXG50 drivers addressed 4 ports of 16 channels with the port select message `F5 nn` (nn = 1-4, Yamaha "cable select"). The VST plugins used to lose every message after `F5 02` (issue #74); since r49 `F5` is ignored, and the experimental multi-port build (branch `multiport`) plays real ports:

- `F5 01` ... `F5 04` select port A-D for all following channel messages. The first `F5 02` / `03` / `04` creates one more complete engine for that port (128 voices, about 1.3 MB), made the same way as the second engine of the polyphony patch, so an unused port costs nothing. The Polyphony setting applies to port A only (with its second engine).
- Port B-D engines take the settings of the plugin (effects, output level) and add their sound to the plugin's stereo output. Their reverb and chorus are separate from port A's (the original shares them).
- System messages and SysEx (resets, setup) go to all ports. A GM / GM2 / XG / GS reset selects port A again; a new port engine is first given the last reset the plugin saw. `F5` with a number outside 1-4 is ignored.
- Not done yet: XG parts above 16 / GS block B by SysEx address (they act on port A), a port selector in the panel, voices of ports B-D in the POLYPHONY readout. Hosts with only 16 channels never send `F5`, so nothing changes for them.
- Like the second engine, the port engines exist only in the first four instances of a DLL copy.

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

![Panel with the control row CHN / PRG / MSB / LSB](../utility/dev/gui/panel_preset.png)

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
