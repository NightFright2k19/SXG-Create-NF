# Table converters: element / drum voice byte data from each source model to the S-YXG50 layout.
# (merged from cnv_fromBASE / cnv_fromMU50 / cnv_fromMU80 / cnv_fromMU90 / cnv_fromMU1000 / cnv_fromSYXG50)

from table import DrumVoice, Voice, WaveBank, Wave, Sample
from dataenum import *

from abc import abstractmethod
from dataclasses import dataclass
from typing import Literal, override

from utils import fmtbyte, fmtbytes # debug



# -------------------- from BASE --------------------

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



# -------------------- from MU50 --------------------

class fromMU50(TableConverter) : 

    source : MU = MU.MU50
    
    # pre requirements
    # * 1. handle sample associated with this drum voice first
    # * 2. update sample information
    # * 3. If ext voice, update associated voice
    # * 4. lastly, call this and update drum voice using sample / voice
    @override
    def ConvertDrumVoice(self, drum : DrumVoice, sample : Sample | None, ext_voice : Voice | None, target : MU) : 
        # * good for MU80, MU50, S-YXG50
        assert drum.format == MU.MU50 or drum.format == MU.SYXG50 or drum.format == MU.MU80
        assert len(drum.data) == 30
        assert target == MU.SYXG50

        # update addresses beforehand
        assert sample or ext_voice
        if sample : 
            assert sample.format == MU.SYXG50 
            assert sample.out_loop_address >= 0
        
        # MU50 and S-YXG50 drumvoice tables are exactly the same.
        # MU80 tables are close enough to work too.
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
            # sample_format = get_SampleFormat_Target(sample.sample_type, MU.MU50, MU.SYXG50)

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
            # new_data[27] = SampleFormat_to_Byte_SYXG50(sample.sample_type)
            new_data[27] = SampleFormat_to_Byte_SYXG50(sample.out_sample_type)
        
        drum.data = bytes(new_data)
        drum.format = MU.SYXG50


    # modifies elements. the voice's header is simple enough it will be handled in the main loop
    # * wavebank must be handled (and wavedata index assigned) before this
    @override
    def ConvertElements(self, voice : Voice, wavebanks : list[WaveBank], target : MU) -> None : 
        assert target == MU.SYXG50

        assert len(wavebanks) == len(voice.elements)

        # * S-YXG50 element format is a slightly condensed version of the MU50
        # * from 80 -> 78 bytes

        for i, e in enumerate(voice.elements) : 
            assert e.format == MU.MU50
            assert len(e.data) == 80

            # wavedata_index = wavedata_indexes[i]
            wavedata_index = wavebanks[i].index
            assert wavedata_index < 256 and wavedata_index >= 0

            new_data = bytearray(78)
            # MU50 +0 / +1: 8-bit waveID, but with the top bit in +0
            # S-YXG50: combined into a single byte at +0
            new_data[0] = wavedata_index

            # same
            new_data[1:5] = e.data[2:6]

            # MU50 +6: 1-bit LFO something-or-other
            # S-YXG50: condensed into top bit of +5
            LFOthing = e.data[6] << 7
            new_data[5] = LFOthing + e.data[7]

            # MU50 +8 - +80 same as S-YXG50 +6 to +78 (72 bytes)
            new_data[6:78] = e.data[8:80]

            e.data = bytes(new_data)
            e.format = MU.SYXG50

        voice.converted = True



# -------------------- from MU80 --------------------

