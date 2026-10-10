
from decBase import *
import json # hex comments export


def read32(array : bytes | bytearray, idx : int) : 
    return int.from_bytes(array[idx : idx + 4], byteorder = 'little', signed=False)


# * Dynamic - use factory method on an input table file
@dataclass
class SYXG50(MUdecoder) : 

    # * special. There are two voice sections: when PRG map offset last bit, it means start at VoicesB
    SXG50_voice_banks_GS : TableData = TABLEDATA_BLANK
    SXG50_voice_banks_XG : TableData = TABLEDATA_BLANK
    SXG50_VoicesA : TableData = TABLEDATA_BLANK
    SXG50_VoicesB : TableData = TABLEDATA_BLANK
    SXG50_Prgmap_GS : TableData = TABLEDATA_BLANK
    SXG50_Prgmap_XG : TableData = TABLEDATA_BLANK

    # bankorder_voice : list[Bank] = [Bank.GS, Bank.SFX, Bank.XG, Bank.GM2] 
    # bankorder_drums : list[Bank] = [Bank.GS_DRUMS, Bank.XG_DRUMS, Bank.SFX_DRUMS, Bank.GM2_DRUMS]
    bankorder_voice : list[Bank] = field(default_factory=lambda : [Bank.GS, Bank.SFX, Bank.XG, Bank.GM2] )
    bankorder_drums : list[Bank] = field(default_factory=lambda : [Bank.GS_DRUMS, Bank.XG_DRUMS, Bank.SFX_DRUMS, Bank.GM2_DRUMS] )

    @classmethod
    def From_Bytes(cls, table : bytes | bytearray) : 
        HEADER_LEN = 0x64
        # drums: GS / XG MSB=127 / XG MSB=126 / GM2
        _drumbank_PRGs = TableData(HEADER_LEN, HEADER_LEN + read32(table, 0x20) + read32(table, 0x24) +  read32(table, 0x28) + read32(table, 0x2C))
        _drumkit_keymaps = TableData(_drumbank_PRGs.end, _drumbank_PRGs.end + read32(table,0x30))
        _drum_voices = TableData(_drumkit_keymaps.end, _drumkit_keymaps.end + read32(table,0x34))
        # offsets * 1
        _drumvoice_ext_offsets = TableData(_drum_voices.end, _drum_voices.end + read32(table,0x38))

        # voices: GS / XG SFX LSB=0 / XG MSB=0 / GM2
        # they are two distinct sections in S-YXG50, GS has it's own unique seqID range
        _voice_banks = TableData(_drumvoice_ext_offsets.end, _drumvoice_ext_offsets.end + read32(table,0x3C) + read32(table,0x40) + read32(table,0x44) + read32(table,0x48))
        _voice_banks_GS = TableData(_drumvoice_ext_offsets.end, _drumvoice_ext_offsets.end + read32(table,0x3C))
        _voice_banks_XG = TableData(_voice_banks_GS.end, _voice_banks_GS.end + read32(table,0x40) + read32(table,0x44) + read32(table,0x48))
        # offsets * 2
        _voice_PRGmap = TableData(_voice_banks.end, _voice_banks.end + read32(table,0x4C) + read32(table,0x50))
        _voice_PRGmap_GS = TableData(_voice_banks.end, _voice_banks.end + read32(table,0x4C))
        _voice_PRGmap_XG = TableData(_voice_PRGmap_GS.end, _voice_PRGmap_GS.end + read32(table,0x50))

        _voices = TableData(_voice_PRGmap.end, _voice_PRGmap.end + read32(table,0x54) + read32(table,0x58))
        # need both of these, special
        _SXG50_VoicesA = TableData(_voice_PRGmap.end, _voice_PRGmap.end + read32(table,0x54))
        _SXG50_VoicesB = TableData(_SXG50_VoicesA.end, _SXG50_VoicesA.end + read32(table,0x58))
        
        _wavedata_offsets = TableData(_voices.end, _voices.end + read32(table,0x5C))
        _wavedata = TableData(_wavedata_offsets.end, _wavedata_offsets.end + read32(table,0x60))

        obj = cls(
            source = MU.SYXG50,
            data = table,

            drumbank_PRGs = _drumbank_PRGs,
            drumkit_keymaps = _drumkit_keymaps,
            drum_voices = _drum_voices,

            drumvoice_ext_offsets = _drumvoice_ext_offsets,

            voice_banks = _voice_banks,

            voice_PRGmap = _voice_PRGmap,
            SXG50_voice_banks_GS = _voice_banks_GS,
            SXG50_voice_banks_XG = _voice_banks_XG,
            SXG50_Prgmap_GS = _voice_PRGmap_GS,
            SXG50_Prgmap_XG = _voice_PRGmap_XG,
            SXG50_VoicesA = _SXG50_VoicesA,
            SXG50_VoicesB = _SXG50_VoicesB,
                        
            voices = _voices,
            wavedata_offsets = _wavedata_offsets,
            wavedata = _wavedata,

            # * the last bit of the voice offset indicates voice bank B and should be trimmed off 
            # any 16 bit values inside of tables are still big endian
            endian = 'little'

        )
        return obj

    # * ProcessWaveData, ProcessVoive, ProcessDrumVoice are set up for S-YXG50 already in base class

    # debug: auto-generated comments for the rehex hex editor
    def get_rehex_json(self) -> str : 
        # offset, length, text
                #  (self.voice_banks.start, len(self.voice_banks), f"voice_banks   len {len(self.voice_banks)}"),
        parts = [(0, 100, "header"), 
                 (self.drumbank_PRGs.start, len(self.drumbank_PRGs), f"drumbank PRGs   len {len(self.drumbank_PRGs)}"),
                 (self.drumkit_keymaps.start, len(self.drumkit_keymaps), f"drumkit_keymaps   len {len(self.drumkit_keymaps)}"),
                 (self.drum_voices.start, len(self.drum_voices), f"drum_voices   len {len(self.drum_voices)}"),
                 (self.drumvoice_ext_offsets.start, len(self.drumvoice_ext_offsets), f"ext drum voice offsets   len {len(self.drumvoice_ext_offsets)}"),
                 (self.SXG50_voice_banks_GS.start, len(self.SXG50_voice_banks_GS), f"SXG50_voice_banks_GS   len {len(self.SXG50_voice_banks_GS)}"),
                 (self.SXG50_voice_banks_XG.start, len(self.SXG50_voice_banks_XG), f"SXG50_voice_banks_XG   len {len(self.SXG50_voice_banks_XG)}"),
                 (self.SXG50_Prgmap_GS.start, len(self.SXG50_Prgmap_GS), f"SXG50_Prgmap_GS   len {len(self.SXG50_Prgmap_GS)}"),
                 (self.SXG50_Prgmap_XG.start, len(self.SXG50_Prgmap_XG), f"SXG50_Prgmap_XG   len {len(self.SXG50_Prgmap_XG)}"),
                 (self.SXG50_VoicesA.start, len(self.SXG50_VoicesA), f"SXG50_VoicesA   len {len(self.SXG50_VoicesA)}"),
                 (self.SXG50_VoicesB.start, len(self.SXG50_VoicesB), f"SXG50_VoicesB   len {len(self.SXG50_VoicesB)}"),
                 (self.wavedata_offsets.start, len(self.wavedata_offsets), f"wavedata_offsets   len {len(self.wavedata_offsets)}"),
                 (self.wavedata.start, len(self.wavedata), f"wavedata   len {len(self.wavedata)}"),
                 ]
        comments : list = []
        for offset, length, text in parts : 
            comments.append({
                "offset" : offset,
                "length" : length,
                "text" : text,
            })
        return json.dumps({
            "write_protect" : False,
            "comments" : comments
        }, 
        indent=4)
