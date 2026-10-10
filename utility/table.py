from dataclasses import dataclass, field
from typing import Literal, Self, Any

from pathlib import Path

from dataenum import *



@dataclass
# * this is hashed by it's src loop address. 
class Sample() : 

    address_src : str | int # same as loop_address_src?

    offset_negative : int # samples
    offset_positive : int
    loop_address : int # identical to address_src

    sample_type : SampleFormat 

    encoding_parameters : int # * if DPCM

    # * change this to indicate updated offsets?
    # that won't work if the source is s-yxg50!
    format : MU 

    address_book : set[int] 

    # trace *every* associated name
    names : set[str] = field(default_factory=set)

    out_loop_address : int = -1 
    out_sample_type : SampleFormat = SampleFormat.TMP
    written : bool = False # just update loop_address and use this
    waverom_bank : int = 0 # for multiple table input, to keep track of source rom

    # todo not implemented yet, but referenced
    # voices contain "offset offsets" which will need to be modified as well
    upsample_mult : int = 1 

    # get first name on the list
    def get_a_name(self) : 
        if not len(self.names) : 
            return ''
        for n in self.names : 
            return n

    # During our intake, we'll find many cases where the samples are clipped
    # to quiet the transients, or for whatever other reason
    # so whenever dupes are found, check them against here and we'll return the bigger one
    # To keep the clipped voices, start offsets and loop offsets are encapsulated upstream 
    # ... in either Wave or DrumVoice objects
    def ReturnGreater(self, self2 : Self) -> Self : 
        # *  take the max of both negative and positive
        # ... did not result in any changes, at least in MU80
        out = self if self.len_samples() >= self2.len_samples() else self2
        out.offset_negative = max(self.offset_negative, self2.offset_negative)
        out.offset_positive = max(self.offset_positive, self2.offset_positive)
        return out


    def len_samples(self) : 
        return self.offset_positive + self.offset_negative

    def get_start_address(self) -> int : 

        bits_per_sample = SampleFormat_To_Bits(self.sample_type)
        offs_bytes = int(((self.offset_negative * bits_per_sample) / 8))

        return self.loop_address - offs_bytes

    # nibble check which should only be relevant for S12
    # returns [1]==True if first byte is on last half a byte   
    def get_start_address_12bit(self) -> tuple[int, bool] : 

        bits_per_sample = SampleFormat_To_Bits(self.sample_type)
        offs_bytes = int(((self.offset_negative * bits_per_sample) / 8)+0.5) # round up if fractional
        start_on_nibble =  bool((self.offset_negative * bits_per_sample) % 8)

        return(self.loop_address - offs_bytes, start_on_nibble)

    # nibble check which should only be relevant for S12
    # returns [1]==True if last byte is on first half a byte   
    def get_end_address_12bit(self) -> tuple[int, bool] : 

        bits_per_sample = SampleFormat_To_Bits(self.sample_type)
        offs_bytes = int(((self.offset_positive * bits_per_sample) / 8)+0.5) # round up if fractional
        start_on_nibble =  bool((self.offset_positive * bits_per_sample) % 8)

        return(self.loop_address + offs_bytes, start_on_nibble)

    def get_end_address(self) -> int : 

        bits_per_sample = SampleFormat_To_Bits(self.sample_type)
        offs_bytes = int(((self.offset_positive * bits_per_sample) / 8)) 

        return self.loop_address + offs_bytes

    def len_bytes(self) -> tuple[int, bool] : 

        bits_per_sample = SampleFormat_To_Bits(self.sample_type)
        totalbytes = int(((self.offset_negative + self.offset_positive) * bits_per_sample) / 8) 
        remainder =  bool(((self.offset_negative + self.offset_positive) * bits_per_sample) % 8)

        return(totalbytes, remainder)

    # just a helper for rom reconsruction. does not update object
    # * call immediately *before* appending sample to new waverom
    def Get_New_Loop_Address(self, waverom : bytearray) -> int :  
        bits_per_sample = SampleFormat_To_Bits(self.sample_type)
        offs_bytes = int(((self.offset_negative * bits_per_sample) / 8))
        return len(waverom) + offs_bytes



