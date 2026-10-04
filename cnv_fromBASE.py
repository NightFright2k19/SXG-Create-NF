from table import DrumVoice, Voice, WaveBank, Wave, Sample
from dataenum import *

from abc import abstractmethod
# from dataclasses import dataclass
from dataclasses import dataclass

from utils import fmtbyte, fmtbytes # debug

# base class for table converters (drumvoice / voice byte data)
# mostly just shuffles bytes around, if anything needs abstraction it should be handled elsewhere

# functions with overrides
# ConvertDrumVoices
# ConvertElements

# .. that's it, wavedata is abstracted by decwhatever immediately, and voice header (it's only 2 bytes) is handled by makewhatever

# * big S-YXG50 drum voice layout (see buildtarget.py)
def ToBigDrumVoice(new_data : bytearray, drum : DrumVoice, sample : Sample | None, ext_voice : Voice | None) -> bytearray : 
    out = bytearray(new_data)
    # root key: +0x12 in the classic layout, +0x0A in the big layout
    out[10] = new_data[18]
    if ext_voice : 
        # +16..+17: ext voice index, 16-bit LE (+17 must not be 0xFF)
        assert ext_voice.extvoice_index < 0xFF00
        out[16:18] = ext_voice.extvoice_index.to_bytes(2, 'little')
        for i in range(18, 30) : 
            out[i] = 0x00
    else : 
        assert sample is not None
        out[16] = 0xFF
        out[17] = 0xFF
        # +18..+20: start offset 24-bit BE, +21..+23: loop length 24-bit BE
        out[18:21] = drum.offset_negative.to_bytes(3, 'big')
        out[21:24] = drum.offset_positive.to_bytes(3, 'big')
        # +24..+27: byte address (30 bits), top two bits = sample format (0x80 = 8 bit)
        assert sample.out_loop_address < 0x40000000, 'drum sample beyond 1 GB'
        fmt = SampleFormat_to_Byte_SYXG50(sample.out_sample_type) & 0xC0
        out[24:28] = (sample.out_loop_address | (fmt << 24)).to_bytes(4, 'big')
    return out


@dataclass
class TableConverter : 

    source : MU = MU.UNDEFINED

    # pre requirements
    # * 1. handle sample associated with this drum voice first
    # * 2. update sample information
    # * 3. If ext voice, update associated voice
    # * 4. lastly, call this and update drum voice using sample / voice

    # * base implementation: good for MU80, MU50, S-YXG50
    @abstractmethod
    def ConvertDrumVoice(self, drum : DrumVoice, sample : Sample | None, ext_voice : Voice | None, target : MU) : 

        assert drum.format == MU.MU50 or drum.format == MU.SYXG50 or drum.format == MU.MU80
        assert len(drum.data) == 30
        assert target == MU.SYXG50

        # update addresses beforehand
        assert sample or ext_voice
        if sample : 
            assert sample.format == MU.SYXG50 
            assert sample.out_loop_address >= 0
        
        # MU50 and S-YXG50 drumvoice tables are exactly the same.
        # MU80 tables are close enough to work too
        # all multi-byte values are big endian
        new_data = bytearray(drum.data)

        # +16: external voice seqID MSB 
        # +17: external voice seqID LSB
        if ext_voice : 
            assert ext_voice.converted
            assert ext_voice.extvoice_index >= 0
            new_data[16:16+2] = ext_voice.extvoice_index.to_bytes(2, byteorder='big', signed=False)

            #  if ext voice is used, the rest of the table should be blank
            for i in range(18, 30) : 
                new_data[i] = 0x00

        elif sample : 
            
            assert sample.out_sample_type != SampleFormat.UNKNOWN

            # todo workaround for curious amp EG issue with MU80 tables
            # +13=0x7F appears to be a bad value in S-YXG50, drum samples sound cut off
            # this isn't a great solution, but it is confirmable against S-YXG50/MU50 tables
            # they usually use 0x5E. 0x60+ seems to break.
            # new_data[13] = 0x5E if new_data[13] == 0x7F else new_data[13]
            # todo experimental heuristic: if 14 is < 0x30, then subtract 32 (0x7F->0x5F)
            # new_data[13] = new_data[13]-32 if new_data[13] > 0x60 and new_data[14] < 0x30 else new_data[13]

            # * drum EG rate (byte 13), calibrated against the S-YXG50 table (same kit and key):
            # the MU80 stores this rate including the +0x21 offset that syxg50.dll adds itself
            # (0x7F on the MU80 = 0x5E in S-YXG50). S-YXG50 = MU80 - 0x21 for 245 of 253 matched
            # drum voices, the 8 others are sounds Yamaha re-voiced for S-YXG50.
            # Without this, raw values >= 0x60 put the drum envelope into a special state in
            # syxg50.dll, which is what made MU80 drums sound cut off.
            if self.source == MU.MU80 : 
                new_data[13] = max(0, new_data[13] - 0x21)


            # +16 0xFFFF means use internal sample 
            new_data[16] = 0xFF
            new_data[17] = 0xFF

            # +19: offset negative
            # +20: offset negative
            # ! use encapsulated drum offsets, not sample offset
            new_data[19:19+2] = drum.offset_negative.to_bytes(2, byteorder='big', signed=False) 

            # +21: offset positive msb, maybe
            # +22: offset positive
            # +23: offset positive
            new_data[21:21+3] = drum.offset_positive.to_bytes(3, byteorder='big', signed=False)

            # +24: loop address
            # +25: loop address
            # +26: loop address
            new_data[24:24+3] = sample.out_loop_address.to_bytes(3, byteorder='big', signed=False)

            # +27: sample type
            # new_data[27] = SampleFormat_to_Byte_SYXG50(sample.sample_type)
            new_data[27] = SampleFormat_to_Byte_SYXG50(sample.out_sample_type)

            if new_data[23] == 0x07 : 
                test = fmtbytes(new_data)
                assert True
        
        drum.data = bytes(new_data)
        drum.format = MU.SYXG50

    @abstractmethod
    def ConvertElements(self, voice : Voice, wavebanks : list[WaveBank], target : MU) -> None : 
        raise NotImplementedError()