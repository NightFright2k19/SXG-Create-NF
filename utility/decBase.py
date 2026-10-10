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

    # * voice program maps: MU50-MU90 = 16-bit entries, offset * 2. MU100 = 32-bit entries, plain byte offset
    prgmap_entry_bytes : int = 2
    prgmap_offset_mult : int = 2
    # * size of the (possibly sparse) wave address space, 0 = sum of the wave ROM file sizes
    waverom_span : int = 0

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
                # the full differences between MU50 and S-YXG50 tables are in tableconvert.fromMU50
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
                if self.drumvoice_ext_offsets.end :      # table in the ROM: 32-bit absolute addresses
                    voice_offset_address = self.drumvoice_ext_offsets.start + (ExtVoice_SeqID * 4)
                    assert voice_offset_address + 3 <= self.drumvoice_ext_offsets.end
                    voice_address = int.from_bytes(data[voice_offset_address : voice_offset_address + 4], byteorder='big')
                    address_book.add(voice_offset_address)
                else : 
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
#         a[addr : addr + len(name)] = name.encode(encoding='ANSI')

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


# -------------------- table creation (was decode.py) --------------------

# * designed to work with everything - MU80, MU50, S-YXG50, and MU90
# but we'll see if that holds
def Create_Table(MUinfo : MUdecoder, table_name : str, data : bytes | bytearray, waveroms : list[Path]) -> Table :

    Sample_pool : dict[str | int, Sample] = {}
    Wavebank_pool : dict[str | int, WaveBank] = {}
    Voice_pool : dict[str | int, Voice] = {}
    Drumvoice_pool : dict[str | int, DrumVoice] = {}

    drumkits : dict[int | str, DrumKit] = {}

    voice_banks : dict[int | str, VoiceBank] = {}

    waverom_length : int = 0
    for rom in waveroms : 
        waverom_length = waverom_length + len(bytes(open(rom, mode='rb').read() ))
    if MUinfo.waverom_span : 
        waverom_length = MUinfo.waverom_span



    # * Trace and decode Drum Voices ---------

    for idx, bank in enumerate(MUinfo.bankorder_drums) : 

        # both LSB and MSB can be inferred by just the section they are in / bank enum
        lsb, msb = BankToDrumLSBMSB(bank) 

        # * Drum PRG assignment tables (128 bytes)   # idx= program,  value = seqID

        drumPRG_address = MUinfo.drumbank_PRGs.start + (128 * idx)

        for prg, seqIDaddress in enumerate(range(drumPRG_address, drumPRG_address + 128)) : 

            kit_seqID = data[seqIDaddress]

            if kit_seqID == 0xFF :
                continue

            # * Drumkit / Keymaps (256 byte tables)  idx*2 = key#,  value = drumvoice offset
            drumkit_keymap_address = MUinfo.drumkit_keymaps.start + (256 * kit_seqID)
            assert drumkit_keymap_address < MUinfo.drumkit_keymaps.end


            # add duplicate maps to "aliases" list. Tuple of (bank enum, byte) 
            # what the byte represents depends on context
            # for drumkits, it's always PRG (use BankToDrumLSBMSB to get lsb/msb)
            # for voice banks, it's either LSB or MSB (use BankToLSBMSB to get lsb/msb)
            if drumkit_keymap_address in drumkits : 
                drumkits[drumkit_keymap_address].aliases.append((bank, prg) )
                continue


            #  debug: try to attach a name to our samples
            # _, kit_name, _ = dataXG.TryFindPatch(bank, lsb, msb, prg, drums=True)
            # if not success : kit_name = f'{bank.value}_{lsb:03}{msb:03}{prg:03}' 
            kit_name = f'{bank.value}_{lsb:03}{msb:03}{prg:03}'


            drumkit = DrumKit(drumkit_keymap_address, bank, prg, {}, {}, aliases=[], seqID=kit_seqID)
            if kit_name : drumkit.name = kit_name

            for key, keyaddress in enumerate(range(drumkit_keymap_address, drumkit_keymap_address + 256, 2)) : 

                # drumvoice_offs = MUinfo.b16.decode_bytes(data, keyaddress)
                drumvoice_offs = MUinfo.decode_bytes(data, keyaddress, 16, MUinfo.endian)

                if drumvoice_offs == 0xFFFF : continue

                drumvoice_address = MUinfo.drum_voices.start + (drumvoice_offs)
                assert drumvoice_address < MUinfo.drum_voices.end

                ExtVoiceAddress, drumvoice, sample = MUinfo.ProcessDrumVoice(data, drumvoice_address)
                assert sample.get_start_address() >= 0
                assert sample.get_end_address() < waverom_length

                if not ExtVoiceAddress :

                    sample.names = {f'{kit_name}_{key:02}'}

                    Drumvoice_pool[drumvoice_address] = drumvoice
                    AddToSampleList(Sample_pool, sample)

                    drumkit.drumvoices[key] = drumvoice_address

                else : 

                    # * handle drumvoice linked to regular voice
                    voice, ext_wavebanks, ext_samples = MUinfo.ProcessVoice(data, ExtVoiceAddress)

                    for i, sample in enumerate(ext_samples.values()) : 
                        sample.names = {f'{kit_name}_{key:02}#{i}'}
                        # sample.address_book.add(ExtVoiceAddress) # add element addr instead

                    Voice_pool[ExtVoiceAddress] = voice
                    Drumvoice_pool[drumvoice_address] = drumvoice

                    Wavebank_pool = Wavebank_pool | ext_wavebanks

                    Sample_pool = MergeSampleDicts(Sample_pool, ext_samples)

                    drumkit.drumvoices[key] = drumvoice_address
                    drumkit.voices[ExtVoiceAddress] = voice.address_src


            drumkits[drumkit_keymap_address] = drumkit



    # * Trace and decode Regular Voices ---------

    # * instrument bank definition tables, 128 byte w/ sequential IDs
    for tablenum, bank in enumerate(MUinfo.bankorder_voice) : 

        banktable_address = MUinfo.voice_banks.start + (128 * tablenum)

        for idx, bankaddress in enumerate(range(banktable_address, banktable_address + 128 )) : 

            lsb, msb = BankToLSBMSB(bank, idx)

            prg_seqID = data[bankaddress]

            # note: 0xFF programs are only valid for GS mode in S-YXG50
            if prg_seqID == 0xFF :
                continue

            prgmap_stride = 128 * MUinfo.prgmap_entry_bytes
            program_map_address = MUinfo.voice_PRGmap.start + (prg_seqID * prgmap_stride)

            # S-YXG50: program sections split into GS & Non-GS
            if MUinfo.source == MU.SYXG50 : 
                if bank == Bank.GS : 
                    program_map_address = MUinfo.SXG50_Prgmap_GS.start + (prg_seqID * 256)
                else : 
                    program_map_address = MUinfo.SXG50_Prgmap_XG.start + (prg_seqID * 256)

            assert program_map_address < MUinfo.voice_PRGmap.end


            # add duplicate voicebank maps to "aliases" list. Tuple of (bank enum, byte) 
            # use BankToLSBMSB(bank,byte) to decode to lsb/msb
            if program_map_address in voice_banks : 
                voice_banks[program_map_address].aliases.append((bank, idx))
                continue

            voicebank = VoiceBank(program_map_address, bank, lsb, msb, voices={}, aliases=[], seqID=prg_seqID)


            # * program definitions, 256 byte table w/ offsets for 'voices' table(s)

            for prg, offset_address in enumerate(range(program_map_address, program_map_address + prgmap_stride, MUinfo.prgmap_entry_bytes) ) :

                voice_offset_raw = MUinfo.decode_bytes(data, offset_address, 8 * MUinfo.prgmap_entry_bytes, MUinfo.endian)

                # S-YXG50: top bit of program map offset determines whether to start in voicesA or voicesB
                # MU50 through MU90: One big voices section
                if MUinfo.source == MU.SYXG50 : 
                    if voice_offset_raw & 0x8000 : 
                        voice_bank_start = MUinfo.SXG50_VoicesB.start
                    else : 
                        voice_bank_start = MUinfo.SXG50_VoicesA.start

                    voice_offset = (voice_offset_raw & 0x7FFF) * 2
                else : 
                    voice_bank_start = MUinfo.voices.start
                    # Voices offset is * 2 (MU50-MU90), plain on the MU100
                    voice_offset = voice_offset_raw * MUinfo.prgmap_offset_mult

                # ? unlike in the drumkit keymaps, I think FFFF will just crash S-YXG50
                assert voice_offset != 0xFFFF 

                voice_address = voice_bank_start + voice_offset
                assert voice_address < MUinfo.voices.end


                # * this is two linked passes of encapsulation: ProcessVoice (Voices/Elements) -> ProcessWavedata (WaveBank/Samples)
                # returns: Voice, dict[str | int, WaveBank], dict[int, Sample]
                voice, some_wavebanks, some_samples = MUinfo.ProcessVoice(data, voice_address)

                assert len(some_wavebanks)
                assert len(some_samples)

                # debug: try to attach names to our samples
                if len(voice.name) : 
                    name = voice.name
                else : 
                    # _, name, _ = dataXG.TryFindPatch(bank, lsb, msb, prg)
                    name = f'{bank.value[:2]}{idx:03}{prg:03}' # 8 chars

                for i, sample in enumerate(some_samples.values()) : 
                    assert sample.get_start_address() >= 0
                    assert sample.get_end_address() < waverom_length
                    sample.names = {f'{name}#{i:02}'} if len(some_samples) > 1 else {f'{name}'}


                Voice_pool[voice_address] = voice
                voicebank.voices[prg] = voice_address

                Wavebank_pool = Wavebank_pool | some_wavebanks

                # special merge, will pick the longer of two duplicate samples 
                # dupes determined by having the same loop address 
                # (loop address is used as a dictionary key in table.Samples_pool)
                # body/loop offsets will be contained upstream as well, in Wave or DrumVoice objects
                Sample_pool = MergeSampleDicts(Sample_pool, some_samples)


            voice_banks[program_map_address] = voicebank



    return Table(table_name, MUinfo.source, 
                    Sample_pool=Sample_pool, Wavebank_pool=Wavebank_pool, 
                    Voice_pool=Voice_pool, DrumVoice_pool=Drumvoice_pool, 
                    drumkits=drumkits, 
                    voice_banks=voice_banks, 
                    waveroms=waveroms,
                    waveroms_byte_len=waverom_length)