# * picks the longer of two samples if they conflict
# * key should be the src loop address
def AddToSampleList(samples : dict[Any, Sample], s : Sample) : 

    if s.address_src not in samples.keys() : 
        samples[s.address_src] = s
        return

    # ? the huge address list is confusing, but allows for a more complete RomBackTrace()
    addrs = samples[s.address_src].address_book | s.address_book
    names = samples[s.address_src].names | s.names
    samples[s.address_src] = samples[s.address_src].ReturnGreater(s)
    samples[s.address_src].names = names
    samples[s.address_src].address_book = addrs


# picks the longer of two samples if any conflict
def MergeSampleDicts(dict_1 : dict[Any, Sample], dict_2 : dict[Any, Sample]) -> dict[Any, Sample] :
   dict_3 = {**dict_1, **dict_2}
   for key in dict_3.keys():
       if key in dict_1 and key in dict_2:
               addrs = dict_1[key].address_book | dict_2[key].address_book 
               names = dict_1[key].names | dict_2[key].names 
               dict_3[key] = dict_1[key].ReturnGreater(dict_2[key])
               dict_3[key].names = names
                # ? the huge address list is confusing, but allows for a more complete RomBackTrace()
               dict_3[key].address_book = addrs
   return dict_3
    



# Contained by WaveBank. 
# unlike voices/drumvoices, these are abstracted on decode, rather than a big lump of bytes
# not used for DrumVoices
@dataclass
class Wave() : 

    # wavedatatable entry address in src rom
    address_src : str | int 

    offset_negative : int 
    offset_positive : int

    # * used to find connected sample. 
    # Use Wave offsets + Samples loop address
    loop_address_src : int 

    attenuation : int
    tune_note : int
    tune_cent : int
    key_min : int
    key_max : int

    mu90_plus4 : int = 0    # mu90 unknown byte
    backwards : bool = False # mu90

@dataclass
class WaveBank() : 

    address_src : str | int # should == first wave in list
    waves : list[Wave]

    # for reconstruction
    index : int = -1 
    out_data : bytes = bytes()
    offset : int = -1

    def __len__(self) -> int : 
        return len(self.waves) * 16

    def get_samples(self, sample_pool : dict[str | int, Sample]) -> list[Sample] : 
        out : list[Sample] = []
        for w in self.waves : 
            out.append(sample_pool[w.loop_address_src])
        assert len(out) == len(self.waves)
        return out




# contained by Voice
@dataclass
class Element() : 

    wavebank_address : str | int # should match WaveBank.address_src

    data : bytearray | bytes 
    format : MU

    # just for debugging - don't use in dicts
    waveID : int 

    def get_wavebank(self, wavebank_pool : dict[str | int, WaveBank]) -> WaveBank: 
        return wavebank_pool[self.wavebank_address]


# holds elements
@dataclass 
class Voice() : 

    address_src : str | int #  src address

    volume : int
    name : str

    elements : list[Element]
    
    format : MU

    # for reconstruction, do not serialize
    converted : bool = False 
    extvoice_index : int = -1 
    data : bytes = bytes()
    offset : int = -1 # note: real, not 15 bit or multiplied
    voicebank : Literal['bankA', 'bankB', ''] = ''

    def __len__(self) : 
        length : int = 2 # +0=volume +1=element cnt
        for e in self.elements :
            length = length + len(e.data)
        return length

    def get_wavebanks(self, wavebank_pool : dict[str | int, WaveBank]) -> list[WaveBank]: 
        l = []
        for e in self.elements : 
            l.append(wavebank_pool[e.wavebank_address])
        return l



