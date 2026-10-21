# SXG-Create-NF Patcher (issue #33): window around main.py for Windows, Linux and macOS.
# Releases freeze this file with PyInstaller into one executable per system (.github/workflows/build.yml);
# it runs exactly the same converter as main.py, so both always produce the same plugins.
# * ROM files are searched in the patcher's folder (subfolders included) by CRC32, or in a folder the user
#   chooses. 'Patch' converts every complete model with --embed into the folder 'Plugins' next to the patcher
#   (one DLL per model, tables inside). The plugins are made from the pre-patched templates bundled with the
#   patcher (utility/template.py, issue #40), so no syxg50.dll is needed; the S-YXG2006LE still needs the
#   user's SGP2.OLD / SGP2.DLL (sgp2patch.py).
# * patcher --cli <args> runs main.py's command line (used for the per-model runs).
# * Language: the system language, else English; a menu at the top right switches it.
# * Update (issue #72): a release patcher looks for a newer release a moment after it has started and offers it with the
#   Update button (utility/selfupdate.py); `--no-update-check` (or SXG_NO_UPDATE_CHECK=1) leaves out the check at the start.
#   Test options: --update-dir <folder with release files>, --update-test-version r<N>; --after-update <old> and
#   --selftest-out <file> are used by the update itself.
import sys, os, threading, queue, subprocess, locale
from pathlib import Path

FROZEN = getattr(sys, 'frozen', False)
HERE = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
if FROZEN and sys.platform == 'darwin' and HERE.parent.name == 'Contents' :
    HERE = HERE.parents[2]                      # Patcher.app/Contents/MacOS -> folder holding the .app
CODE = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
ICONS = [CODE / ('icons' if FROZEN else 'utility/icons') / n for n in ('patcher.png', 'patcher_32.png', 'patcher_16.png')]
                                                # window icons in three sizes (the exe / app icon is set by the build)
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

def scan(folder : Path, log) :
    # -> models: list of (name, programs, waves)
    from utils import calccrc32
    from dataCRCs import ROMLIST
    from dataenum import MU
    files = [p for p in folder.rglob('*') if p.is_file() and p.stat().st_size <= 64 << 20
             and 'Plugins' not in p.relative_to(folder).parts[:1]]
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
    models.sort(key = lambda m : not m[0].startswith('MU50 '))     # MU50 first, the rest in ROMLIST order
    # S-YXG2006LE: its own engine (SGP2.OLD / SGP2.DLL) and tables, patched in addition to the MU plugins
    import sgp2patch
    sizes = {937984, 716608, 11723868}
    sgp2 = sgp2patch.Find({calccrc32(p) : p for p in files if p.stat().st_size in sizes})
    if sgp2 : models.insert(0, (SGP2_NAME, list(sgp2), []))     # listed first
    return models

SGP2_NAME = 'S-YXG2006LE'

