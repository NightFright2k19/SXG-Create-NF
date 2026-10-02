# DPCM delta table, limits table, and decoding code based on Mame
# license:BSD-3-Clause
# copyright-holders:Olivier Galibert

from dataclasses import dataclass, field

from dataenum import *

from table import Sample
from utils import fmtbyte, fmtbytes
import time

dpcm_table : list[int] = [0, 
1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 
17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 
34, 36, 38, 40, 42, 44, 46, 48, 50, 52, 54, 56, 58, 60, 62, 64, 
66, 68, 70, 72, 74, 76, 78, 80, 82, 84, 86, 88, 90, 92, 94, 96, 
100, 104, 108, 112, 116, 120, 124, 128, 132, 136, 140, 144, 148, 152, 156, 160, 
164, 168, 172, 176, 180, 184, 188, 192, 196, 200, 204, 208, 212, 216, 220, 224, 
232, 240, 248, 256, 264, 272, 280, 288, 296, 304, 312, 320, 328, 336, 344, 352, 
360, 368, 376, 384, 392, 400, 408, 416, 424, 432, 440, 448, 456, 464, 472, 136, 
-1, -2, -3, -4, -5, -6, -7, -8, -9, -10, -11, -12, -13, -14, -15, -16, 
-17, -18, -19, -20, -21, -22, -23, -24, -25, -26, -27, -28, -29, -30, -31, -32, 
-34, -36, -38, -40, -42, -44, -46, -48, -50, -52, -54, -56, -58, -60, -62, -64, 
-66, -68, -70, -72, -74, -76, -78, -80, -82, -84, -86, -88, -90, -92, -94, -96, 
-100, -104, -108, -112, -116, -120, -124, -128, -132, -136, -140, -144, -148, -152, -156, -160, 
-164, -168, -172, -176, -180, -184, -188, -192, -196, -200, -204, -208, -212, -216, -220, -224, 
-232, -240, -248, -256, -264, -272, -280, -288, -296, -304, -312, -320, -328, -336, -344, -352, 
-360, -368, -376, -384, -392, -400, -408, -416, -424, -432, -440, -448, -456, -464, -472, ]

# different for each scale value
dpcm_limits : list[int] = [0x7fff, 0x7ffe, 0x7ffc, 0x7ff8, 0x7ff0, 0x7fe0, 0x7fc0, 0x7f80]



# Interleaved 12-bit format:
    #  v v LSB1 and LSB2
    # v   v MSB1 B & A
    #       vv MSB2 A & B
    # 00 00 00 | 00 00 00 | 00 00 00
    # v1 v2 v3
    # nL LM Mn   ... where 'n' is second nibble of MSB
# A:  nL .M .. -> 0412
# B:  .. L. Mn -> 0563 
#   # Aa bA BB
# * it makes more sense if you swap all the nibbles around
# * then it goes aa Ab bB, in LE order, and no longer interleaved

def S12_to_16bit(sample : Sample, waves : bytes) -> bytes : 
    assert sample.sample_type == SampleFormat.S12
    assert sample.out_sample_type == SampleFormat.U16 

    output : list[int] = []

    start_address, starts_on_nibble = sample.get_start_address_12bit()
    end_address, ends_on_nibble = sample.get_end_address_12bit()

    start_pt = start_address if not starts_on_nibble else start_address + 2
    end_pt = end_address if not ends_on_nibble else end_address - 2

    def Cnv12_pos1(val1 : int, val2 : int, val3 : int) : 
          #     12 34 56
          # A:  nL  M    -> 0412
        a : int = ((val2 & 0x0F) << 8) | ((val1 & 0xF0)) | ((val1 & 0x0F))

        out = a
        if a & 0x0800 :
            out = out - 4096

        out = out * 16

        return out


    # XX X1 23 -> 03 12
    def Cnv12_pos2(val1 : int, val2 : int, val3 : int) : 

        #     12 34 56
        #     .. L. Mn -> 0563 
        a : int = ((val2 & 0xF0) >> 4) | ((val3) << 4)

        out = a
        if a & 0x0800 : 
            out = out - 4096

        out = out * 16

        return out


    if starts_on_nibble : 
        # output.append(Cnv12_pos2(* waves[start_address : start_address + 3])) # wrong I think
        #     12 34 56
        # A:  nL  M    
        #     00 12 34   <- this one but offset by -1?
        # B:  .. L. Mn
        output.append(Cnv12_pos2(0, waves[start_address], waves[start_address+1]))

    for idx in range(start_pt, end_pt,3) : 

        output.append(Cnv12_pos1(*waves[idx : idx+3]))
        output.append(Cnv12_pos2(*waves[idx : idx+3]))


    # # # X1 23
    if ends_on_nibble : 
        output.append(Cnv12_pos1(waves[end_address-2], waves[end_address-1], waves[end_address])) 


    outbytes : bytearray = bytearray()

    if sample.out_sample_type == SampleFormat.U16 : 
        for val in output : 
            val = val + 32768
            outbytes = outbytes + val.to_bytes(2, byteorder='little', signed=False)
    else : 
        for val in output : 
            outbytes = outbytes + val.to_bytes(2, byteorder='little', signed=True)


    return bytes(outbytes)



