#!/usr/bin/env python3
"""phylax - back up a Claude Code project's context (metadata, git, encrypted sessions) to your own Google Drive.
Cross-platform (macOS/Windows/Linux), stdlib only. External tools: rclone, age, git (optional)."""
import argparse, datetime, fnmatch, hashlib, json, os, re, shutil, stat as statmod, subprocess, sys, tarfile, tempfile, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HOME = Path.home()
IS_WIN = os.name == "nt"
CFG_DIR = Path(os.environ.get("APPDATA", HOME / "AppData/Roaming")) / "phylax" if IS_WIN else HOME / ".config/phylax"
CFG_FILE, STATE = CFG_DIR / "config.json", CFG_DIR / "state"
KEY_DIR = CFG_DIR  # recipient.txt (public) lives here; identity.txt (private) is created by install and must be moved off-machine
C = dict(g="\033[32m", r="\033[31m", y="\033[33m", c="\033[36m", m="\033[35m", d="\033[2m", b="\033[1m", n="\033[0m")
if IS_WIN: os.system("")  # enable ANSI in Windows Terminal/conhost

def load():
    """Config = {interval_min, projects:{name:{workdir,remote,folder,git_backup}}}. Migrates the old single-project format."""
    if not CFG_FILE.exists(): sys.exit("phylax is not configured. Run the installer or: phylax init --help")
    c = json.loads(CFG_FILE.read_text())
    if "projects" not in c:
        c = dict(interval_min=c.get("interval_min", 30), projects={c["name"]: {k: c[k] for k in ("workdir", "remote", "folder", "git_backup") if k in c}})
        save(c)
    return c

def save(c): CFG_DIR.mkdir(parents=True, exist_ok=True); CFG_FILE.write_text(json.dumps(c, indent=2))

def pick(c, name=None, one=False):
    """Select projects: --project NAME, else (one=True) the project containing cwd / the only one, else all."""
    ps = c["projects"]
    if name:
        if name not in ps: sys.exit(f"unknown project '{name}'. Known: {', '.join(ps) or 'none'}")
        return {name: ps[name]}
    if one:
        here = Path.cwd().resolve()
        m = [n for n, p in ps.items() if here == Path(p["workdir"]) or Path(p["workdir"]) in here.parents]
        if len(m) == 1: return {m[0]: ps[m[0]]}
        if len(ps) == 1: return dict(ps)
        sys.exit(f"several projects configured; pass --project NAME ({', '.join(ps)})")
    return dict(ps)

def sdir(name): return STATE / name

def proj_dir(workdir):  # Claude Code encodes the cwd by replacing every non-alphanumeric char with '-'
    return HOME / ".claude/projects" / re.sub(r"[^A-Za-z0-9]", "-", str(Path(workdir).resolve()))

def run(cmd, **kw): return subprocess.run(cmd, check=True, **kw)
def rc(*a): return ["rclone", *a, "--drive-scope", "drive.file"]

def record(name, state, dur=0):
    sdir(name).mkdir(parents=True, exist_ok=True)
    now = int(time.time())
    (sdir(name) / "status").write_text(f"{state} {now}")
    with open(sdir(name) / "history", "a") as f: f.write(f"{state} {now} {dur}\n")

def read_status(name):
    try: s, t = (sdir(name) / "status").read_text().split(); return s, int(t)
    except Exception: return None, 0

def history(name, n=30):
    try:
        return [(p[0], int(p[1]), int(p[2]) if len(p) > 2 else 0)
                for p in (l.split() for l in (sdir(name) / "history").read_text().splitlines()[-n:])]
    except Exception: return []

# ---------- commands ----------
def cmd_init(a):
    """Add or update a project."""
    CFG_DIR.mkdir(parents=True, exist_ok=True)
    c = json.loads(CFG_FILE.read_text()) if CFG_FILE.exists() else dict(interval_min=30, projects={})
    if "projects" not in c: c = load()
    if a.interval: c["interval_min"] = a.interval
    old = c["projects"].get(a.name, {})
    c["projects"][a.name] = dict(workdir=str(Path(a.dir).expanduser().resolve()), remote=a.remote or old.get("remote", "gdrive-phylax"),
                                 folder=a.folder or old.get("folder", f"{a.name}-context"), git_backup=old.get("git_backup", False),
                                 mode=a.mode or old.get("mode", "context"), exclude=a.exclude or old.get("exclude", []),
                                 max_file_mb=a.max_file_mb or old.get("max_file_mb", 200),
                                 retention={**old.get("retention", {}), **{k: v for k, v in (("daily", a.keep_daily), ("weekly", a.keep_weekly), ("monthly", a.keep_monthly)) if v is not None}})
    save(c); Path(c["projects"][a.name]["workdir"]).mkdir(parents=True, exist_ok=True)
    print(f"project '{a.name}' saved ({len(c['projects'])} total) -> {CFG_FILE}")

def cmd_projects(a):
    c = load()
    if a.action == "remove":
        if a.name not in c["projects"]: sys.exit("unknown project")
        del c["projects"][a.name]; save(c); return print(f"removed '{a.name}' from phylax (files and Drive data untouched)")
    for n, p in c["projects"].items():
        st, ts = read_status(n); print(f"{n:16} {st or 'never':6} {ago(time.time()-ts) + ' ago' if ts else '':10} {p['workdir']}  ->  {p['remote']}:{p['folder']}")

SECRET_RE = re.compile(r"(\.pem|\.key|\.p12|\.pfx|\.jks|\.kdbx|\.tfstate(\.backup)?|\.tfvars|id_rsa.*|id_ed25519.*|identity\.txt|credentials.*|\.npmrc|\.netrc)$|(^|/)\.env(\..*)?$", re.I)
SKIP_DIRS = {".git", "logs", "node_modules", "__pycache__", ".venv", "venv", ".terraform", "dist", "build", ".next", "target"}

