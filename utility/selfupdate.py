# Self-update of the Patcher (issue #72). Standard library only (the patcher is frozen with PyInstaller).
#
# * Looking for a newer version: https://github.com/<repo>/releases/latest answers with a redirect to
#   .../releases/tag/autobuild-r<N>; no API (the REST API allows only 60 requests an hour per IP address).
# * Downloading: .../releases/download/autobuild-r<N>/SXG-Create-NF-Patcher-r<N>-<system>; only https and only the
#   hosts of GitHub (also after a redirect). Size and, when GitHub names it, the SHA-256 are checked, and the new
#   version has to pass its own `--selftest` before anything is replaced.
# * Replacing, per system: Windows puts the new exe next to the old one and the new patcher deletes the old exe once it
#   has ended (only if its name is that of an official download); Linux replaces the running binary by renaming;
#   macOS swaps the .app and the new app deletes the old one. The new version starts with
#   PYINSTALLER_RESET_ENVIRONMENT=1, otherwise a onefile app started by a onefile app would use the temporary folder
#   of its parent, which disappears when the parent ends.
# Test hooks (not for users): SXG_UPDATE_TEST_VERSION=r1 (act as that version), SXG_UPDATE_DIR=<folder> (a folder with
# release files instead of GitHub), SXG_NO_UPDATE_CHECK=1 (no check at the start; the button still works).
import sys, os, re, ssl, time, shutil, hashlib, platform, subprocess, tarfile, tempfile
import urllib.request, urllib.error
from pathlib import Path
from urllib.parse import urlparse

REPO = 'NightFright2k19/SXG-Create-NF'
BASE = 'https://github.com/' + REPO
APP = 'SXG-Create-NF-Patcher'
USER_AGENT = APP
OFFICIAL_EXE = re.compile(r'^' + re.escape(APP) + r'-r\d+-windows\.exe$')

class UpdateError(Exception) : pass

def number(version) -> int | None :
    m = re.fullmatch(r'r(\d+)', version or '')
    return int(m[1]) if m else None

def test_version() -> int | None : return number(os.environ.get('SXG_UPDATE_TEST_VERSION'))
def local_dir() -> Path | None :
    d = os.environ.get('SXG_UPDATE_DIR')
    return Path(d) if d else None
def auto_check() -> bool : return not os.environ.get('SXG_NO_UPDATE_CHECK')

def enabled(version : str, frozen : bool) -> bool :
    """The frozen patcher of a release can update itself (also a test hook makes it possible)."""
    return (frozen and number(version) is not None) or test_version() is not None or local_dir() is not None

def current(version : str) -> int | None :
    t = test_version()
    return t if t is not None else number(version)

def suffix() -> str :
    if sys.platform == 'win32' : return 'windows.exe'
    if sys.platform == 'darwin' :
        return 'macos-' + ('applesilicon' if platform.machine().lower() in ('arm64', 'aarch64') else 'intel') + '.zip'
    return 'linux.tar.gz'

def asset_name(rev : int) -> str : return f'{APP}-r{rev}-{suffix()}'
def asset_revision(name : str) -> int | None :
    m = re.fullmatch(re.escape(APP) + r'-r(\d+)-' + re.escape(suffix()), name)
    return int(m[1]) if m else None

# ---- network ------------------------------------------------------------------------------------------------------

def host_ok(host : str | None) -> bool :
    h = (host or '').lower()
    return h == 'github.com' or h.endswith('.github.com') or h.endswith('.githubusercontent.com')

class _GitHubOnly(urllib.request.HTTPRedirectHandler) :
    def redirect_request(self, req, fp, code, msg, headers, newurl) :
        u = urlparse(newurl)
        if u.scheme != 'https' or not host_ok(u.hostname) : raise UpdateError(f'redirect to {u.hostname}')
        return super().redirect_request(req, fp, code, msg, headers, newurl)

class _NoRedirect(urllib.request.HTTPRedirectHandler) :
    def redirect_request(self, *a) : return None

def context() -> ssl.SSLContext :
    ctx = ssl.create_default_context()
    if sys.platform == 'darwin' and not ctx.cert_store_stats().get('x509_ca') :      # python.org builds: no certificates
        for f in ('/etc/ssl/cert.pem', '/private/etc/ssl/cert.pem') :
            if os.path.exists(f) : ctx.load_verify_locations(f); break
    try :                                                                           # Mozilla roots in addition to the system store (#84)
        import certifi
        ctx.load_verify_locations(cafile = certifi.where())
    except Exception : pass                                                         # no certifi: system store only
    return ctx

def _why(e : BaseException) -> str : return str(getattr(e, 'reason', None) or e)

