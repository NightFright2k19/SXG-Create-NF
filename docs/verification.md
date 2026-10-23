# Verification against the S-MU2000 and the S-YXG50

## Method

- **Reference:** the **S-MU2000** (Yamaha's software MU2000, same firmware and sound data as the MU2000/MU1000) as a VST, and recordings of a real **MU1000**. Dedicated test MIDI files were played on both and on syxg50.dll with the converted tables (drum kits and levels, drum EGs, drum HPF and velocity, element HPF, voices with 3/4 elements, all effect types).
- **syxg50.dll** was run in an x86 emulator (Unicorn) so that every measurement could be repeated with modified tables or DLL patches, and so that internal DLL behaviour (EG rates and levels, pan law, key-on delays, effect routines) could be measured directly.
- Levels were compared per note (RMS in fixed windows, after aligning the recordings), plus spectral shape for filters and pitch for tuning.

## Results

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

## Cross-checks between models

- **MU50 against the S-YXG50's own table** (`SXGBIN41.TBL`, Yamaha's port of the MU50 sound set): the converted voice and drum parameters are identical for all 438 XG voices and 303 drum keys. The wave tuning matches within 1-2 cents (the S-YXG50 table writes some fine tunes from the next note down, e.g. note 50 / +52 cents instead of note 49 / +209, measured as the same pitch in the DLL). Rendered in the DLL, 80 % of 1,313 notes are within 0.1 dB of the original S-YXG50, and 3 are more than 3 dB apart.
- **MU80:** its voices are revoiced against the MU50 (scattered differences, no systematic offset), so the S-YXG50 table is no reference there.
- **MU90 / MU100 / MU128 / MU1000:** all XG voices were rendered (keys 36/60/84) and compared where two models share a voice (same bank, program and name): MU128 vs MU1000 1,014 voices, MU100 vs MU128 939, MU90 vs MU100 505. The converted voice data of MU128 and MU1000 is identical for all shared voices; MU100 differs in 4 (Whistle, Ocarina, DrawOrg2, Dim&Cool: different ROM data). After the MU100 element HPF fix, every remaining level difference above 2 dB was traced to identical data played after a different preceding voice (LFO phase), not to the conversion. No clipping voices; the only silent one (Lite Org) led to the rising decay 2 fix.
- **Builds:** the multi-model run with `--embed` (MU90, MU100, MU128, MU1000 from the `source` folder) and the MU50, MU80 and MU90B sets convert without errors. Rebuilds after each change were compared byte by byte against the previous build, so that only the intended bytes changed.