def manifest(wd):
    files = []
    for root, dirs, fs in os.walk(wd):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for f in sorted(fs):
            if SECRET_RE.search(f): continue  # never list secret-looking files, even by name
            p = Path(root, f)
            try: st = p.stat()
            except OSError: continue
            h = hashlib.sha256(p.read_bytes()).hexdigest() if st.st_size <= 20_000_000 else None  # skip hashing huge files
            files.append(dict(path=str(p.relative_to(wd)).replace("\\", "/"), size=st.st_size, mtime=int(st.st_mtime), sha256=h))
    return dict(generated=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), files=files)

def sync_one(name, cfg, dry=False, yes=False):
    wd = Path(cfg["workdir"]); t0 = time.time(); mode = cfg.get("mode", "context")
    try:
        if not wd.exists(): raise RuntimeError(f"folder missing: {wd}")
        if dry:
            if mode in ("full", "both"): full_backup(name, cfg, dry=True)
            else: print(f"[{name}] context mode uploads only metadata + encrypted sessions (nothing to preview)")
            return True
        stage = Path(tempfile.mkdtemp())
        if mode == "context":  # readable metadata only in context mode; full/both keep Drive fully encrypted
            if (wd / "CLAUDE.md").exists(): shutil.copy(wd / "CLAUDE.md", stage / "CLAUDE.md")
            (stage / "manifest.json").write_text(json.dumps(manifest(wd), indent=1))
            pd = proj_dir(wd)
            sess = [dict(session_id=f.stem, bytes=f.stat().st_size, mtime=int(f.stat().st_mtime))
                    for f in sorted(pd.glob("*.jsonl"))] if pd.exists() else []
            (stage / "sessions-index.json").write_text(json.dumps(dict(project=pd.name, sessions=sess), indent=1))
        if cfg.get("git_backup") and (wd / ".git").exists():  # never blocks the sync
            try:
                if subprocess.run(["git", "-C", str(wd), "status", "--porcelain"], capture_output=True, text=True).stdout.strip():
                    run(["git", "-C", str(wd), "add", "-A"])
                    staged = subprocess.run(["git", "-C", str(wd), "diff", "--cached", "--name-only"], capture_output=True, text=True).stdout.split("\n")
                    bad = [f for f in staged if f and SECRET_RE.search(f)]
                    if bad: run(["git", "-C", str(wd), "reset", "-q"]); raise RuntimeError(f"refusing to auto-commit secret-looking files: {bad[:3]} (add them to .gitignore)")
                    run(["git", "-C", str(wd), "commit", "-q", "-m", f"auto-backup {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}"])
                    run(["git", "-C", str(wd), "push", "-q"])
            except Exception as e: print(f"[{name}] git backup failed (continuing): {e}")
        try: backup_one(name, cfg, force=False)
        except Exception as e: print(f"[{name}] encrypted backup failed (continuing): {e}")
        if mode in ("full", "both"):
            full_backup(name, cfg, yes=yes)
            pm = sdir(name) / "last-prune"
            if not pm.exists() or time.time() - pm.stat().st_mtime > 20 * 3600:
                try: prune_full(name, cfg); pm.write_text("")
                except Exception as e: print(f"[{name}] prune failed (continuing): {e}")
        if any(stage.iterdir()): run(rc("copy", str(stage), f"{cfg['remote']}:{cfg['folder']}"), capture_output=True)
        record(name, "ok", int(time.time() - t0)); print(f"[{name}] synced ({mode}) -> {cfg['remote']}:{cfg['folder']}"); return True
    except Exception as e:
        record(name, "fail"); print(f"[{name}] sync failed: {e}"); alert_failure(name, str(e)); return False

def cmd_sync(a):
    c = load(); ps = pick(c, a.project); ok = [sync_one(n, p, a.dry_run, a.yes) for n, p in ps.items()]
    if not a.project and not a.dry_run:  # machine-wide: Claude memory + global CLAUDE.md, once
        try: backup_global(c, force=False)
        except Exception as e: print(f"[global] encrypted backup failed (continuing): {e}")
    if not all(ok): sys.exit(1)

def encrypt_tar(paths, prefix, remote, folder, force, mark):
    rec = KEY_DIR / "recipient.txt"
    if not rec.exists(): raise RuntimeError(f"no {rec}; run the installer to create an age key")
    paths = [p for p in paths if p.exists()]
    if not paths: return
    if not force and mark.exists():
        m = mark.stat().st_mtime
        if not any(f.stat().st_mtime > m for p in paths for f in ([p] if p.is_file() else p.rglob("*")) if f.is_file()): return
    mark.parent.mkdir(parents=True, exist_ok=True)
    name = f"{prefix}--claude-backup-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.tar.gz.age"
    out = Path(tempfile.mkdtemp()) / name; start = time.time()
    p = subprocess.Popen(["age", "-R", str(rec), "-o", str(out)], stdin=subprocess.PIPE)
    with tarfile.open(fileobj=p.stdin, mode="w|gz") as tf:
        for path in paths: tf.add(path, arcname=str(path.relative_to(HOME)).replace("\\", "/"))
    p.stdin.close()
    if p.wait() != 0: raise RuntimeError("age encryption failed")
    dest = f"{remote}:{folder}/encrypted"
    run(rc("copy", str(out), dest), capture_output=True)
    subprocess.run(rc("delete", dest, "--include", f"{prefix}--*", "--min-age", "14d"), capture_output=True)
    mark.write_text(""); os.utime(mark, (start, start)); print(f"[{prefix}] encrypted backup -> {dest}/{name}")