def main_window() :
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    from patcher_i18n import TEXT, LANGUAGES
    import selfupdate

    root = tk.Tk()
    root.title(f'SXG-Create-NF Patcher {VERSION}')
    root.resizable(False, False)
    try : root.iconphoto(True, *[tk.PhotoImage(file = str(f)) for f in ICONS])
    except Exception : pass                                     # a missing icon must never stop the patcher
    st = dict(lang = system_language(LANGUAGES), folder = HERE, models = [],
              busy = False, details = False, status = ('scanning', {}))
    q = queue.Queue()
    def T(key, **kw) : return TEXT[st['lang']].get(key, TEXT['en'][key]).format(**kw)

    frame = ttk.Frame(root, padding = 14); frame.grid(sticky = 'nsew')
    head = ttk.Frame(frame); head.grid(row = 0, column = 0, columnspan = 4, sticky = 'ew')
    ttk.Label(head, text = 'SXG-Create-NF Patcher', font = ('TkDefaultFont', 13, 'bold')).pack(side = 'left')
    lang_var = tk.StringVar(value = LANGUAGES[st['lang']])
    lang_box = ttk.Combobox(head, textvariable = lang_var, values = list(LANGUAGES.values()), state = 'readonly',
                            width = 16, height = len(LANGUAGES))
    lang_box.pack(side = 'right')
    intro = ttk.Label(frame); intro.grid(row = 1, column = 0, columnspan = 4, sticky = 'w', pady = (2, 10))
    box = ttk.LabelFrame(frame, padding = 10); box.grid(row = 2, column = 0, columnspan = 4, sticky = 'ew')
    box.columnconfigure(1, weight = 1)
    folder_lbl = ttk.Label(box); folder_lbl.grid(row = 0, column = 0, sticky = 'w')
    folder_val = ttk.Label(box, foreground = '#444'); folder_val.grid(row = 0, column = 1, sticky = 'w', padx = 6)
    browse = ttk.Button(box); browse.grid(row = 0, column = 2, sticky = 'e')
    rows = ttk.Frame(box); rows.grid(row = 1, column = 0, columnspan = 3, sticky = 'ew', pady = (6, 0))
    rows.columnconfigure(1, weight = 1)
    target = ttk.Label(frame, foreground = '#444'); target.grid(row = 3, column = 0, columnspan = 4, sticky = 'w', pady = (8, 0))
    progress = ttk.Progressbar(frame, mode = 'determinate'); progress.grid(row = 4, column = 0, columnspan = 4, sticky = 'ew', pady = (8, 0))
    ttk.Separator(frame).grid(row = 5, column = 0, columnspan = 4, sticky = 'ew', pady = 10)
    status = ttk.Label(frame, wraplength = 330); status.grid(row = 6, column = 0, sticky = 'w')
    det_btn = ttk.Button(frame); det_btn.grid(row = 6, column = 2, sticky = 'e', padx = 6)
    patch_btn = ttk.Button(frame, width = 14); patch_btn.grid(row = 6, column = 3, sticky = 'e')
    open_btn = ttk.Button(frame)
    cur = selfupdate.current(VERSION)
    upd_on = selfupdate.enabled(VERSION, FROZEN)
    # state: None, checking, new, current, error, load, verify, start, failed; quiet: no message (the check at the start)
    upd = dict(state = None, rev = None, err = '', done = 0, total = 0, quiet = True)
    upd_btn = ttk.Button(frame); upd_note = ttk.Label(frame, wraplength = 330)
    if upd_on : upd_btn.grid(row = 6, column = 1, sticky = 'e')
    log = tk.Text(frame, height = 14, width = 80, font = ('TkFixedFont', 9), state = 'disabled')
    frame.columnconfigure(0, weight = 1)

    def plugins_dir() : return HERE / 'Plugins'
    def refresh() :
        intro['text'] = T('intro'); box['text'] = T('files'); folder_lbl['text'] = T('folder') + ':'
        folder_val['text'] = str(st['folder']); browse['text'] = T('browse')
        for w in rows.winfo_children() : w.destroy()
        for i, (name, _, _) in enumerate(st['models']) :
            ttk.Label(rows, text = '✔', foreground = '#1a7f37', width = 2).grid(row = i, column = 0, sticky = 'w')
            ttk.Label(rows, text = name).grid(row = i, column = 1, sticky = 'w', padx = 6)
            ttk.Label(rows, text = T('complete'), foreground = '#555').grid(row = i, column = 2, sticky = 'e')
        target['text'] = T('target') + ':  ' + str(plugins_dir())
        key, kw = st['status']; status['text'] = T(key, **kw)
        det_btn['text'] = T('hide') if st['details'] else T('details')
        patch_btn['text'] = T('patch'); open_btn['text'] = T('open_folder')
        can = not st['busy'] and st['models']
        patch_btn.state(['!disabled'] if can else ['disabled'])
        browse.state(['disabled'] if st['busy'] else ['!disabled'])
        refresh_upd()
    def refresh_upd() :
        if not upd_on : return
        s, v = upd['state'], f"r{upd['rev']}"
        av = f'Autobuild {v}'                                          # the name of the release, in the messages of the update itself
        upd_btn['text'] = T('upd_btn')
        upd_btn.state(['disabled'] if st['busy'] or s in ('checking', 'load', 'verify', 'start') else ['!disabled'])
        mb = lambda n : f'{n / 1e6:.1f}'
        note, color = {
            'checking' : ('' if upd['quiet'] else T('upd_checking'), '#444'),
            'new' : (T('upd_new', ver = v), '#1a7f37'),
            'current' : ('' if upd['quiet'] else T('upd_none', ver = f'r{cur}'), '#444'),
            'error' : ('' if upd['quiet'] else T('upd_fail', err = upd['err']), '#b3261e'),
            'load' : (T('upd_load', ver = av, done = mb(upd['done']), total = mb(upd['total']) if upd['total'] else '?'), '#444'),
            'verify' : (T('upd_verify', ver = av), '#444'),
            'start' : (T('upd_start', ver = av), '#444'),
            'failed' : (T('upd_fail', err = upd['err']), '#b3261e'),
        }.get(s, ('', '#444'))
        upd_note.configure(text = note, foreground = color)
        if note : upd_note.grid(row = 7, column = 0, columnspan = 3, sticky = 'w', pady = (8, 0))
        else : upd_note.grid_remove()
    def start_check(manual) :
        if upd['state'] in ('checking', 'load', 'verify', 'start') : return
        upd.update(state = 'checking', quiet = not manual); refresh_upd()
        def work() :
            try : q.put(('upd_checked', selfupdate.latest_revision(), '', manual))
            except Exception as e : q.put(('upd_checked', None, str(e) or type(e).__name__, manual))
        threading.Thread(target = work, daemon = True).start()
    def upd_checked(rev, err, manual) :
        if err : upd.update(state = 'error', err = err, quiet = not manual)
        elif rev is not None and cur is not None and rev > cur : upd.update(state = 'new', rev = rev, quiet = False)
        else : upd.update(state = 'current', quiet = not manual)
        refresh_upd()
        if manual and upd['state'] == 'new' : upd_click()
    def upd_click() :
        if upd['state'] == 'new' :
            if messagebox.askokcancel(T('upd_btn'), T('upd_ask', ver = f"Autobuild r{upd['rev']}")) : start_update()
        else : start_check(True)
    def start_update() :
        st['busy'] = True; upd.update(state = 'load', done = 0, total = 0, err = '')
        progress.configure(mode = 'determinate', maximum = 100, value = 0); refresh()
        rev = upd['rev']
        def work() :
            try : cmd = selfupdate.perform(rev, HERE, FROZEN, lambda d, t : q.put(('upd_prog', d, t)), lambda key : q.put(('upd_stage', key)))
            except Exception as e : q.put(('upd_failed', str(e) or type(e).__name__)); return
            q.put(('upd_ready', cmd))
        threading.Thread(target = work, daemon = True).start()
    def upd_prog(done, total) :
        upd.update(state = 'load', done = done, total = total)
        progress.configure(value = 100 * done / total if total else 0); refresh_upd()
    def upd_stage(key) : upd['state'] = key; progress.configure(value = 100); refresh_upd()
    def upd_ready(cmd) :
        upd['state'] = 'start'; refresh_upd()
        try : selfupdate.launch(cmd, HERE)
        except Exception as e : return upd_failed(str(e) or type(e).__name__)
        root.after(400, root.destroy)
    def upd_failed(err) :
        st['busy'] = False; upd.update(state = 'failed', err = err); progress.configure(value = 0); refresh()
    def set_status(key, **kw) : st['status'] = (key, kw); refresh()
    def write_log(text) :
        log.configure(state = 'normal'); log.insert('end', text); log.see('end'); log.configure(state = 'disabled')

    def start_scan() :
        st['busy'] = True; set_status('scanning'); progress.configure(mode = 'indeterminate'); progress.start(12)
        def work() :
            try : q.put(('scanned', scan(st['folder'], None)))
            except Exception : q.put(('scanned', []))
        threading.Thread(target = work, daemon = True).start()
    def scanned(models) :
        progress.stop(); progress.configure(mode = 'determinate', value = 0)
        st.update(busy = False, models = models)
        if not models : set_status('no_roms' if st['folder'] != HERE else 'need_roms')
        else : set_status('ready', n = len(models))
        if not models and st['folder'] == HERE and not st.get('asked') :
            st['asked'] = True; root.after(200, choose_folder)

    def choose_folder() :
        d = filedialog.askdirectory(title = T('pick_folder'), initialdir = str(st['folder']))
        if d : st['folder'] = Path(d); start_scan()
    def toggle_details() :
        st['details'] = not st['details']
        if st['details'] : log.grid(row = 8, column = 0, columnspan = 4, sticky = 'nsew', pady = (10, 0))
        else : log.grid_remove()
        refresh()
    def start_patch() :
        out = plugins_dir(); out.mkdir(exist_ok = True)
        files = [str(p) for _, pr, wv in st['models'] for p in pr + wv]
        args = files + ['--embed', '--out-dir', str(out)]
        me = [sys.executable] if FROZEN else [sys.executable, str(Path(__file__).resolve())]
        st.update(busy = True, total = len(st['models']), done_n = 0, finished_models = 0, running = st['models'][0][0]); open_btn.grid_remove()
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
        names = [m[0] for m in st['models']]
        # main.py reports "---- <model>: started" when a model's conversion begins and prints its log under
        # "==== <model>" when it is done (several models are converted at the same time)
        if s.startswith('---- ') and s.endswith(': started') :
            hit = [n for n in names if s[5:].startswith(n)]
            if hit : st['running'] = hit[0]
        elif s.startswith('==== ') and s != '==== summary' :
            hit = [n for n in names if s[5:].startswith(n)]
            if hit :
                st['finished_models'] = st.get('finished_models', 0) + 1
                progress.configure(value = st['finished_models'])
        else : return
        n = st.get('finished_models', 0)
        set_status('converting', model = st.get('running', names[0]).split(' ')[0], i = min(n + 1, len(names)), total = len(names))
    def finished(code) :
        st['busy'] = False; progress.configure(value = progress['maximum'])
        log_text = log.get('1.0', 'end')
        failed = [m[0].split(' ')[0] for m in st['models'] if f'  {m[0]}: FAILED' in log_text]
        if code != 0 and not failed : failed = [m[0].split(' ')[0] for m in st['models']] if len(st['models']) == 1 else ['?']
        n = len(list(plugins_dir().glob('*.dll')))
        if 'S-YXG2006LE: ' in log_text and 'written' not in log_text.split('S-YXG2006LE: ')[-1].split('\n')[0] :
            failed.append(SGP2_NAME)
        if failed : set_status('failed', models = ', '.join(failed))
        else : set_status('done', n = n)
        open_btn.grid(row = 7, column = 3, sticky = 'e', pady = (8, 0))
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
                {'scanned' : scanned, 'line' : line, 'finished' : finished, 'upd_checked' : upd_checked, 'upd_prog' : upd_prog,
                 'upd_stage' : upd_stage, 'upd_ready' : upd_ready, 'upd_failed' : upd_failed}[m[0]](*m[1:])
        except queue.Empty : pass
        root.after(80, poll)

    browse['command'] = choose_folder; det_btn['command'] = toggle_details
    patch_btn['command'] = start_patch; open_btn['command'] = open_folder; upd_btn['command'] = upd_click
    lang_box.bind('<<ComboboxSelected>>', pick_lang)
    refresh(); start_scan(); poll()
    old = os.environ.get('SXG_AFTER_UPDATE', '')
    if old : threading.Thread(target = selfupdate.after_update, args = (old, FROZEN), daemon = True).start()   # just updated
    if upd_on and selfupdate.auto_check() : root.after(1500, lambda : start_check(False))
    root.mainloop()

