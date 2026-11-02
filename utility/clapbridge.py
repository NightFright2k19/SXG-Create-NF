# clapbridge.py - CLAP versions of the plugins (issue #97): Windows, Linux and macOS (Linux / macOS run the helper under Wine).
#
# The plugins are 32-bit Windows VST2 DLLs. Their CLAP version is a bridge: one small CLAP file per plugin
# (the same file under each plugin's name, e.g. syxg1000.clap) that runs the DLL in the 32-bit helper
# sxgbridge32.exe (clapbridge/host32.c) and exchanges audio, MIDI and the editor window with it:
#   Windows: sxgbridge.clap (clapbridge/clap_bridge.c, 64-bit), the helper runs directly
#   Linux:   sxgbridge-linux.clap (clapbridge/clap_bridge_posix.c, x86-64), the helper runs under Wine
# Each patcher writes only the CLAP of its own system. Layout written next to the patcher:
#     Plugins\VST2\syxg1000.dll ...        the plugins
#     Plugins\CLAP\syxg1000.clap ...       the bridges (they find ..\VST2\<same name>.dll)
#     Plugins\CLAP\sxgbridge32.exe         the helper (one copy for all)
# The bridge files are built from clapbridge/ by the Autobuild workflow and bundled with the Windows and Linux patchers;
# a checkout builds them with `make -C clapbridge` (Windows files, mingw-w64), `make -C clapbridge linux` (gcc, libxcb-dev) or `make -C clapbridge macos` (clang).
#   python utility/clapbridge.py <VST2 folder> <CLAP folder>      writes the CLAP files for the DLLs in the first folder
import plistlib, shutil, stat, struct, subprocess, sys
from pathlib import Path

CLAP_FILES = {'win32': 'sxgbridge.clap', 'linux': 'sxgbridge-linux.clap', 'darwin': 'sxgbridge-macos'}
CLAP_FILE = CLAP_FILES.get(sys.platform)             # None on other systems
HELPER_FILE = 'sxgbridge32.exe'
HERE = Path(__file__).resolve().parent

def bridge_dir() -> Path | None :
    # frozen patcher: bundled in 'bridge'; checkout: the build folder clapbridge/
    candidates = [Path(getattr(sys, '_MEIPASS', HERE.parent)) / 'bridge', HERE.parent / 'clapbridge']
    if CLAP_FILE is None : return None
    for d in candidates :
        if (d / CLAP_FILE).is_file() and (d / HELPER_FILE).is_file() : return d
    return None

def supported() -> bool :
    return bridge_dir() is not None

def wanted() -> bool :
    # the patcher of this system carries a bridge (Windows, Linux, macOS)
    return CLAP_FILE is not None

def machine(f : Path) -> int :
    # PE: machine field; ELF: e_machine
    data = f.read_bytes()[:4096]
    if data[:4] == b'\x7fELF' : return struct.unpack_from('<H', data, 18)[0]
    return struct.unpack_from('<H', data, struct.unpack_from('<I', data, 0x3C)[0] + 4)[0]

def mac_archs(f : Path) -> set[int] :
    # CPU types in a universal Mach-O file (0x0100000C arm64, 0x01000007 x86_64)
    data = f.read_bytes()[:4096]
    if data[:4] != b'\xca\xfe\xba\xbe' : return {struct.unpack_from('<I', data, 4)[0]} if data[:4] == b'\xcf\xfa\xed\xfe' else set()
    n = struct.unpack_from('>I', data, 4)[0]
    return {struct.unpack_from('>I', data, 8 + 20 * i)[0] for i in range(n)}

def check() -> None :
    # selftest: both files are there and are the right kind of file (64-bit CLAP: PE x64 / ELF x86-64, 32-bit PE helper)
    d = bridge_dir()
    assert d is not None, 'CLAP bridge files missing'
    if sys.platform == 'darwin' : assert mac_archs(d / CLAP_FILE) == {0x0100000C, 0x01000007}, f'{CLAP_FILE} is not a universal (arm64 + x86_64) plugin'
    else : assert machine(d / CLAP_FILE) == (0x8664 if sys.platform == 'win32' else 62), f'{CLAP_FILE} is not a 64-bit plugin'
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
        if sys.platform == 'darwin' : make_bundle(d / CLAP_FILE, clap / (p.stem + '.clap'), p.stem)
        else : shutil.copyfile(d / CLAP_FILE, clap / (p.stem + '.clap'))
        names.append(p.stem + '.clap')
    return names

def make_bundle(binary : Path, bundle : Path, stem : str) -> None :
    # macOS: <stem>.clap/Contents/{Info.plist, MacOS/<stem>}; hosts load the bundle, Apple Silicon wants a signature (ad hoc is enough)
    if bundle.exists() : shutil.rmtree(bundle)
    exe = bundle / 'Contents' / 'MacOS' / stem
    exe.parent.mkdir(parents = True)
    shutil.copyfile(binary, exe)
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    info = dict(CFBundleName = stem, CFBundleExecutable = stem, CFBundleIdentifier = 'io.github.nightfright2k19.sxg-create-nf.' + stem,
                CFBundlePackageType = 'BNDL', CFBundleSignature = '????', CFBundleVersion = '1.0', CFBundleShortVersionString = '1.0',
                LSMinimumSystemVersion = '11.0')
    (bundle / 'Contents' / 'Info.plist').write_bytes(plistlib.dumps(info))
    r = subprocess.run(['codesign', '--force', '--sign', '-', str(bundle)], capture_output = True, text = True)
    if r.returncode != 0 : raise RuntimeError(f'codesign failed for {bundle.name}: {r.stderr.strip()}')

if __name__ == '__main__' :
    if len(sys.argv) != 3 : sys.exit(__doc__ or 'usage: clapbridge.py <VST2 folder> <CLAP folder>')
    done = install(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f'{len(done)} CLAP bridge(s) written:', ', '.join(done))
