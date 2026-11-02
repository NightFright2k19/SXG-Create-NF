// vst2.h - the few VST 2.4 declarations the helper needs (written from the public interface description;
// no Steinberg SDK file is used). Compile as 32-bit: the structures follow the 32-bit layout.
#ifndef SXG_VST2_H
#define SXG_VST2_H
#include <stdint.h>

typedef struct AEffect AEffect;
typedef intptr_t (__cdecl *AudioMasterCallback)(AEffect*, int32_t opcode, int32_t index, intptr_t value, void* ptr, float opt);
typedef intptr_t (__cdecl *DispatcherProc)(AEffect*, int32_t opcode, int32_t index, intptr_t value, void* ptr, float opt);

struct AEffect {
    int32_t magic;                      // 'VstP'
    DispatcherProc dispatcher;
    void (__cdecl *process)(AEffect*, float**, float**, int32_t);
    void (__cdecl *setParameter)(AEffect*, int32_t, float);
    float (__cdecl *getParameter)(AEffect*, int32_t);
    int32_t numPrograms, numParams, numInputs, numOutputs, flags;
    intptr_t resvd1, resvd2;
    int32_t initialDelay, realQualities, offQualities;
    float ioRatio;
    void* object; void* user;
    int32_t uniqueID, version;
    void (__cdecl *processReplacing)(AEffect*, float**, float**, int32_t);
    void (__cdecl *processDoubleReplacing)(AEffect*, double**, double**, int32_t);
    char future[56];
};

#define kEffectMagic 0x56737450
enum { effFlagsHasEditor = 1, effFlagsProgramChunks = 32, effFlagsIsSynth = 256 };
enum {
    effOpen = 0, effClose = 1, effSetSampleRate = 10, effSetBlockSize = 11, effMainsChanged = 12,
    effEditGetRect = 13, effEditOpen = 14, effEditClose = 15, effEditIdle = 19,
    effGetChunk = 23, effSetChunk = 24, effProcessEvents = 25, effGetEffectName = 45,
    effStartProcess = 71, effStopProcess = 72
};
enum {
    audioMasterAutomate = 0, audioMasterVersion = 1, audioMasterCurrentId = 2, audioMasterIdle = 3,
    audioMasterWantMidi = 6, audioMasterGetTime = 7, audioMasterIOChanged = 13, audioMasterSizeWindow = 15,
    audioMasterGetSampleRate = 16, audioMasterGetBlockSize = 17, audioMasterGetCurrentProcessLevel = 23,
    audioMasterGetVendorString = 32, audioMasterGetProductString = 33, audioMasterGetVendorVersion = 34,
    audioMasterCanDo = 37, audioMasterGetLanguage = 38, audioMasterUpdateDisplay = 42
};

typedef struct { int16_t top, left, bottom, right; } ERect;

typedef struct {
    int32_t numEvents; intptr_t reserved; void* events[2];     // events[] really has numEvents entries
} VstEventsHdr;

typedef struct {
    int32_t type, byteSize, deltaFrames, flags, noteLength, noteOffset;
    char midiData[4]; char detune, noteOffVelocity, reserved1, reserved2;
} VstMidiEvent;                         // type 1

typedef struct {
    int32_t type, byteSize, deltaFrames, flags, dumpBytes;
    intptr_t resvd1; char* sysexDump; intptr_t resvd2;
} VstMidiSysexEvent;                    // type 6

typedef struct {
    double samplePos, sampleRate, nanoSeconds, ppqPos, tempo, barStartPos, cycleStartPos, cycleEndPos;
    int32_t timeSigNumerator, timeSigDenominator, smpteOffset, smpteFrameRate, samplesToNextClock, flags;
} VstTimeInfo;
#endif
