
from decBase import *

from utils import fmtbyte, fmtbytes

# ! work in progress

@dataclass
class MU90(MUdecoder) : 

    # bankorder_voice : list[Bank] = [Bank.GS, Bank.SFX, Bank.XG]
    # bankorder_drums : list[Bank] = [Bank.GS_DRUMS, Bank.XG_DRUMS, Bank.SFX_DRUMS]
    bankorder_voice : list[Bank] = field(default_factory=lambda : [Bank.GS, Bank.SFX, Bank.XG] )
    bankorder_drums : list[Bank] = field(default_factory=lambda : [Bank.GS_DRUMS, Bank.XG_DRUMS, Bank.SFX_DRUMS] )

    
    
    
    @classmethod
    def From_Bytes(cls, table : bytes | bytearray) : 
        return cls(
            source = MU.MU90,
            data = table,
            # 3 tables: GS, XG msb=127, XG msb=126 (typical)
            drumbank_PRGs = TableData(0x970DE, 0x9725D),
            # 31 drum kits
            drumkit_keymaps = TableData(0x951DE, 0x970DD),
            # 42 bytes per entry   499 voices  +24 +25 = ext seqID
            drum_voices = TableData(0x90000, 0x951DD),
            # drum_voice_seqID_offset = 0x18,

            # max value 0x57 / 87  88 entries
            # * In MU90 these are implicitly multiplied by two, like the PRGmap offsets
            drumvoice_ext_offsets = TableData(0x9BBDE, 0x9BC8D),

            # 128 x 3 tables: GS, XG SFX, XG (different order!)
            voice_banks = TableData(0x9BA5E, 0x9BBDD),

            # 256 bytes per entry = 71 voice banks (same as mu80)
            voice_PRGmap = TableData(0x9725E, 0x9BA5D),
            
            # 10 bytes + 70 bytes per element (80 / 150) offs+0 elements. seqID on element +1
            # nearly the same as MU80, but with two columns for the wave# like the mu50
            # then just one blank column, probably just to keep the len even
            voices = TableData(0x9BC8E, 0xB36CB),

            # * Note: additional voices at 0xCA754 -> 0xD5FB5
            # 294 entries
            wavedata_offsets = TableData(0xB9A7C, 0xB9CC7),

            # wavedata   16 x 1595
            wavedata = TableData(0xB36CC, 0xB9A7B),

        )

            # drumvoice_extoffset_mult = 2 # MU80 = 2, MU50 = ???, MU90 = 2





    @abstractmethod
    # full decoding / abstraction here, no big lump of general 'data' as in the voice/drumvoice tables
    # return WaveBank & Samples  dict[int, Sample]
    # use MergeSampleLists() on output to merge them into our table's sample pool
    def ProcessWaveData(self, data : bytes | bytearray, address : int) -> tuple[WaveBank, dict[int, Sample]] : 

        assert self.source == MU.MU90

        samples : dict[int, Sample] = {} # key = loop address
        waves : list[Wave] = []

        # 16 bytes, but different from both the MU50 and MU80
        # table extends pages until key range high is >= 0x7F

        # there is no explicit key low, just as in the MU80, it's implied from the last key high
        last_key : int = 0 

        for addr in range(address, self.wavedata.end, 16) : 
            # + 0: attenuation
            # + 1: pitch, note
            # + 2: pitch, cent
            # + 3: note range, high (low is implicit)
            # + 4: unknown value, likely two bitsmashed values
            # + 5: samples -
            # + 6: -
            # + 7: -
            # + 8: backwards playback(!)
            # + 9: loop samples + 
            # +10: +
            # +11: +
            # +12: sample fmt and 25th address bit
            # +13: loop address
            # +14: loop address
            # +15: loop address

            mu90_plus4 = data[address + 4]

            offset_negative = self.decode_bytes(data,addr+5, 24, 'big') >> 1
            offset_positive = self.decode_bytes(data,addr+9, 24, 'big') >> 1
            loop_address = self.decode_bytes(data,addr+13, 24, 'big') * 2 # todo wrong
            sample_byte = data[addr+12] & 0xC0
            sample_format = Byte_To_SampleFormat(self.source, sample_byte)
            assert sample_format != SampleFormat.UNKNOWN
            ADPCM_params = (data[addr+12] & 0b00111110) >> 1

            sample = Sample(loop_address, offset_negative, offset_positive, loop_address, sample_format, 
                            encoding_parameters=ADPCM_params, format=self.source, address_book={addr})

            AddToSampleList(samples, sample) # will only add the longer sample if clipped

            key_min = last_key
            key_max = data[addr+3]
            last_key = key_max + 1 # + 1 is more in line with what s-yxg50 expects, always sequential key ranges

            wave = Wave(addr, 
                        offset_negative, offset_positive, loop_address, 
                        attenuation=data[addr+0],
                        tune_note=data[addr+1],
                        tune_cent=data[addr+2],
                        key_min=key_min,
                        key_max=key_max,
                        mu90_plus4=mu90_plus4,
                        backwards=bool(data[addr+8]),
                        )

            waves.append(wave)

            if key_max >= 0x7F : break

        return (WaveBank(address, waves), samples)



    @abstractmethod
    # return voice (w/ elements), wavebank, & samples
    def ProcessVoice(self, data : bytes | bytearray, address: int) -> tuple[Voice, dict[str | int, WaveBank], dict[int, Sample]] : 
        assert self.source == MU.MU90

        HEADER_LENGTH = 10 
        ELEMENT_LENGTH = 70 # full voice: 80 or 150

        element_cnt = data[address] + 1  # + 0 (like mu80)
        volume = data[address+1]         # + 1

        name = data[address+2 : address + 10].decode(encoding='cp1252') # +2

        elements : list[Element] = []
        wavebanks : dict[str | int, WaveBank] = {} # key = wavedata start addr
        samples : dict[int, Sample] = {} # key = loop address

        for element_address in range(address + HEADER_LENGTH, address + HEADER_LENGTH + (ELEMENT_LENGTH * element_cnt), ELEMENT_LENGTH) : 

            element_data = data[element_address : element_address + ELEMENT_LENGTH]

            # top bits of wave# is on the el+0. Same as Mu50, but the full value sometimes goes to 9 bits now
            wavebankID = (element_data[0] << 7) + element_data[1] 

            # trace wavebankID to wavedatatable
            wavedata_offset_address = self.wavedata_offsets.start + (wavebankID * 2)
            assert wavedata_offset_address < self.wavedata_offsets.end
            # wavedata_address = self.b16.decode_bytes(data, wavedata_offset_address) + self.wavedata.start
            wavedata_address = self.decode_bytes(data, wavedata_offset_address, 16, 'big') + self.wavedata.start
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
        





    @override
    #  returns: ExtVoiceAddress, Drumvoice, Sample 
    # * ExtVoiceAddress=0 if non-applicable
    def ProcessDrumVoice(self, data : bytes | bytearray, address : int) -> tuple[int, DrumVoice, Sample] : 

        # expanded from 30 to 42 bytes
        # up to +15 is the same as MU50, then there are additions that add more robust EG options, 
        # though they are not utilized too much
        assert self.source == MU.MU90

        address_book : set[int] = set([address]) # * keep a log of our visited addresses for debugging
        drumvoice_data = data[address : address + 42]
        ExtVoice_SeqID = int.from_bytes(drumvoice_data[24 : 24+2], byteorder='big') # always BE
        voice_address : int = 0

        if ExtVoice_SeqID < 0xFFFF : 
            voice_offset_address = self.drumvoice_ext_offsets.start + (ExtVoice_SeqID * 2)
            # voice_offset = self.b16.decode_bytes(data, voice_offset_address)
            voice_offset = self.decode_bytes(data, voice_offset_address, bits=16)
            voice_address = self.voices.start + (voice_offset * 2) # * ext voice offset is times two on MU90
            address_book.add(voice_offset_address)
            address_book.add(voice_address)


        sample_format = Byte_To_SampleFormat(self.source, drumvoice_data[38]) # +38: sample byte, always C0 or 00
        # * +38: DPCM parameters are left shifted... I think. Only EE is used for drums
        dpcm_parameters : int = (drumvoice_data[38] & 0x3F) >> 1 

        # todo this is all wrong
        # * 0x80: S8, offsets / 2
        # * 0x40: S12, offsets * 0.75  / 1.5    23,873 -> ~17,905
        # * 0x00: S16  offsets / 2  -  1 offset = 1 bytes (0.5 samples)
        # * 0xEE: ADPCM, offsets / 2
        # offset_negative = self.decode_bytes(drumvoice_data, 31, bits=24)
        # offset_positive = self.decode_bytes(drumvoice_data, 35, bits=24)


        offset_negative = self.decode_bytes(drumvoice_data, 31, bits=24) >> 1
        offset_positive = self.decode_bytes(drumvoice_data, 35, bits=24) >> 1

        # +38 & 1FFFFFF << 2 on mu100
        # loop_address = self.decode_bytes(drumvoice_data, 39, bits=24) * 4

        # todo wrong
        loop_address = self.decode_bytes(drumvoice_data, 39, bits=24) * 2 


        address_book.add(address)


        drumvoice = DrumVoice(drumvoice_data, loop_address, voice_address, 
                              offset_negative, offset_positive, 
                              format=self.source, 
                              address_book=set(address_book),)
        sample = Sample(loop_address, offset_negative, offset_positive, loop_address, sample_format, 
                        encoding_parameters=dpcm_parameters,
                        format=self.source,
                        address_book=set(address_book))

        
        return voice_address, drumvoice, sample



