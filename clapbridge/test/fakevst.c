// fakevst.c - tiny 32-bit VST2 instrument for testing the bridge without ROM data:
// note on = sine of the note's pitch (starts at the event's sample offset), a SysEx of n bytes sets the gain to n / 10,
// state chunk = the text last set, editor = a 200 x 100 window.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <math.h>
#include <string.h>
#include "../vst2.h"

static AudioMasterCallback cb;
static float gain = 0.5f, rate = 44100;
static double phase, freq;
static int on;
static char chunk[64] = "initial";
static AEffect fx;
static ERect rect = { 0, 0, 100, 200 };
static HWND ed;

static void __cdecl proc(AEffect* e, float** in, float** out, int32_t n)
{
    (void)e; (void)in;
    for (int i = 0; i < n; i++) { out[0][i] = out[1][i] = 0; }
    extern int g_start; int from = g_start; g_start = 0;
    for (int i = from; i < n; i++) if (on) { float s = (float)sin(phase) * gain; out[0][i] = s; out[1][i] = s; phase += 6.283185307 * freq / rate; }
}
int g_start;
static intptr_t __cdecl disp(AEffect* e, int32_t op, int32_t idx, intptr_t val, void* ptr, float opt)
{
    (void)e; (void)idx;
    switch (op) {
    case effSetSampleRate: rate = opt; return 0;
    case effGetEffectName: strcpy((char*)ptr, "Fake VST"); return 1;
    case effEditGetRect: *(ERect**)ptr = &rect; return 1;
    case effEditOpen: ed = CreateWindowExA(0, "STATIC", "fake editor", WS_CHILD | WS_VISIBLE, 0, 0, 200, 100, (HWND)ptr, 0, 0, 0); return 1;
    case effEditClose: DestroyWindow(ed); return 1;
    case effGetChunk: *(void**)ptr = chunk; return (intptr_t)strlen(chunk) + 1;
    case effSetChunk: memcpy(chunk, ptr, val < 64 ? val : 63); return 0;
    case effProcessEvents: {
        VstEventsHdr* h = (VstEventsHdr*)ptr;
        for (int i = 0; i < h->numEvents; i++) {
            VstMidiEvent* m = (VstMidiEvent*)h->events[i];
            if (m->type == 1) {
                unsigned char st = (unsigned char)m->midiData[0] & 0xF0, k = (unsigned char)m->midiData[1];
                if (st == 0x90) { on = 1; freq = 440.0 * pow(2.0, (k - 69) / 12.0); g_start = m->deltaFrames; }
                if (st == 0x80) on = 0;
            } else if (m->type == 6) gain = ((VstMidiSysexEvent*)m)->dumpBytes / 10.0f;
        }
        return 1;
    }
    }
    return 0;
}
__declspec(dllexport) AEffect* __cdecl VSTPluginMain(AudioMasterCallback c)
{
    cb = c;
    fx.magic = kEffectMagic; fx.dispatcher = disp; fx.processReplacing = proc;
    fx.numOutputs = 2; fx.flags = effFlagsHasEditor | effFlagsIsSynth | effFlagsProgramChunks; fx.uniqueID = 0x46414b45;
    return &fx;
}