def backup_one(name, cfg, force):
    encrypt_tar([proj_dir(cfg["workdir"])], name, cfg["remote"], cfg["folder"], force, sdir(name) / "last-backup")

def backup_global(c, force):
    first = next(iter(c["projects"].values()), None)
    if not first: return
    mem = HOME / ".claude/projects" / re.sub(r"[^A-Za-z0-9]", "-", str(HOME)) / "memory"
    encrypt_tar([mem, HOME / ".claude/CLAUDE.md"], "_global", first["remote"], "phylax-global", force, sdir("_global") / "last-backup")

def cmd_backup(a):
    c = load(); ps = pick(c, a.project)
    for n, p in ps.items(): backup_one(n, p, a.force)
    if not a.project: backup_global(c, a.force)

def cmd_restore(a):
    c = load(); ps = pick(c, a.project); to = Path(a.to).expanduser() if a.to else HOME
    targets = [(n, p["remote"], p["folder"]) for n, p in ps.items()]
    if not a.project and ps: targets.append(("_global", next(iter(ps.values()))["remote"], "phylax-global"))
    for prefix, remote, folder in targets:
        dest = f"{remote}:{folder}/encrypted"
        names = sorted(n for n in subprocess.run(rc("lsf", dest), capture_output=True, text=True).stdout.split() if n.startswith(f"{prefix}--"))
        if not names: print(f"[{prefix}] no backups found"); continue
        tmp = Path(tempfile.mkdtemp()) / "b.age"; print(f"[{prefix}] restoring {names[-1]}")
        run(rc("copyto", f"{dest}/{names[-1]}", str(tmp)), capture_output=True)
        pr = subprocess.Popen(["age", "-d", "-i", a.identity, str(tmp)], stdout=subprocess.PIPE)
        with tarfile.open(fileobj=pr.stdout, mode="r|gz") as tf:
            try: tf.extractall(to, filter="data")
            except TypeError: tf.extractall(to)
        if pr.wait() != 0: sys.exit("decryption failed (wrong key?)")
    print(f"restored into {to}")

def ago(sec):
    sec = max(0, int(sec)); return f"{sec}s" if sec < 60 else f"{sec//60}m" if sec < 3600 else f"{sec//3600}h{(sec%3600)//60:02d}m"

def cmd_status(a):
    c = load(); ps = pick(c, a.project); iv = c.get("interval_min", 30) * 60
    rows = [(n, *read_status(n)) for n in ps]; now = time.time()
    if a.json: print(json.dumps({n: dict(state=st, last=ts, age_s=int(now - ts) if ts else None) for n, st, ts in rows})); return
    if a.short:  # aggregate for the status line
        fails = [n for n, st, ts in rows if st == "fail"]; ages = [now - ts for n, st, ts in rows if ts]
        if not any(ts for _, _, ts in rows): print(f"{C['y']}☁ phylax never{C['n']}", end="")
        elif fails: print(f"{C['r']}☁ phylax ✗ {','.join(fails)[:24]}{C['n']}", end="")
        elif any(a_ > iv * 1.5 for a_ in ages) or len(ages) < len(rows): print(f"{C['y']}☁ phylax ⚠ {ago(max(ages))}{C['n']}", end="")
        else: print(f"{C['g']}☁ phylax ✓ {len(rows)}×{C['n']}{C['d']} {ago(max(ages))}{C['n']}", end="")
        return
    print(f"{C['b']}{C['c']}☁  phylax → Google Drive{C['n']}  {C['d']}{time.strftime('%H:%M:%S')}  ·  every {c.get('interval_min', 30)} min{C['n']}\n")
    blocks = "▁▂▃▄▅▆▇█"
    for n, st, ts in rows:
        age = now - ts if ts else 0
        badge = (f"{C['g']}● SYNCED" if st == "ok" and age <= iv * 1.5 else f"{C['y']}● STALE " if st == "ok" else f"{C['r']}● FAILED" if st == "fail" else f"{C['y']}● NO DATA") + C["n"]
        h = history(n); mx = max([d for s_, _, d in h if s_ == "ok"] or [1]) or 1
        spark = "".join(f"{C['r']}✗{C['n']}" if s_ == "fail" else f"{C['g']}{blocks[min(7, int(d / mx * 7))]}{C['n']}" for s_, _, d in h[-20:])
        f = int(min(age / iv, 1) * 20) if ts else 0
        print(f" {C['b']}{n:14}{C['n']} {badge}  {ago(age) + ' ago' if ts else 'never':>10}  {'█'*f}{'░'*(20-f)} {'next in ' + ago(iv - age) if ts and iv > age else 'due':>12}  {spark}")
        print(f" {'':14} {C['d']}{ps[n]['workdir']}  [{ps[n].get('mode', 'context')}]  →  {C['m']}{ps[n]['remote']}:{ps[n]['folder']}{C['n']}")

def cmd_watch(a):
    try:
        while True:
            sys.stdout.write("\033[H\033[2J"); cmd_status(argparse.Namespace(short=False, json=False, project=a.project))
            print(f"\n {C['d']}Ctrl+C to quit{C['n']}"); time.sleep(2)
    except KeyboardInterrupt: pass

