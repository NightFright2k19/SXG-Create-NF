from enum import Enum, StrEnum, auto


class MU(StrEnum) : 
    UNDEFINED = auto()
    MU80 = auto()
    MU50 = auto()
    QS300 = auto()
    TG300 = auto()
    SYXG50 = auto()
    MU90 = auto()
    MU100 = auto()
    MU1000 = auto()
    MU128 = auto()
    MU2000 = auto()

class Bank(StrEnum) : 
    GS = auto()
    XG = auto()
    XG_MODERN = auto()
    SFX = auto()
    GM2 = auto() # msb 121
    UNKNOWN = auto()

    GS_DRUMS = auto()
    XG_DRUMS = auto()
    XG_MODERN_DRUMS = auto() #  MU100: program 126 is modern, program 127 is basic
    SFX_DRUMS = auto()
    GM2_DRUMS = auto() # msb 120

# returns LSB, MSB
def BankToDrumLSBMSB(bank : Bank) -> tuple[int,int] : 
    match bank : 
        case Bank.GS | Bank.GS_DRUMS : return (0, 0)
        case Bank.XG | Bank.XG_DRUMS : return (0, 127)
        case Bank.SFX | Bank.SFX_DRUMS : return (0, 126)
        case Bank.GM2 | Bank.GM2_DRUMS : return (0, 120)
        case _ : raise ValueError()

# returns LSB, MSB
def BankToLSBMSB(bank : Bank, byte : int) -> tuple[int,int] : 
    match bank : 
        case Bank.GS :  return (0, byte)
        case Bank.SFX : return (0, byte)
        case Bank.XG :  return (byte, 0)
        case Bank.GM2 : return (byte, 121)
        case _ : raise ValueError()

def IsDrumBank(b : Bank) -> bool :  
    match b : 
        case Bank.GS_DRUMS | Bank.XG_DRUMS | Bank.XG_MODERN_DRUMS | Bank.GM2_DRUMS : 
            return True
        case _ : 
            return False


class SampleFormat(StrEnum) : 
    S16 = auto()   # 0x80 in MU80 
    U16 = auto()   # 0x00 S-YXG50
    ADPCM = auto()  # 0x00 in MU80. On MU50, the parameters are the lower 6 bits
    S12 = auto()   # introduced with MU50
    S8 = auto()    # 0x80 MU50. 0x00 in MU90, possibly
    U8 = auto()    # 0x80 S-YXG50 / MU90
    UNKNOWN = auto()
    TMP = auto() # use instead of unknown for out_sample_type



def SampleFormat_to_Byte_SYXG50(fmt : SampleFormat) : 
    match fmt : 
        case SampleFormat.U16 : return 0x00
        case SampleFormat.U8 : return 0x80
        case _ : raise ValueError()

def Byte_To_SampleFormat(mu : MU, b : int) -> SampleFormat : 
    b = (b & 0b11000000)
    match mu : 
        case MU.MU80 : 
            match b : 
                # ? 0xC0 shares some of the same loop addresses as 0x80, so they gotta be s16
                # * bit 6 (0xC0 vs 0x80), checked against the MU80 v1.04 data (analyze_sample_flags.py):
                #   - only occurs with 16-bit PCM (never with ADPCM), all 211 PCM drum voices use 0xC0,
                #     only 14 of 513 voice wave entries use 0xC0
                #   - not a loop flag: 0x80 entries without loop exist, all 0xC0 voice entries loop
                #   - not a data format: the same sample data is used with 0x80 and 0xC0, levels are normal
                #   - not a pitch/octave flag: loop length vs. tune note follows the same rule in 0x80 and
                #     0xC0 zones (e.g. single-cycle waves), RockOrgn uses the same sample with the same tune
                #     in a 0xC0 and a 0x80 zone, chromatic listening test across the zone borders is smooth
                #   -> treating both as S16 is correct; any remaining hardware meaning has no audible
                #      counterpart that the S-YXG50 table format could express
                case 0x80 | 0xC0 : return SampleFormat.S16 
                case _ : return SampleFormat.ADPCM # parameters in a separate column
        case MU.MU50 | MU.MU90 : 
            match b : 
                case 0x80 : return SampleFormat.S8
                case 0x40 : return SampleFormat.S12
                case 0xC0 : return SampleFormat.ADPCM
                case 0x00 : return SampleFormat.S16 # unused on MU50
                case _ : raise ValueError() 
        case MU.SYXG50 : 
            match b : 
                case 0x80 : return SampleFormat.U8
                case 0x00 : return SampleFormat.U16
                case _ : raise ValueError()
        case _ :
            raise NotImplementedError()


def SampleFormat_To_Bits(format : SampleFormat) :
    match format : 
        case SampleFormat.S16 | SampleFormat.U16 : return 16
        case SampleFormat.S12 : return 12
        case SampleFormat.S8 | SampleFormat.U8 : return 8
        case SampleFormat.ADPCM : return 8
        case _ : raise ValueError()


def get_SampleFormat_Target(sampletype : SampleFormat, mu_src : MU, mu_dest : MU) -> SampleFormat : 

    match mu_dest : 
        case MU.SYXG50 : 
            match sampletype : 
                case SampleFormat.U16 | SampleFormat.U8 : # S-YXG50's native formats
                    return sampletype
                case SampleFormat.S8 : 
                    return SampleFormat.U8
                case SampleFormat.S12 | SampleFormat.S16 | SampleFormat.ADPCM : 
                    return SampleFormat.U16
                case _ :
                    raise ValueError()
                
        # todo vampire uses S16 I think?
        case _ : 
            raise NotImplementedError() 




