from table import Voice, WaveBank
from dataenum import *
from cnv_fromMU90 import fromMU90
from typing import override

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