def S8_To_U8(sample : Sample, waves : bytes) : 
    assert sample.sample_type == SampleFormat.S8
    out : bytearray = bytearray(sample.len_bytes()[0])

    for idx, addr in enumerate(range(sample.get_start_address(), sample.get_end_address())) : 
        value = int.from_bytes(waves[addr:addr+1], signed=True)
        out[idx] = value + 128

    return bytes(out)



def S16_To_U16(sample : Sample, waves : bytes) : 
    assert sample.sample_type == SampleFormat.S16
    assert sample.out_sample_type == SampleFormat.U16
    out : bytearray = bytearray(sample.len_bytes()[0])

    for idx, addr in enumerate(range(sample.get_start_address(), sample.get_end_address(), 2)) : 
        value = int.from_bytes(waves[addr:addr+2], 'little', signed=True)

        idx = idx * 2
        out[idx : idx + 2] = (value + 32768).to_bytes(2, 'little', signed=False)

    return bytes(out)



# * Tarboh's non-leaky ADPCM decoding with remainder, 2026-09-16
# Possibly *100%* accurate to SWP00 and SWP20 output!
# Or not, because we aren't letting the delta run from loop to loop
# Loops are coming through pretty clean though
def _ADPCM_Stepper(encoding : int) : 
    # returns MakeSample(input, prev_sample, prev_delta, prev_remainder) for this sample's encoding

    mode = encoding & 0x03
    scale = (encoding >> 2) & 0x07
    dpcm_limit = dpcm_limits[scale]

    # Tarboh smooshed the delta and remainder together into 24 bits
    # here it's untangled. Seems to match the C++ output
    def MakeSample(input : int, prev_sample : int, prev_delta : int, prev_remainder : int) -> tuple[int,int, int] : 

        accum = prev_sample >> scale
        delta = prev_delta + dpcm_table[input]

        output = (accum + delta) << scale

        if output < -0x8000 : 
            output = -0x8000
        elif output > dpcm_limit : 
            output = dpcm_limit

        new_delta = (output >> scale) - accum
        new_remainder = 0

        # delta decay
        match mode : 
            case 0 : # 7/8   not used on MU50, but MU80 uses it a little
                y = (new_delta * 7) + prev_remainder
                new_remainder = -(8 - (y & 7)) if (y & 7) else 0
                new_delta = y >> 3

            case 1 : # 3/4
                y = (new_delta * 3) + prev_remainder
                new_remainder = -(4 - (y & 3)) if (y & 3) else 0
                new_delta = y >> 2

            case 2 : # 1/2
                y = new_delta + prev_remainder
                new_remainder = -(2 - (y & 1)) if (y & 1) else 0
                new_delta = y >> 1
                 
            case 3 : 
                new_delta = 0
                new_remainder = 0

        return output, new_delta, new_remainder

    return MakeSample


# * ADPCM loop continuity
# The hardware keeps decoding through the loop: every pass starts with the decoder state
# (sample, delta, remainder) that the previous pass ended with. A PCM table can only repeat
# one fixed loop, so we emulate the passes until the state settles, put the transitional
# passes in front of the loop (lead-in) and use the settled pass as the loop.
# The result then plays back exactly like the continuously decoded hardware stream.
ADPCM_MAX_PASSES = 8