def cmd_gitinit(a):
    """Create a PRIVATE GitHub repo (the user's own account) for the project folder and push the first commit."""
    full = load(); name, cfg = next(iter(pick(full, a.project, one=True).items())); wd = Path(cfg["workdir"]); g = lambda *x, **k: subprocess.run(["git", "-C", str(wd), *x], **k)
    if not (wd / ".git").exists(): run(["git", "-C", str(wd), "init", "-q", "-b", "main"])
    gi = wd / ".gitignore"
    if not gi.exists(): gi.write_text("logs/\n.DS_Store\n*.pem\n*.key\n.env*\n*.jsonl\nidentity.txt\n")
    existing = g("remote", "get-url", "origin", capture_output=True, text=True)
    if existing.returncode == 0 and not a.use_existing_remote:
        sys.exit(f"This folder is already a git repo with remote {existing.stdout.strip()}.\nphylax will NOT auto-commit/push to an existing repo unless you re-run with --use-existing-remote (it commits EVERYTHING not in .gitignore).")
    if not shutil.which("gh"): sys.exit("GitHub CLI (gh) not found: install it, run 'gh auth login', then re-run: phylax git-init")
    if subprocess.run(["gh", "auth", "status"], capture_output=True).returncode != 0: sys.exit("Not logged in to GitHub: run 'gh auth login' first")
    user = subprocess.run(["gh", "api", "user", "-q", ".login"], capture_output=True, text=True, check=True).stdout.strip()
    if not g("config", "user.name", capture_output=True, text=True).stdout.strip():
        g("config", "user.name", user); g("config", "user.email", f"{user}@users.noreply.github.com")
    # use gh's credentials (avoids the OS keychain handing git a different GitHub account)
    g("config", "--replace-all", "credential.helper", ""); g("config", "--add", "credential.helper", "!gh auth git-credential")
    repo = a.repo or f"{name}-context"
    if existing.returncode != 0:
        run(["gh", "repo", "create", f"{user}/{repo}", "--private"], capture_output=True)
        g("remote", "add", "origin", f"https://{user}@github.com/{user}/{repo}.git")
    g("add", "-A"); g("commit", "-q", "-m", "Initial context backup")
    run(["git", "-C", str(wd), "push", "-q", "-u", "origin", "main"])
    full["projects"][name]["git_backup"] = True; save(full); print(f"private repo ready: https://github.com/{user}/{repo}")

def cmd_schedule(a):
    cfg = load(); py = sys.executable; me = str(Path(__file__).resolve()); mins = cfg.get("interval_min", 30); lc = launcher()
    cmdline = [lc] if lc else [py, me]
    if sys.platform == "darwin":
        plist = HOME / "Library/LaunchAgents/com.phylax.sync.plist"; uid = os.getuid()
        if a.action == "remove":
            subprocess.run(["launchctl", "bootout", f"gui/{uid}/com.phylax.sync"], capture_output=True); plist.unlink(missing_ok=True); return print("schedule removed")
        plist.parent.mkdir(parents=True, exist_ok=True)
        plist.write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.phylax.sync</string>
