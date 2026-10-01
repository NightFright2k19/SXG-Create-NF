from dataclasses import dataclass
from typing import Literal, Self, override, ClassVar

from abc import abstractmethod

from dataenum import *
from table import *

from utils import fmtbyte, fmtbytes


@dataclass(frozen=True)
class TableData() : 
    start : int
    end : int

    def __len__(self) : 
        return self.end - self.start

TABLEDATA_BLANK = TableData(0,0)

@dataclass 
class MUdecoder() : 

    source : MU = MU.UNDEFINED

    drumbank_PRGs : TableData = TABLEDATA_BLANK
    drumkit_keymaps : TableData = TABLEDATA_BLANK
    drum_voices : TableData = TABLEDATA_BLANK
    drumvoice_ext_offsets : TableData = TABLEDATA_BLANK # MU80 = N/A, MU50 = MIA...

    voice_banks : TableData = TABLEDATA_BLANK
    voice_PRGmap : TableData = TABLEDATA_BLANK
    voices : TableData = TABLEDATA_BLANK
    wavedata_offsets : TableData = TABLEDATA_BLANK
    wavedata : TableData = TABLEDATA_BLANK

    endian : Literal['big', 'little'] = 'big'

    # ? S-YXG50 is messy 
    SXG50_voice_banks_GS : TableData = TABLEDATA_BLANK
    SXG50_voice_banks_XG : TableData = TABLEDATA_BLANK
    SXG50_VoicesA : TableData = TABLEDATA_BLANK
    SXG50_VoicesB : TableData = TABLEDATA_BLANK
    SXG50_Prgmap_GS : TableData = TABLEDATA_BLANK
    SXG50_Prgmap_XG : TableData = TABLEDATA_BLANK

    data : bytes | bytearray = bytes(0)

    
    bankorder_voice : list[Bank] = field(default_factory=lambda : [Bank.GS, Bank.XG, Bank.SFX])

    bankorder_drums : list[Bank] = field(default_factory=lambda : [Bank.GS_DRUMS, Bank.XG_DRUMS, Bank.SFX_DRUMS])

    def name(self) : 
        return self.__class__.__name__

    def decode_bytes(self, array : bytes | bytearray, idx : int, bits : int = 16, endian : Literal['big', 'little'] = 'big') -> int : 
        return int.from_bytes(array[idx:idx+(bits>>3)], byteorder=endian, signed=False)


    # debug
    def PrintInfo(self) : 
        print(f'drumbank_PRGs = TableData(0x{fmtbyte(self.drumbank_PRGs.start)},0x{fmtbyte(self.drumbank_PRGs.end)})')
        print(f'drumkit_keymaps = TableData(0x{fmtbyte(self.drumkit_keymaps.start)},0x{fmtbyte(self.drumkit_keymaps.end)})')
        print(f'drum_voices = TableData(0x{fmtbyte(self.drum_voices.start)},0x{fmtbyte(self.drum_voices.end)})')
        print(f'drumvoice_ext_offsets = TableData(0x{fmtbyte(self.drumvoice_ext_offsets.start)},0x{fmtbyte(self.drumvoice_ext_offsets.end)})')
        print(f'voice_banks = TableData(0x{fmtbyte(self.voice_banks.start)},0x{fmtbyte(self.voice_banks.end)})')
        print(f'voice_PRGmap = TableData(0x{fmtbyte(self.voice_PRGmap.start)},0x{fmtbyte(self.voice_PRGmap.end)})')
        print(f'self_Prgmap_GS = TableData(0x{fmtbyte(self.SXG50_Prgmap_GS.start)},0x{fmtbyte(self.SXG50_Prgmap_GS.end)})')
        print(f'SXG50_Prgmap_XG = TableData(0x{fmtbyte(self.SXG50_Prgmap_XG.start)},0x{fmtbyte(self.SXG50_Prgmap_XG.end)})')
        print(f'SXG50_VoicesA = TableData(0x{fmtbyte(self.SXG50_VoicesA.start)},0x{fmtbyte(self.SXG50_VoicesA.end)})')
        print(f'SXG50_VoicesB = TableData(0x{fmtbyte(self.SXG50_VoicesB.start)},0x{fmtbyte(self.SXG50_VoicesB.end)})')
        print(f'voices = TableData(0x{fmtbyte(self.voices.start)},0x{fmtbyte(self.voices.end)})')
        print(f'wavedata_offsets = TableData(0x{fmtbyte(self.wavedata_offsets.start)},0x{fmtbyte(self.wavedata_offsets.end)})')
        print(f'wavedata = TableData(0x{fmtbyte(self.wavedata.start)},0x{fmtbyte(self.wavedata.end)})')



    @abstractmethod
    # * should be good for MU50 and S-YXG50
    # full decoding / abstraction here, no big lump of general 'data' as in the voice/drumvoice tables
    # return WaveBank & Samples  dict[int, Sample]
    # use MergeSampleLists() on output to merge them into our table's sample pool
    def ProcessWaveData(self, data : bytes | bytearray, address : int) -> tuple[WaveBank, dict[int, Sample]] : 

        samples : dict[int, Sample] = {} # key = loop address
        waves : list[Wave] = []

        # table extends pages until last byte (key range high) is >= 0x7F
        for addr in range(address, self.wavedata.end, 16) : 
            # + 0: attenuation
            # + 1: pitch, note
            # + 2: pitch, cent
            # + 3: samples -
            # + 4: 
            # + 5: 
            # + 6: loop samples +
            # + 7: 
            # + 8: 
            # + 9: loop pt address
            # +10: 
            # +11: 
            # +12: sample fmt
            # +13: unknown
            # +14: note range, low 
            # +15: note range, high

            offset_negative = self.decode_bytes(data,addr+3, 24, 'big')
            # todo confirmed incorrect on S-YXG50, it's limited to only 16 bits
            offset_positive = self.decode_bytes(data,addr+6, 24, 'big')
            loop_address = self.decode_bytes(data,addr+9, 24, 'big')

            sample_byte = data[addr+12]
            sample_format = Byte_To_SampleFormat(self.source, sample_byte)
            assert sample_format != SampleFormat.UNKNOWN

            sample = Sample(loop_address, offset_negative, offset_positive, loop_address, sample_format, 
                            encoding_parameters=sample_byte, format=self.source, address_book={addr})

            AddToSampleList(samples, sample) # will only add the longer sample if clipped

            wave = Wave(addr, 
                        offset_negative, offset_positive, loop_address, 
                        attenuation=data[addr+0],
                        tune_note=data[addr+1],
                        tune_cent=data[addr+2],
                        key_min=data[addr+14],
                        key_max=data[addr+15],
                        )

            waves.append(wave)

            if data[addr+15] >= 0x7F : break

        return (WaveBank(address, waves), samples)



    @abstractmethod
    # * encapsulated logic. This one is for MU50 and S-YXG50
    # return voice (w/ elements), wavebank, & samples
    def ProcessVoice(self, data : bytes | bytearray, address: int) -> tuple[Voice, dict[str | int, WaveBank], dict[int, Sample]] : 
        assert self.source == MU.MU50 or self.source == MU.SYXG50
        if self.source == MU.MU50 : 
            HEADER_LENGTH = 10 
            ELEMENT_LENGTH = 80 # full voice: 90 or 170
        else :  # self.source == MU.SYXG50 : 
            HEADER_LENGTH = 2
            ELEMENT_LENGTH = 78 # full voice: 80 or 158

        volume = data[address]          # + 0
        element_cnt = data[address+1]   # + 1
        if self.source == MU.MU50 : 
            name = data[address+2 : address + 10].decode(encoding='cp1252') # +2
        else : 
            name = '' # f'{address}' # ? 
        assert element_cnt > 0 and element_cnt < 4
        element_cnt = 2 if element_cnt == 0x03 else 1

        elements : list[Element] = []
        wavebanks : dict[str | int, WaveBank] = {} # key = wavedata start addr
        samples : dict[int, Sample] = {} # key = loop address

        for element_address in range(address + HEADER_LENGTH, address + HEADER_LENGTH + (ELEMENT_LENGTH * element_cnt), ELEMENT_LENGTH) : 

            element_data = data[element_address : element_address + ELEMENT_LENGTH]

            if self.source == MU.MU50 : 
                # top bits of wave# is on the el+0
                # the full differences between MU50 and S-YXG50 tables are in cnv_fromMU50.py
                wavebankID = (element_data[0] << 7) + element_data[1] 
            else : 
                wavebankID = element_data[0]

            # trace wavebankID to wavedatatable
            wavedata_offset_address = self.wavedata_offsets.start + (wavebankID * 2)
            assert wavedata_offset_address < self.wavedata_offsets.end

            wavedata_address = self.decode_bytes(data, wavedata_offset_address, 16, self.endian) + self.wavedata.start
            assert wavedata_address < self.wavedata.end

            # * pull wavedata, collect WaveBank, Samples
            wavebank, samples_wave = self.ProcessWaveData(data, wavedata_address)

            wavebanks[wavedata_address] = wavebank

            for sample in samples_wave.values() : 
                sample.address_book.add(element_address)

            samples = MergeSampleDicts(samples, samples_wave)

            elements.append(Element(wavedata_address, bytearray(element_data), self.source, waveID=wavebankID) )

        voice = Voice(address, volume, name, elements, self.source)

        return voice, wavebanks, samples
        


    @abstractmethod
    # * encapsulated logic. This should be good for MU50 and S-YXG50
    #  returns: ExtVoiceAddress, Drumvoice, Sample 
    # * ExtVoiceAddress=0 if non-applicable
    def ProcessDrumVoice(self, data : bytes | bytearray, address : int) -> tuple[int, DrumVoice, Sample] : 
        # for 30 byte MU50/S-YXG50
        assert self.source == MU.MU50 or self.source == MU.SYXG50 

        address_book : set[int] = set([address]) # * keep a log of our visited addresses for debugging
        drumvoice_data = data[address : address + 30]
        ExtVoice_SeqID = int.from_bytes(drumvoice_data[16 : 16+2], byteorder='big') # always BE
        voice_address : int = 0
        if ExtVoice_SeqID < 0xFFFF : 
            if self.source == MU.SYXG50 : 
                voice_offset_address = self.drumvoice_ext_offsets.start + (ExtVoice_SeqID * 2)
                # voice_offset = self.b16.decode_bytes(data, voice_offset_address)
                voice_offset = self.decode_bytes(data, voice_offset_address, 16, self.endian)
                voice_address = self.voices.start + voice_offset
                address_book.add(voice_offset_address)
                address_book.add(voice_address)

            elif self.source == MU.MU50 : 
                voice_address = self.voices.start + (MU50extVoiceTable[ExtVoice_SeqID] * 2)
                address_book.add(voice_address)

        offset_negative = int.from_bytes(drumvoice_data[19 : 19+2], byteorder='big') # always BE

        # todo confirmed limited to 16 bits on S-YXG50
        offset_positive = int.from_bytes(drumvoice_data[21 : 21+3], byteorder='big')

        loop_address = int.from_bytes(drumvoice_data[24 : 24+3], byteorder='big')

        sample_byte : int = drumvoice_data[27]
        sample_format = Byte_To_SampleFormat(self.source, sample_byte)

        address_book.add(address)


        drumvoice = DrumVoice(drumvoice_data, loop_address, voice_address, 
                              offset_negative, offset_positive, 
                              format=self.source, 
                              address_book=set(address_book),)
        sample = Sample(loop_address, offset_negative, offset_positive, loop_address, sample_format, 
                        encoding_parameters=sample_byte,
                        format=self.source,
                        address_book=set(address_book))

        
        return voice_address, drumvoice, sample