def ADPCM_Stream(sample : Sample, waverom : bytes, loop_len : int, n_out : int) -> list[int] : 
    # continuous decode: body + loop, then the loop bytes again with carried-over state
    MakeSample = _ADPCM_Stepper(sample.encoding_parameters)
    loop = sample.loop_address
    body_bytes = waverom[loop - sample.offset_negative : loop]
    loop_bytes = waverom[loop : loop + loop_len]
    assert len(loop_bytes) == loop_len
    out : list[int] = []
    smp = delta = rem = 0
    for b in body_bytes : 
        smp, delta, rem = MakeSample(b, smp, delta, rem)
        out.append(smp)
    while len(out) < n_out : 
        for b in loop_bytes : 
            smp, delta, rem = MakeSample(b, smp, delta, rem)
            out.append(smp)
    return out[:n_out]


def ADPCM_Find_LeadIn(sample : Sample, waverom : bytes, loop_len : int, max_passes : int = ADPCM_MAX_PASSES) -> tuple[int, bool] : 
    # returns (number of transitional passes, settled?)
    # pass j is followed by an identical pass when the state at its start equals the state at its end
    MakeSample = _ADPCM_Stepper(sample.encoding_parameters)
    loop = sample.loop_address
    body_bytes = waverom[loop - sample.offset_negative : loop]
    loop_bytes = waverom[loop : loop + loop_len]
    smp = delta = rem = 0
    for b in body_bytes : 
        smp, delta, rem = MakeSample(b, smp, delta, rem)
    state = (smp, delta, rem)
    for j in range(max_passes) : 
        for b in loop_bytes : 
            smp, delta, rem = MakeSample(b, smp, delta, rem)
        new_state = (smp, delta, rem)
        if new_state == state : 
            return j, True
        state = new_state
    return 0, False


def ADPCM_to_S16(sample : Sample, waverom : bytes, looptime : int = 0, ADPCMloop : bool = False) : 

    lead_in = getattr(sample, 'lead_in', 0)
    loop_len = getattr(sample, 'adpcm_loop_len', 0)
    n_out = sample.offset_negative + lead_in + sample.offset_positive

    if loop_len > 0 : 
        # looped: continuous stream. The guard samples after the loop end are the loop's continuation
        out = ADPCM_Stream(sample, waverom, loop_len, n_out)
        if looptime : # * debug: pad loop out so we can test the loop point
            out = ADPCM_Stream(sample, waverom, loop_len, n_out + looptime)
    else : 
        # one-shot: unchanged behaviour
        MakeSample = _ADPCM_Stepper(sample.encoding_parameters)
        start = sample.get_start_address()
        end = sample.get_end_address()
        assert end < len(waverom)
        out = [0 for _ in range(n_out)]
        smp = delta = rem = 0
        for i, input in enumerate(waverom[start : end]) : 
            smp, delta, rem = MakeSample(input, smp, delta, rem)
            out[i] = smp

    out_bytes = bytearray(len(out) * 2)

    if sample.out_sample_type == SampleFormat.U16 : 
        for i, val in enumerate(out) : 
            i = i * 2
            val = val + 32768
            out_bytes[i], out_bytes[i+1] = val.to_bytes(length=2, byteorder='little', signed=False)
    else : 
        for i, val in enumerate(out) : 
            i = i * 2
            out_bytes[i], out_bytes[i+1] = val.to_bytes(length=2, byteorder='little', signed=True)

    return bytes(out_bytes)




#  extracts U8/U16 from S-YXG50
def ExtractSample(sample : Sample, waves : bytes) -> bytes : 
    return bytes(waves[sample.get_start_address() : sample.get_end_address()])


