
from decBase import *

from utils import fmtbyte, fmtbytes

# * MU90 wave ROMs: xs518a0 and xs743a0 are two 16-bit halves of one 32-bit data bus.
# Word n = xs518a0[2n:2n+2] + xs743a0[2n:2n+2], read as a little-endian byte stream.
# (verified: 8-bit, 12-bit, 16-bit and ADPCM samples all decode to smooth audio this way,
# and consecutive samples line up back to back with only 1-4 words of padding in between)
def MU90_Waverom(rom_a : bytes, rom_b : bytes) -> bytes :
    assert len(rom_a) == len(rom_b)
    out = bytearray(len(rom_a) * 2)
    for i in range(0, len(rom_a), 2) :
        out[2*i : 2*i+2] = rom_a[i : i+2]
        out[2*i+2 : 2*i+4] = rom_b[i : i+2]
    return bytes(out)


# * "backwards" flag (wavedata +8 / drum voice +34, bit 7): the hardware plays the sample in
# reverse, starting at the loop address. Yamaha uses this both ways: the tom sample is stored
# backwards in the ROM and only sounds right with the flag (toms 47/48/50 of the standard kits,
# MelodTom, Real Tom), while the same data without the flag gives Rev Tom / Rev Kick etc.
# The reversed copy gets its own sample-pool key; the data is reversed on conversion
# (SampleConvert.ConvertSample). The reversed sample is a one-shot.
REVERSED_KEY = 0x40000000

# * drum HPF (MU100 and later): XG drum setup "HPF Cutoff Frequency" is stored per drum voice
# (MU100 +21, MU1000 +20; the MU90 has no HPF). syxg50.dll has no high-pass filter, so it is
# baked into a filtered copy of the sample. Measured on the S-MU2000 (MU2000 firmware):
# 2nd-order high-pass, Q ~1.0, cutoff at the output 2^(5.066 + 0.0591 * value) Hz
# (value 55 = 319 Hz, 61 = 407 Hz, 69 = 565 Hz, 94 = 1.57 kHz), independent of the note pitch.
# The sample is filtered in its own time base, so the cutoff is divided by the playback ratio
# 2^((byte0 - root + tune note)/12 + tune cent/1200) (root +26, tune +27/+28, MU90 layout;
# verified against the S-MU2000 recordings, within ~0.5 semitone).
HPF_KEY_SHIFT = 36

def Drum_HPF_Cutoff(value : int) -> float :
    return 2 ** (5.066 + 0.0591 * value)

def Apply_Drum_HPF(sample : Sample, drum : bytes | bytearray, value : int) -> None :
    if not value :
        return
    s8 = lambda b : b - 256 if b > 127 else b
    semis = drum[0] - drum[26] + s8(drum[27])
    ratio = 2 ** (semis / 12 + s8(drum[28]) / 1200)
    fc = min(Drum_HPF_Cutoff(value) / ratio, 18000.0)
    sample.hpf_fc = max(1, round(fc))
    # own sample-pool key: the filtered copy must not replace the plain sample
    sample.address_src = sample.address_src + ((sample.hpf_fc + 1) << HPF_KEY_SHIFT)


# * element HPF (MU128 engine: MU128 / MU1000 / MU2000): element byte +80 is a high-pass cutoff
# (0 = off), same scale as the drum HPF and also fixed in Hz, independent of the note.
# Measured on the S-MU2000 (Oboe +80=80: -21 dB at 250 Hz, -5 dB at 630 Hz at both C2 and C4;
# Muted Guitar +80=49: -11 dB at 125 Hz): 2nd-order high-pass, Q ~1.0, 2^(5.066 + 0.0591 * value) Hz.
# syxg50.dll has no HPF, so the multisample gets a filtered copy. The sample is filtered in its
# own time base, which makes the cutoff follow the pitch within one wave: so the low keys of a
# wave (fundamental below 3x the cutoff, where the cutoff is audible) are cut into pieces of
# ELEMENT_HPF_SPAN keys, each with its own filtered copy set for its middle key (+-3 semitones);
# the keys above share one copy, set for their lowest key. Keys outside ELEMENT_HPF_KEYS belong to
# the outermost piece. Cutoffs are rounded to 1/6 octave, so copies are shared between elements
# and pieces wherever they come out the same.
ELEMENT_HPF_MIN = 16                # below ~62 Hz: no audible effect, left out
ELEMENT_HPF_SPAN = 6
ELEMENT_HPF_KEYS = (24, 108)

