from typing import Generator

from table import *
from cnv_fromBASE import TableConverter, ToBigDrumVoice
import SampleConvert

import decSYXG50
import buildtarget

from utils import fmtbyte, fmtbytes

# wavebank attribute holding the multisample number of each page (big layout paging)
PAGE_INDEX = ('index', 'index1', 'index2')

# * S-YXG50 Table format limitations:

# * Voices: limited to 16 bits of offset (2 x 16 bit banks)
# probably could hold around ~1100 voices total, depends on the amount of elements. 
# ... Would likely run out last

# * WaveData: index limited to 255 entries
# Accessed by Voices, WaveData is a variable-length table that handles keysplits. 
# It seems to be used as an 'overall' sample manifest, and is chock full of drum sounds, 
# test tones, other stuff that isn't actually addressed through normal means and can be 
# safely pruned. By default, S-YXG50 is already at 245 (more for the 2MB version, oddly), 
# ... but yeah it's not as bad as it seems. Preliminary MU90 traces come back with 243/255. 
# Drum Voices are 'free', and do not require a wavedata entry, instead terminating in 
# their own section

# * Sample Offsets: limited to 16 bits
# limits how long a sample's "body" and "loop" can be to 65535 samples
# ...Already a problem with some of the MU80 pads, which use 17 bits of loop offset

# * Sample Address: limited to 24 bits (16 MB)
# After ADPCM-to-16bit conversions, the MU80 comes in at ~12.5 megs of full 16-bit audio
# preserving the S8 from the MU50 and MU90 does help

# MU50, MU80, and even MU90 *will* fit, but only barely, and perhaps with a few compromises





# * generic writers for our data that's already been fully abstracted
# the only data fully abstracted on decode is voices (just the 2-byte header) and wavedata
# (for now)

# * needs wave address for each wave, convert all samples first and then use wavebank.get_samples
def WriteWaveData(wavebank : WaveBank, samples : list[Sample], target : MU) -> bytes : 
    assert len(wavebank.waves)
    assert len(wavebank.waves) == len(samples)
    assert target == MU.SYXG50
    out = bytearray(len(wavebank.waves) * 16)

    for i, wave in enumerate(wavebank.waves) : 
        offs = i * 16
        sample = samples[i]

        assert sample.out_sample_type != SampleFormat.UNKNOWN
        # * should be written already. disable for testing
        assert sample.written 
        assert sample.out_loop_address >= 0

        # +0: attenuation
        out[offs+0] = wave.attenuation
        # +1: tune, note
        out[offs+1] = wave.tune_note
        # +2: tune, cent
        out[offs+2] = wave.tune_cent
         
        # ? +3: offset_negative (24 bits? probably not...) BE
        # + ADPCM lead-in (extra decoded passes in front of the loop, see SampleConvert.ADPCM_Find_LeadIn)
        offset_negative = wave.offset_negative + getattr(sample, 'lead_in', 0)
        assert offset_negative <= 0xFFFFFF
        out[offs+3:offs+3+3] = offset_negative.to_bytes(3, 'big')

        # +6..+8: offset_positive (loop length), 24 bits BE
        # syxg50.dll reads all 3 bytes, but masks the value to 16 bits at voice setup.
        # Loops > 65535 need the patched DLL (masks at 0x1A6EC/0x1A6F8 widened to 0xFFFFFF).
        assert wave.offset_positive <= 0xFFFFFF
        if wave.offset_positive > 0xFFFF : 
            print(f'makeSYXG50 -> WriteWaveData: Info, WDT srcaddr=0x{wave.address_src} ({sample.get_a_name()}) loop length {wave.offset_positive} > 65535, written as 24 bit (needs patched syxg50.dll)')
        out[offs+6:offs+6+3] = wave.offset_positive.to_bytes(3, 'big')

        if buildtarget.SYXG50_BIG : 
            # S-YXG50 big: +9..+12 wave address, 32-bit BE in bytes, +13: sample type
            assert sample.out_loop_address <= 0xFFFFFFFF
            out[offs+9:offs+9+4] = sample.out_loop_address.to_bytes(4, 'big')
            out[offs+13] = SampleFormat_to_Byte_SYXG50(sample.out_sample_type)
        else : 
            # +9: wave address BE
            out[offs+9:offs+9+3] = sample.out_loop_address.to_bytes(3, 'big')

            #+12: sample type
            out[offs+12] = SampleFormat_to_Byte_SYXG50(sample.out_sample_type)
            #+13: unused
        #+14: note low
        out[offs+14] = wave.key_min
        #+15: note high, FF for end keysplit
        out[offs+15] = wave.key_max
        if i == len(wavebank.waves)-1 : 
            assert wave.key_max >= 0x7F
            # MU90 marks last keysplit with 7F 
            # but S-YXG50 is probably looking for FF specifically
            out[offs+15] = 0xFF 

    return bytes(out)

