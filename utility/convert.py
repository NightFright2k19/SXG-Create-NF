import sys


from dataenum import *


# contains decoding information, makes table object
import decBase
import decMU80 
import decMU50
import decSYXG50 
import decMU90 
import decMU100
import decMU1000
from decBase import PrintTableInfo

# makes S-YXG50 using table object
import makeSYXG50 

# converts tables (used by makeSYXG50)
import tableconvert

from utils import WriteBytesToFile, WriteTXT, FileExists, Dejumble, Friendly_error

from pathlib import Path
import buildtarget
import dllpatch
import template


def Convert(mu_src : MU, mu_tgt : MU, out_path : str, program_roms : list[Path], wave_roms : list[Path], dll : Path | None = None) : 

    in_wave_bytes = bytes()
    mu_src_original = mu_src
    alt_decoder = None      # second voice map (MU Basic) for MU100 / MU128 / MU1000
    match mu_src : 
 
        case MU.MU80 : 

            # todo 
            # unknown significance of the second bit in the sample format (never DPCM, always 1 with s16 drums?)
            # two of the pad samples can't fit into the 16 bit loop offset, and click when they loop
            # could be cleaned up by hand with a new loop point (with more body offset to fit the whole sample)
            # (and targeting vampire will probably fix it properly) 
  
            table_decoder = decMU80.MU80.From_Bytes(Dejumble(open( program_roms[0], mode='rb').read() ) )
            table_converter=tableconvert.fromMU80(MU.MU80)
            
            for path in wave_roms : 
                in_wave_bytes = in_wave_bytes + bytes(open(path, mode='rb').read() )


        case MU.MU50 : 

    
            table_decoder = decMU50.MU50.From_Bytes(Dejumble(open( program_roms[0], mode='rb').read() ) )
            table_converter=tableconvert.fromMU50(MU.MU50)
            for path in wave_roms : 
                in_wave_bytes = in_wave_bytes + bytes(open(path, mode='rb').read() )
 
        case MU.SYXG50 : 
            
            new_table_version='S-YXG50a1'
            new_table_name=f'{new_table_version}.TBL'
            new_waverom_name='SYXGTESTa1.UPCM'

            table_decoder = decSYXG50.SYXG50.From_Bytes(open( program_roms[0], mode='rb').read() )
            table_converter=tableconvert.fromSYXG50(MU.SYXG50)
            for path in wave_roms : 
                in_wave_bytes = in_wave_bytes + bytes(open(path, mode='rb').read() )
                     
        case MU.MU90 : 

            # * wave ROM interleave and reverse samples: solved (decMU90.MU90_Waverom / Make_Reversed)
            # ? 1 new byte of totally unknown function, it's present in both drum voice and wavedata tables
            # drum voices that make use of new EG parameters can be reconstructed as ext voices, possibly
            # (but no way will they all fit in S-YXG50, wavedata entries is at 243/255 already)
            # MU90 has also found a new way to break the S-YXG50's bank map table (100% fixable)


            table_decoder = decMU90.MU90.From_Bytes(Dejumble(open( program_roms[0], mode='rb').read() ) )
            table_converter=tableconvert.fromMU90(MU.MU90)

            # * the two wave ROMs are the two halves of a 32-bit bus (see decMU90.MU90_Waverom)
            assert len(wave_roms) == 2
            in_wave_bytes = decMU90.MU90_Waverom(open(wave_roms[0], mode='rb').read(), 
                                                 open(wave_roms[1], mode='rb').read())
 
        case MU.MU100 : 

            # * big table layout: ~30 MB of samples and more than 256 multisamples
            buildtarget.SYXG50_BIG = True
            # both voice maps in one table (MU100 Native + MU Basic, switched in the DLL's Settings page)
            print('MU100 voice maps: MU100 Native (default) + MU Basic')

            prg100 = Dejumble(open( program_roms[0], mode='rb').read() )
            table_decoder = decMU100.MU100.From_Bytes(prg100, False)
            alt_decoder = decMU100.MU100.From_Bytes(prg100, True)
            table_converter=tableconvert.fromMU90(MU.MU90)
            assert len(wave_roms) == 6
            rd = lambda p : open(p, mode='rb').read()
            in_wave_bytes = decMU100.MU100_Waverom([(rd(wave_roms[0]), rd(wave_roms[1])), 
                                                    (rd(wave_roms[2]), rd(wave_roms[3])), 
                                                    (rd(wave_roms[4]), rd(wave_roms[5]))])
            mu_src = MU.MU90   # same data formats from here on

        case MU.MU1000 | MU.MU128 : 

            model = 'MU1000' if mu_src == MU.MU1000 else 'MU128'
            # * big table layout: up to ~50 MB of samples and more than 256 multisamples
            buildtarget.SYXG50_BIG = True
            # both voice maps in one table (MU Native + MU Basic, switched in the DLL's Settings page)
            print(f'{model} voice maps: MU Native (default) + MU Basic')

            # program flash: high/low 16-bit halves of a 32-bit bus
            assert len(program_roms) == 2
            prg = decMU1000.MU1000_Program(open(program_roms[0], mode='rb').read(), open(program_roms[1], mode='rb').read())
            table_decoder = decMU1000.MU1000.From_Bytes(Dejumble(prg), model, False)
            alt_decoder = decMU1000.MU1000.From_Bytes(Dejumble(prg), model, True)
            table_converter = tableconvert.fromMU1000(MU.MU90)
            assert len(wave_roms) == 4
            rd = lambda p : open(p, mode='rb').read()
            in_wave_bytes = decMU1000.MU1000_Waverom([(rd(wave_roms[0]), rd(wave_roms[1])), 
                                                      (rd(wave_roms[2]), rd(wave_roms[3]))])
            mu_src = MU.MU90

        case MU.MU2000 : 

            # * same voice data as the MU1000, scalings stored as per-note tables (decMU1000.MU2000_Scaling)
            buildtarget.SYXG50_BIG = True
            print('MU2000 voice maps: MU Native (default) + MU Basic')
            rd = lambda p : open(p, mode='rb').read()
            if len(program_roms) == 1 :     # S-MU2000's mu2000_flash.bin
                prg = decMU1000.MU1000_Program(*decMU1000.MU2000_Flash_Split(rd(program_roms[0])))
            else : 
                assert len(program_roms) == 2
                prg = decMU1000.MU1000_Program(rd(program_roms[0]), rd(program_roms[1]))
            image = decMU1000.MU2000_Scaling(Dejumble(prg))
            table_decoder = decMU1000.MU1000.From_Bytes(image, 'MU2000', False)
            alt_decoder = decMU1000.MU1000.From_Bytes(image, 'MU2000', True)
            table_converter = tableconvert.fromMU1000(MU.MU90)
            assert len(wave_roms) == 4
            in_wave_bytes = decMU1000.MU1000_Waverom([(rd(wave_roms[0]), rd(wave_roms[1])), 
                                                      (rd(wave_roms[2]), rd(wave_roms[3]))])
            mu_src = MU.MU90

        case _ : 
            raise NotImplementedError()


    # file names per model (template.MODEL_FILES, the templates use the same; big layout: X = extended)
    if mu_src_original.name in template.MODEL_FILES : 
        new_table_version, new_table_name, new_waverom_name, big = template.MODEL_FILES[mu_src_original.name]
        assert big == buildtarget.SYXG50_BIG

    # without a syxg50.dll the plugin is made from the model's template (template.py, issue #40)
    tpl = None
    if not dll : 
        try : 
            tpl = template.Load(mu_src_original.name)
        except template.TemplateError as e : 
            Friendly_error(f'template not readable: {e}')
        if tpl is None and buildtarget.EMBED : 
            Friendly_error(f'--embed needs a syxg50.dll among the input files or the template {template.Name(mu_src_original.name)}')

    table_decoder.waverom = in_wave_bytes     # source samples, for loudness estimates (elemreduce)
    table = decBase.Create_Table(table_decoder, mu_src, table_decoder.data, wave_roms)
    alt_table = None
    if alt_decoder is not None : 
        # second voice map (MU Basic): same ROM, its voices / banks / rows are merged in (makeSYXG50.Merge_Alt_Table)
        alt_decoder.waverom = in_wave_bytes
        alt_table = decBase.Create_Table(alt_decoder, mu_src, alt_decoder.data, wave_roms)
    PrintTableInfo(table)
    hpf = [s for s in table.Sample_pool.values() if getattr(s, 'hpf_fc', 0)]
    if hpf : 
        n_el = sum(1 for s in hpf if getattr(s, 'hpf_element', False))
        print(f'HPF: {len(hpf)} filtered sample copies ({len(hpf) - n_el} drum keys, {n_el} voice elements; '
              f'cutoff {min(s.hpf_fc for s in hpf)}-{max(s.hpf_fc for s in hpf)} Hz in sample time base)')


    table_bin, samplemonster = makeSYXG50.MakeSYXG50(table, 
                                in_waves=in_wave_bytes,
                                tablecnv=table_converter, 
                                new_table_version=new_table_version,
                                new_table_name=new_table_name,
                                new_waverom_name=new_waverom_name,
                                alt_table=alt_table, alt_default=False)



    embed = buildtarget.EMBED
    if not embed : 
        WriteBytesToFile(table_bin, new_table_name, root_dir=out_path)

    def patch_dll(embed_files = None) : 
        try : 
            if dll : 
                dllpatch.Write(dll, out_path, new_table_name, buildtarget.SYXG50_BIG, mu_src_original.name, embed_files,
                               dll_name=buildtarget.DLL_NAME)
            else : 
                template.Write(tpl, out_path, new_table_name, mu_src_original.name, embed_files, dll_name=buildtarget.DLL_NAME)
        except (dllpatch.DllPatchError, template.TemplateError, AssertionError) as e : 
            Friendly_error(f'DLL not patched: {e}')
            sys.exit(1)

    # patched DLL + ini: "Enhanced" (24-bit loop length) for the classic layout, "Full" for the big one
    print('S-YXG50 table layout: ' + ('big (MU100 and later)' if buildtarget.SYXG50_BIG else 'classic'))
    if (dll or tpl) and not embed : 
        patch_dll()


    # create rehex (debug) - the S-YXG50 decoder can't read the big layout
    if not buildtarget.SYXG50_BIG and not embed : 
        out_table_decoder = decSYXG50.SYXG50.From_Bytes(table_bin)
        WriteTXT(out_table_decoder.get_rehex_json(), new_table_name+r'.rehex-meta', root_dir=out_path)

    if not embed and FileExists(new_waverom_name, root_dir=out_path) : 
        Friendly_error(f'\'{new_waverom_name}\' already exists, exiting early')
        sys.exit(1)

    # * construct our (deferred) new waverom
    waverom = samplemonster.Generate()
    if embed : 
        # --embed: both go into the DLL, no separate files
        patch_dll([(new_table_name, bytes(table_bin)), (new_waverom_name, bytes(waverom))])
    else : 
        WriteBytesToFile(waverom, new_waverom_name, root_dir=out_path)


