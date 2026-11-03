#!/bin/bash
# Builds the CLAP bridges and runs the Wine tests (issue #97). Needs: gcc, gcc-mingw-w64, libxcb-dev, wine (64-bit, with 32-bit support),
# xvfb (or a DISPLAY), a Wine prefix (WINEPREFIX, default ~/.wine). Run from anywhere:  bash clapbridge/test/run_tests.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SELF="$HERE/$(basename "$0")"
if [ -z "${DISPLAY:-}" ]; then exec xvfb-run -a bash "$SELF" "$@"; fi      # no X server: start one
cd "$HERE/.."
export WINEDEBUG=-all
make clean >/dev/null; make; make linux
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
cd test
i686-w64-mingw32-gcc -O2 -Wall -shared -o "$T/fake.dll" fakevst.c -static-libgcc -s
x86_64-w64-mingw32-gcc -O2 -Wall -I.. -o "$T/testhost.exe" testhost.c -static -s
gcc -O2 -Wall -I.. -o "$T/testhost_posix" testhost_posix.c -lxcb -ldl -lm
gcc -O2 -w -DTEST_FLOAT -I.. -o "$T/testhost_float" testhost_posix.c -lxcb -ldl -lm
# the macOS source compiled on Linux (stub header for _NSGetEnviron): same transport, floating editor
gcc -O2 -Wall -Wno-format-truncation -D__APPLE__ -Istub -I.. -shared -fPIC -fvisibility=hidden -o "$T/mac.clap" ../clap_bridge_posix.c -lpthread
for d in win lin mac; do mkdir -p "$T/$d/CLAP" "$T/$d/VST2"; cp "$T/fake.dll" "$T/$d/VST2/fake.dll"; cp ../sxgbridge32.exe "$T/$d/CLAP/"; done
cp ../sxgbridge.clap "$T/win/CLAP/fake.clap"; cp ../sxgbridge-linux.clap "$T/lin/CLAP/fake.clap"; cp "$T/mac.clap" "$T/mac/CLAP/fake.clap"
echo "== Windows bridge (Wine)";  wine "$T/testhost.exe" "$(winepath -w "$T/win/CLAP/fake.clap")"
echo "== Windows bridge, path with mixed separators (as Woof! gives it)"
wine "$T/testhost.exe" "$(winepath -w "$T/win/CLAP")/fake.clap" | grep -E "plugin init|RESULT"
echo "== Linux bridge";           "$T/testhost_posix" "$T/lin/CLAP/fake.clap"
echo "== macOS bridge (floating editor, emulated on Linux)"; "$T/testhost_float" "$T/mac/CLAP/fake.clap"
echo "ALL BRIDGE TESTS PASSED"