# * amp EG decay 2 going up (decay 2 level above decay 1 level, S-YXG50 element +74 > +73): the MU moves
#   to the decay 1 level and then back up to the decay 2 level. syxg50.dll does that too, but it ends the
#   note as soon as the envelope falls below level 64 (-46 dB, measured on the emulator: decay 1 level 63
#   ends the note at any key and velocity, 64 keeps it), so a decay 1 level below 64 silenced the note
#   right after the attack. Affected: Lite Org (an organ that sounded like a click), WireLead, synecho2,
#   Bounce, Ana Echo (MU80 2 voices ... MU128/MU1000 5); never used in the S-YXG50 / MU50 data.
#   The decay 1 level is raised to 64 (-46.3 instead of at most -47 dB on the way).
def Rising_Decay2_Fix(data) : 
    if data[73] < 64 and data[74] > data[73] : 
        data = bytearray(data)
        data[73] = 64
        data = bytes(data)
    return data

# * second voice map (MU Basic) in the same table. The MU100 / MU128 / MU1000 have two voice maps
#   (module setting "Voice Map": MU Basic = MU90 voices, MU Native = revoiced). Both use the same samples,
#   drum kits and drum voices; they differ in which voice bank an XG bank select (and the XG / GM2 drum
#   program) gives. The table holds the voices and banks of both maps, the bank map / drum program rows of
#   the native map in the normal place, and those of the second map in an appendix behind the wave data,
#   which the patched DLL swaps in (dllpatch.SYXG50_VOICEMAP). The DLL ignores data behind the last section.
#   Appendix (VOICE_MAP_APPENDIX bytes): +0 'MAP2', +4 default map (0 = native, 1 = second), +5..+7 0,
#   +8 eight alternate rows of 128 bytes: drum programs GS / XG / SFX / GM2, voice banks GS / MSB / XG / GM2
VOICE_MAP_MAGIC = b'MAP2'
VOICE_MAP_APPENDIX = 8 + 8 * 128

def Merge_Alt_Table(table : Table, alt : Table) :
    # voices, wavebanks, samples, drum voices and kits are keyed by their ROM address, the banks of the second
    # map that the first one does not have are added and marked (their rows go to the appendix)
    added_voices = 0
    for pool in ('Voice_pool', 'Wavebank_pool', 'Sample_pool', 'DrumVoice_pool') : 
        mine, other = getattr(table, pool), getattr(alt, pool)
        for k, v in other.items() : 
            if k not in mine : 
                mine[k] = v
                if pool == 'Voice_pool' : added_voices += 1
    assert set(alt.drumkits) <= set(table.drumkits), 'second voice map uses drum kits the first one does not have'
    added = 0
    for k, vb in alt.voice_banks.items() : 
        if k not in table.voice_banks : 
            import copy
            nb = copy.copy(vb)
            nb.aliases = list(vb.aliases)
            nb.alt = True
            table.voice_banks[k] = nb
            added += 1
    print(f'voice maps: the second map adds {added} banks and {added_voices} voices')

def Voice_Map_Appendix(alt : Table, table : Table, GSbanks : dict, XGbanks : dict, bank_map_order : list,
                       drum_bank_locations : dict, voice_bankmaps : bytes, drumbank_prgmaps : bytes, alt_default : bool) -> bytes :
    # rows of the second map, with the bank and kit indices of this table
    # voice bank rows: same filling rule as the main rows (aliases included), GS / XG side kept apart
    rows = bytearray(0xFF for _ in range(128)) + bytearray(len(voice_bankmaps) - 128)
    for vb in alt.voice_banks.values() : 
        for bank, byte in [(vb.bank, vb.relevant_byte())] + list(vb.aliases) : 
            if bank not in bank_map_order : continue
            dst = (GSbanks if bank == Bank.GS else XGbanks).get(vb.prg_address)
            assert dst is not None and dst.index >= 0, f'bank {vb.prg_address} of the second map has no index on the {bank} side'
            rows[byte + 128 * bank_map_order.index(bank)] = dst.index
    # MSB row: syxg50.dll reads a bank index of 1 there as "XG: take the bank from the LSB row" (which is why
    # the native XG LSB 0 bank gets index 1). The second map's XG LSB 0 bank has another index, so its MSB
    # entries are written as 1 as well
    lsb0 = [vb for vb in alt.voice_banks.values() if vb.bank == Bank.XG and vb.lsb == 0]
    if lsb0 : 
        i0 = XGbanks[lsb0[0].prg_address].index
        msb_row = 128 * bank_map_order.index(Bank.SFX)
        for i in range(msb_row, msb_row + 128) : 
            if rows[i] == i0 : rows[i] = 1
    # drum program rows: kits are shared, so the second map's program -> kit, with this table's kit index
    drows = bytearray(len(drumbank_prgmaps))
    for key, kit in alt.drumkits.items() : 
        idx = table.drumkits[key].index
        for bank, prg in [(kit.bank, kit.prg)] + list(kit.aliases) : 
            drows[prg + 128 * drum_bank_locations[bank]] = idx
    drows = (drows + bytearray(4 * 128))[:4 * 128]
    rows = (bytes(rows) + bytes(4 * 128))[:4 * 128]
    same_v = sum(1 for a, b in zip(rows, voice_bankmaps) if a != b)
    same_d = sum(1 for a, b in zip(drows, drumbank_prgmaps) if a != b)
    print(f'voice maps: second map differs in {same_v} bank map and {same_d} drum program entries'
          f' (default: {"second" if alt_default else "native"} map)')
    out = bytearray(VOICE_MAP_MAGIC) + bytes([1 if alt_default else 0, 0, 0, 0]) + drows + rows
    assert len(out) == VOICE_MAP_APPENDIX
    return bytes(out)

