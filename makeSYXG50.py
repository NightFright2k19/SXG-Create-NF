from typing import Generator

from table import *
from cnv_fromBASE import TableConverter 
import SampleConvert

import decSYXG50

from utils import fmtbyte, fmtbytes

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
        out[offs+3:offs+3+3] = wave.offset_negative.to_bytes(3, 'big')

        # +6: blank
        # *  +7: offset_positive 16 bits confirmed D:
        if wave.offset_positive > 0xFFFF : 
            print(f'makeSYXG50 -> WriteWaveData: Warning, WDT srcaddr=0x{wave.address_src} ({sample.get_a_name()}) loop too long for S-YXG50! Clamping from {wave.offset_positive} to 65535')
            out[offs+7:offs+7+2] = 0xFFFF.to_bytes(2, 'big')
        else : 
            out[offs+7:offs+7+2] = wave.offset_positive.to_bytes(2, 'big')

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
def MakeSYXG50(table : Table, in_waves : bytes, tablecnv : TableConverter, new_table_version : str, new_table_name : str, new_waverom_name : str, VOICE_PAD : int = 8) -> tuple[bytes,SampleConvert.SampleMonster]  : 

    
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
    extvoiceIDX = (i for i in range(350)) # next(extvoiceIDX)

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

            if wavebank.index < 0 : 
                wavebank.index = next(waveIDX)

        tablecnv.ConvertElements(voice, voice.get_wavebanks(table.Wavebank_pool), MU.SYXG50)
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
            tablecnv.ConvertDrumVoice(drumvoice, drumvoice.get_sample(table.Sample_pool), 
                                        drumvoice.get_voice(table.Voice_pool), 
                                        target=MU.SYXG50)
        drumvoice.converted = True

        # test_after : str = fmtbytes(drumvoice.data)


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
    if VOICE_PAD == 0 : 
        for voice in table.Voice_pool.values() : 
            assert voice.converted
            if len(voices_bankA) < (0xFFFF - len(voice)) : 
                offs = len(voices_bankA)
                voices_bankA = voices_bankA + voice.data
                voice.offset = offs
                voice.voicebank = 'bankA'
            else : 
                offs = len(voices_bankB)
                assert offs <= 0xFFFF # out of space!
                voices_bankB = voices_bankB + voice.data
                voice.offset = offs
                voice.voicebank = 'bankB'

    # * print name before our voice for easier debugging
    elif VOICE_PAD == 8 :  
        for voice in table.Voice_pool.values() : 
            assert voice.converted
            name = voice.name[0:9]
            assert len(name) == 8

            str_bytes = name.encode(encoding='cp1252')

            if len(voices_bankA) < (0xFFFF - (len(str_bytes) + len(voice)) ) : 
                offs = len(str_bytes) + len(voices_bankA)
                voices_bankA = voices_bankA + str_bytes + voice.data
                voice.offset = offs
                voice.voicebank = 'bankA'
            else : 
                offs = len(str_bytes) + len(voices_bankB)
                assert offs <= 0xFFFF # out of space!
                voices_bankB = voices_bankB + str_bytes + voice.data
                voice.offset = offs
                voice.voicebank = 'bankB'



    highest_wavedata_index = next(waveIDX)-1

    to_delete = []
    for key, wavebank in table.Wavebank_pool.items() :  # * debug
        if wavebank.index < 0 : 
            to_delete.append(key)

    for key in to_delete : del table.Wavebank_pool[key]

    # create wavedata table
    # relevant offset value stored in wavebank.offset
    for idx in range(highest_wavedata_index+1) : 
        for wavebank in table.Wavebank_pool.values() : 

            if not wavebank.index == idx : continue

            offs = len(wavedata)
            wavedata = wavedata + wavebank.out_data
            wavebank.offset = offs
            break


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

    ext_drumvoice_offsets = bytearray((highest_extvoice_index+1) * 2)

    for idx, addr in enumerate(range(0, len(ext_drumvoice_offsets), 2) ) : 

        for drumvoice in table.DrumVoice_pool.values() : 
            if drumvoice.extvoice_index == idx : 
                voice = drumvoice.get_voice(table.Voice_pool)
                assert voice
                assert voice.offset >= 0
                ext_drumvoice_offsets[addr:addr+2] = voice.offset.to_bytes(2, 'little')



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

                        if vb.prg_address not in GSbanks : 
                            GSbanks[vb.prg_address] = new_voicebank
                        else : 
                            GSbanks[vb.prg_address].aliases.append((dupebank, dupebyte))

    # S-YXG50 voicebank mapping is very fragile!
    # sort XGbank SFX MSB1 (silent bank) first
    # ! THIS IS LOAD BEARING, if XG voice banks start at index 00 it breaks bank changing!
    for xgbank in XGbanks.values() : 
        if xgbank.bank == Bank.SFX and xgbank.msb == 1 : 
            xgbank.index = next(banksXG_IDX)
            break

    # ! additionally: XG voice banks must start at 01
    # todo: none of the XG range can be 00, this is currently causing issues with the MU90
    # ? though XG MSB(SFX) and GM2 use 00 just fine
    for xgbank in XGbanks.values() : 
        if xgbank.bank == Bank.XG and xgbank.lsb == 0 : 
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
    voice_prgmap_GS = bytearray((highest_bankID_GS+1) * 256)
    voice_prgmap_XG = bytearray((highest_bankID_XG+1) * 256)

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


    for voicebank in table.voice_banks.values() : 

        # voicebank -> voices : dict[int, str | int] #  prg, voice hash (voice address)
        bank_addr = voicebank.index * 256
        for prg, addr in enumerate(range(bank_addr, bank_addr+256, 2)) : 
            voice_hash = voicebank.voices[prg]
            voice = table.Voice_pool[voice_hash]
            offs = encode_SYXG50_voice_offset(voice.offset, voice.voicebank)

            if voicebank.bank == Bank.GS : 
                voice_prgmap_GS[addr : addr+2] = offs.to_bytes(2,'little')
            else : 
                voice_prgmap_XG[addr : addr+2] = offs.to_bytes(2,'little')



    # * wavedata offset table
    # these are accessed via Voices and should already have unique identifiers in wavebank.index

    highest_waveIDX = next(waveIDX)-1
    wavedata_offsets = bytearray((highest_waveIDX+1)*2)

    for wavebank in table.Wavebank_pool.values() :
        assert wavebank.index >= 0 
        assert wavebank.offset >= 0 
        addr = wavebank.index * 2
        wavedata_offsets[addr : addr+2] = wavebank.offset.to_bytes(2,'little')


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


    return bytes(table_file), samplemonster


