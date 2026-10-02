from decBase import *
from decMU90 import MU90, MU90_Waverom, Make_Reversed

# * Yamaha MU1000 (program v2.01, h/l flash pair) and MU128 (v2.00), 2026-10-01
#
# MU1000 / MU2000 use the MU128 engine data formats:
# - voice: 14-byte header (+0 element mask 1/3/7/15, +1 volume, +2..+11 name (10 chars),
#   +12/+13 unused here) followed by 84-byte elements (up to 4)
# - element: +0/+1 wave number (like MU90), then the S-YXG50 element layout almost 1:1:
#       S-YXG50 +1..+4  = +2..+5,  +5 = +7 | 0x80 if +6 (LFO phase init),  +6..+77 = +8..+79
#   (verified on 2,317 elements of voices shared with the MU100: all 77 bytes match)
#   +80..+83 are new MU128 parameters without an S-YXG50 equivalent.
# - drum voice: 42 bytes, MU90 layout except byte 0, which moved to +23 (86% of 2,999 kit/key
#   pairs with the MU100; the rest is re-voicing) and the EQ bytes +16..+23 (not used)
# - wavedata: MU90 format, one table, 16-bit offsets
# - wave ROMs: two 32-bit pairs, contiguous: xv364a0+xv365a0 (words 0x000000-), xw848a0+xw849a0 (0x400000-)
# - program maps: 32-bit BE offsets in 16-bit words, 512 bytes per bank (221 banks)
# - voice maps: MU Basic, MU Native (converted by default, --mu-basic: MU Basic), GS, MSB 48, GM2 (basic/native)
#   MU Basic = the MU90-compatible voice set (unrevoiced names like "GrandPno"), MU Native = "GrandP #" etc.
#
# The MU2000 has the same voice data, but its program ROM stores the filter/level scaling of
# every element (+36..+43, +58..+65) as an index into a table that is not in the ROM dump.

def MU1000_Program(high : bytes, low : bytes) -> bytes :
    # 32-bit bus: word n = high[2n:2n+2] + low[2n:2n+2], then byte swapped like the other MU ROMs
    assert len(high) == len(low)
    out = bytearray(len(high) * 2)
    for i in range(0, len(high), 2) :
        out[2*i : 2*i+2] = high[i : i+2]
        out[2*i+2 : 2*i+4] = low[i : i+2]
    return bytes(out)

def MU1000_Waverom(pairs : list[tuple[bytes, bytes]]) -> bytes :
    return b''.join(MU90_Waverom(a, b) for a, b in pairs)


# program ROM locations (assembled + dejumbled). The MU128 (v2.00) uses the same layout.
_LAYOUTS = {
    'MU1000' : dict(
        WAVEDATA   = (0x164598, 0x16FAE8),
        WDOFFS     = (0x16FAE8, 0x16FAE8 + 503*2),
        VOICES     = (0x16FED8, 0x1ABEC6),
        PRGMAP     = (0x1ABEC8, 0x1C78C8),     # 221 banks
        BANKROWS   = 0x1C78C8,                 # 0 MSB, 1 XG basic, 2 XG native, 3 MSB 48
        EXTOFFS    = (0x1C7AC8, 0x1C7AC8 + 97*4),
        GSROW      = 0x1C7CC8,
        DRUMVOICES = (0x1C7D48, 0x1D25C6),     # 1027 x 42
        KEYMAPS    = (0x1D25C6, 0x1D61C6),     # 60 kits
        DRUMPRG    = 0x1D62B8,                 # 0 XG basic, 1 XG native, 2 SFX, 3 GS, 4/5 GS (other maps), 6/7 GM2 voice LSB rows (basic/native)
        NATIVE_XG_BASE = 0x5B, SILENT = 0x4C,
        WAVESPAN   = 0x2000000),
    'MU128' : dict(
        WAVEDATA   = (0x0FDB0C, 0x1084BC),
        WDOFFS     = (0x1084BC, 0x108856),     # 461 entries
        VOICES     = (0x108858, 0x1418B2),
        PRGMAP     = (0x1418B4, 0x15C6B4),     # 215 banks
        BANKROWS   = 0x15C6B4,
        EXTOFFS    = (0x15C8B4, 0x15CA2C),     # 94 entries
        GSROW      = 0x15CAB4,
        DRUMVOICES = (0x15CB34, 0x166836),     # 957 x 42
        KEYMAPS    = (0x166836, 0x16A236),     # 58 kits
        DRUMPRG    = 0x16A320,
        NATIVE_XG_BASE = 0x58, SILENT = 0x49,
        WAVESPAN   = 0x1800000),
}

ELEMENT_LENGTH = 84