# drum voices include sample information. sometimes
@dataclass
class DrumVoice() : 

    # For now, we just box up this data and convert it on table reconstruction
    # see cnv modules
    data : bytes | bytearray

    Sample_hash : str | int
    ext_Voice_address : str | int # for external voice only!!

    offset_negative : int 
    offset_positive : int

    format : MU

    # debug, help trace addresses during decoding
    address_book : set[int]

    # for reconstruction, do not serialize
    converted : bool = False
    extvoice_index : int = -1
    offset : int = -1

    def get_sample(self, Sample_pool : dict[str | int, Sample]) : 
        return Sample_pool[self.Sample_hash]

    def get_voice(self, Voice_pool : dict[str | int, Voice]) -> Voice | None : 
        if self.ext_Voice_address : 
            return Voice_pool[self.ext_Voice_address]

    def uses_ext_voice(self) -> bool:
        return bool(self.ext_Voice_address)



@dataclass
class VoiceBank() : 
    # prg table address (keeps it s-yxg50 compatible)
    prg_address : int | str 

    bank : Bank
    lsb : int
    msb : int

    seqID : int # debug mostly

    voices : dict[int, str | int] # * prg, voice hash (voice address)

    # bank, byte (msb or lsb, depends on bank, get with BankToLSBMSB)
    aliases : list[tuple[Bank, int]]

    # for reconstruction
    index : int = -1

    # return MSB for gs/sfx, LSB for xg/gm2
    def relevant_byte(self) -> int : 
        if self.bank == Bank.GS or self.bank == Bank.SFX : 
            return self.msb
        else : 
            return self.lsb
        
    # # old, use BankToLSBMSB
    # @staticmethod
    # def alias_to_lsb_msb(alias : tuple[Bank, int]) -> tuple[int,int] : 
    #     bank, byte = alias
    #     match bank : 
    #         case Bank.GS | Bank.SFX : 
    #             return 0, byte
    #         case Bank.GM2 : 
    #             return byte, 121
    #         case _ : # XG 
    #             return byte, 0

    def info(self) -> str : 
        return f'{self.bank} {self.lsb:03}{self.msb:03}'

    def get_voice(self, Voice_pool : dict[int | str, Voice] , prg) -> Voice : 

        voice_hash = self.voices[prg]
        return Voice_pool[voice_hash]

    def tryget_voice(self, Voice_pool : dict[int | str, Voice] , prg, verbose = True) -> Voice | None: 
        if not prg in self.voices : 
            if verbose : print(f'tryget_voice: {self.info()} could not find prg={prg}')
            return
        voice_hash = self.voices[prg]

        if not voice_hash in Voice_pool : 
            print(f'tryget_voice: {self.info()} could not associated voice for prg {prg}! hash={voice_hash}')
            return # ^ serious error!
        return Voice_pool[voice_hash]



@dataclass
class DrumKit() : 

    # keymap table address
    keymap_address : int

    # MSB / LSB implicitly fixed based on bank enum. use BankToLSBMSB to decode
    bank : Bank 
    prg : int

    # * note, DrumVoice_Pool holds this dict's hash
    drumvoices : dict[int, int | str] 

    # for external voices
    voices : dict[int, int | str] 

    seqID : int # * for debug mostly

    # list of duplicate indexes [bank, prg] 
    aliases : list[tuple[Bank, int]]

    name : str = ''

    # recontruction
    index : int = -1

    def get_drumvoice(self, DrumVoice_pool : dict[str | int, DrumVoice], key : int ) : 
        return DrumVoice_pool[self.drumvoices[key]]




# * keys for dictionaries are rom addresses
# * except for Samples, which use their wave address (loop address)
# voicebanks key is the prg table address (keeps it s-yxg50 compatible)
# drumkits key is keymap table address (more consistent with voicebanks key)

# objects in charge of wrangling other objects must keep these keys on em
# ? after importing is complete, the keys can be baked with prefixes to avoid future conflicts