# #  debug
# #  do a voice check and look for untouched addresses
# def RomBackTrace(data : bytes | bytearray, table : Table, mu : MUdecoder) -> bytearray :

#     def find_section(addr : int) -> tuple[TableData | None, int] : 
#         if addr >= mu.drum_voices.start and addr <= mu.drum_voices.end : return (mu.drum_voices,30 )
#         if addr >= mu.voices.start and addr <= mu.voices.end : return (mu.voices,80 )
#         if addr >= mu.wavedata.start and addr <= mu.wavedata.end : return (mu.wavedata,16 ) 
#         return None,0

#     def set_range(a : list | bytearray, addr : int , length : int, value : int = 1) :
#         a[addr : addr + length] = [value for _ in range(0, length)] 

#     def set_range2(a : list | bytearray, addr : int, name : str) :
#         # assert len(name) <= length 
#         a[addr : addr + len(name)] = name.encode(encoding='cp1252')

#     out_data = bytearray(len(data))

#     for sample in table.Sample_pool.values() : 
#         sample_name = ''
#         for n in sample.names : 
#             sample_name = n
#             break

#         for addr in sample.address_book : 
#             section, section_length = find_section(addr)
#             if not section : continue
#             assert isinstance(section, TableData)

#             set_range(out_data, addr, section_length, 0xFF)
#             set_range2(out_data, addr, sample_name)

#     return out_data