def Rounded_HPF_Cutoff(fc : float) -> int :
    import math
    return max(1, round(2 ** (round(math.log2(max(fc, 1.0)) * 6) / 6)))

def HPF_Sample(sample : Sample, fc : float) -> Sample :
    import copy
    fc = Rounded_HPF_Cutoff(min(fc, 18000.0))
    s = copy.copy(sample)
    s.address_book = set(sample.address_book)
    s.names = set(sample.names)
    s.hpf_fc = fc
    s.hpf_element = True
    s.address_src = sample.address_src + ((fc + 1) << HPF_KEY_SHIFT)
    return s

# * static pitch EG: all five PEG levels equal (rates do not matter then) and no PEG velocity
# sensitivity, so the element always plays this many semitones away from key + coarse tune.
# Depth 0..3 = +-3 / 6 / 12 / 24 semitones at level 0 / 127 (measured in syxg50.dll: linear in
# the level, 64 = 0). E.g. Parasite element 2: coarse tune -24, PEG depth 3, all levels 127 = +24.
# Element layouts: MU128 / MU1000 (84 bytes) and MU90 / MU100 (70 bytes, see cnv_fromMU90).
def Static_PEG_Semitones(element : bytes | bytearray) -> float :
    if len(element) == 84 :
        depth, vel_sens, levels = element[19], element[20], element[28 : 33]
    elif len(element) == 70 :
        depth, vel_sens, levels = element[9] >> 6, (element[10] >> 4) - 7 + 64, element[21 : 26]
    else :
        return 0.0
    level = levels[0]
    if vel_sens != 64 or any(l != level for l in levels) or level == 64 :
        return 0.0
    return 3 * 2 ** depth * (level - 64) / (63 if level > 64 else 64)

