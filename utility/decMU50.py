
from decBase import *

# ? the DOC drum bank contains two drumvoices with no sample length. very weird

@dataclass
class MU50(MUdecoder) : 

    # bankorder_voice : list[Bank] = [Bank.GS, Bank.XG, Bank.SFX]
    bankorder_voice : list[Bank] = field(default_factory=lambda : [Bank.GS, Bank.XG, Bank.SFX])

    @classmethod
    def From_Bytes(cls, table : bytes | bytearray) : 
        return cls(
            source = MU.MU50,
            data = table,
            # 3 tables: GS, XG msb=127, XG msb=126
            drumbank_PRGs = TableData(0x22A5A, 0x22BD9),
            # 23 drum kits  len=5888
            drumkit_keymaps = TableData(0x6F0E6, 0x707E5),
            # 30 byte tables, ext voice bytes @ +16 +17
            drum_voices = TableData(0x6C788, 0x6F0E5),

            # ext drum voices (SFX voices): 87 x 32-bit BE absolute addresses of the voices
            # (location from TaleTN/MUTable, mu50.cpp). Replaces the hand-made dataenum.MU50extVoiceTable,
            # which had two entries wrong (0x0A: SynMalet instead of FootStep, 0x1F: Bird 2 instead of Tweet;
            # used by the TG300B C/M Kit keys 81 / 102 and the TG300B SFX Set keys 57 / 78)
            drumvoice_ext_offsets = TableData(0x3B3CA, 0x3B3CA + 87*4 - 1),

            # 128 x 3 tables
            # order is slightly unusual: GS, XG, SFX
            bankorder_voice = [Bank.GS, Bank.XG, Bank.SFX],
            voice_banks = TableData(0x6C606, 0x6C785),

            # 256 bytes per entry / 71 total voice programs
            # unlike S-YXG50, the PRG seqIDs are all mixed up betwen GS and XG
            # the seqID order is very messy
            # gs 0x2D - 0x44   xg 00 -> 2B  XG SFX ->  2C, 45, 46
            voice_PRGmap = TableData(0x67F06, 0x6C605),

            # * bonus voices at 0x76000, like WhistleLeadd
            # 10 + 80 bytes per element (90 or 170) +1 = element cnt. 
            # seqID on *element* +0 and +1, with the top bit on +0 to match the 8-bit value that's just +0 on S-YXG50
            voices = TableData(0x4F000, 0x67F05),
            # 248 entries, many of them are not addressed by voices
            wavedata_offsets = TableData(0x74F36, 0x75125),
            wavedata = TableData(0x707e6, 0x74F35),

        )


    # * ProcessWaveData, ProcessVoive, ProcessDrumVoice are set up for MU50 already in base class