def ConvertSample(sample : Sample, waverom : bytes, mu_src : MU, mu_dest : MU, experimental : bool = False, looptime : int = 0) -> bytes : 

    assert mu_dest == MU.SYXG50

    # * MU90 reverse playback: convert the source region forwards, then reverse it (one-shot)
    if getattr(sample, 'reverse', False) :
        import copy
        total = sample.offset_negative                 # body + loop of the source region
        guard = sample.offset_positive                 # guard samples added by FeedSample
        fwd = copy.copy(sample)
        fwd.reverse = False
        fwd.offset_positive = sample.src_offset_positive
        fwd.offset_negative = total - fwd.offset_positive
        fwd.lead_in = 0; fwd.adpcm_loop_len = 0        # no loop -> plain one-shot decode
        fwd_positive = fwd.offset_positive
        fwd.offset_positive = fwd_positive + guard     # read a little further, same total length
        data = ConvertSample(fwd, waverom, mu_src, mu_dest)
        bps = SampleFormat_To_Bits(sample.out_sample_type) >> 3
        assert len(data) == (total + guard) * bps
        frames = [data[i:i+bps] for i in range(0, total * bps, bps)]
        frames.reverse()
        frames += [frames[-1]] * guard                 # guard: hold the last (= first source) value
        sample.format = mu_dest
        return b''.join(frames)

    src_encoding = sample.sample_type
    output_bytes = bytes()

    match src_encoding : 
        case SampleFormat.U8 : 
            if sample.out_sample_type == SampleFormat.U8 : 
                output_bytes = ExtractSample(sample, waverom)
            else : 
                raise NotImplementedError()
        case SampleFormat.U16 : 
            if sample.out_sample_type == SampleFormat.U16 : 
                output_bytes = ExtractSample(sample, waverom)
            else : 
                raise NotImplementedError()
        case SampleFormat.S8 : 
            output_bytes = S8_To_U8(sample, waverom)

        case SampleFormat.S12 : 
            output_bytes = S12_to_16bit(sample, waverom)

        case SampleFormat.S16 :
            output_bytes = S16_To_U16(sample, waverom)
        case SampleFormat.ADPCM : 
            output_bytes = ADPCM_to_S16(sample, waverom)

        case _ : 
            raise ValueError()

    # * for testing samples
    if sample.offset_positive and looptime : 
        loopcnt = max(2, int((looptime / sample.offset_positive)+0.5))
        samplelen = SampleFormat_To_Bits(sample.out_sample_type)
        for _ in range(loopcnt) : 
            output_bytes = output_bytes + output_bytes[-sample.offset_positive*(samplelen>>3):]

    sample.format = mu_dest

    assert len(output_bytes)
    return output_bytes









