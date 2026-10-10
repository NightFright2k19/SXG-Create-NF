
from dataclasses import dataclass
from dataenum import MU
import dataenum
from pathlib import Path
from typing import Self, Literal

@dataclass
class TableIn() : 
    source : MU
    name : str
    program_roms : dict[str,str] # crc, description
    waveroms : dict[str, str]
    support : Literal['decode','encode','both','neither'] = 'neither'

    def Can_Decode(self) -> bool : 
        if self.support == 'decode' or self.support=='both' : return True
        return False

    def Is_Ours(self, crc : str) -> bool : 
        if crc in self.program_roms : return True
        if crc in self.waveroms : return True
        return False

    def Is_List_Ours(self, paths : dict[str, Path]) -> bool : 
        if len(paths) < len(self.program_roms) + len(self.waveroms) : return False

        for prg_crc in self.program_roms.keys() : 
            if prg_crc not in paths.keys() : 
                return False
        for waverom_crc in self.waveroms.keys() : 
            if waverom_crc not in paths.keys() :
                return False

        return True

    def Order_Pathlists(self, paths : dict[str, Path]) -> tuple[list[Path],list[Path]] : 
        assert len(paths) >= len(self.program_roms) + len(self.waveroms)
        out_prg : list[Path] = []
        out_waves : list[Path] = []
        for prg_crc in self.program_roms.keys() : 
            for crc, p in paths.items() : 
                if crc == prg_crc : 
                    out_prg.append(p)
        for waverom_crc in self.waveroms.keys() : 
            for crc, p in paths.items()  : 
                if crc == waverom_crc : 
                    out_waves.append(p)
        assert len(out_prg) + len(out_waves) == len(self.program_roms) + len(self.waveroms)
        return (out_prg, out_waves)

    def __str__(self) -> str : 
        return f'{self.name}: {[f'{name} CRC32={crc}' for (crc, name) in self.program_roms.items()]} \
        waveroms: {[f'{name} CRC32={crc}' for (crc, name) in self.waveroms.items()]}'



ROMLIST : list[TableIn] = [
TableIn(dataenum.MU.SYXG50, 'S-YXG50 2.0MB Encrypted', program_roms={'B23C8878' : 'SXG50 2MB.TBL'}, waveroms={'BC2AA577' : 'S-YXG50 2MB (ENCRYPTED).TBL'}, support='neither'),
TableIn(dataenum.MU.SYXG50, 'S-YXG50 4.1MB Decrypted', program_roms={'32919DF0' : 'SXGBIN41.TBL'}, waveroms={'10F63E24' : 'SXGWAVE4.TBL'}, support='neither'),
TableIn(dataenum.MU.SYXG50, 'Vampire.dll', program_roms={'6D4930CC' : 'Vampire.dll'}, waveroms={'8E49DE70' : 'Vampire.bsm'}, support='neither'),
TableIn(dataenum.MU.MU80, 'MU80 xq556a0 v1.04, 1994-12-04', program_roms={'C31074C0' : 'yamaha_mu80.bin'}, waveroms={'CB454418' : 'xq012b0-822.bin',
                                                                                                        'F14117B4' : 'xq013b0-823.bin',
                                                                                                        '0ADBF203' : 'xq089b0-824.bin',
                                                                                                        '34C422B3' : 'xq090b0-825.bin',
                                                                                                        }, support='decode'),

TableIn(dataenum.MU.MU90, 'MU90 xs519d0 v1.01, 1996-11-27', program_roms={'6FC85B41' : 'xs519d0.ic9'}, waveroms={'2550D44F' : 'xs518a0.ic22',
                                                                                                        'A9109A6C' : 'xs743a0.ic23',
                                                                                                        }, support='decode'),
TableIn(dataenum.MU.MU90, 'MU90B xt040c0 v1.01, 2005-12-26', program_roms={'66FE5896' : 'xt040c0.ic9'}, waveroms={'2550D44F' : 'xs518a0.ic22',
                                                                                                        'A9109A6C' : 'xs743a0.ic23',
                                                                                                        }, support='decode'),
TableIn(dataenum.MU.MU100, 'MU100 xu50720 v1.11, 1999-08-03', program_roms={'1126A8A4' : 'xu50720.ic11'}, waveroms={'2550D44F' : 'xs518b0.ic34',
                                                                                                        'A9109A6C' : 'xs743b0.ic35',
                                                                                                        '225C2280' : 'xt445a0-828.ic36',
                                                                                                        'A1D138A3' : 'xt461a0-829.ic37',
                                                                                                        '2E82CBD4' : 'xt462a0.ic39',
                                                                                                        'CCE5F8D3' : 'xt463a0.ic38',
                                                                                                        }, support='decode'),
TableIn(dataenum.MU.MU128, 'MU128 v2.00', program_roms={'2891487B' : 'mu128-v2.00-h.bin', 'CC236DC4' : 'mu128-v2.00-l.bin'}, 
                                                         waveroms={'CDA1AFD6' : 'xv364a0.ic53', '10985ED0' : 'xv365a0.ic54',
                                                                   '781DFAC6' : 'xv366a0.ic57', '91A7533B' : 'xv376a0.ic58',}, support='decode'),
TableIn(dataenum.MU.MU1000, 'MU1000 v2.01', program_roms={'D0809297' : 'mu1000-v2.01-h.bin', '048A2750' : 'mu1000-v2.01-l.bin'}, 
                                                         waveroms={'CDA1AFD6' : 'xv364a0.ic49', '10985ED0' : 'xv365a0.ic50',
                                                                   '34913E42' : 'xw848a0.ic53', '3728F1F2' : 'xw849a0.ic54',}, support='decode'),
TableIn(dataenum.MU.MU2000, 'MU2000 v2.01', program_roms={'BE3668F6' : 'mu2000-v2.01-h.bin', '55921A50' : 'mu2000-v2.01-l.bin'}, 
                                                         waveroms={'CDA1AFD6' : 'xv364a0.ic49', '10985ED0' : 'xv365a0.ic50',
                                                                   '34913E42' : 'xw848a0.ic53', '3728F1F2' : 'xw849a0.ic54',}, support='decode'),
TableIn(dataenum.MU.MU50, 'MU50 xr174c0 v1.05, 1995-08-21', program_roms={'902520A4' : 'xr174c0.ic7'}, waveroms={'D4ADBC7E' : 'xq057c0.ic18',
                                                                                                                '7B68F475' : 'xq058c0.ic19'}, support='decode'),
]
# TableIn('TABLENAMETABLENAME', program_roms={'CRCRCC' : 'NAMENAMENAME'}, waveroms={'CRCRCRCRC' : 'DESCDESCDESC',}, support='neither'),