class fromMU80(TableConverter) : 

    source : MU = MU.MU80

    # modifies elements. the voice's header is simple enough it will be handled in the main loop
    # * wavebank must be handled (and wavedata index assigned) before this
    @override
    def ConvertElements(self, voice : Voice, wavebanks : list[WaveBank], target : MU) -> None : 
        assert target == MU.SYXG50

        assert len(wavebanks) == len(voice.elements)

        # * MU80 element format is quite a bit smaller than the MU50
        # * 68 bytes, vs 80 for MU50
        # however, it's just condensed with values bitsmashed together

        def fourbit_to_S7(n : int) : 
            # many MU80 values are -7 to +7, with 7 being zero. 0-6 - 7 - 8-E
            # center value should become 0x40
            return n - 7 + 64

        for i, e in enumerate(voice.elements) : 
            assert e.format == MU.MU80
            assert len(e.data) == 68

            wavedata_index = wavebanks[i].index
            assert wavedata_index < 256 and wavedata_index >= 0

            new_data = bytearray(78)

            # +0: wave index
            new_data[0] = wavedata_index

            # +1 thru +4: same. note key thresholds, note velocity thresholds
            new_data[1:5] = e.data[1:5]

            # My sources are contradictory
            # I'm not confident enough to start abstracting all the data
            # For this I'm taking Theo Niessink's work on faith
            # but hopefully the values all line up together, even if the descriptions are off
            # * nothing is missing!

            # SXG  +5: top bit: LFO phase init   
            # SXG  +5: bottom two bits: LFO wave type
            # MU80: LFO wave type @+6 top bit   LFO wave type @+5 top two bits
            new_data[5] = (e.data[6] & 0x80) + ((e.data[5] & 0b11000000) >> 6)

            # SXG +6: filter EG velo curve (bottom bit)
            # MU80 EG velo curve @+7 (top bit)
            new_data[6] = e.data[7] >> 7

            # SXG +7: LFO speed
            # MU80 LFO speed +5 (lower six bits)
            new_data[7] = e.data[5] & 0b00111111

            # SXG +8: Vibrato delay time
            # MU80 Vibrato delay time @ +7 (lower 7 bits)
            new_data[8] = e.data[6] & 0x7F 

            # SXG +9: Vibrato fade time
            # MU80 Vibrato fade time @ +7 (lower 7 bits)
            new_data[9] = e.data[7] & 0x7F    

            # SXG +10: LFO pitch mod depth
            # MU80 LFO pitch mod depth @ +8 (lower SIX bits, bits 6-7 are the PEG depth)
            # calibrated against S-YXG50: every S-YXG50 depth >= 0x20 has bit 5 set, the old
            # 5-bit mask halved the vibrato/pitch-LFO depth of voices like Siren, Ghost, Goblins, Wind
            new_data[10] = e.data[8] & 0x3F    

            # SXG +11: LFO filter mod depth
            # MU80 LFO filter mod depth @ +9 (lower 4)
            new_data[11] = e.data[9] & 0x0F  

            # SXG +12: LFO amp mod depth
            # MU80 LFO amp mod depth @ +10 (lower 5)
            new_data[12] = e.data[10] & 0x1F       

            # SXG +13 / +14: pitch envelope Note shift / pitch envelope detune 
            # MU80 @ +11 +12
            new_data[13:15] = e.data[11:13]    

            # SXG +15: Pitch scaling depth
            # MU80 Pitch scaling depth @ +10 (top 3 bits)
            new_data[15] = (e.data[10] & 0b11100000) >> 5

            # SXG +16: Pitch scaling center note
            # MU80 Pitch scaling center note @ +13
            new_data[16] = e.data[13]

            # SXG +17: Pitch EG depth
            # MU80 Pitch EG depth @ +8 (top two bits)
            new_data[17] = (e.data[8] & 0b11000000) >> 6

            # SXG +18: PEG velocity level sens
            # MU80 PEG velocity level sens @ +9 (top 4 bits)
            new_data[18] = fourbit_to_S7((e.data[9] & 0xF0 ) >> 4)

            # SXG +19: PEG velocity rate sens
            # MU80 PEG velocity rate sens @ +14 (top 4 bits)
            new_data[19] = fourbit_to_S7((e.data[14] & 0xF0 ) >> 4)

            # SXG +20: Pitch EG rate scaling
            # MU80 Pitch EG rate scaling @ +14 (lower 4 bits)
            new_data[20] = fourbit_to_S7(e.data[14] & 0x0F    )

            # SXG +21 to +30: Various Pitch EG settings 
            # MU80 +15 to +24
            new_data[21 : 31] = e.data[15 : 25]  

            # SXG +31 to +41: various filter EG settings
            # MU80 +25 to +35
            new_data[31 : 42] = e.data[25 : 36]    

            # SXG +42: FEG velocity level sens
            # MU80 FEG velocity level sens @ +36 (top four bits)
            new_data[42] = fourbit_to_S7((e.data[36] & 0xF0) >> 4)

            # SXG +43: FEG velocity rate sens
            # MU80 FEG velocity rate sens @ +36 (lower four bits)
            new_data[43] = fourbit_to_S7(e.data[36] & 0x0F)

            # SXG +44: Filter EG rate scaling
            # MU80 Filter EG rate scaling @ +37 (lower 4)
            new_data[44] = fourbit_to_S7(e.data[37] & 0x0F  )

            # SXG +45 to +54: various filter EG stuff
            # MU80 +38 to +47
            new_data[45:55] = e.data[38:48]    

            # SXG +55 to +63: Elemenet level and level scaling stuff
            # MU80 +48 to +56
            new_data[55:64] = e.data[48:57]    


            # SXG +64: Velocity curve   0-6
            # MU80 Velocity curve @ +36 (lower four bits)
            # new_data[64] = (e.data[36] & 0xF0) >> 4  # ! wrong
            new_data[64] = (e.data[37] & 0xF0) >> 4

            # SXG +65: Pan   (0 - 14, 15:scaling)
            # MU80 Pan @ +57 (lower 4 bits)
            new_data[65] = e.data[57] & 0x0F   


            # SXG +66: Amp EG rate scaling
            # MU80 Amp EG rate scaling @ +57 (top four)
            new_data[66] = fourbit_to_S7((e.data[57] & 0xF0) >> 4)

            # SXG +67: Amp EG RS center note
            # MU80 Amp EG RS center note @ +58
            new_data[67] = e.data[58]  

            # SXG +68: Amp EG key on delay
            # MU80 Amp EG key on delay @ +59 (lower four bits)
            new_data[68] = e.data[59] & 0x0F  

            # SXG +69 to +74: Amp EG envelope stuff
            # MU80 +60 to +65
            new_data[69:75] = e.data[60:66]   

            # SXG +75 +76
            # MU80 +66 +67 wave offset - 
            new_data[75:77] = e.data[66:68]    

            
            # SXG +77: Resonance sensitivity
            # MU80 Resonance sensitivity @ +59 (top four bits)
            # new_data[77] = (e.data[59] & 0xF0) >> 4  # ! wrong
            new_data[77] = fourbit_to_S7((e.data[59] & 0xF0) >> 4 )


            e.data = bytes(new_data)
            e.format = MU.SYXG50

        voice.converted = True