@dataclass
class MU1000(MU90) :

    bankorder_voice : list[Bank] = field(default_factory=lambda : [Bank.XG, Bank.SFX, Bank.GS, Bank.GM2] )
    bankorder_drums : list[Bank] = field(default_factory=lambda : [Bank.GS_DRUMS, Bank.XG_DRUMS, Bank.SFX_DRUMS] )

    @classmethod
    def From_Bytes(cls, table : bytes | bytearray, model : str = 'MU1000', basic : bool = False) : 
        L = _LAYOUTS[model]
        _WAVEDATA, _WDOFFS, _VOICES, _PRGMAP = L['WAVEDATA'], L['WDOFFS'], L['VOICES'], L['PRGMAP']
        _BANKROWS, _EXTOFFS, _GSROW, _DRUMVOICES = L['BANKROWS'], L['EXTOFFS'], L['GSROW'], L['DRUMVOICES']
        _KEYMAPS, _DRUMPRG, NATIVE_XG_BASE, SILENT = L['KEYMAPS'], L['DRUMPRG'], L['NATIVE_XG_BASE'], L['SILENT']
        data = bytearray(table)
        row = lambda a, r : bytes(data[a + 128*r : a + 128*(r+1)])

        drumprg_start = len(data)
        data += row(_DRUMPRG, 3)                    # GS
        data += row(_DRUMPRG, 0 if basic else 1)    # XG: MU Basic or MU Native map
        data += row(_DRUMPRG, 2)                    # SFX
        drumprg_end = len(data)

        banks_start = len(data)
        # --mu-basic: row 1 (MU Basic, base bank 0x00), otherwise row 2 (MU Native)
        data += row(_BANKROWS, 1 if basic else 2)   # XG LSB
        msb = bytearray(row(_BANKROWS, 0))
        for i, v in enumerate(msb) :
            if v == 0x00 and not basic : msb[i] = NATIVE_XG_BASE  # MSB 0 / 96-111 -> native base bank
        msb[121] = SILENT                           # GM2 has its own row
        data += msb
        data += row(_GSROW, 0)                      # GS
        data += row(_DRUMPRG, 6 if basic else 7)    # GM2 LSB: basic or native
        banks_end = len(data)

        return cls(
            source = MU.MU90,   # wavedata and drum voices use the MU90 formats from here on
            data = data,
            drumbank_PRGs = TableData(drumprg_start, drumprg_end),
            drumkit_keymaps = TableData(*_KEYMAPS),
            drum_voices = TableData(*_DRUMVOICES),
            drumvoice_ext_offsets = TableData(*_EXTOFFS),
            voice_banks = TableData(banks_start, banks_end),
            voice_PRGmap = TableData(*_PRGMAP),
            voices = TableData(*_VOICES),
            wavedata_offsets = TableData(*_WDOFFS),
            wavedata = TableData(*_WAVEDATA),
            prgmap_entry_bytes = 4,
            prgmap_offset_mult = 2,
            waverom_span = L['WAVESPAN'],
        )


    @override
    def ProcessVoice(self, data : bytes | bytearray, address: int) -> tuple[Voice, dict[str | int, WaveBank], dict[int, Sample]] :
        HEADER_LENGTH = 14
        mask = data[address]
        assert 1 <= mask <= 15
        element_cnt = bin(mask).count('1')
        volume = data[address+1]
        name = data[address+2 : address + 10].decode(encoding='cp1252')   # 10 chars, first 8 kept

        elements : list[Element] = []
        wavebanks : dict[str | int, WaveBank] = {}
        samples : dict[int, Sample] = {}

        # * S-YXG50 voices have at most 2 elements: 3- and 4-element voices keep the first two
        for k in range(min(element_cnt, 2)) :
            element_address = address + HEADER_LENGTH + ELEMENT_LENGTH * k
            element_data = data[element_address : element_address + ELEMENT_LENGTH]
            wavebankID = (element_data[0] << 7) + element_data[1]
            wavedata_offset_address = self.wavedata_offsets.start + (wavebankID * 2)
            assert wavedata_offset_address < self.wavedata_offsets.end
            wavedata_address = self.decode_bytes(data, wavedata_offset_address, 16, 'big') + self.wavedata.start
            assert wavedata_address < self.wavedata.end

            wavebank, samples_wave = self.ProcessWaveData(data, wavedata_address)
            wavebanks[wavedata_address] = wavebank
            for sample in samples_wave.values() :
                sample.address_book.add(element_address)
            samples = MergeSampleDicts(samples, samples_wave)
            elements.append(Element(wavedata_address, bytearray(element_data), MU.MU90, waveID=wavebankID) )

        voice = Voice(address, volume, name, elements, MU.MU90)
        voice.source_elements = element_cnt
        return voice, wavebanks, samples


    @override
    def ProcessDrumVoice(self, data : bytes | bytearray, address : int) -> tuple[int, DrumVoice, Sample] :
        address_book : set[int] = set([address])
        raw = data[address : address + 42]
        # * back to the MU90 layout: byte 0 lives at +23 on the MU1000, EQ bytes +16..+23 unused
        drumvoice_data = bytearray(raw)
        drumvoice_data[0] = raw[23]
        drumvoice_data = bytes(drumvoice_data)

        ExtVoice_SeqID = int.from_bytes(raw[24 : 24+2], byteorder='big')
        voice_address : int = 0
        if ExtVoice_SeqID < 0xFFFF :
            voice_offset_address = self.drumvoice_ext_offsets.start + (ExtVoice_SeqID * 4)
            assert voice_offset_address < self.drumvoice_ext_offsets.end
            voice_address = self.voices.start + 2 * self.decode_bytes(data, voice_offset_address, bits=32)
            address_book.add(voice_offset_address)
            address_book.add(voice_address)

        sample_format = Byte_To_SampleFormat(MU.MU90, raw[38] & 0xC0)
        dpcm_parameters : int = (raw[38] & 0x3E) >> 1
        offset_negative = self.decode_bytes(raw, 31, bits=24)
        offset_positive = self.decode_bytes(raw, 35, bits=24)
        loop_address = self.decode_bytes(raw, 39, bits=24) * 4

        sample = Sample(loop_address, offset_negative, offset_positive, loop_address, sample_format,
                        encoding_parameters=dpcm_parameters, format=MU.MU90, address_book=set(address_book))
        if raw[34] & 0x80 :
            sample, offset_negative, offset_positive = Make_Reversed(sample)

        drumvoice = DrumVoice(drumvoice_data, sample.address_src, voice_address,
                              offset_negative, offset_positive, format=MU.MU90, address_book=set(address_book))
        return voice_address, drumvoice, sample