# * convert voice / element first, then this will generically write it
def WriteVoice(voice : Voice, target : MU) -> bytes : 
    assert target == MU.SYXG50
    assert voice.converted
    assert len(voice.elements) > 0

    # S-YXG50 voice header: only 2 bytes
    # missing the 8-character name common in MUs
    out : bytearray = bytearray(2)

    # +0: volume
    # +1: number of voices (1 or 3)
    out[0] = voice.volume
    out[1] = 0x03 if len(voice.elements) == 2 else 0x01

    for e in voice.elements : 
        out = out + e.data

    return bytes(out)

# things wrap if idx is < 0
def WriteANSI(array : bytearray, idx : int, string : str) : 

    str_bytes = string.encode(encoding='cp1252')

    for i, addr in enumerate(range(idx, min(len(array) , idx+len(str_bytes)))) : 
        array[addr] = str_bytes[i]


# note for S-YXG50 table creation:
# ext drum voices should be queued in early into voice_pool 
# I'm not sure if they are restricted to VoicesA or not

    # * ------------ table reconstruction
def MakeSYXG50(table : Table, in_waves : bytes, tablecnv : TableConverter, new_table_version : str, new_table_name : str, new_waverom_name : str, VOICE_PAD : int = 8,
               alt_table : Table | None = None, alt_default : bool = False) -> tuple[bytes,SampleConvert.SampleMonster]  : 
    # alt_table: the same model decoded with its second voice map (MU Basic, MU100 / MU128 / MU1000).
    # Its voices and banks are added to this table, and the bank map / drum program rows of the second map
    # are appended to the table (see VOICE_MAP_APPENDIX); the patched syxg50.dll switches between the two
    # maps (Settings page, "MU Basic voice map"). alt_default: start in the second map.
    if alt_table is not None : 
        Merge_Alt_Table(table, alt_table)

    
    # todo this should be validated before it goes in here
    assert len(new_table_version) <= 16  # 16 bytes max
    assert len(new_table_name) <= 16     # ?? unknown max
    assert len(new_waverom_name) <= 15   # 15 bytes max
    assert len(new_table_version)
    assert len(new_table_name)
    assert len(new_waverom_name)

    # sequential number generators for reconstruction
    # could also just use a list and .index, but I think this might be less messy. idk 
    drumkitIDX = (i for i in range(257))
    waveIDX = (i for i in range(257)) # next(waveIDX)
    waveIDX1 = (i for i in range(256, 513)) # second page (big layout, 512 multisamples)
    waveIDX2 = (i for i in range(512, 769)) # third page (big layout, 768 multisamples)
    extvoiceIDX = (i for i in range(0xFF00)) # next(extvoiceIDX)

    header = bytearray(100) # 0
    drumbank_prgmaps = bytearray() # 64
    drumkit_keymaps = bytearray() # 264
    drum_voices = bytearray() # 2164
    ext_drumvoice_offsets = bytearray() # 45F4

    voice_bankmaps = bytearray() # * new

    voice_prgmap_GS = bytearray() # 48A2
    voice_prgmap_XG = bytearray() # 60A2

    voices_bankA = bytearray() # 98A2
    voices_bankB = bytearray() # 193CC
    wavedata_offsets = bytearray() # 1F07A
    wavedata = bytearray() # 1F266

    # * samples are fed into this guy, which defers waverom creation until after the table is done 
    # ? samples are in a list, can be utilized along with 'bank' value on sample objects?
    samplemonster = SampleConvert.SampleMonster([in_waves], table.format, MU.SYXG50, {})

    # Precheck the presence of GM2 voices or GM2 drumkits
    GM2_present = False
    for v in table.voice_banks.values() : 
        if v.bank == Bank.GM2 : 
            GM2_present = True
            break
    if not GM2_present :
        for v in table.drumkits.values() : 
            if v.bank == Bank.GM2 : 
                GM2_present = True
                break

    # for drum PRG / voice Bank tables, respectively
    drum_bank_cnt : int = 3 if not GM2_present else 4
    voice_bank_cnt_XG : int = 2 if not GM2_present else 3

    # ! keeping GM2 bank sections for now
    # todo confirm if the GM2 table is load-bearing or not...
    drum_bank_cnt = 4
    voice_bank_cnt_XG = 3


    # * Data Tables ----------------------
    # first: voice, drumvoice, and wavedata tables (with associated samples)
    # these have to be converted, written, and offsets assigned for the next part

    # we need these as we write:
    # 1: voice: needs wavedata index
    # 2. drum voice (with ext): needs voice index

    # update metadata for regular voices
    # voices, wavebanks, and samples 
    # actual sample conversion is deferred until the end
    def ConvertVoice(table: Table, voice : Voice, 
                    waveIDX : Generator, 
                    samplemonster : SampleConvert.SampleMonster) : 

        for element in voice.elements : 

            lookup = element.wavebank_address
            wavebank = table.Wavebank_pool[lookup]

            for wave in wavebank.waves : 

                sample = table.Sample_pool[wave.loop_address_src]

                if not sample.written : 

                    new_loop_addr, new_sample_format = samplemonster.FeedSample(sample, table.format, MU.SYXG50)

                    sample.out_loop_address = new_loop_addr
                    sample.out_sample_type = new_sample_format
                    sample.format = MU.SYXG50
                    sample.written = True
    

            wavebank.out_data = WriteWaveData(wavebank, 
                                        wavebank.get_samples(table.Sample_pool), 
                                        MU.SYXG50)

            page = getattr(voice, 'page', 0)
            attr = PAGE_INDEX[page]
            if getattr(wavebank, attr, -1) < 0 : 
                setattr(wavebank, attr, next((waveIDX, waveIDX1, waveIDX2)[page]))

        # the element stores the wave number as one byte; page n numbers are stored minus 256 * n
        class _PagedWB : 
            def __init__(self, wb, page) : 
                self.index = getattr(wb, PAGE_INDEX[page]) - 256 * page
        page = getattr(voice, 'page', 0)
        tablecnv.ConvertElements(voice, [_PagedWB(wb, page) for wb in voice.get_wavebanks(table.Wavebank_pool)], MU.SYXG50)
        for element in voice.elements : 
            element.data = Rising_Decay2_Fix(element.data)
        voice.data = WriteVoice(voice, MU.SYXG50)



    def ConvertDrumVoice(table : Table, drumvoice : DrumVoice, 
                        extvoiceIDX : Generator, waveIDX : Generator, 
                        samplemonster : SampleConvert.SampleMonster) : 
        
        if drumvoice.ext_Voice_address : 
            # should still be able to look it up by it's address_src value
            voice = drumvoice.get_voice(table.Voice_pool)
            if isinstance(voice, Voice) : 
                voice.extvoice_index = next(extvoiceIDX)
                drumvoice.extvoice_index = voice.extvoice_index
                if not voice.converted : 
                    ConvertVoice(table, voice, waveIDX, samplemonster)
            else : 
                raise ValueError()
        else : 
            sample = drumvoice.get_sample(table.Sample_pool)

            if not sample.written : 

                new_loop_addr, new_sample_format = samplemonster.FeedSample(sample, table.format, MU.SYXG50)

                sample.out_loop_address = new_loop_addr
                sample.out_sample_type = new_sample_format
                sample.format = MU.SYXG50
                sample.written = True


        # test_before : str = fmtbytes(drumvoice.data)

        # * updates drum.data and drum.format
        if drumvoice.ext_Voice_address : 
            tablecnv.ConvertDrumVoice(drumvoice, None, 
                                        drumvoice.get_voice(table.Voice_pool), 
                                        target=MU.SYXG50)
        else : 
            # ADPCM lead-in moves the loop point back by lead_in samples, the start stays where it was
            drumvoice.offset_negative += getattr(drumvoice.get_sample(table.Sample_pool), 'lead_in', 0)
            tablecnv.ConvertDrumVoice(drumvoice, drumvoice.get_sample(table.Sample_pool), 
                                        drumvoice.get_voice(table.Voice_pool), 
                                        target=MU.SYXG50)

        # big layout: rearrange the finished S-YXG50 drum voice
        if buildtarget.SYXG50_BIG : 
            if drumvoice.ext_Voice_address : 
                drumvoice.data = bytes(ToBigDrumVoice(bytearray(drumvoice.data), drumvoice, None, 
                                                         drumvoice.get_voice(table.Voice_pool)))
            else : 
                drumvoice.data = bytes(ToBigDrumVoice(bytearray(drumvoice.data), drumvoice, 
                                                         drumvoice.get_sample(table.Sample_pool), None))
        drumvoice.converted = True

        # test_after : str = fmtbytes(drumvoice.data)


    # mark samples played directly by drum keys (their start offset is only 16 bit in syxg50.dll)
    for drumvoice in table.DrumVoice_pool.values() : 
        if not drumvoice.ext_Voice_address : 
            drumvoice.get_sample(table.Sample_pool).used_by_drum = True

    # * more than 256 multisamples (MU100+): up to three pages of 256, big layout only.
    # The "Full" patched syxg50.dll adds 256 to the wave number of every element that lies in
    # voice bank B, as soon as the wavedata offset table has more than 256 entries, and another
    # 256 for elements behind the page 2 start in bank B, when the table has more than 512 entries
    # (the page 2 start, as a byte offset from bank B, is stored in wavedata offset entry 768).
    # So: page 0 voices -> bank A, page 1 voices -> bank B, page 2 voices -> end of bank B, and each
    # page gets its own wave numbers (a multisample used by two pages gets an entry in both, same data).
    paging = False
    pages : list[set] = [set(), set(), set()]
    used_wb = {e.wavebank_address for v in table.Voice_pool.values() for e in v.elements}
    if len(used_wb) > 256 : 
        if not buildtarget.SYXG50_BIG : 
            raise Exception(f'{len(used_wb)} multisamples, the classic table layout can only address 256')
        paging = True
        for voice in table.Voice_pool.values() : 
            wbs = {e.wavebank_address for e in voice.elements}
            voice.page = next((p for p in range(3) if len(pages[p] | wbs) <= 256), 3)
            if voice.page > 2 : 
                raise Exception('more than 768 multisamples needed')
            pages[voice.page] |= wbs
        npages = 3 if pages[2] else 2
        print(f'multisamples: {len(used_wb)} -> {npages} pages: {len(pages[0])} (bank A) + {len(pages[1])} (bank B)'
              + (f' + {len(pages[2])} (bank B, page 2)' if pages[2] else '')
              + f', {len(pages[0]) + len(pages[1]) + len(pages[2]) - len(used_wb)} shared  (needs the "Full" patched syxg50.dll)')

    # update metadata for regular voices
    # voices, wavebanks, and samples 
    for addr, voice in table.Voice_pool.items() : 

        if voice.converted : continue

        ConvertVoice(table, voice, waveIDX, samplemonster)
        

    # update metadata, drum voices
    # touches drum voices, samples. /  drum voice external voices, wavebanks, samples 
    for addr, drumvoice in table.DrumVoice_pool.items() : 

        assert isinstance(drumvoice, DrumVoice)
        if drumvoice.converted : continue

        ConvertDrumVoice(table, drumvoice, extvoiceIDX, waveIDX, samplemonster)

    # * drum velocity sensitivity: internal drum keys -> ext drum voices in bank B (see drumvel.py)
    if True : 
        import drumvel
        # paging: the last page in use (page 2 opens when page 1 is nearly full)
        dv_page = (2 if pages[2] or len(pages[1]) > 256 - 16 else 1) if paging else 0
        free_ms = (256 - len(pages[dv_page])) if paging else (256 - sum(1 for wb in table.Wavebank_pool.values() if wb.index >= 0))
        drumvel.Convert(table, extvoiceIDX, (waveIDX, waveIDX1, waveIDX2)[dv_page], dv_page, buildtarget.SYXG50_BIG, free_ms,
                        lambda wb, samples : WriteWaveData(wb, samples, MU.SYXG50),
                        lambda voice : WriteVoice(voice, MU.SYXG50))


    # * create voice & wavedata data tables
    # creating offsets for our jump tables along the way

    drum_voices = bytearray() # 2164
    voices_bankA = bytearray() # 98A2
    voices_bankB = bytearray() # 193CC
    wavedata = bytearray() # 1F266

    # * create drumtables table
    # drumvoice offsets are simple 16-bit values, should be good to directly copy into keymap table
    for drumvoice in table.DrumVoice_pool.values() : 
        assert drumvoice.converted
        offs = len(drum_voices) 
        drum_voices = drum_voices + drumvoice.data
        drumvoice.offset = offs


    # * create voice tables
    # voice objects store offset and voicebank
    # note: the offset values are 'real' offsets, not encoded
    # * Voices used by drum keys (ext drum voices) must live in bank A:
    # syxg50.dll reads their position as a 16-bit byte offset from the start of bank A,
    # so a voice that lands in bank B would be read from the wrong place.
    # Place them first, the order of all other voices is unchanged.
    voices_ordered : list[Voice] = [v for v in table.Voice_pool.values() if v.extvoice_index >= 0] \
                                 + [v for v in table.Voice_pool.values() if v.extvoice_index < 0]
    # paging: page 2 voices at the end of bank B (stable sort keeps the order inside each page)
    page2_start = -1
    if paging : 
        voices_ordered.sort(key=lambda v : 1 if v.page == 2 else 0)

    if VOICE_PAD == 0 : 
        for voice in voices_ordered : 
            assert voice.converted
            if (voice.page == 0) if paging else (len(voices_bankA) < (0xFFFF - len(voice))) : 
                offs = len(voices_bankA)
                voices_bankA = voices_bankA + voice.data
                voice.offset = offs
                voice.voicebank = 'bankA'
            else : 
                if paging and voice.page == 2 and page2_start < 0 : page2_start = len(voices_bankB)
                offs = len(voices_bankB)
                assert offs <= 0xFFFF or paging # out of space!
                voices_bankB = voices_bankB + voice.data
                voice.offset = offs
                voice.voicebank = 'bankB'

    # * print name before our voice for easier debugging
    elif VOICE_PAD == 8 :  
        for voice in voices_ordered : 
            assert voice.converted
            # debug label only (the engine doesn't read it): always exactly 8 bytes.
            # S-YXG50 source tables have no voice names, MU50/MU80 names are 8 characters
            name = (voice.name if voice.name else '--------')[0:8].ljust(8)
            str_bytes = name.encode(encoding='cp1252', errors='replace')
            assert len(str_bytes) == 8

            if (voice.page == 0) if paging else (len(voices_bankA) < (0xFFFF - (len(str_bytes) + len(voice)) )) : 
                offs = len(str_bytes) + len(voices_bankA)
                voices_bankA = voices_bankA + str_bytes + voice.data
                voice.offset = offs
                voice.voicebank = 'bankA'
            else : 
                if paging and voice.page == 2 and page2_start < 0 : page2_start = len(voices_bankB)
                offs = len(str_bytes) + len(voices_bankB)
                assert offs <= 0xFFFF or paging # out of space!
                voices_bankB = voices_bankB + str_bytes + voice.data
                voice.offset = offs
                voice.voicebank = 'bankB'



    to_delete = []
    for key, wavebank in table.Wavebank_pool.items() :  # * debug
        if all(getattr(wavebank, a, -1) < 0 for a in PAGE_INDEX) : 
            to_delete.append(key)

    for key in to_delete : del table.Wavebank_pool[key]

    # create wavedata table (each multisample once, even if it has a number in both pages)
    # relevant offset value stored in wavebank.offset
    first_index = lambda wb : min(i for i in (getattr(wb, a, -1) for a in PAGE_INDEX) if i >= 0)
    for wavebank in sorted(table.Wavebank_pool.values(), key=first_index) : 
        wavebank.offset = len(wavedata)
        wavedata = wavedata + wavebank.out_data


    for wavebank in table.Wavebank_pool.values() :  # * debug
        assert wavebank.offset >= 0





    # * index and offset tables creation -----------------

    # Section 1: Drumbank Program Maps
    # 128 byte tables x4, with implicit fixed lsb/msb values. index = prg value = seqID for drumvoice mapping
    drum_bank_locations = {Bank.GS_DRUMS : 0, Bank.XG_DRUMS : 1, Bank.SFX_DRUMS : 2, Bank.GM2_DRUMS : 3}

    # note: S-YXG50's "silent kit" is index 00 (last index in MU50)
    # however it seems to work fine either way (Voice banks are a different story)
    kits : list[DrumKit] = [k for k in table.drumkits.values()]

    drumbank_prgmaps = bytearray(128 * drum_bank_cnt)

    for kit in kits : 
        offset = drum_bank_locations[kit.bank]
        addr = kit.prg + (128 * offset)
        kit.index = next(drumkitIDX) # assign seqID
        drumbank_prgmaps[addr] = kit.index

    # add in duplicates ('aliases')
    for kit in kits : 
        for bank, prg in kit.aliases : 
            addr = prg + (drum_bank_locations[bank] * 128)
            assert kit.index > -1
            drumbank_prgmaps[addr] = kit.index


    # * Section 2: Drumkit key mappings
    # 256 byte tables. Index*2 = midi key number, value=16-bit offset to drumvoice table
    # 0xFFFF = blank voice

    # get highest kit index using our drumkit index generator
    highest_kit_index = max(0, next(drumkitIDX)-1)

    # sort kits by assigned index
    kits.sort(key=lambda k : k.index)

    drumkit_keymaps = bytearray([0xFF for _ in range(256 * (highest_kit_index+1))])

    # kits[] has been sorted by internal index
    for i, kit in enumerate(kits) : 

        kit_address = 256 * i

        for key in kit.drumvoices.keys() : 

            drumvoice = kit.get_drumvoice(table.DrumVoice_pool, key)
            addr = kit_address + (key * 2)

            drumkit_keymaps[addr : addr+2] = drumvoice.offset.to_bytes(2, 'little')


    # * ext drum voice offsets table
    highest_extvoice_index = max(0, next(extvoiceIDX)-1)

    # big layout: 32-bit LE byte offsets from the start of voice bank A (bank B follows bank A)
    ptr_size = 4 if buildtarget.SYXG50_BIG else 2

    def voice_byte_offset(voice : Voice) -> int : 
        assert voice.offset >= 0
        if voice.voicebank == 'bankB' : 
            return len(voices_bankA) + voice.offset
        return voice.offset

    ext_drumvoice_offsets = bytearray((highest_extvoice_index+1) * ptr_size)

    for idx, addr in enumerate(range(0, len(ext_drumvoice_offsets), ptr_size) ) : 

        for drumvoice in table.DrumVoice_pool.values() : 
            if drumvoice.extvoice_index == idx : 
                voice = drumvoice.get_voice(table.Voice_pool)
                assert voice
                assert voice.offset >= 0
                if buildtarget.SYXG50_BIG : 
                    ext_drumvoice_offsets[addr:addr+4] = voice_byte_offset(voice).to_bytes(4, 'little')
                else : 
                    # must be in bank A (see voices_ordered), otherwise the drum key plays the wrong data
                    if voice.voicebank != 'bankA' : 
                        raise Exception(f'ext drum voice "{voice.name}" is in {voice.voicebank}, syxg50.dll can only reach bank A')
                    ext_drumvoice_offsets[addr:addr+2] = voice.offset.to_bytes(2, 'little')



    ext_voices = [v for v in table.Voice_pool.values() if v.extvoice_index >= 0]
    print(f'ext drum voices: {len(ext_voices)}, in bank A: {sum(1 for v in ext_voices if v.voicebank == "bankA")}, '
          f'bank A size: {len(voices_bankA):,} bytes, bank B size: {len(voices_bankB):,} bytes')

    # * Voice Bank mapping - 128 byte tables
    # allows (limited) assignment for 'banks'. Each bank contains 128 programs
    # limited, because one axis is always fixed. GS index=MSB with LSB=0, XG index=LSB with MSB=0
    # value is a seqID for the next section, which contains offsets to VoicesA/VoicesB

    # in S-YXG50, voice bank mapping is split up into GS and non-GS 
    # each with their own range of seqIDs
    banksGS_IDX = (i for i in range(257))
    banksXG_IDX = (i for i in range(257))

    # * in S-YXG50's GS bank map, all the empty indexes are FF 
    voice_bankmaps = bytearray(0xFF for _ in range(128 * (voice_bank_cnt_XG+1))) # * new

    # * 0xFF in XG bank definitions, however means crash!
    # start everything in GM2 to 00 to be safe
    for i in range(128, len(voice_bankmaps)) : 
        voice_bankmaps[i] = 0x00

    # * split voicebanks into two, duplicating when necessary. S-YXG50 requirement
    # voicebank.aliases are fully intact. Make sure to 
    # disregard opposite banks in aliases when generating program maps
    GSbanks : dict[int | str, VoiceBank] = {}
    XGbanks : dict[int | str, VoiceBank] = {}

    for vb in table.voice_banks.values() : 
        match vb.bank : 
            case Bank.GS : 
                GSbanks[vb.prg_address] = vb
                # GS, peel apart any non-GS aliases and dupe them into the XGbanks list
                for dupebank, dupebyte in vb.aliases : 

                    if dupebank != Bank.GS :

                        dupe_lsb, dupe_msb = BankToLSBMSB(dupebank, dupebyte)

                        new_voicebank = VoiceBank(vb.prg_address, dupebank, lsb=dupe_lsb, msb=dupe_msb, voices=vb.voices, seqID=0, aliases=[])
                        new_voicebank.alt = getattr(vb, 'alt', False)

                        if vb.prg_address not in XGbanks : 
                            XGbanks[vb.prg_address] = new_voicebank
                        else : 
                            XGbanks[vb.prg_address].aliases.append((dupebank, dupebyte))

            case _ : 
                XGbanks[vb.prg_address] = vb
                # XG or GM2, peel apart any GS aliases and copy them into GSbanks list
                byte = vb.lsb
                for dupebank, dupebyte in vb.aliases : 
                    if dupebank == Bank.GS : 

                        new_voicebank = VoiceBank(vb.prg_address, dupebank, lsb=0, msb=dupebyte, voices=vb.voices, seqID=0, aliases=[])
                        new_voicebank.alt = getattr(vb, 'alt', False)

                        if vb.prg_address not in GSbanks : 
                            GSbanks[vb.prg_address] = new_voicebank
                        else : 
                            GSbanks[vb.prg_address].aliases.append((dupebank, dupebyte))

    # S-YXG50 voicebank mapping is very fragile!
    # sort XGbank SFX MSB1 (silent bank) first
    # ! THIS IS LOAD BEARING, if XG voice banks start at index 00 it breaks bank changing!
    for xgbank in XGbanks.values() : 
        if xgbank.bank == Bank.SFX and xgbank.msb == 1 and not getattr(xgbank, 'alt', False) : 
            xgbank.index = next(banksXG_IDX)
            break

    # ! additionally: XG voice banks must start at 01
    # todo: none of the XG range can be 00, this is currently causing issues with the MU90
    # ? though XG MSB(SFX) and GM2 use 00 just fine
    for xgbank in XGbanks.values() : 
        if xgbank.bank == Bank.XG and xgbank.lsb == 0 and not getattr(xgbank, 'alt', False) : 
            xgbank.index = next(banksXG_IDX)
            break

    # * assign seqID indexes to our defined banks
    # S-YXG50: two different ranges for GS and Non-GS
    for gsbank in GSbanks.values() : 
        assert gsbank.bank == Bank.GS 
        gsbank.index = next(banksGS_IDX)

    for xgbank in XGbanks.values() : 
        assert xgbank.bank != Bank.GS 
        if xgbank.index < 0 :
            xgbank.index = next(banksXG_IDX)


    voicebanks_expanded : list[VoiceBank] = list(GSbanks.values()) + list(XGbanks.values())

    bank_map_order : list[Bank] = decSYXG50.SYXG50().bankorder_voice

    for voicebank in voicebanks_expanded :

        assert voicebank.bank in bank_map_order 
        if getattr(voicebank, 'alt', False) : continue      # second voice map only: rows in the appendix

        addr = voicebank.relevant_byte() + (128 * bank_map_order.index(voicebank.bank))
        voice_bankmaps[addr] = voicebank.index

        # handle dupes (aliases)
        for bank, byte in voicebank.aliases : 
            # don't cross the GS/XG barrier. the previous loop will duplicate the voicebanks to their proper side
            if (voicebank.bank == Bank.GS and bank != Bank.GS) or (voicebank.bank != Bank.GS and bank == Bank.GS) :
                continue

            addr = byte + (128 * bank_map_order.index(bank))
            voice_bankmaps[addr] = voicebank.index


    highest_bankID_GS = max(0, next(banksGS_IDX)-1)
    highest_bankID_XG = max(0, next(banksXG_IDX)-1)


    # * Voice Program Mapping - 256 byte tables
    # index*2 = program#, value=2-byte offset
    # special-encoded: top bit specifies use voices voicebank A or B, 
    # ... then the address is multiplied by two

    # Also, in S-YXG50, there are two of these. One for GS, one for XG
    voice_prgmap_GS = bytearray((highest_bankID_GS+1) * 128 * ptr_size)
    voice_prgmap_XG = bytearray((highest_bankID_XG+1) * 128 * ptr_size)

    # returns: encoded offset value
    # our voices should already have offset & bank values stored in them
    def encode_SYXG50_voice_offset(offs : int, voicebank : Literal['bankA', 'bankB', '']) -> int : 
        assert not offs % 2 # offsets should be even only
        assert offs < 0xFFFF # FFFE max value
        assert not voicebank == ''
        if voicebank == 'bankA' : 
            return offs>>1 # div2 and return
        elif voicebank == 'bankB' : 
            return (offs>>1) | 0x8000 # top bit: start at bank B
        raise Exception('no assigned bank!')


    # all banks incl. the GS/XG duplicates made above: a duplicate gets its own index in the bank map, so
    # its program map must be written too (MU80: MSB 126/127 point to the GS bank; the XG copy's program
    # map stayed empty, all 128 programs read the 8-byte debug label at bank A offset 0 as a voice)
    for voicebank in voicebanks_expanded : 

        # voicebank -> voices : dict[int, str | int] #  prg, voice hash (voice address)
        bank_addr = voicebank.index * 128 * ptr_size
        for prg, addr in enumerate(range(bank_addr, bank_addr + 128 * ptr_size, ptr_size)) : 
            voice_hash = voicebank.voices[prg]
            voice = table.Voice_pool[voice_hash]
            if buildtarget.SYXG50_BIG : 
                # big layout: plain 32-bit byte offset
                offs_bytes = voice_byte_offset(voice).to_bytes(4, 'little')
            else : 
                offs_bytes = encode_SYXG50_voice_offset(voice.offset, voice.voicebank).to_bytes(2,'little')

            if voicebank.bank == Bank.GS : 
                voice_prgmap_GS[addr : addr+ptr_size] = offs_bytes
            else : 
                voice_prgmap_XG[addr : addr+ptr_size] = offs_bytes



    # * wavedata offset table
    # these are accessed via Voices and should already have unique identifiers in wavebank.index

    highest_waveIDX = max(getattr(wb, a, -1) for wb in table.Wavebank_pool.values() for a in PAGE_INDEX)
    if not paging : 
        highest_waveIDX += 1   # unchanged from before: one spare entry at the end
    if page2_start >= 0 : 
        assert highest_waveIDX >= 512
        highest_waveIDX = 768  # entry 768: page 2 start in bank B
    wavedata_offsets = bytearray((highest_waveIDX+1)*ptr_size)
    assert not paging or highest_waveIDX >= 256   # the DLL switches on paging by the table size

    for wavebank in table.Wavebank_pool.values() :
        assert wavebank.offset >= 0 
        for index in (getattr(wavebank, a, -1) for a in PAGE_INDEX) : 
            if index < 0 : continue
            assert index < 768
            addr = index * ptr_size
            wavedata_offsets[addr : addr+ptr_size] = wavebank.offset.to_bytes(ptr_size,'little')
    if page2_start >= 0 : 
        wavedata_offsets[768 * ptr_size : 769 * ptr_size] = page2_start.to_bytes(ptr_size, 'little')


    # * Construct header

    header = bytearray(100)
    # +0 - +15  - table version string
    WriteANSI(header, 0, new_table_version)
    # +16 - + 30 - wave table filename
    WriteANSI(header, 16, new_waverom_name)
    # +31 (0x1F) -  top bit= Embedded?  bottom bit = UnEncrypted?
    header[0x1F] = 0x01 # unencrypted, not embedded

    # 0x20 -> 0x2F drum bank PRG mapping table sizes (x4)
    le_128 = bytes([0x80, 0x00, 0x00, 0x00])
    header[0x20 : 0x20 +4] = le_128
    header[0x24 : 0x24 +4] = le_128
    header[0x28 : 0x28 +4] = le_128
    if drum_bank_cnt == 4 : 
        header[0x2C : 0x2C +4] = le_128

    # 0x30: drumkit keymap len
    header[0x30 : 0x30 +4] = len(drumkit_keymaps).to_bytes(4,'little')
    # 0x34: drumvoice len
    header[0x34 : 0x34 +4] = len(drum_voices).to_bytes(4,'little')

    # 0x38: drumvoice ext.voice offset table len
    header[0x38 : 0x38 +4] = len(ext_drumvoice_offsets).to_bytes(4,'little')

    # 0x3C - 0x40: voice bank maps len (GS, SFX, XG, GM2)
    header[0x3C : 0x3C +4] = le_128
    header[0x40 : 0x40 +4] = le_128
    header[0x44 : 0x44 +4] = le_128
    if voice_bank_cnt_XG == 3 : 
        header[0x48 : 0x48 +4] = le_128

    # 0x4C: GS voice program map len
    header[0x4C : 0x4C +4] = len(voice_prgmap_GS).to_bytes(4,'little')

    # 0x50: XG voice program map len
    header[0x50 : 0x50 +4] = len(voice_prgmap_XG).to_bytes(4,'little')

    # 0x54: Voices bank A len
    header[0x54 : 0x54 +4] = len(voices_bankA).to_bytes(4,'little')

    # 0x58: Voices bank B len
    header[0x58 : 0x58 +4] = len(voices_bankB).to_bytes(4,'little')

    # 0x5C: WaveData offset table len
    header[0x5C : 0x5C +4] = len(wavedata_offsets).to_bytes(4,'little')

    # 0x60: WaveData table len
    header[0x60 : 0x60 +4] = len(wavedata).to_bytes(4,'little')


    table_file : bytearray = header \
    + drumbank_prgmaps + drumkit_keymaps \
    + drum_voices + ext_drumvoice_offsets \
    + voice_bankmaps \
    + voice_prgmap_GS + voice_prgmap_XG \
    + voices_bankA + voices_bankB \
    + wavedata_offsets + wavedata

    if alt_table is not None : 
        table_file = table_file + Voice_Map_Appendix(alt_table, table, GSbanks, XGbanks, bank_map_order,
                                                     drum_bank_locations, voice_bankmaps, drumbank_prgmaps, alt_default)


    return bytes(table_file), samplemonster