<key>ProgramArguments</key><array>{"".join(f"<string>{x}</string>" for x in cmdline + ["sync"])}</array>
<key>EnvironmentVariables</key><dict><key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string></dict>
<key>StartInterval</key><integer>{mins*60}</integer><key>RunAtLoad</key><true/>
<key>StandardOutPath</key><string>{CFG_DIR}/sync.log</string><key>StandardErrorPath</key><string>{CFG_DIR}/sync.log</string>
</dict></plist>''')
        subprocess.run(["launchctl", "bootout", f"gui/{uid}/com.phylax.sync"], capture_output=True)
        run(["launchctl", "bootstrap", f"gui/{uid}", str(plist)]); print(f"scheduled every {mins} min (launchd)")
    elif IS_WIN:
        if a.action == "remove": subprocess.run(["schtasks", "/Delete", "/TN", "phylax-sync", "/F"]); return print("schedule removed")
        run(["schtasks", "/Create", "/F", "/SC", "MINUTE", "/MO", str(mins), "/TN", "phylax-sync", "/TR", " ".join(f'"{x}"' for x in cmdline + ["sync"])])
        print(f"scheduled every {mins} min (Task Scheduler)")
    else: print(f"Linux: add to crontab:  */{mins} * * * * {py} {me} sync")

def cmd_statusline(a):
    """Install the team ccstatusline config (+ Claude Code statusLine) with the phylax widget."""
    kit = Path(__file__).resolve().parent; cc = HOME / ".config/ccstatusline/settings.json"
    widget = dict(id="phylax", type="custom-command", commandPath=(f'"{launcher()}" status --short' if launcher() else f'"{sys.executable}" "{Path(__file__).resolve()}" status --short'), timeout=2000, preserveColors=True)
    if cc.exists() and not a.overwrite:
        cur = json.loads(cc.read_text())
        if not any(w.get("id") == "phylax" for l in cur.get("lines", []) for w in l): cur["lines"][0].append(widget)
        cfg = cur
    else:
        cfg = json.loads((kit / "statusline/ccstatusline.settings.json").read_text()); cfg["lines"][0].append(widget)
    if cc.exists(): shutil.copy(cc, cc.with_suffix(".bak"))
    cc.parent.mkdir(parents=True, exist_ok=True); cc.write_text(json.dumps(cfg, indent=2))
    cs = HOME / ".claude/settings.json"; s = json.loads(cs.read_text()) if cs.exists() else {}
    if "statusLine" not in s:
        s["statusLine"] = dict(type="command", command="npx -y ccstatusline@latest", padding=0)
        cs.parent.mkdir(parents=True, exist_ok=True); cs.write_text(json.dumps(s, indent=2)); print("Claude Code statusLine set")
    else: print("Claude Code statusLine already set (left unchanged)")
    print(f"ccstatusline config written: {cc}")

# ---------- alerts ----------
def notify(title, msg):
    title, msg = title.replace('"', "'").replace("'", "")[:60], msg.replace('"', "").replace("'", "")[:160]
    try:
        if sys.platform == "darwin": subprocess.run(["osascript", "-e", f'display notification "{msg}" with title "{title}"'], capture_output=True)
        elif IS_WIN:
            ps = ("[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null;"
                  "$t=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
                  f"$x=$t.GetElementsByTagName('text');$x.Item(0).AppendChild($t.CreateTextNode('{title}'))|Out-Null;$x.Item(1).AppendChild($t.CreateTextNode('{msg}'))|Out-Null;"
                  "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('phylax').Show([Windows.UI.Notifications.ToastNotification]::new($t))")
            subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True)
        elif shutil.which("notify-send"): subprocess.run(["notify-send", title, msg])
    except Exception: pass

def alert_failure(name, msg):  # at most one desktop alert per project every 6 h
    f = sdir(name) / "last-alert"
    if f.exists() and time.time() - f.stat().st_mtime < 6 * 3600: return
    sdir(name).mkdir(parents=True, exist_ok=True); f.write_text(""); notify("phylax backup failed", f"{name}: {msg}")

# ---------- full encrypted file backup ----------
FULL_SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv", ".terraform", ".next"}
EPHEMERAL_RE = re.compile(r"(^|/)(\.DS_Store|Thumbs\.db|desktop\.ini|~\$[^/]*|[^/]*\.tmp|\.~lock[^/]*)$", re.I)

def human(b):
    for u in ("B", "KB", "MB", "GB"):
        if b < 1024: return f"{b:.0f}{u}" if u == "B" else f"{b:.1f}{u}"
        b /= 1024
    return f"{b:.1f}TB"

def mt_sec(m):  # state written by older versions stores seconds; newer stores nanoseconds
    return m["mtime"] / 1e9 if m["mtime"] > 1e11 else m["mtime"]

def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""): h.update(chunk)
    return h.hexdigest()

def scan_full(wd, cfg):
    ex = cfg.get("exclude", []); cap = cfg.get("max_file_mb", 200) * 1024 * 1024; out, skipped = [], []
    for root, dirs, fs in os.walk(wd):
        dirs[:] = sorted(d for d in dirs if d not in FULL_SKIP)
        for f in sorted(fs):
            p = Path(root, f); rel = str(p.relative_to(wd)).replace("\\", "/")
            if EPHEMERAL_RE.search(rel) or any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(f, g) for g in ex): continue
            try: st = p.stat()
            except OSError: continue
            if not statmod.S_ISREG(st.st_mode): continue
            if st.st_size > cap: skipped.append((rel, st.st_size)); continue
            out.append((rel, p, st.st_size, st.st_mtime_ns))   # ns: whole-second mtimes miss rapid same-size edits
    return out, skipped

def age_encrypt(src, dst):
    subprocess.run(["age", "-R", str(KEY_DIR / "recipient.txt"), "-o", str(dst), str(src)], check=True, capture_output=True)

DEFAULT_RETENTION = dict(daily=14, weekly=8, monthly=12)

def snap_map(name):
    f = sdir(name) / "snapshots.json"
    return json.loads(f.read_text()) if f.exists() else {}

def full_backup(name, cfg, dry=False, yes=False):
    """Content-addressed encrypted objects + one encrypted snapshot index per change. Snapshots give point-in-time restore."""
    if not (KEY_DIR / "recipient.txt").exists(): raise RuntimeError("no age recipient; run the installer")
    wd = Path(cfg["workdir"]); sf = sdir(name) / "files-state.json"; state = json.loads(sf.read_text()) if sf.exists() else {}
    files, skipped = scan_full(wd, cfg); pending = []; present = {r for r, *_ in files}
    for rel, p, size, mt in files:
        old = state.get(rel); ok_obj = old and old.get("obj") == old["sha"][:40] + ".age"   # older path-hash layout => re-upload once
        if ok_obj and old["size"] == size and old["mtime"] == mt: continue
        sha = sha_file(p)
        if ok_obj and old["sha"] == sha: state[rel] = dict(old, mtime=mt); continue
        pending.append((rel, p, size, mt, sha, sha[:40] + ".age"))
    gone = [r for r in state if r not in present]; total = sum(x[2] for x in pending)
    print(f"[{name}] full backup: {len(files)} files, {len(pending)} changed ({human(total)}), {len(gone)} deleted; {len(skipped)} skipped over {cfg.get('max_file_mb', 200)}MB")
    if dry:
        for rel, _, size, *_ in pending[:25]: print(f"   + {rel}  ({human(size)})")
        if len(pending) > 25: print(f"   … and {len(pending) - 25} more")
        for r in gone[:10]: print(f"   - {r} (deleted locally; stays in older snapshots)")
        for rel, size in skipped[:5]: print(f"   ! skipped (too large): {rel} ({human(size)})")
        return
    if total > 2 * 1024 ** 3 and not yes and not sys.stdout.isatty():
        raise RuntimeError(f"upload of {human(total)} needs approval: run 'phylax sync -p {name} --yes' once")
    dest = f"{cfg['remote']}:{cfg['folder']}/files"; sdir(name).mkdir(parents=True, exist_ok=True); sent = set()
    def flush(batch):
        stage = Path(tempfile.mkdtemp()); uniq = {b[5]: b for b in batch if b[5] not in sent}   # identical content is uploaded once
        with ThreadPoolExecutor(4) as ex: list(ex.map(lambda b: age_encrypt(b[1], stage / b[5]), uniq.values()))
        if uniq: run(rc("copy", str(stage), f"{dest}/objects"), capture_output=True)
        sent.update(uniq)
        for rel, _, size, mt, sha, obj in batch: state[rel] = dict(size=size, mtime=mt, sha=sha, obj=obj)
        sf.write_text(json.dumps(state)); shutil.rmtree(stage, ignore_errors=True); print(f"   uploaded {len(uniq)} objects")
    batch, bsize = [], 0
    for item in pending:
        batch.append(item); bsize += item[2]
        if bsize >= 500 * 1024 ** 2 or len(batch) >= 400: flush(batch); batch, bsize = [], 0
    if batch: flush(batch)
    snaps = snap_map(name)
    if pending or gone or not snaps:   # new snapshot only when something changed
        live = {r: state[r] for r in present if r in state}; now = time.time(); ts = time.strftime("%Y%m%dT%H%M%S", time.gmtime(now)) + f"{int(now * 1000) % 1000:03d}Z"   # ms: two syncs in one second must not share a snapshot
        tmp = Path(tempfile.mkdtemp()); (tmp / f"{ts}.json").write_text(json.dumps(dict(generated=int(time.time()), files=live)))
        age_encrypt(tmp / f"{ts}.json", tmp / f"{ts}.json.age"); run(rc("copy", str(tmp / f"{ts}.json.age"), f"{dest}/snapshots"), capture_output=True)
        snaps[ts] = sorted({m["obj"] for m in live.values()}); (sdir(name) / "snapshots.json").write_text(json.dumps(snaps))
        for r in gone: state.pop(r, None)
        sf.write_text(json.dumps(state)); print(f"   snapshot {ts} ({len(live)} files)")

def list_snapshots(cfg):
    out = subprocess.run(rc("lsf", f"{cfg['remote']}:{cfg['folder']}/files/snapshots"), capture_output=True, text=True).stdout.split()
    return sorted(n[:-len(".json.age")] for n in out if n.endswith(".json.age"))

def retention_keep(snaps, daily, weekly, monthly):
    snaps = sorted(snaps); keep = set()
    if not snaps: return keep
    day, week, month = {}, {}, {}
    for s_ in snaps:  # later snapshots overwrite earlier ones => newest per bucket
        d = datetime.datetime.strptime(s_[:8], "%Y%m%d").date(); day[s_[:8]] = s_; week[d.isocalendar()[:2]] = s_; month[s_[:6]] = s_
    keep |= {day[k] for k in sorted(day)[-daily:]} | {week[k] for k in sorted(week)[-weekly:]} | {month[k] for k in sorted(month)[-monthly:]}
    keep.add(snaps[-1]); return keep

def prune_full(name, cfg, dry=False):
    ret = {**DEFAULT_RETENTION, **cfg.get("retention", {})}; dest = f"{cfg['remote']}:{cfg['folder']}/files"
    remote = list_snapshots(cfg); keep = retention_keep(remote, ret["daily"], ret["weekly"], ret["monthly"]); drop = [x for x in remote if x not in keep]
    print(f"[{name}] retention daily={ret['daily']} weekly={ret['weekly']} monthly={ret['monthly']}: {len(remote)} snapshots, keeping {len(keep)}, removing {len(drop)}")
    local = snap_map(name); unknown = [x for x in remote if x not in local]
    if dry:
        for x in drop[:10]: print(f"   - snapshot {x}")
    else:
        for x in drop: subprocess.run(rc("deletefile", f"{dest}/snapshots/{x}.json.age"), capture_output=True); local.pop(x, None)
        (sdir(name) / "snapshots.json").write_text(json.dumps(local))
    if unknown: return print(f"   skipping object cleanup: {len(unknown)} snapshot(s) were made elsewhere and can't be read without the private key")
    referenced = set(); [referenced.update(local.get(x, [])) for x in keep]
    sf = sdir(name) / "files-state.json"; referenced |= {m["obj"] for m in (json.loads(sf.read_text()).values() if sf.exists() else [])}
    listing = json.loads(subprocess.run(rc("lsjson", f"{dest}/objects"), capture_output=True, text=True).stdout or "[]")
    cutoff = time.time() - 24 * 3600
    def old(e):
        try: return datetime.datetime.fromisoformat(e["ModTime"].replace("Z", "+00:00")).timestamp() < cutoff
        except Exception: return False
    orphans = [e["Path"] for e in listing if e["Path"] not in referenced and old(e)]
    print(f"   {len(orphans)} unreferenced objects (older than 24h) {'would be ' if dry else ''}deleted")
    if orphans and not dry:
        lf = Path(tempfile.mkdtemp()) / "del.txt"; lf.write_text("\n".join(orphans))
        subprocess.run(rc("delete", f"{dest}/objects", "--files-from", str(lf)), capture_output=True)

def cmd_prune(a):
    c = load()
    for n, p in pick(c, a.project).items():
        if p.get("mode", "context") in ("full", "both"): prune_full(n, p, a.dry_run)

def cmd_restore_files(a):
    c = load(); name, cfg = next(iter(pick(c, a.project, one=True).items()))
    dest = f"{cfg['remote']}:{cfg['folder']}/files"; to = Path(a.to).expanduser().resolve() if a.to else HOME / "phylax-restore" / name
    wd = Path(cfg["workdir"]).resolve(); snaps = list_snapshots(cfg)
    if not snaps: sys.exit("no snapshots found for this project")
    if a.snapshots:
        for x in snaps: print(f"  {x[:4]}-{x[4:6]}-{x[6:8]} {x[9:11]}:{x[11:13]} UTC   ({x})")
        return
    if a.at:
        cut = (a.at.replace("-", "") + "T235959Z") if len(a.at) == 10 else a.at
        cand = [x for x in snaps if x <= cut]
        if not cand: sys.exit(f"no snapshot on or before {a.at}; oldest is {snaps[0]}")
        pick_snap = cand[-1]
    else: pick_snap = snaps[-1]
    if (to == wd or wd in to.parents) and not a.force: sys.exit(f"refusing to restore into the original folder ({to}); pick another --to or pass --force")
    tmp = Path(tempfile.mkdtemp()); run(rc("copyto", f"{dest}/snapshots/{pick_snap}.json.age", str(tmp / "index.age")), capture_output=True)
    index = json.loads(subprocess.run(["age", "-d", "-i", a.identity, str(tmp / "index.age")], capture_output=True, check=True).stdout)["files"]
    sel = {r: m for r, m in index.items() if not a.match or a.match.lower() in r.lower()}
    print(f"snapshot {pick_snap}: {len(sel)} of {len(index)} files match" + ("" if a.list else f" -> restoring into {to}"))
    if a.list:
        for r, m in sorted(sel.items()): print(f"  {r}  ({human(m['size'])}, {time.strftime('%Y-%m-%d', time.localtime(mt_sec(m)))})")
        return
    (tmp / "list").write_text("\n".join(sorted({m["obj"] for m in sel.values()}))); stage = tmp / "dl"
    run(rc("copy", f"{dest}/objects", str(stage), "--files-from", str(tmp / "list")), capture_output=True)
    for rel, m in sel.items():
        out = (to / rel).resolve()
        if to not in out.parents: print(f"skipped unsafe path: {rel}"); continue
        out.parent.mkdir(parents=True, exist_ok=True)
        run(["age", "-d", "-i", a.identity, "-o", str(out), str(stage / m["obj"])], capture_output=True); os.utime(out, (mt_sec(m), mt_sec(m)))
    print(f"restored {len(sel)} files into {to}")

# ---------- helpers: bulk add, recovery key, doctor ----------
def cmd_discover(a):
    for d in sorted(Path(a.parent).expanduser().iterdir()):
        if d.is_dir() and not d.name.startswith("."): print(d.name)

def cmd_addrecipient(a):
    if not a.key.startswith("age1"): sys.exit("that doesn't look like an age public key (starts with age1…)")
    f = KEY_DIR / "recipient.txt"; cur = f.read_text().split() if f.exists() else []
    if a.key in cur: return print("already a recipient")
    f.write_text("\n".join(cur + [a.key]) + "\n"); print(f"added recovery recipient ({len(cur) + 1} total). New backups are readable by all recipients; older archives are not.")

def cmd_doctor(a):
    good = lambda m, h=None: print(f" {C['g']}✓{C['n']} {m}"); warn = lambda m, h: print(f" {C['y']}!{C['n']} {m}\n    → {h}"); bad = lambda m, h: print(f" {C['r']}✗{C['n']} {m}\n    → {h}")
    for t, req in (("rclone", True), ("age", True), ("git", False)):
        if shutil.which(t): good(f"{t} found")
        else: (bad if req else warn)(f"{t} missing", f"install {t}")
    rec = KEY_DIR / "recipient.txt"
    if rec.exists(): n = len(rec.read_text().split()); good(f"{n} encryption recipient(s)") if n > 1 else warn("only 1 encryption recipient", "add an IT recovery key: phylax add-recipient age1…")
    else: bad("no encryption recipient", "re-run the installer")
    if (KEY_DIR / "identity.txt").exists(): warn("private key file is still on this machine", "save it in your password manager, then delete it (the backup only needs the public recipient)")
    try: c = load()
    except SystemExit: return bad("not configured", "run the installer")
    for r in sorted({p["remote"] for p in c["projects"].values()}):
        t = subprocess.run(rc("lsf", f"{r}:", "--max-depth", "1"), capture_output=True, text=True, timeout=60)
        good(f"Google Drive remote '{r}' reachable") if t.returncode == 0 else bad(f"remote '{r}' failed: {t.stderr.strip()[:90]}", f"re-authorize: rclone config reconnect {r}:")
    for n, p in c["projects"].items():
        (good if Path(p["workdir"]).exists() else bad)(f"[{n}] folder {p['workdir']}" + ("" if Path(p["workdir"]).exists() else " is missing"), "fix the path: phylax init --name … --dir …")
        st, ts = read_status(n); age = time.time() - ts if ts else None
        if st == "fail": bad(f"[{n}] last sync failed", f"run: phylax sync -p {n}")
        elif age is None: warn(f"[{n}] never synced", f"run: phylax sync -p {n}")
        elif age > c.get("interval_min", 30) * 60 * 3: warn(f"[{n}] last success {ago(age)} ago", "is the schedule installed? phylax schedule install")
        else: good(f"[{n}] synced {ago(age)} ago ({p.get('mode', 'context')})")
    sch = (subprocess.run(["launchctl", "list", "com.phylax.sync"], capture_output=True).returncode == 0) if sys.platform == "darwin" else (subprocess.run(["schtasks", "/Query", "/TN", "phylax-sync"], capture_output=True).returncode == 0) if IS_WIN else None
    if sch is not None: good("background schedule installed") if sch else bad("background schedule NOT installed", "phylax schedule install")
    free = shutil.disk_usage(HOME).free; good(f"disk free {human(free)}") if free > 5 * 1024 ** 3 else warn(f"low disk space ({human(free)})", "free some space")


# ---------- distribution helpers ----------
KIT = Path(__file__).resolve().parent

def launcher():
    """Stable absolute path of the `phylax` command if it is on PATH (survives brew/scoop upgrades), else None."""
    p = shutil.which("phylax"); return str(Path(p)) if p else None

def cmd_version(a):
    v = (KIT / "VERSION").read_text().strip() if (KIT / "VERSION").exists() else "unknown"; print(f"phylax {v}")

def cmd_setup(a):
    if IS_WIN: sys.exit(subprocess.call(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(KIT / "install.ps1")]))
    sys.exit(subprocess.call(["bash", str(KIT / "install.sh")]))

def cmd_menu(a):
    if IS_WIN: sys.exit(subprocess.call(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(KIT / "phylax.ps1")]))
    sys.exit(subprocess.call(["bash", str(KIT / "phylax.sh")]))

def cmd_update(a):
    repo = (KIT / "REPO").read_text().strip() if (KIT / "REPO").exists() else "agentnetes/phylax"
    if "/opt/homebrew" in str(KIT) or "/Cellar/" in str(KIT): sys.exit("installed with Homebrew: run  brew upgrade phylax")
    if "scoop" in str(KIT).lower(): sys.exit("installed with Scoop: run  scoop update phylax")
    base = f"https://github.com/{repo}/releases/latest/download"
    if IS_WIN: sys.exit(subprocess.call(["powershell", "-NoProfile", "-Command", f"$env:PHYLAX_NO_SETUP='1'; irm {base}/bootstrap.ps1 | iex"]))
    sys.exit(subprocess.call(["bash", "-c", f"PHYLAX_NO_SETUP=1 curl -fsSL {base}/bootstrap.sh | bash"]))


def main():
    p = argparse.ArgumentParser(prog="phylax", description="Back up Claude Code project context to your own Google Drive. Multi-project.")
    sp = p.add_subparsers(dest="cmd", required=True)
    def proj(x): x.add_argument("-p", "--project", help="project name (default: all, or the one containing the current folder where noted)"); return x
    i = sp.add_parser("init", help="add/update a project"); i.add_argument("--name", required=True); i.add_argument("--dir", required=True)
    i.add_argument("--remote"); i.add_argument("--folder"); i.add_argument("--interval", type=int)
    i.add_argument("--mode", choices=["context", "full", "both"], help="context=metadata+encrypted sessions (default); full=encrypted copy of all files; both"); i.add_argument("--exclude", action="append", help="glob to skip in full mode (repeatable)"); i.add_argument("--max-file-mb", type=int)
    i.add_argument("--keep-daily", type=int, help="daily snapshots to keep (default 14)"); i.add_argument("--keep-weekly", type=int, help="weekly (default 8)"); i.add_argument("--keep-monthly", type=int, help="monthly (default 12)"); i.set_defaults(f=cmd_init)
    pj = sp.add_parser("projects", help="list or remove projects"); pj.add_argument("action", nargs="?", choices=["list", "remove"], default="list"); pj.add_argument("name", nargs="?"); pj.set_defaults(f=cmd_projects)
    sy = proj(sp.add_parser("sync")); sy.add_argument("--dry-run", action="store_true", help="full mode: show what would upload"); sy.add_argument("--yes", action="store_true", help="approve a large (>2GB) upload"); sy.set_defaults(f=cmd_sync)
    b = proj(sp.add_parser("backup")); b.add_argument("--force", action="store_true"); b.set_defaults(f=cmd_backup)
    r = proj(sp.add_parser("restore")); r.add_argument("--identity", required=True); r.add_argument("--to"); r.set_defaults(f=cmd_restore)
    st = proj(sp.add_parser("status")); st.add_argument("--short", action="store_true"); st.add_argument("--json", action="store_true"); st.set_defaults(f=cmd_status)
    proj(sp.add_parser("watch")).set_defaults(f=cmd_watch)
    rf = proj(sp.add_parser("restore-files", help="restore full-backup files (never over the original unless --force)")); rf.add_argument("--identity", required=True)
    rf.add_argument("--at", help="restore the state as of this date (YYYY-MM-DD)"); rf.add_argument("--snapshots", action="store_true", help="list available restore points"); rf.add_argument("--to"); rf.add_argument("--match", help="only paths containing this text"); rf.add_argument("--list", action="store_true"); rf.add_argument("--force", action="store_true"); rf.set_defaults(f=cmd_restore_files)
    pr = proj(sp.add_parser("prune", help="apply retention now (full mode)")); pr.add_argument("--dry-run", action="store_true"); pr.set_defaults(f=cmd_prune)
    sp.add_parser("version").set_defaults(f=cmd_version)
    sp.add_parser("setup", help="interactive first-time setup").set_defaults(f=cmd_setup)
    sp.add_parser("menu", help="interactive menu").set_defaults(f=cmd_menu)
    sp.add_parser("update", help="update phylax").set_defaults(f=cmd_update)
    sp.add_parser("doctor", help="check everything and say what to fix").set_defaults(f=cmd_doctor)
    ar = sp.add_parser("add-recipient", help="add a recovery public key (age1…)"); ar.add_argument("key"); ar.set_defaults(f=cmd_addrecipient)
    ds = sp.add_parser("discover", help="list subfolders of a folder (for bulk add)"); ds.add_argument("parent"); ds.set_defaults(f=cmd_discover)
    gi = proj(sp.add_parser("git-init")); gi.add_argument("--repo"); gi.add_argument("--use-existing-remote", action="store_true"); gi.set_defaults(f=cmd_gitinit)
    sc = sp.add_parser("schedule"); sc.add_argument("action", choices=["install", "remove"]); sc.set_defaults(f=cmd_schedule)
    sl = sp.add_parser("statusline"); sl.add_argument("--overwrite", action="store_true"); sl.set_defaults(f=cmd_statusline)
    a = p.parse_args(); a.f(a)

if __name__ == "__main__": main()
