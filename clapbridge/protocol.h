// protocol.h - shared by the 64-bit CLAP bridge (clap_bridge.c) and the 32-bit helper (host32.c), issue #97.
// One shared-memory block and four events connect the two processes of an instance. Fixed-size, no pointers,
// the layout is identical when compiled for 32 and 64 bits.
#ifndef SXG_PROTOCOL_H
#define SXG_PROTOCOL_H
#include <stdint.h>

#define SXG_MAGIC       0x53584742u     // 'SXGB'
#define SXG_VERSION     1
#define SXG_MAXFRAMES   8192            // longest block given to the plugin at once (longer ones are split)
#define SXG_MAXEVENTS   2048            // MIDI events per block (more are dropped)
#define SXG_SYSEX_MAX   65536           // SysEx bytes per block
#define SXG_BLOB_MAX    (4 * 1024 * 1024)   // plugin state (chunk)
#define SXG_OUTS        2

enum {                                  // control commands (host -> helper, answered on the helper's UI thread)
    SXG_CMD_ACTIVATE = 1,               // arg0 = sample rate, arg1 = max block size; mains on
    SXG_CMD_DEACTIVATE,                 // mains off
    SXG_CMD_EDIT_RECT,                  // -> arg0 = width, arg1 = height (0 = no editor)
    SXG_CMD_EDIT_OPEN,                  // arg0/arg1 = parent window handle (low/high 32 bits)
    SXG_CMD_EDIT_CLOSE,
    SXG_CMD_EDIT_SHOW,                  // arg0 = 1 show, 0 hide
    SXG_CMD_GET_CHUNK,                  // -> blob, blob_len
    SXG_CMD_SET_CHUNK,                  // <- blob, blob_len
    SXG_CMD_EDIT_OPEN_FLOAT,            // macOS: editor in a floating window with a title bar (the user can close it: editor_closed) -> arg0/arg1 = size
    SXG_CMD_EDIT_OPEN_TOP,              // Linux: editor in a window of its own (title "SXGBridge <token>"); -> arg0/arg1 = size
    SXG_CMD_QUIT
};

enum { SXG_EV_MIDI = 0, SXG_EV_SYSEX = 1 };

typedef struct {
    uint32_t delta;                     // sample offset in the block
    uint32_t kind;                      // SXG_EV_*
    uint8_t  data[4];                   // MIDI bytes (kind = MIDI)
    uint32_t sysex_off, sysex_len;      // into Shared.sysex (kind = SYSEX)
} SxgEvent;

typedef struct {
    uint32_t magic, version;
    // set by the helper before it signals "ready"
    int32_t  ok;                        // 1 = plugin loaded
    int32_t  outputs, inputs, flags, unique_id, has_editor;
    volatile int32_t editor_closed;     // helper -> host: the user closed the floating editor window
    char     error[256];
    char     name[64];
    // audio: the host fills frames / events, signals audio_go, waits for audio_done
    int32_t  frames;
    uint32_t n_events, sysex_bytes;
    SxgEvent events[SXG_MAXEVENTS];
    uint8_t  sysex[SXG_SYSEX_MAX];
    float    out[SXG_OUTS][SXG_MAXFRAMES];
    // control mailbox
    int32_t  cmd, arg[4], result;
    uint32_t blob_len;
    uint8_t  blob[SXG_BLOB_MAX];
} Shared;

// names (objects are named "Local\SXGB<host pid>_<n>_<suffix>")
#define SXG_OBJ_READY   "r"             // helper -> host, plugin loaded (or failed)
#define SXG_OBJ_AGO     "ag"            // host -> helper: process a block
#define SXG_OBJ_ADONE   "ad"
#define SXG_OBJ_CGO     "cg"            // host -> helper: run a command
#define SXG_OBJ_CDONE   "cd"
#define SXG_OBJ_MAP     "m"
#endif
