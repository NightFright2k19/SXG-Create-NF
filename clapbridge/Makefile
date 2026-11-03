# Builds the CLAP bridge (issue #97) with mingw-w64:  make   (needs gcc-mingw-w64)
#   sxgbridge.clap    64-bit CLAP; the patcher copies it once per plugin under the plugin's name (syxg1000.clap ...)
#   sxgbridge-vst2.dll  64-bit VST2 (#104); the patcher copies it per plugin as <name>_x64.dll into Plugins\VST2\x64
#   sxgbridge32.exe   32-bit helper that runs the VST2 DLL
CFLAGS = -O2 -Wall -Wextra -I.
all: sxgbridge.clap sxgbridge-vst2.dll sxgbridge32.exe
# macOS CLAP (universal Mach-O, on a Mac with the Xcode command line tools):  make macos  ->  sxgbridge-macos
# (the patcher puts it into a .clap bundle, see utility/clapbridge.py)
macos: sxgbridge-macos
sxgbridge-macos: clap_bridge_posix.c clap_common.h protocol.h
	clang $(CFLAGS) -arch arm64 -arch x86_64 -mmacosx-version-min=11.0 -fvisibility=hidden -bundle -o $@ clap_bridge_posix.c
# Linux CLAP (needs libxcb-dev):  make linux   ->  sxgbridge-linux.clap
linux: sxgbridge-linux.clap
sxgbridge-linux.clap: clap_bridge_posix.c clap_common.h protocol.h
	gcc $(CFLAGS) -Wno-format-truncation -shared -fPIC -fvisibility=hidden -o $@ clap_bridge_posix.c -lxcb -lpthread -s
sxgbridge.clap: clap_bridge.c win_transport.h protocol.h
	x86_64-w64-mingw32-gcc $(CFLAGS) -shared -o $@ clap_bridge.c -static-libgcc -s
sxgbridge-vst2.dll: vst2_bridge.c win_transport.h vst2.h protocol.h
	x86_64-w64-mingw32-gcc $(CFLAGS) -shared -o $@ vst2_bridge.c -static-libgcc -s
sxgbridge32.exe: host32.c vst2.h protocol.h
	i686-w64-mingw32-gcc $(CFLAGS) -mwindows -o $@ host32.c -static -lshell32 -lws2_32 -s
clean:
	rm -f sxgbridge.clap sxgbridge-vst2.dll sxgbridge32.exe sxgbridge-linux.clap sxgbridge-macos
