
from decBase import *

from utils import fmtbyte, fmtbytes

# * MU90 wave ROMs: xs518a0 and xs743a0 are two 16-bit halves of one 32-bit data bus.
# Word n = xs518a0[2n:2n+2] + xs743a0[2n:2n+2], read as a little-endian byte stream.
# (verified: 8-bit, 12-bit, 16-bit and ADPCM samples all decode to smooth audio this way,
# and consecutive samples line up back to back with only 1-4 words of padding in between)
def MU90_Waverom(rom_a : bytes, rom_b : bytes) -> bytes :
    assert len(rom_a) == len(rom_b)
    out = bytearray(len(rom_a) * 2)
    for i in range(0, len(rom_a), 2) :
        out[2*i : 2*i+2] = rom_a[i : i+2]
        out[2*i+2 : 2*i+4] = rom_b[i : i+2]
    return bytes(out)


# * "backwards" flag (wavedata +8 / drum voice +34, bit 7): the hardware plays the sample in
# reverse, starting at the loop address. Yamaha uses this both ways: the tom sample is stored
# backwards in the ROM and only sounds right with the flag (toms 47/48/50 of the standard kits,
# MelodTom, Real Tom), while the same data without the flag gives Rev Tom / Rev Kick etc.
# The reversed copy gets its own sample-pool key; the data is reversed on conversion
# (SampleConvert.ConvertSample). The reversed sample is a one-shot.
REVERSED_KEY = 0x40000000

def Make_Reversed(sample : Sample) -> tuple[Sample, int, int] :
    sample.reverse = True
    sample.src_offset_negative = sample.offset_negative
    sample.src_offset_positive = sample.offset_positive
    sample.address_src = sample.loop_address + REVERSED_KEY
    sample.offset_negative = sample.offset_negative + sample.offset_positive
    sample.offset_positive = 0
    return sample, sample.offset_negative, sample.offset_positive


@dataclass
class MU90(MUdecoder) : 

    # bankorder_voice : list[Bank] = [Bank.GS, Bank.SFX, Bank.XG]
    # bankorder_drums : list[Bank] = [Bank.GS_DRUMS, Bank.XG_DRUMS, Bank.SFX_DRUMS]
    # * voice bank map order on the MU90 is XG (LSB), SFX (MSB), GS (verified: the first row holds the
    # XG LSB numbers 1,3,6,8,12,..,96-101, the last one the GS variation numbers 1-11,16,24,32,40,126,127)
    bankorder_voice : list[Bank] = field(default_factory=lambda : [Bank.XG, Bank.SFX, Bank.GS] )
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

            # * MU90 wave ROM layout (verified against the ROM data, 2026-09-30):
            #   the two wave ROMs form 32-bit words: bytes 0-1 from xs518a0, bytes 2-3 from xs743a0
            #   (see MU90_Waverom). The loop address counts these 32-bit words -> byte address * 4.
            #   Offsets (+5 body, +9 loop) are plain sample counts, like on the MU80.
            #   Samples are packed back to back, format-dependent: 16 bit = 2 bytes, 12 bit = LE
            #   bit stream (3 bytes per 2 samples, same as MU50), 8 bit and ADPCM = 1 byte.
            mu90_plus4 = data[addr + 4]

            offset_negative = self.decode_bytes(data,addr+5, 24, 'big')
            offset_positive = self.decode_bytes(data,addr+9, 24, 'big')
            loop_address = self.decode_bytes(data,addr+13, 24, 'big') * 4
            sample_byte = data[addr+12] & 0xC0
            sample_format = Byte_To_SampleFormat(self.source, sample_byte)
            assert sample_format != SampleFormat.UNKNOWN
            ADPCM_params = (data[addr+12] & 0b00111110) >> 1
            backwards = bool(data[addr+8] & 0x80)

            sample = Sample(loop_address, offset_negative, offset_positive, loop_address, sample_format,
                            encoding_parameters=ADPCM_params, format=self.source, address_book={addr})
            if backwards :
                sample, offset_negative, offset_positive = Make_Reversed(sample)

            AddToSampleList(samples, sample) # will only add the longer sample if clipped

            key_min = last_key
            key_max = data[addr+3]
            last_key = key_max + 1 # + 1 is more in line with what s-yxg50 expects, always sequential key ranges

            wave = Wave(addr,
                        offset_negative, offset_positive, sample.address_src,
                        attenuation=data[addr+0],
                        tune_note=data[addr+1],
                        tune_cent=data[addr+2],
                        key_min=key_min,
                        key_max=key_max,
                        mu90_plus4=mu90_plus4,
                        backwards=backwards,
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


        # * the sample part (+30..+41) mirrors the wavedata entry (+4..+15):
        #   +30 unknown (= wavedata +4), +31..+33 body, +34 bit 7 = backwards, +35..+37 loop,
        #   +38 format / ADPCM parameters, +39..+41 loop address in 32-bit words
        sample_format = Byte_To_SampleFormat(self.source, drumvoice_data[38] & 0xC0)
        dpcm_parameters : int = (drumvoice_data[38] & 0x3E) >> 1

        offset_negative = self.decode_bytes(drumvoice_data, 31, bits=24)
        offset_positive = self.decode_bytes(drumvoice_data, 35, bits=24)
        loop_address = self.decode_bytes(drumvoice_data, 39, bits=24) * 4

        address_book.add(address)

        sample = Sample(loop_address, offset_negative, offset_positive, loop_address, sample_format,
                        encoding_parameters=dpcm_parameters,
                        format=self.source,
                        address_book=set(address_book))
        if drumvoice_data[34] & 0x80 :
            sample, offset_negative, offset_positive = Make_Reversed(sample)

        drumvoice = DrumVoice(drumvoice_data, sample.address_src, voice_address,
                              offset_negative, offset_positive,
                              format=self.source,
                              address_book=set(address_book),)

        
        return voice_address, drumvoice, sample



