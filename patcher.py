# SXG-Create-NF Patcher (issue #33): window around main.py for Windows, Linux and macOS.
# Releases freeze this file with PyInstaller into one executable per system (.github/workflows/build.yml);
# it runs exactly the same converter as main.py, so both always produce the same plugins.
# * ROM files and syxg50.dll are searched in the patcher's folder (subfolders included) by CRC32, or in a
#   folder / DLL the user chooses. 'Patch' converts every complete model with --embed into the folder
#   'Plugins' next to the patcher (one DLL per model, tables inside).
# * patcher --cli <args> runs main.py's command line (used for the per-model runs).
# * Language: the system language, else English; a menu at the top right switches it.
import sys, os, threading, queue, subprocess, locale
from pathlib import Path

FROZEN = getattr(sys, 'frozen', False)
HERE = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
if FROZEN and sys.platform == 'darwin' and HERE.parent.name == 'Contents' :
    HERE = HERE.parents[2]                      # Patcher.app/Contents/MacOS -> folder holding the .app
CODE = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
sys.path.insert(0, str(CODE / 'utility'))
sys.path.insert(0, str(CODE))
try : from patcher_version import VERSION
except ImportError : VERSION = 'dev'

def run_cli(args : list[str]) :
    os.environ['SXG_NO_PAUSE'] = '1'
    sys.argv = ['main.py'] + args
    import main
    main.main()

def system_language(known) -> str :
    names = []
    if sys.platform == 'win32' :
        try :
            import ctypes
            names.append(locale.windows_locale.get(ctypes.windll.kernel32.GetUserDefaultUILanguage(), ''))
        except Exception : pass
    elif sys.platform == 'darwin' :
        try :
            out = subprocess.run(['defaults', 'read', '-g', 'AppleLanguages'], capture_output = True, text = True, timeout = 3).stdout
            names += [x.strip(' "(),\n') for x in out.split('\n') if x.strip(' "(),\n')]
        except Exception : pass
    for var in ('LC_ALL', 'LC_MESSAGES', 'LANG', 'LANGUAGE') :
        if os.environ.get(var) : names.append(os.environ[var])
    try : names.append(locale.getlocale()[0] or '')
    except Exception : pass
    alias = {'iw' : 'he', 'in' : 'id', 'pes' : 'fa'}     # old codes some systems report
    for n in names :
        code = n.replace('-', '_').split('_')[0].split('.')[0].lower()
        code = alias.get(code, code)
        if code in known : return code
    return 'en'

def scan(folder : Path, dll_choice : Path | None, log) :
    # -> (models: list of (name, programs, waves)), dll (Path or None), dll_problem (str or None)
    import dllpatch
    from utils import calccrc32
    from dataCRCs import ROMLIST
    from dataenum import MU
    files = [p for p in folder.rglob('*') if p.is_file() and p.stat().st_size <= 64 << 20
             and 'Plugins' not in p.relative_to(folder).parts[:1]]
    dlls = [dll_choice] if dll_choice else [p for p in files if p.suffix.lower() == '.dll' and dllpatch.Is_Dll(p)]
    dll, problem = None, None
    for d in dlls :
        try : dllpatch.Identify(d); dll = d; break
        except Exception as e : problem = f'{d}: {e}'
    crcs = {}
    for p in files :
        if p.suffix.lower() in ('.dll', '.exe', '.zip', '.7z', '.txt', '.md', '.ini', '.tbl', '.upcm') : continue
        try : crcs[calccrc32(p)] = p
        except Exception : pass
    found = []
    for t in ROMLIST :
        if t.Is_List_Ours(crcs) and t.Can_Decode() and t.source not in [f.source for f in found] : found.append(t)
    if any(t.source == MU.MU1000 for t in found) : found = [t for t in found if t.source != MU.MU2000]
    models = []
    for t in found :
        programs, waves = t.Order_Pathlists(crcs)
        models.append((t.name, programs, waves))
    return models, dll, (None if dll else problem)