# * external voice table reconstruction. Offsets should be multiplied by 2
MU50extVoiceTable : list[int] = [0 for _ in range(0,0x57)]
MU50extVoiceTable[0x00] = 0x1C98 # FretNo
MU50extVoiceTable[0x01] = 0xB0E0 # CuttngNz
MU50extVoiceTable[0x02] = 0xB0E0 # Cuttng
MU50extVoiceTable[0x03] = 0xB162 # Str Slap
MU50extVoiceTable[0x04] = 0xB18F # Fl.KClik
MU50extVoiceTable[0x05] = 0xB8B5 # Laughing
MU50extVoiceTable[0x06] = 0xB8E2 # Scream
MU50extVoiceTable[0x07] = 0xB90F # Punch
MU50extVoiceTable[0x08] = 0xB93C # Heart
MU50extVoiceTable[0x09] = 0xB969 # FootStep
MU50extVoiceTable[0x0a] = 0x6009 # SynMalet ("Footsteps 2")
MU50extVoiceTable[0x0b] = 0x1E46 # Applause
MU50extVoiceTable[0x0c] = 0xB4A0 # DoorSqek
MU50extVoiceTable[0x0d] = 0xB4CD # DoorSlam
MU50extVoiceTable[0x0e] = 0xB4FA # Scratch
MU50extVoiceTable[0x0f] = 0xB57C # WindChm
MU50extVoiceTable[0x10] = 0xB5D6 # CarEngin
MU50extVoiceTable[0x11] = 0xB603 # Car Stop
MU50extVoiceTable[0x12] = 0xB630 # Car Pass
MU50extVoiceTable[0x13] = 0xB65D # CarCrash
MU50extVoiceTable[0x14] = 0xB68A # Siren
MU50extVoiceTable[0x15] = 0xB6DF # Train
MU50extVoiceTable[0x16] = 0xB70C # Jetplane
MU50extVoiceTable[0x17] = 0x1E19 # Helicptr
MU50extVoiceTable[0x18] = 0xB761 # Starship
MU50extVoiceTable[0x19] = 0x1E73 # Gunshot
MU50extVoiceTable[0x1a] = 0xB996 # MchinGun
MU50extVoiceTable[0x1b] = 0xB9C3 # LaserGun
MU50extVoiceTable[0x1c] = 0xBA18 # Xplosion
MU50extVoiceTable[0x1d] = 0xB342 # Dog
MU50extVoiceTable[0x1e] = 0xB36F # Horse
MU50extVoiceTable[0x1f] = 0xB39C # Bird 2
MU50extVoiceTable[0x20] = 0xB1BC # Rain
MU50extVoiceTable[0x21] = 0xB1E9 # Thunder
MU50extVoiceTable[0x22] = 0xB216 # Wind
MU50extVoiceTable[0x23] = 0x1D42 # Seashore
MU50extVoiceTable[0x24] = 0xB243 # Stream
MU50extVoiceTable[0x25] = 0xB298 # Bubble
MU50extVoiceTable[0x26] = 0
MU50extVoiceTable[0x27] = 0xB10D # CttngN
MU50extVoiceTable[0x28] = 0
MU50extVoiceTable[0x29] = 0
MU50extVoiceTable[0x2a] = 0
MU50extVoiceTable[0x2b] = 0
MU50extVoiceTable[0x2c] = 0
MU50extVoiceTable[0x2d] = 0
MU50extVoiceTable[0x2e] = 0
MU50extVoiceTable[0x2f] = 0
MU50extVoiceTable[0x30] = 0
MU50extVoiceTable[0x31] = 0
MU50extVoiceTable[0x32] = 0
MU50extVoiceTable[0x33] = 0
MU50extVoiceTable[0x34] = 0xB39C # ? Bird 2
MU50extVoiceTable[0x35] = 0
MU50extVoiceTable[0x36] = 0
MU50extVoiceTable[0x37] = 0xB473 # Tel.Di
MU50extVoiceTable[0x38] = 0
MU50extVoiceTable[0x39] = 0
MU50extVoiceTable[0x3a] = 0
MU50extVoiceTable[0x3b] = 0
MU50extVoiceTable[0x3c] = 0xB527 # Scratc
MU50extVoiceTable[0x3d] = 0
MU50extVoiceTable[0x3e] = 0
MU50extVoiceTable[0x3f] = 0
MU50extVoiceTable[0x40] = 0
MU50extVoiceTable[0x41] = 0
MU50extVoiceTable[0x42] = 0
MU50extVoiceTable[0x43] = 0
MU50extVoiceTable[0x44] = 0
MU50extVoiceTable[0x45] = 0xB7B6 # Burst 
MU50extVoiceTable[0x46] = 0xB80B # Coaste
MU50extVoiceTable[0x47] = 0
MU50extVoiceTable[0x48] = 0
MU50extVoiceTable[0x49] = 0
MU50extVoiceTable[0x4a] = 0
MU50extVoiceTable[0x4b] = 0
MU50extVoiceTable[0x4c] = 0
MU50extVoiceTable[0x4d] = 0
MU50extVoiceTable[0x4e] = 0
MU50extVoiceTable[0x4f] = 0xB2ED # Feed  
MU50extVoiceTable[0x50] = 0
MU50extVoiceTable[0x51] = 0xB3C9 # Ghost 
MU50extVoiceTable[0x52] = 0xB41E # Maou  
MU50extVoiceTable[0x53] = 0xB860 # SbMari
MU50extVoiceTable[0x54] = 0xBA6D # FireWo
MU50extVoiceTable[0x55] = 0xB5A9 # Telpho
MU50extVoiceTable[0x56] = 0x9006 # Silence