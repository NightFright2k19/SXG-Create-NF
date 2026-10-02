from decBase import *



# * designed to work with everything - MU80, MU50, S-YXG50, and MU90
# but we'll see if that holds
def Create_Table(MUinfo : MUdecoder, table_name : str, data : bytes | bytearray, waveroms : list[Path]) -> Table :

    Sample_pool : dict[str | int, Sample] = {}
    Wavebank_pool : dict[str | int, WaveBank] = {}
    Voice_pool : dict[str | int, Voice] = {}
    Drumvoice_pool : dict[str | int, DrumVoice] = {}

    drumkits : dict[int | str, DrumKit] = {}

    voice_banks : dict[int | str, VoiceBank] = {}

    waverom_length : int = 0
    for rom in waveroms : 
        waverom_length = waverom_length + len(bytes(open(rom, mode='rb').read() ))
    if MUinfo.waverom_span : 
        waverom_length = MUinfo.waverom_span



    # * Trace and decode Drum Voices ---------

    for idx, bank in enumerate(MUinfo.bankorder_drums) : 

        # both LSB and MSB can be inferred by just the section they are in / bank enum
        lsb, msb = BankToDrumLSBMSB(bank) 

        # * Drum PRG assignment tables (128 bytes)   # idx= program,  value = seqID

        drumPRG_address = MUinfo.drumbank_PRGs.start + (128 * idx)

        for prg, seqIDaddress in enumerate(range(drumPRG_address, drumPRG_address + 128)) : 

            kit_seqID = data[seqIDaddress]

            if kit_seqID == 0xFF :
                continue

            # * Drumkit / Keymaps (256 byte tables)  idx*2 = key#,  value = drumvoice offset
            drumkit_keymap_address = MUinfo.drumkit_keymaps.start + (256 * kit_seqID)
            assert drumkit_keymap_address < MUinfo.drumkit_keymaps.end


            # add duplicate maps to "aliases" list. Tuple of (bank enum, byte) 
            # what the byte represents depends on context
            # for drumkits, it's always PRG (use BankToDrumLSBMSB to get lsb/msb)
            # for voice banks, it's either LSB or MSB (use BankToLSBMSB to get lsb/msb)
            if drumkit_keymap_address in drumkits : 
                drumkits[drumkit_keymap_address].aliases.append((bank, prg) )
                continue


            #  debug: try to attach a name to our samples
            # _, kit_name, _ = dataXG.TryFindPatch(bank, lsb, msb, prg, drums=True)
            # if not success : kit_name = f'{bank.value}_{lsb:03}{msb:03}{prg:03}' 
            kit_name = f'{bank.value}_{lsb:03}{msb:03}{prg:03}'


            drumkit = DrumKit(drumkit_keymap_address, bank, prg, {}, {}, aliases=[], seqID=kit_seqID)
            if kit_name : drumkit.name = kit_name

            for key, keyaddress in enumerate(range(drumkit_keymap_address, drumkit_keymap_address + 256, 2)) : 

                # drumvoice_offs = MUinfo.b16.decode_bytes(data, keyaddress)
                drumvoice_offs = MUinfo.decode_bytes(data, keyaddress, 16, MUinfo.endian)

                if drumvoice_offs == 0xFFFF : continue

                drumvoice_address = MUinfo.drum_voices.start + (drumvoice_offs)
                assert drumvoice_address < MUinfo.drum_voices.end

                ExtVoiceAddress, drumvoice, sample = MUinfo.ProcessDrumVoice(data, drumvoice_address)
                assert sample.get_start_address() >= 0
                assert sample.get_end_address() < waverom_length

                if not ExtVoiceAddress :

                    sample.names = {f'{kit_name}_{key:02}'}

                    Drumvoice_pool[drumvoice_address] = drumvoice
                    AddToSampleList(Sample_pool, sample)

                    drumkit.drumvoices[key] = drumvoice_address

                else : 

                    # * handle drumvoice linked to regular voice
                    voice, ext_wavebanks, ext_samples = MUinfo.ProcessVoice(data, ExtVoiceAddress)

                    for i, sample in enumerate(ext_samples.values()) : 
                        sample.names = {f'{kit_name}_{key:02}#{i}'}
                        # sample.address_book.add(ExtVoiceAddress) # add element addr instead

                    Voice_pool[ExtVoiceAddress] = voice
                    Drumvoice_pool[drumvoice_address] = drumvoice

                    Wavebank_pool = Wavebank_pool | ext_wavebanks

                    Sample_pool = MergeSampleDicts(Sample_pool, ext_samples)

                    drumkit.drumvoices[key] = drumvoice_address
                    drumkit.voices[ExtVoiceAddress] = voice.address_src


            drumkits[drumkit_keymap_address] = drumkit



    # * Trace and decode Regular Voices ---------

    # * instrument bank definition tables, 128 byte w/ sequential IDs
    for tablenum, bank in enumerate(MUinfo.bankorder_voice) : 

        banktable_address = MUinfo.voice_banks.start + (128 * tablenum)

        for idx, bankaddress in enumerate(range(banktable_address, banktable_address + 128 )) : 

            lsb, msb = BankToLSBMSB(bank, idx)

            prg_seqID = data[bankaddress]

            # note: 0xFF programs are only valid for GS mode in S-YXG50
            if prg_seqID == 0xFF :
                continue

            prgmap_stride = 128 * MUinfo.prgmap_entry_bytes
            program_map_address = MUinfo.voice_PRGmap.start + (prg_seqID * prgmap_stride)

            # S-YXG50: program sections split into GS & Non-GS
            if MUinfo.source == MU.SYXG50 : 
                if bank == Bank.GS : 
                    program_map_address = MUinfo.SXG50_Prgmap_GS.start + (prg_seqID * 256)
                else : 
                    program_map_address = MUinfo.SXG50_Prgmap_XG.start + (prg_seqID * 256)

            assert program_map_address < MUinfo.voice_PRGmap.end


            # add duplicate voicebank maps to "aliases" list. Tuple of (bank enum, byte) 
            # use BankToLSBMSB(bank,byte) to decode to lsb/msb
            if program_map_address in voice_banks : 
                voice_banks[program_map_address].aliases.append((bank, idx))
                continue

            voicebank = VoiceBank(program_map_address, bank, lsb, msb, voices={}, aliases=[], seqID=prg_seqID)


            # * program definitions, 256 byte table w/ offsets for 'voices' table(s)

            for prg, offset_address in enumerate(range(program_map_address, program_map_address + prgmap_stride, MUinfo.prgmap_entry_bytes) ) :

                voice_offset_raw = MUinfo.decode_bytes(data, offset_address, 8 * MUinfo.prgmap_entry_bytes, MUinfo.endian)

                # S-YXG50: top bit of program map offset determines whether to start in voicesA or voicesB
                # MU50 through MU90: One big voices section
                if MUinfo.source == MU.SYXG50 : 
                    if voice_offset_raw & 0x8000 : 
                        voice_bank_start = MUinfo.SXG50_VoicesB.start
                    else : 
                        voice_bank_start = MUinfo.SXG50_VoicesA.start

                    voice_offset = (voice_offset_raw & 0x7FFF) * 2
                else : 
                    voice_bank_start = MUinfo.voices.start
                    # Voices offset is * 2 (MU50-MU90), plain on the MU100
                    voice_offset = voice_offset_raw * MUinfo.prgmap_offset_mult

                # ? unlike in the drumkit keymaps, I think FFFF will just crash S-YXG50
                assert voice_offset != 0xFFFF 

                voice_address = voice_bank_start + voice_offset
                assert voice_address < MUinfo.voices.end


                # * this is two linked passes of encapsulation: ProcessVoice (Voices/Elements) -> ProcessWavedata (WaveBank/Samples)
                # returns: Voice, dict[str | int, WaveBank], dict[int, Sample]
                voice, some_wavebanks, some_samples = MUinfo.ProcessVoice(data, voice_address)

                assert len(some_wavebanks)
                assert len(some_samples)

                # debug: try to attach names to our samples
                if len(voice.name) : 
                    name = voice.name
                else : 
                    # _, name, _ = dataXG.TryFindPatch(bank, lsb, msb, prg)
                    name = f'{bank.value[:2]}{idx:03}{prg:03}' # 8 chars

                for i, sample in enumerate(some_samples.values()) : 
                    assert sample.get_start_address() >= 0
                    assert sample.get_end_address() < waverom_length
                    sample.names = {f'{name}#{i:02}'} if len(some_samples) > 1 else {f'{name}'}


                Voice_pool[voice_address] = voice
                voicebank.voices[prg] = voice_address

                Wavebank_pool = Wavebank_pool | some_wavebanks

                # special merge, will pick the longer of two duplicate samples 
                # dupes determined by having the same loop address 
                # (loop address is used as a dictionary key in table.Samples_pool)
                # body/loop offsets will be contained upstream as well, in Wave or DrumVoice objects
                Sample_pool = MergeSampleDicts(Sample_pool, some_samples)


            voice_banks[program_map_address] = voicebank



    return Table(table_name, MUinfo.source, 
                    Sample_pool=Sample_pool, Wavebank_pool=Wavebank_pool, 
                    Voice_pool=Voice_pool, DrumVoice_pool=Drumvoice_pool, 
                    drumkits=drumkits, 
                    voice_banks=voice_banks, 
                    waveroms=waveroms,
                    waveroms_byte_len=waverom_length)
