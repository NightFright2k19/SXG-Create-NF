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
# The table layout follows the model: classic for MU50 / MU80 / MU90, big for MU100 / MU128 / MU1000.
# With a DLL, a patched copy with the same name ("Enhanced" or "Full", see dllpatch.py) and a matching
# <name>.ini are written next to the table.

# * only one target for now
BUILD_TARGET = MU.SYXG50

def Print_Input_Roms() : 
    s = '---- Decode-Supported input roms ----\n'
    for table_ref in ROMLIST : 
        if table_ref.Can_Decode() : 
            s = s + str(table_ref) + '\n'
    print(s)

def main() : 

    files : list[Path] = []

    args = argv[1:]
    # --mu-basic : MU100 / MU128 / MU1000, use the MU Basic voice map instead of the native one
    if '--mu-basic' in [a.lower() for a in args] : 
        buildtarget.MU_BASIC = True
        args = [a for a in args if a.lower() != '--mu-basic']

    for file in args : 
        f = Path(file)
        if not Path.is_file(f) :
            s = f'input {file} is not a file!'
            # raise Exception(s)
            Friendly_error(s)
            exit(1)
        files.append(Path(file))

    # a DLL among the inputs: patched and written next to the table
    dlls = [f for f in files if dllpatch.Is_Dll(f)]
    files = [f for f in files if f not in dlls]
    # the <name>.orig.dll backup from an earlier run next to <name>.dll: use <name>.dll (patched from the backup)
    names = {d.name.lower() for d in dlls}
    dlls = [d for d in dlls if not (d.name.lower().endswith('.orig.dll') and d.name[:-9].lower() + '.dll' in names)]
    if len(dlls) > 1 : 
        Friendly_error(f'more than one DLL given: {[d.name for d in dlls]}')
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


    table_type : TableIn | None = None
    # match input to reference romlist
    for table_reference in ROMLIST : 
        if table_reference.Is_List_Ours(crcs_paths) : 
            table_type = table_reference
            break

    if not table_type : 
        Print_Input_Roms()
        Friendly_error('valid ROMs not found')
        exit(1)

    if not (table_type.support == 'decode' or table_type.support == 'both') : 
        Friendly_error(f'ROM detected, but decode not supported for {table_type.name}!')


    print(f'{table_type.name} detected, targeting {BUILD_TARGET}')

    paths_program, paths_waves = table_type.Order_Pathlists(crcs_paths)

    print(f'program rom(s) = {[p.name for p in paths_program]}')
    print(f'   wave rom(s) = {[p.name for p in paths_waves]}')

    # get output path
    out_path = str(paths_program[0].parent)
    
    convert.Convert(table_type.source, MU.SYXG50, out_path, paths_program, paths_waves, dll)

    Friendly_error('End of Code')

if __name__ == "__main__":
    main()
