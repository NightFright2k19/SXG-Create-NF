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

            # Amp EG attack NightFright2k19
            # S-YXG50 (and presumably MU50) Amp EG Attack implicitly + 0x21 
            if drum.format == MU.MU80 : 
                new_data[13] = max(0, new_data[13] - 0x21)

            # +16 0xFFFF means use internal sample 
            new_data[16] = 0xFF
            new_data[17] = 0xFF

            # +19: offset negative
            # +20: offset negative
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
            new_data[27] = SampleFormat_to_Byte_SYXG50(sample.out_sample_type)


        
        drum.data = bytes(new_data)
        drum.format = MU.SYXG50

    @abstractmethod
    def ConvertElements(self, voice : Voice, wavebanks : list[WaveBank], target : MU) -> None : 
        raise NotImplementedError()