# -------------------- from MU90 --------------------

DRUM_ATTACK_NOHOLD = 0x60   # see ConvertDrumVoice

# * MU drum decay slope (dB/s) by rate, measured on the S-MU2000 (Seq Click sweep, 9_Drum_Decay_Fast);
# syxg50.dll's decay 2 in the no-hold mode follows the same curve. Below 0x31: halves every 8 steps.
_DECAY_SLOPE = {0x31 : 32, 0x35 : 49, 0x39 : 65, 0x3D : 97, 0x41 : 130, 0x45 : 194, 0x49 : 259, 0x4D : 519,
                0x51 : 713, 0x55 : 1165, 0x59 : 1685, 0x5D : 2585, 0x61 : 3630}
DECAY1_DROP_DB = 0.75       # effective decay 1 share, fitted to Hi Q, Click Noise and Short Guiro (kit level test, S-MU2000)

def drum_decay_slope(rate : int) -> float :
    import math
    pts = sorted(_DECAY_SLOPE.items())
    if rate >= 0x7E : return 1e6
    if rate <= pts[0][0] : return pts[0][1] * 2 ** ((rate - pts[0][0]) / 8)
    if rate >= pts[-1][0] : return pts[-1][1] * 2 ** ((rate - pts[-1][0]) / 8)
    for (r0, s0), (r1, s1) in zip(pts, pts[1:]) :
        if r0 <= rate <= r1 :
            return math.exp(math.log(s0) + (rate - r0) / (r1 - r0) * (math.log(s1) - math.log(s0)))

