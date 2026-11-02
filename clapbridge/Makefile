# Builds the CLAP bridge (issue #97) with mingw-w64:  make   (needs gcc-mingw-w64)
#   sxgbridge.clap    64-bit CLAP; the patcher copies it once per plugin under the plugin's name (syxg1000.clap ...)
#   sxgbridge32.exe   32-bit helper that runs the VST2 DLL
CFLAGS = -O2 -Wall -Wextra -I.
all: sxgbridge.clap sxgbridge32.exe
sxgbridge.clap: clap_bridge.c protocol.h
	x86_64-w64-mingw32-gcc $(CFLAGS) -shared -o $@ clap_bridge.c -static-libgcc -s
sxgbridge32.exe: host32.c vst2.h protocol.h
	i686-w64-mingw32-gcc $(CFLAGS) -mwindows -o $@ host32.c -static -lshell32 -s
clean:
	rm -f sxgbridge.clap sxgbridge32.exe