@dataclass
class name_crc_old() : 
    name : str
    crc32 : str

@dataclass 
class ti_old() : 
    name : str
    roms_crc32 : list[name_crc_old]
    support : Literal['decode','encode','both','neither'] = 'neither'

# TableInput('PRG_MU50 v1.02 1995-04-20.bin', '6FE5BDF5', []),
# TableInput('PRG_MU50 v1.04 1995-05-22.bin', '507168AD', []),
# TableInput('PRG_MU50 v1.05 1995-08-21.bin', '902520A4', []),



VALIDROMS : list[ti_old] = [
ti_old('S-YXG50 2.0MB Encrypted', [name_crc_old('S-YXG50 2MB.TBL', 'B23C8878'), name_crc_old('S-YXG50 2MB (ENCRYPTED).TBL', 'BC2AA577'), ]),
ti_old('S-YXG50 4.1MB Decrypted', [name_crc_old('SXGBIN41.TBL', '32919DF0'), name_crc_old('SXGWAVE4.TBL', '10F63E24'), ]),
ti_old('S-YXG50_VEG.dll (w embedded tables)', [name_crc_old('S-YXG50.dll','80EFA471')]),
ti_old('Vampire.dll', [name_crc_old('Vampire.dll', '6D4930CC'), name_crc_old('Vampire.bsm', '8E49DE70'), ]),
ti_old('MU80 xq556a0 (v1.04, Dec. 04, 1994)', [name_crc_old('yamaha_mu80.bin', 'C31074C0'), 
                                                   name_crc_old('xq012b0-822.bin', 'CB454418'), 
                                                   name_crc_old('xq013b0-823.bin', 'F14117B4'), 
                                                   name_crc_old('xq089b0-824.bin', '0ADBF203'), 
                                                   name_crc_old('xq090b0-825.bin', '34C422B3'), ]),
ti_old('MU50 v1.02 1995-04-20',  [name_crc_old('xq332e0','6FE5BDF5'),
                                      name_crc_old('xq057c0.ic18', 'D4ADBC7E'), 
                                      name_crc_old('xq058c0.ic19', '7B68F475'), ]),
ti_old('MU50 xr174c0 v1.05 1995-08-21', [name_crc_old('xr174c0.ic7', '902520A4'), 
                                             name_crc_old('xq057c0.ic18', 'D4ADBC7E'), 
                                             name_crc_old('xq058c0.ic19', '7B68F475'), ]),
ti_old('MU50 v1.04 1995-05-22', [name_crc_old('yamaha_mu50.bin', '507168AD'), 
                                     name_crc_old('xq057c0.ic18', 'D4ADBC7E'), 
                                     name_crc_old('xq058c0.ic19', '7B68F475'), ]),
ti_old('MU50 v1.02 1995-04-20', [name_crc_old('xq332e0.bin', '6FE5BDF5'), 
                                     name_crc_old('xq057c0.ic18', 'D4ADBC7E'), 
                                     name_crc_old('xq058c0.ic19', '7B68F475'), ]),

ti_old('MU90 xs519d0 (v1.01, Nov. 27, 1996)', [name_crc_old('xs519d0.ic9', '6FC85B41'), 
                                                   name_crc_old('xs743a0.ic23', 'A9109A6C'), 
                                                   name_crc_old('xs518a0.ic22', '2550D44F'), ]),
ti_old('MU90B xt040c0 (v1.01, Dec. 26, 2005)', [name_crc_old('xt040c0.ic9_mu90b', '66FE5896'), 
                                                    name_crc_old('xs518a0.ic22', '2550D44F'), 
                                                    name_crc_old('xs743a0.ic23', 'A9109A6C'), ]),
ti_old('MU100 xu50720 (v1.11, Aug. 3, 1999)', [name_crc_old('PRG_MU100_xu50720 (v1.11, Aug. 3, 1999).ic11', '1126A8A4'), 
                                                   name_crc_old('WAVES_MU100_xs518b0.ic34', '2550D44F'), 
                                                   name_crc_old('WAVES_MU100_xs743b0.ic35', 'A9109A6C'), 
                                                   name_crc_old('WAVES_MU100_xt445a0-828.ic36', '225C2280'), 
                                                   name_crc_old('WAVES_MU100_xt461a0-829.ic37', 'A1D138A3'), 
                                                   name_crc_old('WAVES_MU100_xt462a0.ic39', '2E82CBD4'), 
                                                   name_crc_old('WAVES_MU100_xt463a0.ic38', 'CCE5F8D3'), ]),
ti_old('MU15 xv684c0 v1.01, Nov. 28, 1998', [name_crc_old('PRG_MU15.bin', 'E4046AEF'), ]),

# # * note: the following have 2 program roms!
ti_old('PSR-540 hi_7_v1_6 version 1.6', [name_crc_old('hi_7_v1_6.bin', '1F1992D9'), 
                                             name_crc_old('xw25320.ic310', 'E8D29E49'), 
                                             name_crc_old('xw25410.ic210', 'C7C4736D'), 
                                             name_crc_old('xw25520.ic220', '9EF56C4E'), ]),

ti_old('mu128-v2.00-h.bin (Ver2.00 99-MAY-21)', [name_crc_old('mu128-v2.00-h.bin', '2891487B'), 
                                                     name_crc_old('mu128-v2.00-l.bin', 'CC236DC4'), 
                                                     name_crc_old('xv364a0.ic53', 'CDA1AFD6'), 
                                                     name_crc_old('xv365a0.ic54', '10985ED0'), 
                                                     name_crc_old('xv366a0.ic57', '781DFAC6'), 
                                                     name_crc_old('xv376a0.ic58', '91A7533B'), ]),
ti_old('MU128 xv217c0 (Ver1.06 98-OCT-01)', [name_crc_old('xv217c0.ic27', 'F4BA61F1'), 
                                                 name_crc_old('xv224c0.ic25', '079BFCF0'), 
                                                 name_crc_old('xv364a0.ic53', 'CDA1AFD6'), 
                                                 name_crc_old('xv365a0.ic54', '10985ED0'), 
                                                 name_crc_old('xv366a0.ic57', '781DFAC6'), 
                                                 name_crc_old('xv376a0.ic58', '91A7533B'), ]),
ti_old('mu2000-v2.01-h.bin (Ver2.01 02-MAY-29)', [name_crc_old('mu2000-v2.01-h.bin', 'BE3668F6'), 
                                                      name_crc_old('mu2000-v2.01-l.bin', '55921A50'), 
                                                      name_crc_old('xv364a0.ic49', 'CDA1AFD6'), 
                                                      name_crc_old('xv365a0.ic50', '10985ED0'), 
                                                      name_crc_old('xw848a0.ic53', '34913E42'), 
                                                      name_crc_old('xw849a0.ic54', '3728F1F2'), ]),
ti_old('mu2000 xw86920.ic24 (v1.01, 99-NOV-16)', [name_crc_old('xw86920.ic24', 'AFBAC33C'), 
                                                      name_crc_old('xw87020.ic25', '79F6C158'), 
                                                      name_crc_old('xv364a0.ic49', 'CDA1AFD6'), 
                                                      name_crc_old('xv365a0.ic50', '10985ED0'), 
                                                      name_crc_old('xw848a0.ic53', '34913E42'), 
                                                      name_crc_old('xw849a0.ic54', '3728F1F2'), ]),

]