def fast_decay2_rate(d1 : int, d2 : int) -> int :
    # one decay in the no-hold mode with the energy of the MU's short decay 1 + fast decay 2
    import math
    t1 = DECAY1_DROP_DB / drum_decay_slope(d1)
    target = 4.343 / (t1 + 4.343 / drum_decay_slope(d2))
    return min(range(0x7E), key=lambda r : abs(math.log(drum_decay_slope(r)) - math.log(target)))

class fromMU90(TableConverter) : 

    source : MU = MU.MU90

    # todo some drum voices use a 17th bit for sample length, they will be clamped to FFFF for now
    # todo this can be potentially worked around by using external voices
    # todo and it may be possible to apply the EQ stuff that way too
    @override
    def ConvertDrumVoice(self, drum : DrumVoice, sample : Sample | None, ext_voice : Voice | None, target : MU) : 

        assert drum.format == MU.MU90
        assert target == MU.SYXG50
        assert len(drum.data) == 42

        # update addresses beforehand
        assert sample or ext_voice
        if sample : 
            assert sample.format == MU.SYXG50 
            assert sample.out_loop_address >= 0
        
        # * MU90 drum tables are expanded to 42 bytes, up from 30 on the MU80/50
        # changes:         
        #  8        +16 - +23: 1 blank + 7 new EQ parameters
        #  9        +29: blank column
        # 10        +30: unknown parameters (mirrors similar unknown data in wavedata table)
        # 11        +31: 24-bit MSB for sample-
        # 12        +34: top bit = play backwards (wavedata table mirror)

        # up to +15 is identical
        new_data = bytearray(drum.data[0:30])
        for i in range(16, 30) : new_data[i] = 0

        # * drum EG rate (byte 13): same rule as the MU80 (see TableConverter), calibrated with
        # analyze_drum_eg.py: S-YXG50 = MU90 - 0x21 for 426 of 460 matched drum voices
        if not ext_voice : 
            new_data[13] = max(0, new_data[13] - 0x21)
            # * instant attack (0x7F) with decay 1 = decay 2: syxg50.dll holds the key at full level for
            # 18-120 ms before the decay starts (rate dependent), the MU starts decaying after 2-15 ms
            # (S-MU2000, Seq Click sweep 0x31-0x61). Attack bytes 0x60-0x77 select a mode of
            # syxg50.dll without that hold, which goes straight to decay 2, so it is exact when both
            # decay rates are the same (Seq Click: 4-7 dB too loud before, now within 1-2 dB).
            if drum.data[13] == 0x7F and drum.data[14] == drum.data[15] : 
                new_data[13] = DRUM_ATTACK_NOHOLD
            # * fast decay 2 (0x7E = cut, or 0x50.. after a decay 1 below 0x40) after a decay 1 of 0x30 or
            # faster: the MU plays decay 1 only briefly (~1-2 dB) and then decay 2, syxg50.dll adds its
            # hold first (Hi Q, Click Noise, Short Guiro: 3.5-7.5 dB too much energy). No-hold mode with
            # one decay of the same energy instead. Slower decay 1 (one-shot percussion with decay 2 =
            # 0x7E) and Mute Triangle (0x43/0x53) already match and stay as they are.
            elif drum.data[13] == 0x7F and drum.data[14] >= 0x30 and \
                 (drum.data[15] >= 0x7E or (0x50 <= drum.data[15] and drum.data[14] < 0x40)) : 
                new_data[13] = DRUM_ATTACK_NOHOLD
                new_data[14] = new_data[15] = fast_decay2_rate(drum.data[14], drum.data[15])
        
        # +16: external voice seqID MSB 
        # +17: external voice seqID LSB
        if ext_voice : 
            assert ext_voice.converted
            assert ext_voice.extvoice_index >= 0
            new_data[16:16+2] = ext_voice.extvoice_index.to_bytes(2, byteorder='big', signed=False)

        elif sample : 
            
            assert sample.out_sample_type != SampleFormat.UNKNOWN

            # SXG +18: something-or-other
            # MU90 something-or-other @ +26
            new_data[18] = drum.data[26]

            # SXG +28 +29: something-or-other 8-bit value
            # MU90 something-or-other @ +27 +28
            new_data[28] = drum.data[27]
            new_data[29] = drum.data[28]


            # +16 0xFFFF means use internal sample 
            new_data[16] = 0xFF
            new_data[17] = 0xFF

            # +19: offset negative
            # +20: offset negative
            # * syxg50.dll only has 16 bits for the drum start offset. Four XG open hi-hats have a
            # 70,626 sample body: instead of cutting off the attack (old behaviour), the loop start is
            # moved earlier by the excess, so the sound starts at its real beginning and the loop
            # covers the extra part of the tail (hi-hat noise, the longer loop is inaudible)
            offsetminus = drum.offset_negative
            offsetplus = drum.offset_positive
            loop_address = sample.out_loop_address
            import buildtarget
            if offsetminus > 0xFFFF and not buildtarget.SYXG50_BIG : 
                shift = offsetminus - 0xFFFF
                bps = 1 if sample.out_sample_type in (SampleFormat.U8, SampleFormat.S8) else 2
                print(f'cnv_mu90 info: drum body {offsetminus} > 65535, loop start moved {shift} samples earlier')
                offsetminus = 0xFFFF
                offsetplus = offsetplus + shift
                loop_address = loop_address - shift * bps

            new_data[19:19+2] = min(offsetminus, 0xFFFF).to_bytes(2, byteorder='big', signed=False) # big layout: full value written by ToBigDrumVoice

            # +21: offset positive msb, maybe
            # +22: offset positive
            # +23: offset positive
            new_data[21:21+3] = offsetplus.to_bytes(3, byteorder='big', signed=False)

            # +24: loop address
            # +25: loop address
            # +26: loop address
            new_data[24:24+3] = (loop_address & 0xFFFFFF).to_bytes(3, byteorder='big', signed=False) # big layout: 32-bit value written by ToBigDrumVoice

            # +27: sample type
            new_data[27] = SampleFormat_to_Byte_SYXG50(sample.out_sample_type)

        
        drum.data = bytes(new_data)
        drum.format = MU.SYXG50



    # modifies elements. the voice's header is simple enough it will be handled in the main loop
    # * wavebank must be handled (and wavedata index assigned) before this
    @override
    def ConvertElements(self, voice : Voice, wavebanks : list[WaveBank], target : MU) -> None : 
        assert target == MU.SYXG50

        assert len(wavebanks) == len(voice.elements)

        # * MU90 element format is the MU80 element format, but padded by one byte
        # the only addition is expansion of the wave# to two bytes at +0/+1. 
        # This expanded wave# value works just like the MU50 (handled in decMU90, not here)
        # the last column appears to be unused, perhaps added just to keep the len even
        # * 70 bytes

        def fourbit_to_S7(n : int) : 
            # many MU80/MU90 values are -7 to +7, with 7 being zero. 0-6 - 7 - 8-E
            # center value should become 0x40
            return n - 7 + 64

        for i, e in enumerate(voice.elements) : 
            assert e.format == MU.MU90
            assert len(e.data) == 70

            wavedata_index = wavebanks[i].index
            assert wavedata_index < 256 and wavedata_index >= 0

            new_data = bytearray(78)

            # +0: wave index
            new_data[0] = wavedata_index

            # ! from here, MU90 is just MU80 offset by +1
            # +1 thru +4: same. note key thresholds, note velocity thresholds
            new_data[1:5] = e.data[2:6]

            # SXG  +5: top bit: LFO phase init   
            # SXG  +5: bottom two bits: LFO wave type
            # MU80: LFO wave type @+6 top bit   LFO wave type @+5 top two bits
            new_data[5] = (e.data[7] & 0x80) + ((e.data[6] & 0b11000000) >> 6)

            # SXG +6: filter EG velo curve (bottom bit)
            # MU80 EG velo curve @+7 (top bit)
            new_data[6] = e.data[8] >> 7

            # SXG +7: LFO speed
            # MU80 LFO speed +5 (lower six bits)
            new_data[7] = e.data[6] & 0b00111111

            # SXG +8: Vibrato delay time
            # MU80 Vibrato delay time @ +7 (lower 7 bits)
            new_data[8] = e.data[7] & 0x7F 

            # SXG +9: Vibrato fade time
            # MU80 Vibrato fade time @ +7 (lower 7 bits)
            new_data[9] = e.data[8] & 0x7F    

            # SXG +10: LFO pitch mod depth
            # MU80 LFO pitch mod depth @ +8 (lower six bits, same fix as fromMU80)
            new_data[10] = e.data[9] & 0x3F    

            # SXG +11: LFO filter mod depth
            # MU80 LFO filter mod depth @ +9 (lower 4)
            new_data[11] = e.data[10] & 0x0F  

            # SXG +12: LFO amp mod depth
            # MU80 LFO amp mod depth @ +10 (lower 5)
            new_data[12] = e.data[11] & 0x1F       

            # SXG +13 / +14: pitch envelope Note shift / pitch envelope detune 
            # MU80 @ +11 +12
            new_data[13:15] = e.data[12:14]    

            # SXG +15: Pitch scaling depth
            # MU80 Pitch scaling depth @ +10 (top 3 bits)
            new_data[15] = (e.data[11] & 0b11100000) >> 5

            # SXG +16: Pitch scaling center note
            # MU80 Pitch scaling center note @ +13
            new_data[16] = e.data[14]

            # SXG +17: Pitch EG depth
            # MU80 Pitch EG depth @ +8 (top two bits)
            new_data[17] = (e.data[9] & 0b11000000) >> 6

            # SXG +18: PEG velocity level sens
            # MU80 PEG velocity level sens @ +9 (top 4 bits)
            new_data[18] = fourbit_to_S7((e.data[10] & 0xF0 ) >> 4)

            # SXG +19: PEG velocity rate sens
            # MU80 PEG velocity rate sens @ +14 (top 4 bits)
            new_data[19] = fourbit_to_S7((e.data[15] & 0xF0 ) >> 4)

            # SXG +20: Pitch EG rate scaling
            # MU80 Pitch EG rate scaling @ +14 (lower 4 bits)
            new_data[20] = fourbit_to_S7(e.data[15] & 0x0F    )

            # SXG +21 to +30: Various Pitch EG settings 
            # MU80 +15 to +24
            new_data[21 : 31] = e.data[16 : 26]  

            # SXG +31 to +41: various filter EG settings
            # MU80 +25 to +35
            new_data[31 : 42] = e.data[26 : 37]    

            # SXG +42: FEG velocity level sens
            # MU80 FEG velocity level sens @ +36 (top four bits)
            new_data[42] = fourbit_to_S7((e.data[37] & 0xF0) >> 4)

            # SXG +43: FEG velocity rate sens
            # MU80 FEG velocity rate sens @ +36 (lower four bits)
            new_data[43] = fourbit_to_S7(e.data[37] & 0x0F)

            # SXG +44: Filter EG rate scaling
            # MU80 Filter EG rate scaling @ +37 (lower 4)
            new_data[44] = fourbit_to_S7(e.data[38] & 0x0F  )

            # SXG +45 to +54: various filter EG stuff
            # MU80 +38 to +47
            new_data[45:55] = e.data[39:49]    

            # SXG +55 to +63: Elemenet level and level scaling stuff
            # MU80 +48 to +56
            new_data[55:64] = e.data[49:58]    


            # SXG +64: Velocity curve   0-6
            # MU80 Velocity curve @ +37 (lower four bits)
            new_data[64] = (e.data[38] & 0xF0) >> 4

            # SXG +65: Pan   (0 - 14, 15:scaling)
            # MU80 Pan @ +57 (lower 4 bits)
            new_data[65] = e.data[58] & 0x0F   


            # SXG +66: Amp EG rate scaling
            # MU80 Amp EG rate scaling @ +57 (top four)
            new_data[66] = fourbit_to_S7((e.data[58] & 0xF0) >> 4)

            # SXG +67: Amp EG RS center note
            # MU80 Amp EG RS center note @ +58
            new_data[67] = e.data[59]  

            # SXG +68: Amp EG key on delay
            # MU80 Amp EG key on delay @ +59 (lower four bits)
            new_data[68] = e.data[60] & 0x0F  

            # SXG +69 to +74: Amp EG envelope stuff
            # MU80 +60 to +65
            new_data[69:75] = e.data[61:67]   

            # SXG +75 +76
            # MU80 +66 +67 wave offset - 
            new_data[75:77] = e.data[67:69]    

            # SXG +77: Resonance sensitivity
            # MU80 Resonance sensitivity @ +59 (top four bits)
            new_data[77] = fourbit_to_S7((e.data[60] & 0xF0) >> 4 )


            e.data = bytes(new_data)
            e.format = MU.SYXG50

        voice.converted = True



