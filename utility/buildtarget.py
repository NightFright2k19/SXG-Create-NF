# Build target for SXG-Create: always syxg50.dll, the table layout follows the source model.
#
# SYXG50_BIG = False : classic S-YXG50 table (MU50 / MU80 / MU90, "Enhanced" DLL: 24-bit loop length)
# SYXG50_BIG = True  : big S-YXG50 table (MU100 / MU128 / MU1000, "Full" DLL: loop length + table limits)
#   set automatically from the detected model (convert.py). Big layout, compared to the classic one:
#   * voice program maps (GS/XG): 32-bit LE byte offsets from voice bank A (no bank A/B encoding)
#   * wavedata offset table:      32-bit LE byte offsets, up to 512 multisamples (bank B = page 2)
#   * ext drum voice offsets:     32-bit LE byte offsets
#   * wavedata entry:  +0x09..+0x0C sample address, 32-bit BE, in bytes; +0x0D sample format (was +0x0C)
#   * drum voice:      +0x0A root key (was +0x12)
#                      +0x10..+0x11 ext voice index, 16-bit LE (+0x11 == 0xFF -> internal sample)
#                      +0x12..+0x14 start offset 24-bit BE, +0x15..+0x17 loop length 24-bit BE
#                      +0x18..+0x1B sample address 32-bit BE, in bytes (30 bits),
#                      the top two bits are the sample format (0x80 = 8 bit)
#   * sample data:     S-YXG50 formats (unsigned 16 bit / 8 bit), as in the classic layout
SYXG50_BIG : bool = False

# --embed: table and wave file are embedded in the patched DLL (RT_RCDATA, see dllpatch.embed_files)
# instead of being written as files; the DLL is renamed syxg<n>.dll if it was supplied as syxg50.dll.
EMBED : bool = False

# file name of the patched DLL (multi-model conversion: syxg80.dll ... syxg1000.dll), None: keep the supplied name
DLL_NAME : str | None = None
