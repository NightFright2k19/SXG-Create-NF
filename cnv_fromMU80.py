

from table import DrumVoice, Voice, WaveBank, Wave, Sample
from dataenum import *

from cnv_fromBASE import TableConverter
from typing import Literal, override

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
