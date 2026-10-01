# SXG-Create
MU in S-YXG50. Table Creation and AWM2 Data Table Investigation

# Installation & Usage
Requirements: Python 3.12 or newer

Basic usage: Drag & Drop your roms onto **main.py**

The easiest way to make use of the tables is with Veg's VST2 engine. 
Make sure the table & wave files are in the same folder as the dll and specify the table's name in the included ini. Embedded tables may have to be removed first, which can be done with ResourceExtractor

Everything is moving very quickly right now with XG preservation so keep an eye out for alternative engines!

# Compatibility

| model   | support | waves | Sample Formats   | XG Voices | XG Kits | GS Voices  | FX Passes |
|---------|---------|-------|------------------|-----------|---------|------------|-----------|
| S-YXG50 | --      | 4.1MB | U16 / U8         | 480       | 11      | 579        | 3         |
| MU50    | Yes     | 4MB   | S12/ADPCM/S8     | 480       | 11      | 579        | 3         |
| MU80    | Yes     | 8MB   | S16 / ADPCM      | 537       | 11      | 614        | 5         |
| MU90    | WIP     | 8MB   | S16/S12/ADPCM/S8 | 586       | 20      | 614        | 5         |

MU50 and MU80 are the most similar models to S-YXG50 and will work best

MU90 (**WIP** - currently not working): Believe or not it will fit inside S-YXG50, but there will be some loss to the conversion because of the larger data tables (+12 bytes for drums, 1 additional mysterious byte for voice wavedata)


# Limitations:

Tables run within S-YXG50 are going to be limited to the S-YXG50 engine's capabilities: 3 effects passes with 11/11/43 chorus/reverb/variation effects, no A/D input. This is analogous to the MU50, but a bit less capable than what the MU80 can do.

MU50: The 'DOC' voice bank & drum kit are not preserved. It may be possible to remap them somewhere, but some of the DOC kit's drum voices appear to be missing crucial data for some reason, so it might take some reconstruction.

MU80: A few of the synth pads are simply too long to fit in the S-YXG50's 16-bit loop offset. For now they are clamped, and there may be a slight click when they loop.

MU80: The demo song ("Out Of The Muse") does not sound right, probably due to the missing effects.


# 

DPCM delta table, DPCM limits table, and delta format decoding code based on Mame, copyright (c) MAME contributors, and related contributions by TaleTN, tarboh, and hockinsk under BSD-3 license

license:BSD-3-Clause

copyright-holders:Olivier Galibert