def latest_revision(timeout : float = 10) -> int | None :
    """The number N of the newest release autobuild-rN (None: no release file for this system in a test folder)."""
    d = local_dir()
    if d is not None :
        revs = [r for p in d.iterdir() if (r := asset_revision(p.name)) is not None]
        return max(revs) if revs else None
    opener = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(context = context()))
    req = urllib.request.Request(BASE + '/releases/latest', headers = {'User-Agent' : USER_AGENT}, method = 'HEAD')
    try : opener.open(req, timeout = timeout)
    except urllib.error.HTTPError as e :
        m = re.search(r'/releases/tag/autobuild-r(\d+)$', e.headers.get('Location', '') if 300 <= e.code < 400 else '')
        if m : return int(m[1])
        raise UpdateError(f'GitHub answered {e.code}')
    except (urllib.error.URLError, OSError, ssl.SSLError) as e : raise UpdateError(_why(e))
    raise UpdateError('no redirect to a release')

def expected_sha256(rev : int, name : str, timeout : float = 15) -> str | None :
    """The SHA-256 GitHub shows for the file (read from the asset list of the release; None if it cannot be found)."""
    if local_dir() is not None : return None
    try :
        req = urllib.request.Request(f'{BASE}/releases/expanded_assets/autobuild-r{rev}', headers = {'User-Agent' : USER_AGENT})
        opener = urllib.request.build_opener(_GitHubOnly, urllib.request.HTTPSHandler(context = context()))
        html = opener.open(req, timeout = timeout).read().decode('utf-8', 'replace')
    except Exception : return None
    i = html.find('/' + name + '"')
    if i < 0 : return None
    m = re.search(r'sha256:([0-9a-f]{64})', html[i : i + 4000])
    return m[1] if m else None

def download(rev : int, dest : Path, progress = lambda done, total : None) -> int :
    """Fetch the release file for this system into dest; progress(bytes_done, bytes_total or 0). Returns the size."""
    name = asset_name(rev)
    done = total = 0
    try :
        d = local_dir()
        if d is not None :
            src = d / name
            total = src.stat().st_size
            with open(src, 'rb') as f, open(dest, 'wb') as o :
                while chunk := f.read(1 << 16) :
                    o.write(chunk); done += len(chunk); progress(done, total)
        else :
            req = urllib.request.Request(f'{BASE}/releases/download/autobuild-r{rev}/{name}', headers = {'User-Agent' : USER_AGENT})
            opener = urllib.request.build_opener(_GitHubOnly, urllib.request.HTTPSHandler(context = context()))
            with opener.open(req, timeout = 30) as r, open(dest, 'wb') as o :
                total = int(r.headers.get('Content-Length') or 0)
                while chunk := r.read(1 << 16) :
                    o.write(chunk); done += len(chunk); progress(done, total)
    except UpdateError : raise
    except urllib.error.HTTPError as e : raise UpdateError(f'GitHub answered {e.code} for {name}')
    except (urllib.error.URLError, OSError, ssl.SSLError) as e : raise UpdateError(_why(e))
    if total and done != total : raise UpdateError('the download is incomplete')
    return done

def sha256_of(path : Path) -> str :
    h = hashlib.sha256()
    with open(path, 'rb') as f :
        while chunk := f.read(1 << 20) : h.update(chunk)
    return h.hexdigest()

# ---- start and replace ----------------------------------------------------------------------------------------------

def clean_env() -> dict :
    env = {k : v for k, v in os.environ.items() if not k.startswith('_PYI') and k != '_MEIPASS2'}
    env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    return env

def selftest(exe : Path, rev : int, timeout : float = 300) -> None :
    """Run `exe --selftest`: the file must start, find its parts and (a version with the option) report r<rev>."""
    out = Path(tempfile.gettempdir()) / f'sxg-selftest-{os.getpid()}-{rev}.txt'
    out.unlink(missing_ok = True)
    try :
        r = subprocess.run([str(exe), '--selftest', '--selftest-out', str(out)], env = clean_env(), stdin = subprocess.DEVNULL,
                           stdout = subprocess.DEVNULL, stderr = subprocess.DEVNULL, timeout = timeout,
                           creationflags = 0x08000000 if sys.platform == 'win32' else 0)       # CREATE_NO_WINDOW
    except subprocess.TimeoutExpired : raise UpdateError('the new version does not answer its self test')
    except OSError as e : raise UpdateError(f'the new version does not start ({_why(e)})')
    if r.returncode != 0 : raise UpdateError(f'the new version failed its self test (code {r.returncode})')
    text = out.read_text(errors = 'replace').strip() if out.exists() else ''
    out.unlink(missing_ok = True)
    if text and text.split()[-1] != f'r{rev}' : raise UpdateError(f'the downloaded file is "{text}", not r{rev}')

def _replace(src : Path, dest : Path, tries : int = 40) -> None :
    """os.replace, patiently: a virus scanner may hold a fresh file for a moment."""
    for i in range(tries) :
        try : os.replace(src, dest); return
        except PermissionError :
            if i == tries - 1 : raise
            time.sleep(0.5)

def writable(folder : Path) -> bool :
    try :
        with tempfile.NamedTemporaryFile(dir = folder, prefix = '.sxg-write-test-') : pass
        return True
    except OSError : return False

