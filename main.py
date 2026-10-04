import argparse # todo
from sys import argv
from pathlib import Path

from dataCRCs import TableIn, ROMLIST
from utils import calccrc32, Friendly_error
from dataenum import MU
import buildtarget

import convert
import dllpatch

# input: MU roms (in any order), optionally one syxg50.dll (any file name, recognised by its content).
# ROMs are also searched in the folder 'roms' next to this script (subfolders included). When the ROM
# sets of several models are found, all of them are converted, each DLL named after its model
# (syxg80.dll, syxg90.dll, syxg100.dll, syxg128.dll, syxg1000.dll; MU50: syxgmu50.dll).
# The table layout follows the model: classic for MU50 / MU80 / MU90, big for MU100 / MU128 / MU1000.
# With a DLL, a patched copy with the same name ("Enhanced" or "Full", see dllpatch.py) and a matching
# <name>.ini are written next to the table.

# * only one target for now
BUILD_TARGET = MU.SYXG50

# ROM files are also taken from a folder "roms" next to this script (subfolders included)
ROMS_DIR = Path(__file__).resolve().parent / 'roms'
ROM_MAX_SIZE = 64 << 20         # larger files can't be MU ROMs (skipped there, not CRC'd)

def Print_Input_Roms() :
    s = '---- Decode-Supported input roms ----\n'
    for table_ref in ROMLIST :
        if table_ref.Can_Decode() :
            s = s + str(table_ref) + '\n'
    print(s)

def Roms_Dir_Files() -> list[Path] :
    if not ROMS_DIR.is_dir() :
        return []
    return sorted(p for p in ROMS_DIR.rglob('*') if p.is_file() and p.stat().st_size <= ROM_MAX_SIZE)

def take_flag(args : list[str], flag : str) -> tuple[bool, list[str]] :
    found = flag in [a.lower() for a in args]
    return found, [a for a in args if a.lower() != flag]

def take_option(args : list[str], option : str) -> tuple[str | None, list[str]] :
    # --option value (internal options of the per-model runs)
    for i, a in enumerate(args) :
        if a.lower() == option and i + 1 < len(args) :
            return args[i + 1], args[:i] + args[i + 2:]
    return None, args