def option(name : str) -> str | None :
    a = sys.argv
    return a[a.index(name) + 1] if name in a and a.index(name) + 1 < len(a) else None

if __name__ == '__main__' :
    if len(sys.argv) > 1 and sys.argv[1] == '--cli' : run_cli(sys.argv[2:])
    elif len(sys.argv) > 1 and sys.argv[1] == '--selftest' :
        import dllpatch, convert, dataCRCs, template, selfupdate, main as _m
        assert (Path(dllpatch.__file__).parent / 'bitmaps').is_dir(), 'bitmaps missing'
        assert all(f.is_file() for f in ICONS), 'icons missing'
        template.check()                                    # every model's template is bundled and empty
        assert selfupdate.asset_name(1).startswith('SXG-Create-NF-Patcher-r1-'), 'selfupdate'
        if option('--selftest-out') : Path(option('--selftest-out')).write_text(f'selftest ok {VERSION}\n')    # a windowed exe prints nothing
        print('selftest ok', VERSION); sys.exit(0)
    else :
        for opt, env in (('--update-dir', 'SXG_UPDATE_DIR'), ('--update-test-version', 'SXG_UPDATE_TEST_VERSION'),
                         ('--after-update', 'SXG_AFTER_UPDATE')) :
            if option(opt) is not None : os.environ[env] = option(opt)
        if '--no-update-check' in sys.argv : os.environ['SXG_NO_UPDATE_CHECK'] = '1'
        main_window()