# -------------------- from MU1000 --------------------

# * MU1000 (MU128 engine) elements are the S-YXG50 element layout almost 1:1 (see decMU1000).
# Drum voices are converted to the MU90 layout by decMU1000, so the MU90 drum conversion is reused.
class fromMU1000(fromMU90) : 

    @override
    def ConvertElements(self, voice : Voice, wavebanks : list[WaveBank], target : MU) -> None : 
        assert target == MU.SYXG50
        assert len(wavebanks) == len(voice.elements)
        for i, e in enumerate(voice.elements) : 
            assert len(e.data) == 84
            wavedata_index = wavebanks[i].index
            assert 0 <= wavedata_index < 256
            s = e.data
            new_data = bytearray(78)
            new_data[0] = wavedata_index
            new_data[1:5] = s[2:6]                              # key / velocity limits
            new_data[5] = s[7] | (0x80 if s[6] else 0)          # LFO wave, + phase init in the top bit
            new_data[6:78] = s[8:80]                            # everything else, same order
            e.data = bytes(new_data)
            e.format = MU.SYXG50
        voice.converted = True



# -------------------- from SYXG50 --------------------

class fromSYXG50(TableConverter) : 

    source : MU = MU.SYXG50

    # modifies elements. the voice's header is simple enough it will be handled in the main loop
    # * wavebank must be handled (and wavedata index assigned) before this
    @override
    def ConvertElements(self, voice : Voice, wavebanks : list[WaveBank], target : MU) -> None : 

        # * already formatted correctly, all that's necessary is to insert the new wavedata.index
        assert target == MU.SYXG50

        assert len(wavebanks) == len(voice.elements)

        for i, e in enumerate(voice.elements) : 
            assert e.format == MU.SYXG50
            assert len(e.data) == 78

            new_data = bytearray(e.data)

            assert wavebanks[i].index < 256 and wavebanks[i].index >= 0
            new_data[0] = wavebanks[i].index

            e.data = bytes(new_data)
            e.format = MU.SYXG50

        voice.converted = True