def main() :

    files : list[Path] = []

    args = argv[1:]
    # --mu-basic : MU100 / MU128 / MU1000, use the MU Basic voice map instead of the native one
    buildtarget.MU_BASIC, args = take_flag(args, '--mu-basic')
    # --embed : table and wave file go into the patched DLL (RT_RCDATA), no separate files and no ini
    buildtarget.EMBED, args = take_flag(args, '--embed')
    # internal (multi-model conversion, see below): output folder and DLL name of one model's run
    out_dir, args = take_option(args, '--out-dir')
    buildtarget.DLL_NAME, args = take_option(args, '--dll-name')
    single_run = out_dir is not None

    # wildcards (*.bin): the Windows command line passes them unexpanded, so they are expanded here;
    # a pattern without matches is skipped (the ROMs may all be in the roms folder)
    import glob
    expanded : list[str] = []
    for file in args : 
        if glob.has_magic(file) : 
            hits = sorted(p for p in glob.glob(file) if Path(p).is_file())
            if not hits : 
                print(f'note: no files match {file}, skipped')
            expanded += hits
        else : 
            expanded.append(file)
    args = expanded

    for file in args :
        f = Path(file)
        if not Path.is_file(f) :
            s = f'input {file} is not a file!'
            # raise Exception(s)
            Friendly_error(s)
            exit(1)
        files.append(Path(file))

    # ROMs (and a DLL, if none was given) from the "roms" folder next to the script
    from_roms_dir : set[Path] = set()
    if not single_run :
        given = {f.resolve() for f in files}
        extra = [p for p in Roms_Dir_Files() if p.resolve() not in given]
        if extra :
            print(f'roms folder: {len(extra)} files in {ROMS_DIR}')
            files += extra
            from_roms_dir = set(extra)

    # a DLL among the inputs: patched and written next to the table
    dlls = [f for f in files if dllpatch.Is_Dll(f)]
    files = [f for f in files if f not in dlls]
    # a DLL given on the command line wins over one in the roms folder
    if any(d not in from_roms_dir for d in dlls) :
        dlls = [d for d in dlls if d not in from_roms_dir]
    # the <name>.orig.dll backup from an earlier run next to <name>.dll: use <name>.dll (patched from the backup)
    names = {(d.parent, d.name.lower()) for d in dlls}
    dlls = [d for d in dlls if not (d.name.lower().endswith('.orig.dll') and (d.parent, d.name[:-9].lower() + '.dll') in names)]
    if len(dlls) > 1 :
        Friendly_error(f'more than one DLL given: {[str(d) for d in dlls]}')
        exit(1)
    dll = dlls[0] if dlls else None
    if dll :
        try :
            dll_desc = dllpatch.Identify(dll)
        except dllpatch.DllPatchError as e :
            Friendly_error(str(e))
            exit(1)
        print(f'DLL: {dll_desc}')

    if not files :
        Print_Input_Roms()
        Friendly_error('')
        exit(1)

    print(f'calculating CRC32 ({len(files)} files)...')
    crcs_paths : dict[str, Path] = {calccrc32(x) : x for x in files} # dict comprehension

    print('CRC32 calculation done')

    # every model whose ROM set is complete (one ROM version per model: the first one in ROMLIST)
    found : list[TableIn] = []
    for table_reference in ROMLIST :
        if table_reference.Is_List_Ours(crcs_paths) and table_reference.source not in [t.source for t in found] :
            found.append(table_reference)

    if not found :
        Print_Input_Roms()
        Friendly_error('valid ROMs not found')
        exit(1)

    decodable = [t for t in found if t.Can_Decode()]
    for t in found :
        if t not in decodable :
            print(f'{t.name} detected, but decode not supported, skipped')
    # MU2000: same sound set as the MU1000 (see convert.py), skipped when the MU1000 set is there too
    if len(decodable) > 1 and any(t.source == MU.MU1000 for t in decodable) :
        for t in [t for t in decodable if t.source == MU.MU2000] :
            print(f'{t.name} detected, skipped (same sound set as the MU1000)')
            decodable.remove(t)
    if not decodable :
        Friendly_error(f'ROM detected, but decode not supported for {found[0].name}!')

    # output folder: next to a program ROM given on the command line; for ROMs from the roms folder
    # next to the DLL (if any), else next to this script
    def output_folder(paths_program : list[Path]) -> str :
        if out_dir is not None : return out_dir
        if paths_program[0] not in from_roms_dir : return str(paths_program[0].parent)
        return str(dll.parent if dll else Path(__file__).resolve().parent)

    if len(decodable) == 1 :
        table_type = decodable[0]
        print(f'{table_type.name} detected, targeting {BUILD_TARGET}')
        paths_program, paths_waves = table_type.Order_Pathlists(crcs_paths)
        print(f'program rom(s) = {[p.name for p in paths_program]}')
        print(f'   wave rom(s) = {[p.name for p in paths_waves]}')
        convert.Convert(table_type.source, MU.SYXG50, output_folder(paths_program), paths_program, paths_waves, dll)
        Friendly_error('End of Code', 0)

    # * several models: each one is converted in a run of its own (a separate process, the converter keeps
    # per-model state in module globals); the DLLs and inis are named after the model (syxg80.dll ...)
    import subprocess, sys, os
    print(f'{len(decodable)} models detected: {", ".join(t.name for t in decodable)}')
    results = []
    for table_type in decodable :
        paths_program, paths_waves = table_type.Order_Pathlists(crcs_paths)
        model = table_type.source.name
        cmd = [sys.executable, str(Path(__file__).resolve())] + [str(p) for p in paths_program + paths_waves]
        if dll : cmd += [str(dll), '--dll-name', dllpatch.Model_Dll_Name(model)]
        cmd += ['--out-dir', output_folder(paths_program)]
        if buildtarget.MU_BASIC : cmd.append('--mu-basic')
        if buildtarget.EMBED : cmd.append('--embed')
        print(f'\n==== {table_type.name} ' + '=' * max(0, 60 - len(table_type.name)), flush=True)
        r = subprocess.run(cmd, env=dict(os.environ, SXG_NO_PAUSE='1'), stdin=subprocess.DEVNULL)
        results.append((table_type.name, r.returncode == 0))
    print('\n==== summary')
    for name, ok in results :
        print(f'  {name}: ' + ('done' if ok else 'FAILED'))
    Friendly_error('End of Code', 0 if all(ok for _, ok in results) else 1)

if __name__ == "__main__":
    main()