def target_folder(here : Path) -> Path :
    """Where the new version goes: next to the patcher (that is where it looks for the ROMs), else the Downloads folder."""
    if writable(here) : return here
    for d in (Path.home() / 'Downloads', Path(tempfile.gettempdir())) :
        if d.is_dir() and writable(d) : return d
    raise UpdateError(f'no folder to save the new version in ({here} is read-only)')

def perform(rev : int, here : Path, frozen : bool, progress = lambda done, total : None, stage = lambda key : None) -> list[str] :
    """Download, check and put in place version r<rev>; returns the command that starts it (see launch)."""
    if not frozen : raise UpdateError('only the patcher of a release can update itself')
    exe = Path(sys.executable).resolve()
    folder = target_folder(here)
    name = asset_name(rev)
    part = folder / ('.' + name + '.part' if sys.platform != 'win32' else APP + f'-r{rev}.download')
    try :
        download(rev, part, progress)
        stage('verify')
        want = expected_sha256(rev, name)
        if want and sha256_of(part) != want : raise UpdateError('the checksum of the download does not match')
        if sys.platform == 'win32' : return _install_windows(part, rev, folder, exe)
        if sys.platform == 'darwin' : return _install_macos(part, rev, folder, exe)
        return _install_linux(part, rev, folder, exe)
    finally :
        if part.exists() : part.unlink(missing_ok = True)

def _install_windows(part : Path, rev : int, folder : Path, exe : Path) -> list[str] :
    test = part.with_name(f'{APP}-r{rev}.part.exe')                  # an exe name, so that it can be started to test it
    os.replace(part, test)
    try :
        selftest(test, rev)
        dest = folder / asset_name(rev)
        _replace(test, dest)
    finally : test.unlink(missing_ok = True)
    return [str(dest), '--after-update', str(exe)]

def _install_linux(part : Path, rev : int, folder : Path, exe : Path) -> list[str] :
    new = folder / ('.' + APP + '.new')
    try :
        with tarfile.open(part) as t :
            members = [m for m in t.getmembers() if m.isfile() and m.name.split('/')[-1] == APP]
            if len(members) != 1 : raise UpdateError(f'{asset_name(rev)} does not hold exactly one {APP}')
            with t.extractfile(members[0]) as src, open(new, 'wb') as o : shutil.copyfileobj(src, o)
        os.chmod(new, 0o755)
        selftest(new, rev)
        os.replace(new, exe)                         # renaming over a running program is fine on Linux
    finally : new.unlink(missing_ok = True)
    return [str(exe), '--after-update', '']

def _install_macos(part : Path, rev : int, folder : Path, exe : Path) -> list[str] :
    old_app = exe.parents[2]                                         # .../<name>.app/Contents/MacOS/<exe>
    if old_app.suffix != '.app' : raise UpdateError('the patcher is not run from an app')
    work = folder / ('.' + APP + '.update')
    shutil.rmtree(work, ignore_errors = True); work.mkdir()
    try :
        r = subprocess.run(['ditto', '-x', '-k', str(part), str(work)], capture_output = True)
        if r.returncode != 0 : raise UpdateError('the download cannot be unpacked')
        new_app = work / (APP + '.app')
        selftest(new_app / 'Contents' / 'MacOS' / APP, rev)
        backup = old_app.with_name(old_app.name + '.old')
        shutil.rmtree(backup, ignore_errors = True)
        os.replace(old_app, backup)
        try : os.replace(new_app, old_app)
        except OSError : os.replace(backup, old_app); raise
    finally : shutil.rmtree(work, ignore_errors = True)
    return ['open', '-n', str(old_app), '--args', '--after-update', str(backup)]

def launch(cmd : list[str], cwd : Path) -> None :
    if sys.platform == 'win32' :
        subprocess.Popen(cmd, cwd = str(cwd), env = clean_env(), close_fds = True, stdin = subprocess.DEVNULL,
                         stdout = subprocess.DEVNULL, stderr = subprocess.DEVNULL, creationflags = 0x00000008 | 0x00000200)
    else :                                           # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP above
        subprocess.Popen(cmd, cwd = str(cwd), env = clean_env(), close_fds = True, stdin = subprocess.DEVNULL,
                         stdout = subprocess.DEVNULL, stderr = subprocess.DEVNULL, start_new_session = True)

def after_update(old : str, frozen : bool, wait : float = 40) -> None :
    """The new version (started with --after-update <old>): remove the old one as soon as it has ended."""
    if not old or not frozen : return
    p = Path(old)
    me = Path(sys.executable).resolve()
    if sys.platform == 'win32' :
        if not (OFFICIAL_EXE.match(p.name) and p.parent == me.parent and p != me) : return       # an official download only
        remove = lambda : p.unlink(missing_ok = True)
    elif sys.platform == 'darwin' :
        if not p.name.endswith('.app.old') : return
        remove = lambda : shutil.rmtree(p)
    else : return                                                    # Linux: the binary was replaced by renaming
    end = time.time() + wait
    while time.time() < end :
        try : remove(); return
        except OSError : time.sleep(0.5)                             # still running (Windows: sharing violation)
