# Builds the CLAP bridge (issue #97) with mingw-w64:  make   (needs gcc-mingw-w64)
#   sxgbridge.clap    64-bit CLAP; the patcher copies it once per plugin under the plugin's name (syxg1000.clap ...)
#   sxgbridge32.exe   32-bit helper that runs the VST2 DLL
CFLAGS = -O2 -Wall -Wextra -I.
all: sxgbridge.clap sxgbridge32.exe
# Linux CLAP (needs libxcb-dev):  make linux   ->  sxgbridge-linux.clap
linux: sxgbridge-linux.clap
sxgbridge-linux.clap: clap_bridge_linux.c clap_common.h protocol.h
	gcc $(CFLAGS) -Wno-format-truncation -shared -fPIC -fvisibility=hidden -o $@ clap_bridge_linux.c -lxcb -lpthread -s
sxgbridge.clap: clap_bridge.c protocol.h
	x86_64-w64-mingw32-gcc $(CFLAGS) -shared -o $@ clap_bridge.c -static-libgcc -s
sxgbridge32.exe: host32.c vst2.h protocol.h
	i686-w64-mingw32-gcc $(CFLAGS) -mwindows -o $@ host32.c -static -lshell32 -lws2_32 -s
clean:
	rm -f sxgbridge.clap sxgbridge32.exe sxgbridge-linux.clap
