

from table import DrumVoice, Voice, WaveBank, Wave, Sample
from dataenum import *

from cnv_fromBASE import TableConverter
from typing import Literal, override
from utils import fmtbyte, fmtbytes

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

        # * drum EG rate (byte 13): same rule as the MU80 (see cnv_fromBASE), calibrated with
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
            # MU80 LFO pitch mod depth @ +8 (lower six bits, same fix as cnv_fromMU80)
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