def main_window() :
    import tkinter as tk
    from tkinter import ttk, filedialog
    from patcher_i18n import TEXT, LANGUAGES

    root = tk.Tk()
    root.title(f'SXG-Create-NF Patcher {VERSION}')
    root.resizable(False, False)
    st = dict(lang = system_language(LANGUAGES), folder = HERE, dll = None, dll_choice = None, models = [],
              busy = False, details = False, status = ('scanning', {}), problem = None)
    q = queue.Queue()
    def T(key, **kw) : return TEXT[st['lang']].get(key, TEXT['en'][key]).format(**kw)

    frame = ttk.Frame(root, padding = 14); frame.grid(sticky = 'nsew')
    head = ttk.Frame(frame); head.grid(row = 0, column = 0, columnspan = 3, sticky = 'ew')
    ttk.Label(head, text = 'SXG-Create-NF Patcher', font = ('TkDefaultFont', 13, 'bold')).pack(side = 'left')
    lang_var = tk.StringVar(value = LANGUAGES[st['lang']])
    lang_box = ttk.Combobox(head, textvariable = lang_var, values = list(LANGUAGES.values()), state = 'readonly',
                            width = 16, height = len(LANGUAGES))
    lang_box.pack(side = 'right')
    intro = ttk.Label(frame); intro.grid(row = 1, column = 0, columnspan = 3, sticky = 'w', pady = (2, 10))
    box = ttk.LabelFrame(frame, padding = 10); box.grid(row = 2, column = 0, columnspan = 3, sticky = 'ew')
    box.columnconfigure(1, weight = 1)
    folder_lbl = ttk.Label(box); folder_lbl.grid(row = 0, column = 0, sticky = 'w')
    folder_val = ttk.Label(box, foreground = '#444'); folder_val.grid(row = 0, column = 1, sticky = 'w', padx = 6)
    browse = ttk.Button(box); browse.grid(row = 0, column = 2, sticky = 'e')
    rows = ttk.Frame(box); rows.grid(row = 1, column = 0, columnspan = 3, sticky = 'ew', pady = (6, 0))
    rows.columnconfigure(1, weight = 1)
    dll_row = ttk.Frame(box); dll_row.grid(row = 2, column = 0, columnspan = 3, sticky = 'ew', pady = (2, 0))
    dll_row.columnconfigure(1, weight = 1)
    dll_mark = ttk.Label(dll_row, width = 2); dll_mark.grid(row = 0, column = 0, sticky = 'w')
    dll_name = ttk.Label(dll_row); dll_name.grid(row = 0, column = 1, sticky = 'w', padx = 6)
    dll_state = ttk.Label(dll_row, foreground = '#555'); dll_state.grid(row = 0, column = 2, sticky = 'e')
    dll_btn = ttk.Button(dll_row); dll_btn.grid(row = 0, column = 3, sticky = 'e', padx = (8, 0))
    target = ttk.Label(frame, foreground = '#444'); target.grid(row = 3, column = 0, columnspan = 3, sticky = 'w', pady = (8, 0))
    progress = ttk.Progressbar(frame, mode = 'determinate'); progress.grid(row = 4, column = 0, columnspan = 3, sticky = 'ew', pady = (8, 0))
    ttk.Separator(frame).grid(row = 5, column = 0, columnspan = 3, sticky = 'ew', pady = 10)
    status = ttk.Label(frame, wraplength = 330); status.grid(row = 6, column = 0, sticky = 'w')
    det_btn = ttk.Button(frame); det_btn.grid(row = 6, column = 1, sticky = 'e', padx = 6)
    patch_btn = ttk.Button(frame, width = 14); patch_btn.grid(row = 6, column = 2, sticky = 'e')
    open_btn = ttk.Button(frame)
    log = tk.Text(frame, height = 14, width = 80, font = ('TkFixedFont', 9), state = 'disabled')
    frame.columnconfigure(0, weight = 1)

    def plugins_dir() : return HERE / 'Plugins'
    def refresh() :
        intro['text'] = T('intro'); box['text'] = T('files'); folder_lbl['text'] = T('folder') + ':'
        folder_val['text'] = str(st['folder']); browse['text'] = T('browse'); dll_btn['text'] = T('choose_dll')
        for w in rows.winfo_children() : w.destroy()
        for i, (name, _, _) in enumerate(st['models']) :
            ttk.Label(rows, text = '✔', foreground = '#1a7f37', width = 2).grid(row = i, column = 0, sticky = 'w')
            ttk.Label(rows, text = name).grid(row = i, column = 1, sticky = 'w', padx = 6)
            ttk.Label(rows, text = T('complete'), foreground = '#555').grid(row = i, column = 2, sticky = 'e')
        ok = st['dll'] is not None
        dll_mark.configure(text = '✔' if ok else '✘', foreground = '#1a7f37' if ok else '#c62828')
        dll_name['text'] = T('dll'); dll_state['text'] = T('dll_ok') if ok else T('dll_missing')
        target['text'] = T('target') + ':  ' + str(plugins_dir())
        key, kw = st['status']; status['text'] = T(key, **kw)
        det_btn['text'] = T('hide') if st['details'] else T('details')
        patch_btn['text'] = T('patch'); open_btn['text'] = T('open_folder')
        can = not st['busy'] and st['models'] and ok
        patch_btn.state(['!disabled'] if can else ['disabled'])
        for b in (browse, dll_btn) : b.state(['disabled'] if st['busy'] else ['!disabled'])
    def set_status(key, **kw) : st['status'] = (key, kw); refresh()
    def write_log(text) :
        log.configure(state = 'normal'); log.insert('end', text); log.see('end'); log.configure(state = 'disabled')

    def start_scan() :
        st['busy'] = True; set_status('scanning'); progress.configure(mode = 'indeterminate'); progress.start(12)
        def work() :
            try : q.put(('scanned',) + scan(st['folder'], st['dll_choice'], None))
            except Exception as e : q.put(('scanned', [], None, str(e)))
        threading.Thread(target = work, daemon = True).start()
    def scanned(models, dll, problem) :
        progress.stop(); progress.configure(mode = 'determinate', value = 0)
        st.update(busy = False, models = models, dll = dll, problem = problem)
        if problem and st['dll_choice'] : write_log(T('dll_bad') + ' ' + problem + '\n')
        if not models : set_status('no_roms' if st['folder'] != HERE else 'need_roms')
        elif not dll : set_status('need_dll')
        else : set_status('ready', n = len(models))
        if not models and st['folder'] == HERE and not st.get('asked') :
            st['asked'] = True; root.after(200, choose_folder)

    def choose_folder() :
        d = filedialog.askdirectory(title = T('pick_folder'), initialdir = str(st['folder']))
        if d : st['folder'] = Path(d); start_scan()
    def choose_dll() :
        f = filedialog.askopenfilename(title = T('pick_dll'), initialdir = str(st['folder']),
                                       filetypes = [('syxg50.dll', '*.dll'), ('*', '*')])
        if f : st['dll_choice'] = Path(f); start_scan()
    def toggle_details() :
        st['details'] = not st['details']
        if st['details'] : log.grid(row = 8, column = 0, columnspan = 3, sticky = 'nsew', pady = (10, 0))
        else : log.grid_remove()
        refresh()
    def start_patch() :
        out = plugins_dir(); out.mkdir(exist_ok = True)
        files = [str(p) for _, pr, wv in st['models'] for p in pr + wv]
        args = files + [str(st['dll']), '--embed', '--out-dir', str(out)]
        me = [sys.executable] if FROZEN else [sys.executable, str(Path(__file__).resolve())]
        st.update(busy = True, total = len(st['models']), done_n = 0); open_btn.grid_remove()
        progress.configure(maximum = len(st['models']), value = 0)
        set_status('converting', model = st['models'][0][0].split(' ')[0], i = 1, total = len(st['models']))
        def work() :
            env = dict(os.environ, SXG_NO_PAUSE = '1', PYTHONUNBUFFERED = '1', PYTHONIOENCODING = 'utf-8')
            flags = 0x08000000 if sys.platform == 'win32' else 0          # CREATE_NO_WINDOW
            p = subprocess.Popen(me + ['--cli'] + args, stdout = subprocess.PIPE, stderr = subprocess.STDOUT,
                                 stdin = subprocess.DEVNULL, env = env, text = True, encoding = 'utf-8',
                                 errors = 'replace', creationflags = flags)
            for line in p.stdout : q.put(('line', line))
            q.put(('finished', p.wait()))
        threading.Thread(target = work, daemon = True).start()
    def line(text) :
        write_log(text)
        s = text.strip()
        if s.startswith('==== ') and s != '==== summary' :
            names = [m[0] for m in st['models']]
            hit = [i for i, n in enumerate(names) if s[5:].startswith(n)]
            if hit :
                i = hit[0]; progress.configure(value = i)
                set_status('converting', model = names[i].split(' ')[0], i = i + 1, total = len(names))
    def finished(code) :
        st['busy'] = False; progress.configure(value = progress['maximum'])
        log_text = log.get('1.0', 'end')
        failed = [m[0].split(' ')[0] for m in st['models'] if f'  {m[0]}: FAILED' in log_text]
        if code != 0 and not failed : failed = [m[0].split(' ')[0] for m in st['models']] if len(st['models']) == 1 else ['?']
        n = len(list(plugins_dir().glob('*.dll')))
        if failed : set_status('failed', models = ', '.join(failed))
        else : set_status('done', n = n)
        open_btn.grid(row = 7, column = 2, sticky = 'e', pady = (8, 0))
        if failed and not st['details'] : toggle_details()
    def open_folder() :
        p = str(plugins_dir())
        if sys.platform == 'win32' : os.startfile(p)
        elif sys.platform == 'darwin' : subprocess.Popen(['open', p])
        else : subprocess.Popen(['xdg-open', p])
    def pick_lang(_ = None) :
        st['lang'] = {v : k for k, v in LANGUAGES.items()}[lang_var.get()]; refresh()
    def poll() :
        try :
            while True :
                m = q.get_nowait()
                {'scanned' : scanned, 'line' : line, 'finished' : finished}[m[0]](*m[1:])
        except queue.Empty : pass
        root.after(80, poll)

    browse['command'] = choose_folder; dll_btn['command'] = choose_dll; det_btn['command'] = toggle_details
    patch_btn['command'] = start_patch; open_btn['command'] = open_folder
    lang_box.bind('<<ComboboxSelected>>', pick_lang)
    refresh(); start_scan(); poll()
    root.mainloop()

if __name__ == '__main__' :
    if len(sys.argv) > 1 and sys.argv[1] == '--cli' : run_cli(sys.argv[2:])
    elif len(sys.argv) > 1 and sys.argv[1] == '--selftest' :
        import dllpatch, convert, dataCRCs, main as _m
        assert (Path(dllpatch.__file__).parent / 'bitmaps').is_dir(), 'bitmaps missing'
        print('selftest ok', VERSION); sys.exit(0)
    else : main_window()