@dataclass
class Table() : 
    name : str
    # If our Voice/Drumvoice is missing format, we can pull from the table
    # Thinking ahead for serialization
    format : MU 

    # key = src loop address
    Sample_pool : dict[str | int, Sample]           #    -> Samples 

    # keys=rom addresses
    Wavebank_pool : dict[str | int, WaveBank]       #    -> list[Wave] > Sample Hash
    Voice_pool : dict[str | int, Voice]             #    voice > Element > Wavebank Hash > Sample Hash
    DrumVoice_pool : dict[str | int, DrumVoice]     #    Drum Voice > Sample Hash
                                                    #            \--> Voice Hash

    # Bank lists, they hold keys and no actual data
    # key=keymap table address
    drumkits : dict[int|str, DrumKit]                #    > Drum Voice Hash
    # key=prg table address
    voice_banks : dict[int|str, VoiceBank]           #    > voice hash   key=prgmap start address

    waveroms : list[Path]
    waveroms_byte_len : int 

    def Get_Drumkit(self, bank : Bank, prg : int) -> DrumKit | None : 
        assert IsDrumBank(bank)

        for kit in self.drumkits.values() : 
            if (bank, prg) == (kit.bank, kit.prg) : 
                return kit

            for alias_bank, alias_prg in kit.aliases : 
                if (bank, prg) == (alias_bank, alias_prg) : 
                    return kit

    # can grab lsb and msb using BankToLSBMSB(bank, byte)
    def Get_VoiceBank(self, bank : Bank, lsb : int, msb : int) -> VoiceBank | None : 
        assert not IsDrumBank(bank)

        for vb in self.voice_banks.values() : 
            if (vb.bank, vb.lsb, vb.msb) == (bank,lsb,msb) : 
                return self.voice_banks[vb.prg_address]

            for alias in vb.aliases : 
                alias_lsb, alias_msb = BankToLSBMSB(alias[0], alias[1]) # alias 0=bank, 1=byte
                if (vb.bank, alias_lsb, alias_msb) == (bank,lsb,msb) : 
                    return self.voice_banks[vb.prg_address]
                    
        print(f'GetVoiceBank {bank} {lsb:03}{msb:03}XXX no Voice Bank found')







def PrintTableInfo(table : Table) : 

    print(f'---------------------------------')
    print(f'Info for table \'{table.name}\'')

    print(f'---------------------------------')
    print(f'       Drum Kits {len(table.drumkits)} ...up to 0x{'{:02X}'.format(max(len(table.drumkits)-1,0))}')
    print(f'     Drum Voices {len(table.DrumVoice_pool.keys())}')

    c = 0
    # ctotal : int = 0
    extvoices : set[int] = set()
    for kit in table.drumkits.values() :
         if len(kit.voices) : 
            for voiceaddr in kit.voices.keys() : 
                if voiceaddr not in extvoices : 
                    c = c + 1
                    extvoices.add(voiceaddr)

    print(f' Ext. Drum Voices {c}')
    print(f'Total Drum Voices {len(table.DrumVoice_pool.keys())+c}')

    print(f'---------------------------------')
    print(f'     Voice Banks {len(table.voice_banks.keys())}')
    print(f'          Voices {len(table.Voice_pool.keys())}')
    print(f'WaveData Entries {len(table.Wavebank_pool.keys())} / 255')
    print(f'---------------------------------')
    print(f'  Unique Samples {len(table.Sample_pool.keys())}')
    size_in : int = 0
    size_out : int = 0 # approx size once incompatible sample types are converted to s16
    for sample in table.Sample_pool.values() : 
        b, _ = sample.len_bytes()
        size_in = size_in + b
        match sample.sample_type : 
            case SampleFormat.ADPCM : 
                size_out = size_out + (b * 2)
            case SampleFormat.S12 : 
                size_out = size_out + int((b * (16.0/12.0))+0.5)
            case _ :
                size_out = size_out + b
    print(f' approx wave read: {size_in:,} bytes ({size_in/table.waveroms_byte_len:.2%})')
    print(f'approx wave write: {size_out:,} bytes ({(size_out/size_in):.2%})')


