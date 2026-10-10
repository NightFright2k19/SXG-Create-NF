from decBase import *


@dataclass
class MU80(MUdecoder) : 

    bankorder_voice : list[Bank] = field(default_factory=lambda : [Bank.GS, Bank.XG, Bank.SFX])

    @classmethod
    def From_Bytes(cls, table : bytes | bytearray) : 
        return cls(
            source = MU.MU80,
            data = table,
            # 3 tables: GS, XG msb=127, XG msb=126 (typical)
            drumbank_PRGs = TableData(0x8432, 0x85B1),

            # 22 drum kits  len=5632
            drumkit_keymaps = TableData(0x6E32, 0x8431),

            # 30 byte tables, ext voice bytes @ +16 +17
            drum_voices = TableData(0x49DE, 0x6E31),

            # * MU80 has ext voice offsets directly embedded in the drum voices. and they are *2
            drumvoice_ext_offsets = TableData(0,0),

            # 128 x 3 tables: GS, XG MSB=0, XG LSB=0 (typical)
            voice_banks = TableData(0xCCB2, 0xCE31),

            # 256 bytes per entry = 71 voice banks
            voice_PRGmap = TableData(0x85B2, 0xCCB1),

            # 10 bytes + 68 bytes per element (78 / 146) +0 = element cnt, 8-bit seqID on element +0
            voices = TableData(0x0E3AC, 0x24029),

            # 248 entries (same as MU50, 2 more than SXG)
            wavedata_offsets = TableData(0x47EE, 0x49DD),

            # ? last 2 entries of this table @ 0x47D2 & 0x47E0 are strange
            # still have normal offsets pointing to them though
            # loop pt addresses are *2
            wavedata = TableData(0x0100, 0x47ED),

        )



    @override
    # return WaveBank & Samples  dict[int, Sample]
    # use MergeSampleLists() on output to merge them into our table's sample pool
    def ProcessWaveData(self, data : bytes | bytearray, address : int) -> tuple[WaveBank, dict[int, Sample]] : 

        # only 14 bytes per page, but not too many surprises
        assert self.source == MU.MU80

        samples : dict[int, Sample] = {} # key = loop address
        waves : list[Wave] = []

        # there is no explicit key low in the MU80, it's implied from the last key high
        last_key : int = 0 

        # table extends pages until last byte (key range high) is >= 0x7F
        for addr in range(address, self.wavedata.end, 14) : 
            # + 0: attenuation
            # + 1: pitch, note
            # + 2: pitch, cent
            # + 3: samples - 
            # + 4: samples -
            # + 5: Sample Format   top bit, 1 = S16, 0 = DPCM, bottom bit is MSB of loop sample+
            # + 6: loop samples + 
            # + 7: loop samples +
            # + 8: loop pt address   - multiplied by two implicitly
            # + 9: loop pt address
            # +10: loop pt address 
            # +11: DPCM parameters
            # +12: unused / unknown (only used by mysterious invalid last two entries, where they are 5F)
            # +13: note range, high (low is implicit)

            # debug = fmtbytes(data[addr : addr + 14])

            offset_negative = self.decode_bytes(data,addr+3, 16, 'big') # 16 bits
            offset_positive_17 = (data[addr+5] & 0x01) << 16 # 17th bit of loop +

            offset_positive = offset_positive_17 + self.decode_bytes(data,addr+6, 16, 'big') # 16 bits


            sample_format = Byte_To_SampleFormat(self.source, data[addr+5])
            dpcm_parameters = data[addr+11]


            loop_address = self.decode_bytes(data,addr+8, 24, 'big') * 2 # * multiplied by two


            assert sample_format != SampleFormat.UNKNOWN

            sample = Sample(loop_address, offset_negative, offset_positive, loop_address, sample_format, 
                            encoding_parameters=dpcm_parameters, format=self.source, address_book={addr})

            # if conflicts (same address) will pick the longer sample of the two
            AddToSampleList(samples, sample) 

            key_min = last_key
            key_max = data[addr+13]

            # key max +1 makes the key ranges always sequential, which matches up better with what S-YXG50 expects
            last_key = key_max + 1 


            wave = Wave(addr, 
                        offset_negative, offset_positive, loop_address, 
                        attenuation=data[addr+0],
                        tune_note=data[addr+1],
                        tune_cent=data[addr+2],
                        key_min=key_min,
                        key_max=key_max,
                        )
            

            waves.append(wave)

            if data[addr+13] >= 0x7F : break

        return (WaveBank(address, waves), samples)



    @override
    # return voice (w/ elements), wavebank, & samples
    def ProcessVoice(self, data : bytes | bytearray, address: int) -> tuple[Voice, dict[str | int, WaveBank], dict[int, Sample]] : 
        assert self.source == MU.MU80
        HEADER_LENGTH = 10
        ELEMENT_LENGTH = 68 # full voice MU80: 78 or 146 bytes

        # these two are flipped compared to syxg/mu50
        element_cnt = data[address] + 1  # + 0. 0=1 element 1=2 element
        volume = data[address+1]         # + 1 

        name = data[address+2 : address + 10].decode(encoding='cp1252') # +2

        elements : list[Element] = []
        wavebanks : dict[str | int, WaveBank] = {} # key = wavedata start addr
        samples : dict[int, Sample] = {} # key = loop address

        for element_address in range(address + HEADER_LENGTH, address + HEADER_LENGTH + (ELEMENT_LENGTH * element_cnt), ELEMENT_LENGTH) : 

            element_data = data[element_address : element_address + ELEMENT_LENGTH]

            wavebankID = element_data[0]

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

        # 30 bytes, very similar to MU50/SYXG50 but not quite the same
        # MU80 has no 'external drumvoice' offset table. Instead, offsets are hard-coded here
        assert self.source == MU.MU80

        address_book : set[int] = set([address]) # * keep a log of our visited addresses for debugging
        drumvoice_data = data[address : address + 30]
        ExternalVoiceOffset = int.from_bytes(drumvoice_data[16 : 16+2], byteorder='big') # always BE
        voice_address : int = 0

        # MU80's external voice value is just a 'hard-coded' voice offset. implicitly *2
        if ExternalVoiceOffset > 0x0000 : 
            voice_address = self.voices.start + (ExternalVoiceOffset * 2)
            address_book.add(voice_address)

        offset_negative = self.decode_bytes(drumvoice_data, 19, bits=16)
        offset_positive = self.decode_bytes(drumvoice_data, 22, bits=16) 
        loop_address = self.decode_bytes(drumvoice_data, 24, bits=24) * 2 # MU80: waverom address implicitly *2

        sample_format = Byte_To_SampleFormat(self.source, drumvoice_data[21]) # +21: sample byte, always C0 or 00
        dpcm_parameters : int = drumvoice_data[27] # +27: DPCM parameters

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









