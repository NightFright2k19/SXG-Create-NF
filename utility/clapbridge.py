# clapbridge.py - CLAP versions of the plugins (issue #97), Windows only for now.
#
# The plugins are 32-bit Windows VST2 DLLs. Their CLAP version is a bridge: one small 64-bit CLAP file per plugin
# (clapbridge/clap_bridge.c, the same file under each plugin's name, e.g. syxg1000.clap) that runs the DLL in the
# 32-bit helper sxgbridge32.exe (clapbridge/host32.c) and exchanges audio, MIDI and the editor window with it.
# Layout written next to the patcher:
#     Plugins\VST2\syxg1000.dll ...        the plugins
#     Plugins\CLAP\syxg1000.clap ...       the bridges (they find ..\VST2\<same name>.dll)
#     Plugins\CLAP\sxgbridge32.exe         the helper (one copy for all)
# The two bridge files are built from clapbridge/ by the Autobuild workflow (mingw-w64) and bundled with the Windows
# patcher; a checkout builds them with `make -C clapbridge`.
#   python utility/clapbridge.py <VST2 folder> <CLAP folder>      writes the CLAP files for the DLLs in the first folder
import shutil, struct, sys
from pathlib import Path

CLAP_FILE, HELPER_FILE = 'sxgbridge.clap', 'sxgbridge32.exe'
HERE = Path(__file__).resolve().parent

def bridge_dir() -> Path | None :
    # frozen patcher: bundled in 'bridge'; checkout: the build folder clapbridge/
    candidates = [Path(getattr(sys, '_MEIPASS', HERE.parent)) / 'bridge', HERE.parent / 'clapbridge']
    for d in candidates :
        if (d / CLAP_FILE).is_file() and (d / HELPER_FILE).is_file() : return d
    return None

def supported() -> bool :
    return sys.platform == 'win32' and bridge_dir() is not None

def machine(f : Path) -> int :
    data = f.read_bytes()[:4096]
    return struct.unpack_from('<H', data, struct.unpack_from('<I', data, 0x3C)[0] + 4)[0]

def check() -> None :
    # selftest: both files are there and are the right kind of PE file (64-bit CLAP, 32-bit helper)
    d = bridge_dir()
    assert d is not None, 'CLAP bridge files missing'
    assert machine(d / CLAP_FILE) == 0x8664, 'sxgbridge.clap is not a 64-bit DLL'
    assert machine(d / HELPER_FILE) == 0x014C, 'sxgbridge32.exe is not a 32-bit program'

def install(vst2 : Path, clap : Path) -> list[str] :
    # one CLAP per DLL in vst2; returns the names written
    d = bridge_dir()
    if d is None : raise FileNotFoundError('CLAP bridge files not found')
    dlls = sorted(p for p in vst2.glob('*.dll') if p.stem.lower().startswith('syxg'))
    if not dlls : return []
    clap.mkdir(parents = True, exist_ok = True)
    shutil.copyfile(d / HELPER_FILE, clap / HELPER_FILE)
    names = []
    for p in dlls :
        shutil.copyfile(d / CLAP_FILE, clap / (p.stem + '.clap'))
        names.append(p.stem + '.clap')
    return names

if __name__ == '__main__' :
    if len(sys.argv) != 3 : sys.exit(__doc__ or 'usage: clapbridge.py <VST2 folder> <CLAP folder>')
    done = install(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f'{len(done)} CLAP bridge(s) written:', ', '.join(done))
