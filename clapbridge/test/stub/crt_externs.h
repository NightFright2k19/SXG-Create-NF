// crt_externs.h stand-in for the Linux emulation of the macOS bridge (run_tests.sh); macOS has the real header
extern char **environ;
static inline char ***_NSGetEnviron(void) { return &environ; }
