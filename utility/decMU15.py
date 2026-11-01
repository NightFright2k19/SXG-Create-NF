from decBase import *
from decMU50 import MU50

# * Yamaha MU15 (xv684c0 v1.01, 1998-11-28): one 4 MB ROM, the firmware (byte swapped, the first 448,252 bytes)
#   followed by the wave data. The data formats are those of the MU50 (MU50 voices, 30-byte drum voices,
#   16-byte samples), the tables lie elsewhere (layout from TaleTN/MUTable, mu15.cpp). Decoded as an MU50:
#   the decoder works on a copy of the firmware with the tables of the MU50 order appended.
FW_SIZE = 448252
VOICES, PRGMAP, BANKLISTS, SFXOFFS, TG300B = 247086, 342796, 360716, 360972, 361320
DRUMVOICES, KITS, DRUMBANKS = 361448, 370868, 376588
SAMPLES, SAMPLESETS = 228338, 246594
N_KITS, N_EXT = 22, 87      # drum kits, SFX voices (ext voices of the drum voices)

def MU15_Split(rom : bytes) -> tuple[bytes, bytes] :
    # -> (firmware, wave data)
    from utils import Dejumble
    return Dejumble(rom[:FW_SIZE]), rom[FW_SIZE:]

@dataclass
class MU15(MU50) :
    @classmethod
    def From_Bytes(cls, fw : bytes | bytearray) :
        data = bytearray(fw)
        row = lambda a, r : bytes(data[a + 128*r : a + 128*(r+1)])
        # tables the MU50 decoder reads in one piece, in its order: drum banks, voice banks (TG300B / GS, XG, SFX)
        drum_start = len(data)
        data += row(DRUMBANKS, 2) + row(DRUMBANKS, 0) + row(DRUMBANKS, 1)
        drum_end = len(data)
        banks_start = len(data)
        data += row(TG300B, 0) + row(BANKLISTS, 1) + row(BANKLISTS, 0)
        banks_end = len(data)
        # SFX voices of the drum kits: 16-bit word offsets from the voices in the ROM, written as the 32-bit absolute
        # addresses the MU50 decoder reads
        ext_start = len(data)
        for i in range(N_EXT) :
            data += (VOICES + 2 * int.from_bytes(fw[SFXOFFS + 4*i : SFXOFFS + 4*i + 4], 'big')).to_bytes(4, 'big')
        ext_end = len(data)
        # 6 keys of the XG SFX kits point to SFX voices 87-92, beyond the table, with no sample: left out (silent)
        dropped = 0
        for k in range(N_KITS) :
            for n in range(128) :
                a = KITS + 256*k + 2*n
                off = int.from_bytes(data[a : a + 2], 'big')
                if off == 0xFFFF : continue
                ext = int.from_bytes(data[DRUMVOICES + off + 16 : DRUMVOICES + off + 18], 'big')
                if N_EXT <= ext < 0xFFFF : data[a : a + 2] = b'\xff\xff'; dropped += 1
        if dropped : print(f'MU15: {dropped} drum keys without sample data left out')
        return cls(
            source = MU.MU50, data = data,
            drumbank_PRGs = TableData(drum_start, drum_end - 1),
            drumkit_keymaps = TableData(KITS, KITS + N_KITS*256 - 1),
            drum_voices = TableData(DRUMVOICES, KITS - 1),
            drumvoice_ext_offsets = TableData(ext_start, ext_end - 1),
            bankorder_voice = [Bank.GS, Bank.XG, Bank.SFX],
            voice_banks = TableData(banks_start, banks_end - 1),
            voice_PRGmap = TableData(PRGMAP, BANKLISTS - 1),
            voices = TableData(VOICES, PRGMAP - 1),
            wavedata_offsets = TableData(SAMPLESETS, VOICES - 1),
            wavedata = TableData(SAMPLES, SAMPLESETS - 1),
        )