def Apply_Element_HPF(wavebank : WaveBank, samples : dict[int, Sample], value : int,
                      element : bytes | bytearray) -> tuple[WaveBank, dict[int, Sample]] :
    import copy, math
    fc_out = Drum_HPF_Cutoff(value)
    # wave key ranges are in key + coarse tune (the DLL and the MU pick the wave by the transposed key,
    # see elemreduce.merge_wavebanks), so the critical key and the pitch ratio are taken in that domain.
    # A static pitch EG moves the played pitch away from that key without changing the wave choice:
    # Parasite (coarse -24, PEG +24) had its cutoff set two octaves too high, -13 dB at C4.
    peg = Static_PEG_Semitones(element)
    critical = 69 + 12 * math.log2(3 * fc_out / 440) - peg     # waves below: fundamental < 3 x cutoff
    lo_k, hi_k = (round(k - peg) for k in ELEMENT_HPF_KEYS)     # played keys 24..108
    waves : list[Wave] = []
    out : dict[int, Sample] = {}
    for w in wavebank.waves :
        a, b = max(w.key_min, lo_k), min(w.key_max, hi_k)
        if b < a :                  # wave entirely outside: one piece
            a = b = hi_k if w.key_min > hi_k else w.key_max
        pieces : list[tuple[int, int, float]] = []      # first key, last key, reference key
        c = min(b + 1, max(a, math.ceil(critical)))     # first non-critical key
        if c > a :
            n = -(-(c - a) // ELEMENT_HPF_SPAN)
            bounds = [a + round(i * (c - a) / n) for i in range(n + 1)]
            pieces += [(bounds[i], bounds[i + 1] - 1, (bounds[i] + bounds[i + 1] - 1) / 2) for i in range(n)]
        if c <= b :
            pieces.append((c, b, c + 1))
        for i, (k0, k1, ref) in enumerate(pieces) :
            ratio = 2 ** ((ref + peg - w.tune_note) / 12)
            s = HPF_Sample(samples[w.loop_address_src], fc_out / ratio)
            AddToSampleList(out, s)
            nw = copy.copy(w)
            nw.key_min = w.key_min if i == 0 else k0
            nw.key_max = w.key_max if i == len(pieces) - 1 else k1
            nw.loop_address_src = s.address_src
            waves.append(nw)
    return WaveBank(f'{wavebank.address_src}_hpf{value}', waves), out


def Make_Reversed(sample : Sample) -> tuple[Sample, int, int] :
    sample.reverse = True
    sample.src_offset_negative = sample.offset_negative
    sample.src_offset_positive = sample.offset_positive
    sample.address_src = sample.loop_address + REVERSED_KEY
    sample.offset_negative = sample.offset_negative + sample.offset_positive
    sample.offset_positive = 0
    return sample, sample.offset_negative, sample.offset_positive


@dataclass
class MU90(MUdecoder) : 

    # bankorder_voice : list[Bank] = [Bank.GS, Bank.SFX, Bank.XG]
    # bankorder_drums : list[Bank] = [Bank.GS_DRUMS, Bank.XG_DRUMS, Bank.SFX_DRUMS]
    # * voice bank map order on the MU90 is XG (LSB), SFX (MSB), GS (verified: the first row holds the
    # XG LSB numbers 1,3,6,8,12,..,96-101, the last one the GS variation numbers 1-11,16,24,32,40,126,127)
    bankorder_voice : list[Bank] = field(default_factory=lambda : [Bank.XG, Bank.SFX, Bank.GS] )
    bankorder_drums : list[Bank] = field(default_factory=lambda : [Bank.GS_DRUMS, Bank.XG_DRUMS, Bank.SFX_DRUMS] )

    
    
    
    @classmethod
    def From_Bytes(cls, table : bytes | bytearray) : 
        return cls(
            source = MU.MU90,
            data = table,
            # 3 tables: GS, XG msb=127, XG msb=126 (typical)
            drumbank_PRGs = TableData(0x970DE, 0x9725D),
            # 31 drum kits
            drumkit_keymaps = TableData(0x951DE, 0x970DD),
            # 42 bytes per entry   499 voices  +24 +25 = ext seqID
            drum_voices = TableData(0x90000, 0x951DD),
            # drum_voice_seqID_offset = 0x18,

            # max value 0x57 / 87  88 entries
            # * In MU90 these are implicitly multiplied by two, like the PRGmap offsets
            drumvoice_ext_offsets = TableData(0x9BBDE, 0x9BC8D),

            # 128 x 3 tables: GS, XG SFX, XG (different order!)
            voice_banks = TableData(0x9BA5E, 0x9BBDD),

            # 256 bytes per entry = 71 voice banks (same as mu80)
            voice_PRGmap = TableData(0x9725E, 0x9BA5D),
            
            # 10 bytes + 70 bytes per element (80 / 150) offs+0 elements. seqID on element +1
            # nearly the same as MU80, but with two columns for the wave# like the mu50
            # then just one blank column, probably just to keep the len even
            voices = TableData(0x9BC8E, 0xB36CB),

            # * Note: additional voices at 0xCA754 -> 0xD5FB5
            # 294 entries
            wavedata_offsets = TableData(0xB9A7C, 0xB9CC7),

            # wavedata   16 x 1595
            wavedata = TableData(0xB36CC, 0xB9A7B),

        )

            # drumvoice_extoffset_mult = 2 # MU80 = 2, MU50 = ???, MU90 = 2





    @abstractmethod
    # full decoding / abstraction here, no big lump of general 'data' as in the voice/drumvoice tables
    # return WaveBank & Samples  dict[int, Sample]
    # use MergeSampleLists() on output to merge them into our table's sample pool
    def ProcessWaveData(self, data : bytes | bytearray, address : int) -> tuple[WaveBank, dict[int, Sample]] : 

        assert self.source == MU.MU90

        samples : dict[int, Sample] = {} # key = loop address
        waves : list[Wave] = []

        # 16 bytes, but different from both the MU50 and MU80
        # table extends pages until key range high is >= 0x7F

        # there is no explicit key low, just as in the MU80, it's implied from the last key high
        last_key : int = 0 

        for addr in range(address, self.wavedata.end, 16) : 
            # + 0: attenuation
            # + 1: pitch, note
            # + 2: pitch, cent
            # + 3: note range, high (low is implicit)
            # + 4: unknown value, likely two bitsmashed values
            # + 5: samples -
            # + 6: -
            # + 7: -
            # + 8: backwards playback(!)
            # + 9: loop samples + 
            # +10: +
            # +11: +
            # +12: sample fmt and 25th address bit
            # +13: loop address
            # +14: loop address
            # +15: loop address

            # * MU90 wave ROM layout (verified against the ROM data, 2026-09-30):
            #   the two wave ROMs form 32-bit words: bytes 0-1 from xs518a0, bytes 2-3 from xs743a0
            #   (see MU90_Waverom). The loop address counts these 32-bit words -> byte address * 4.
            #   Offsets (+5 body, +9 loop) are plain sample counts, like on the MU80.
            #   Samples are packed back to back, format-dependent: 16 bit = 2 bytes, 12 bit = LE
            #   bit stream (3 bytes per 2 samples, same as MU50), 8 bit and ADPCM = 1 byte.
            mu90_plus4 = data[addr + 4]

            offset_negative = self.decode_bytes(data,addr+5, 24, 'big')
            offset_positive = self.decode_bytes(data,addr+9, 24, 'big')
            loop_address = self.decode_bytes(data,addr+13, 24, 'big') * 4
            sample_byte = data[addr+12] & 0xC0
            sample_format = Byte_To_SampleFormat(self.source, sample_byte)
            assert sample_format != SampleFormat.UNKNOWN
            ADPCM_params = (data[addr+12] & 0b00111110) >> 1
            backwards = bool(data[addr+8] & 0x80)

            sample = Sample(loop_address, offset_negative, offset_positive, loop_address, sample_format,
                            encoding_parameters=ADPCM_params, format=self.source, address_book={addr})
            if backwards :
                sample, offset_negative, offset_positive = Make_Reversed(sample)

            AddToSampleList(samples, sample) # will only add the longer sample if clipped

            key_min = last_key
            key_max = data[addr+3]
            last_key = key_max + 1 # + 1 is more in line with what s-yxg50 expects, always sequential key ranges

            wave = Wave(addr,
                        offset_negative, offset_positive, sample.address_src,
                        attenuation=data[addr+0],
                        tune_note=data[addr+1],
                        tune_cent=data[addr+2],
                        key_min=key_min,
                        key_max=key_max,
                        mu90_plus4=mu90_plus4,
                        backwards=backwards,
                        )

            waves.append(wave)

            if key_max >= 0x7F : break

        return (WaveBank(address, waves), samples)



    @abstractmethod
    # return voice (w/ elements), wavebank, & samples
    def ProcessVoice(self, data : bytes | bytearray, address: int) -> tuple[Voice, dict[str | int, WaveBank], dict[int, Sample]] : 
        assert self.source == MU.MU90

        HEADER_LENGTH = 10 
        ELEMENT_LENGTH = 70 # full voice: 80 or 150

        element_cnt = data[address] + 1  # + 0 (like mu80)
        volume = data[address+1]         # + 1

        name = data[address+2 : address + 10].decode(encoding='cp1252') # +2

        elements : list[Element] = []
        wavebanks : dict[str | int, WaveBank] = {} # key = wavedata start addr
        samples : dict[int, Sample] = {} # key = loop address

        for element_address in range(address + HEADER_LENGTH, address + HEADER_LENGTH + (ELEMENT_LENGTH * element_cnt), ELEMENT_LENGTH) : 

            element_data = data[element_address : element_address + ELEMENT_LENGTH]

            # top bits of wave# is on the el+0. Same as Mu50, but the full value sometimes goes to 9 bits now
            wavebankID = (element_data[0] << 7) + element_data[1] 

            # trace wavebankID to wavedatatable
            wavedata_offset_address = self.wavedata_offsets.start + (wavebankID * 2)
            assert wavedata_offset_address < self.wavedata_offsets.end
            # wavedata_address = self.b16.decode_bytes(data, wavedata_offset_address) + self.wavedata.start
            wavedata_address = self.decode_bytes(data, wavedata_offset_address, 16, 'big') + self.wavedata.start
            assert wavedata_address < self.wavedata.end

            # * pull wavedata, collect WaveBank, Samples
            wavebank, samples_wave = self.ProcessWaveData(data, wavedata_address)

            wavebanks[wavedata_address] = wavebank

            for sample in samples_wave.values() : 
                sample.address_book.add(element_address)

            samples = MergeSampleDicts(samples, samples_wave)

            elements.append(Element(wavedata_address, bytearray(element_data), self.source, waveID=wavebankID) )

        voice = Voice(address, volume, name, elements, self.source)

        return voice, wavebanks, samples
        





    @override
    #  returns: ExtVoiceAddress, Drumvoice, Sample 
    # * ExtVoiceAddress=0 if non-applicable
    def ProcessDrumVoice(self, data : bytes | bytearray, address : int) -> tuple[int, DrumVoice, Sample] : 

        # expanded from 30 to 42 bytes
        # up to +15 is the same as MU50, then there are additions that add more robust EG options, 
        # though they are not utilized too much
        assert self.source == MU.MU90

        address_book : set[int] = set([address]) # * keep a log of our visited addresses for debugging
        drumvoice_data = data[address : address + 42]
        ExtVoice_SeqID = int.from_bytes(drumvoice_data[24 : 24+2], byteorder='big') # always BE
        voice_address : int = 0

        if ExtVoice_SeqID < 0xFFFF : 
            voice_offset_address = self.drumvoice_ext_offsets.start + (ExtVoice_SeqID * 2)
            # voice_offset = self.b16.decode_bytes(data, voice_offset_address)
            voice_offset = self.decode_bytes(data, voice_offset_address, bits=16)
            voice_address = self.voices.start + (voice_offset * 2) # * ext voice offset is times two on MU90
            address_book.add(voice_offset_address)
            address_book.add(voice_address)


        # * the sample part (+30..+41) mirrors the wavedata entry (+4..+15):
        #   +30 unknown (= wavedata +4), +31..+33 body, +34 bit 7 = backwards, +35..+37 loop,
        #   +38 format / ADPCM parameters, +39..+41 loop address in 32-bit words
        sample_format = Byte_To_SampleFormat(self.source, drumvoice_data[38] & 0xC0)
        dpcm_parameters : int = (drumvoice_data[38] & 0x3E) >> 1

        offset_negative = self.decode_bytes(drumvoice_data, 31, bits=24)
        offset_positive = self.decode_bytes(drumvoice_data, 35, bits=24)
        loop_address = self.decode_bytes(drumvoice_data, 39, bits=24) * 4

        address_book.add(address)

        sample = Sample(loop_address, offset_negative, offset_positive, loop_address, sample_format,
                        encoding_parameters=dpcm_parameters,
                        format=self.source,
                        address_book=set(address_book))
        if drumvoice_data[34] & 0x80 :
            sample, offset_negative, offset_positive = Make_Reversed(sample)

        drumvoice = DrumVoice(drumvoice_data, sample.address_src, voice_address,
                              offset_negative, offset_positive,
                              format=self.source,
                              address_book=set(address_book),)
        drumvoice.vel_pitch, drumvoice.vel_lpf = drumvoice_data[22], drumvoice_data[23]   # see drumvel.py

        return voice_address, drumvoice, sample



