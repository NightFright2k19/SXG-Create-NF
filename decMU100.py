from decBase import *
from decMU90 import MU90, MU90_Waverom, Make_Reversed

# * Yamaha MU100 (xu50720 v1.11), 2026-09-30
#
# The MU100 uses the MU90 table formats (70-byte elements, 42-byte drum voices, 16-byte
# wavedata entries) with these differences:
#
# - three wave ROM pairs. Each pair is a 32-bit bus like on the MU90 (see MU90_Waverom).
#   The loop address (32-bit words) selects the pair with bits 22-23:
#       0x000000- : xs518b0 + xs743b0 (same ROMs as the MU90)
#       0x400000- : xt445a0 + xt461a0
#       0x800000- : xt462a0 + xt463a0
#   so the combined byte stream has the pairs at 0, 16 MB and 32 MB (sparse, 40 MB).
# - three wavedata tables, each with its own offset table. Wave number (element +0/+1):
#       0-292 table 1 (the MU90 set), 293-326 table 2, 327- table 3
# - voice program maps: 32-bit big endian byte offsets into the voice table (512 bytes per bank)
# - drum ext voice offsets: 32-bit big endian byte offsets
# - two voice maps: "MU Basic" (= MU90 voices) and "MU100 Native" (revoiced, new samples).
#   The native map is converted. Bank map rows in the program ROM (128 bytes each):
#       0: MSB table (0 -> XG, 48 -> MSB 48 bank, 64 -> SFX, 0x46 = silent)
#       1: XG LSB, MU Basic     3: XG LSB, MU100 Native (base bank 0x55)
#       2: MSB 48 LSB table     9: GS variations (MSB)
#   S-YXG50 can only address MSB 48 as one bank (LSB 0).
# - drum program maps: 4 rows (GS, XG basic, XG native, SFX); XG native uses a new
#   Standard kit (kit 0x2E).

PAIR_SPAN = 0x1000000  # bytes per ROM pair slot in the combined stream

def MU100_Waverom(pairs : list[tuple[bytes, bytes]]) -> bytes :
    out = bytearray(PAIR_SPAN * (len(pairs) - 1))
    for i, (a, b) in enumerate(pairs) :
        w = MU90_Waverom(a, b)
        if i == len(pairs) - 1 :
            out += w
        else :
            assert len(w) <= PAIR_SPAN
            out[i * PAIR_SPAN : i * PAIR_SPAN + len(w)] = w
    return bytes(out)


# program ROM locations (dejumbled)
_DRUMVOICES   = (0xA8000, 0xB1798)
_KEYMAPS      = (0xB1798, 0xB4698)
_DRUMPRG      = 0xB4698          # 4 x 128
_PRGMAP       = (0xB4898, 0xCB098) # 180 banks x 512
_BANKROWS     = 0xCB098          # 10 x 128
_EXTOFFS      = (0xCB598, 0xCB710) # 94 x 4
_VOICES       = (0xCB710, 0xF692E)
_WAVETABLES   = [ # (wavedata start, offset table start, entries in offset table, first wave number)
    (0xF692E, 0xFCCDE, 294, 0),
    (0xFCF30, 0xFDF80, 34, 293),
    (0xFDFC4, 0x100C34, 116, 327),
]
_WAVEDATA     = (0xF692E, 0x100C34)

NATIVE_XG_BASE = 0x55