# mass sample conversion and reconstruction
@dataclass
class SampleMonster() : 

    # todo for multiple table input, set sample.waverom_bank (WIP)
    waveroms_src : list[bytes]
    source : MU
    dest : MU

    # loop byte, sample
    queue : dict[int,tuple[Sample,int, int, int]] # sample, length (not used), loopoffs, new_loop_address
    rom_end : int = 0

    # * returns new loop address & format
    adpcm_stats : dict = field(default_factory=lambda : {'settled':0, 'settled+lead':0, 'unsettled':0, 'unsettled+lead':0})
    adpcm_lead_samples : int = 0
    adpcm_reserve : int = 0x400000   # keep 4 MB free for the samples that are still to come

    def FeedSample(self, sample : Sample, mu_src : MU, mu_dest : MU) -> tuple[int, SampleFormat] : 
        assert sample.waverom_bank < len(self.waveroms_src)
        assert not sample.written
        assert sample.upsample_mult == 1 # todo not implemented yet

        target_format = get_SampleFormat_Target(sample.sample_type, mu_src, mu_dest)
        bytes_per_sample = SampleFormat_To_Bits(target_format) >> 3

        # * ADPCM loops: emulate the hardware's continuous decoding (see ADPCM_Find_LeadIn)
        sample.lead_in = 0
        sample.adpcm_loop_len = 0
        if sample.sample_type == SampleFormat.ADPCM and sample.offset_positive > 0 : 
            sample.adpcm_loop_len = sample.offset_positive
            passes, settled = ADPCM_Find_LeadIn(sample, self.waveroms_src[sample.waverom_bank], sample.offset_positive)
            lead_in = passes * sample.offset_positive
            # limits: wave start offset 24 bit; drum voices only store a 16-bit start offset in syxg50.dll
            import buildtarget
            body_limit = 0xFFFF if (getattr(sample, 'used_by_drum', False) and not buildtarget.SYXG50_BIG) else 0xFFFFFF
            if sample.offset_negative + lead_in > body_limit : 
                lead_in = 0
            # syxg50.dll addresses the wave file with 24 bits (16 MB), the big layout with 26 bits (64 MB):
            # only spend lead-in while it fits
            if lead_in : 
                projected = self.rom_end + (sample.offset_negative + lead_in + sample.offset_positive + 2) * bytes_per_sample
                if projected + self.adpcm_reserve > (0x3FFFFFF if buildtarget.SYXG50_BIG else 0xFFFFFF) : 
                    lead_in = 0
                    self.adpcm_stats['skipped (16 MB limit)'] = self.adpcm_stats.get('skipped (16 MB limit)', 0) + 1
            sample.lead_in = lead_in
            self.adpcm_stats[('settled' if settled else 'unsettled') + ('+lead' if lead_in else '')] += 1
            self.adpcm_lead_samples += lead_in

        # todo messy
        # * we are off by -1, so we need a little more breathing room
        # this will not get written to the table, but the loop address will be, by + 1
        sample.offset_positive = sample.offset_positive + 2

        bytelength_body = (sample.offset_negative + sample.lead_in) * bytes_per_sample * sample.upsample_mult
        bytelength_loop = sample.offset_positive * bytes_per_sample * sample.upsample_mult
        bytelength_total = bytelength_body + bytelength_loop

        # to make debugging easier, ensure our u16le samples always start on even indexes
        if self.rom_end % 2 :  
            self.rom_end = self.rom_end + 1

        new_loop_address = self.rom_end + bytelength_body

        self.queue[self.rom_end] = (sample, 0, bytelength_body, new_loop_address)

        self.rom_end = self.rom_end + bytelength_total

        if mu_dest == MU.SYXG50 : 
            return (new_loop_address + (SampleFormat_To_Bits(target_format) >> 3), target_format) # + 1 sample
            
        else : 
            raise NotImplementedError()


    def Generate(self, mask_mode : bool = False) -> bytes : 

        start_time : float = time.perf_counter()

        out_bytes : bytearray = bytearray()

        print(f'converting {len(self.queue)} samples...')

        for idx, (sample, sample_len, loop_pt_offs, new_loop_address) in self.queue.items() : 

            sample.out_loop_address = new_loop_address

            # buffer any gaps
            delta = (idx - len(out_bytes))

            if delta != 0 :  # debug
                assert True
            assert delta < 2

            while len(out_bytes) < idx : 
                out_bytes.append(0x7F)

            if mask_mode : 
                bytes_per_sample = 1 if sample.out_sample_type == SampleFormat.U8 else 2
                length = (sample.offset_negative + getattr(sample, 'lead_in', 0) + sample.offset_positive) * bytes_per_sample
                mask_bytes = bytearray(length)
                mask_bytes[0] = 0xFF
                if sample.offset_positive : 
                    # assert len(out_bytes) + loop_pt_offs == new_loop_address # -1?
                    mask_bytes[loop_pt_offs] = 0x6F
                    mask_bytes[-1] = 0x3F
                else : 
                    mask_bytes[-1] = 0x6F
                out_bytes = out_bytes + mask_bytes
            else : 
                cnv_bytes = ConvertSample(sample, 
                                        self.waveroms_src[sample.waverom_bank],
                                        self.source, self.dest)

                # debug
                bytes_per_sample = 1 if sample.out_sample_type == SampleFormat.U8 else 2
                length = (sample.offset_negative + getattr(sample, 'lead_in', 0) + sample.offset_positive) * bytes_per_sample
                assert len(cnv_bytes) == length

                out_bytes = out_bytes + cnv_bytes

        print(f'sample conversions complete, took {time.perf_counter() - start_time:.2f}s')
        print(f'out waverom size = {len(out_bytes):,}')
        n = sum(v for k, v in self.adpcm_stats.items() if not k.startswith('skipped'))
        if n : 
            print(f'ADPCM loops: {n} total, {self.adpcm_stats["settled"]} already seamless, '
                  f'{self.adpcm_stats["settled+lead"]} made seamless with lead-in (+{self.adpcm_lead_samples:,} samples), '
                  f'{self.adpcm_stats["unsettled"]} not settling within {ADPCM_MAX_PASSES} passes (loop as before)'
                  + (f', {self.adpcm_stats["skipped (16 MB limit)"]} skipped because of the 16 MB limit' if self.adpcm_stats.get("skipped (16 MB limit)") else ''))
        return bytes(out_bytes)