@dataclass
class MU100(MU90) :

    bankorder_voice : list[Bank] = field(default_factory=lambda : [Bank.XG, Bank.SFX, Bank.GS] )
    bankorder_drums : list[Bank] = field(default_factory=lambda : [Bank.GS_DRUMS, Bank.XG_DRUMS, Bank.SFX_DRUMS] )

    @classmethod
    def From_Bytes(cls, table : bytes | bytearray, basic : bool = False) : 
        data = bytearray(table)
        row = lambda r : bytes(data[_BANKROWS + 128*r : _BANKROWS + 128*(r+1)])

        # * synthetic tables appended to the program data, in MU90 order
        # drum programs: GS, XG native, SFX
        drumprg_start = len(data)
        data += data[_DRUMPRG : _DRUMPRG + 128]            # GS
        if basic : 
            data += data[_DRUMPRG + 128 : _DRUMPRG + 256]  # XG, MU Basic map
        else : 
            data += data[_DRUMPRG + 256 : _DRUMPRG + 384]  # XG, native map
        data += data[_DRUMPRG + 384 : _DRUMPRG + 512]      # SFX
        drumprg_end = len(data)

        # voice banks: XG (native LSB row), SFX (MSB row), GS
        banks_start = len(data)
        # --mu-basic: row 1 (MU Basic, base bank 0x00), otherwise row 3 (MU100 Native, base bank 0x55)
        data += row(1) if basic else row(3)
        msb = bytearray(row(0))
        for i, v in enumerate(msb) :
            if v == 0x00 and not basic : msb[i] = NATIVE_XG_BASE   # MSB 0 / 96-111 / 126 / 127 -> native base bank
        data += msb
        data += row(9)
        banks_end = len(data)

        return cls(
            source = MU.MU90,   # same data formats as the MU90 (element, drum voice, wavedata)
            data = data,
            drumbank_PRGs = TableData(drumprg_start, drumprg_end),
            drumkit_keymaps = TableData(*_KEYMAPS),
            drum_voices = TableData(*_DRUMVOICES),
            drumvoice_ext_offsets = TableData(*_EXTOFFS),
            voice_banks = TableData(banks_start, banks_end),
            voice_PRGmap = TableData(*_PRGMAP),
            voices = TableData(*_VOICES),
            wavedata_offsets = TableData(_WAVETABLES[0][1], _WAVETABLES[0][1] + 2*_WAVETABLES[0][2]),
            wavedata = TableData(*_WAVEDATA),
            prgmap_entry_bytes = 4,
            prgmap_offset_mult = 1,
            waverom_span = 3 * PAIR_SPAN,
        )


    def WaveNumber_To_Address(self, data : bytes | bytearray, wave : int) -> int :
        for wd_start, offs_start, count, first in reversed(_WAVETABLES) :
            if wave >= first :
                idx = wave - first
                assert idx < count - 1 or first == _WAVETABLES[1][3]   # last entry of tables 1 and 3 is an end marker
                return wd_start + self.decode_bytes(data, offs_start + 2*idx, 16, 'big')
        raise ValueError(wave)


    @override
    def ProcessVoice(self, data : bytes | bytearray, address: int) -> tuple[Voice, dict[str | int, WaveBank], dict[int, Sample]] :
        HEADER_LENGTH = 10
        ELEMENT_LENGTH = 70

        element_cnt = data[address] + 1
        volume = data[address+1]
        name = data[address+2 : address + 10].decode(encoding='cp1252')

        elements : list[Element] = []
        wavebanks : dict[str | int, WaveBank] = {}
        samples : dict[int, Sample] = {}

        for element_address in range(address + HEADER_LENGTH, address + HEADER_LENGTH + (ELEMENT_LENGTH * element_cnt), ELEMENT_LENGTH) :
            element_data = data[element_address : element_address + ELEMENT_LENGTH]
            wavebankID = (element_data[0] << 7) + element_data[1]
            wavedata_address = self.WaveNumber_To_Address(data, wavebankID)
            assert wavedata_address < self.wavedata.end

            wavebank, samples_wave = self.ProcessWaveData(data, wavedata_address)
            wavebanks[wavedata_address] = wavebank
            for sample in samples_wave.values() :
                sample.address_book.add(element_address)
            samples = MergeSampleDicts(samples, samples_wave)
            elements.append(Element(wavedata_address, bytearray(element_data), MU.MU90, waveID=wavebankID) )

        voice = Voice(address, volume, name, elements, MU.MU90)
        return voice, wavebanks, samples


    @override
    def ProcessDrumVoice(self, data : bytes | bytearray, address : int) -> tuple[int, DrumVoice, Sample] :
        # same layout as the MU90, only the ext voice offset table has 32-bit plain offsets
        address_book : set[int] = set([address])
        drumvoice_data = data[address : address + 42]
        ExtVoice_SeqID = int.from_bytes(drumvoice_data[24 : 24+2], byteorder='big')
        voice_address : int = 0

        if ExtVoice_SeqID < 0xFFFF :
            voice_offset_address = self.drumvoice_ext_offsets.start + (ExtVoice_SeqID * 4)
            assert voice_offset_address < self.drumvoice_ext_offsets.end
            voice_address = self.voices.start + self.decode_bytes(data, voice_offset_address, bits=32)
            address_book.add(voice_offset_address)
            address_book.add(voice_address)

        sample_format = Byte_To_SampleFormat(MU.MU90, drumvoice_data[38] & 0xC0)
        dpcm_parameters : int = (drumvoice_data[38] & 0x3E) >> 1
        offset_negative = self.decode_bytes(drumvoice_data, 31, bits=24)
        offset_positive = self.decode_bytes(drumvoice_data, 35, bits=24)
        loop_address = self.decode_bytes(drumvoice_data, 39, bits=24) * 4

        sample = Sample(loop_address, offset_negative, offset_positive, loop_address, sample_format,
                        encoding_parameters=dpcm_parameters, format=MU.MU90, address_book=set(address_book))
        if drumvoice_data[34] & 0x80 :
            sample, offset_negative, offset_positive = Make_Reversed(sample)

        drumvoice = DrumVoice(drumvoice_data, sample.address_src, voice_address,
                              offset_negative, offset_positive, format=MU.MU90, address_book=set(address_book))
        return voice_address, drumvoice, sample
