"""The PadMint window: a page in the player's web browser, served by this computer.

It serves only on 127.0.0.1 with a random token, uses the Python standard library,
and makes copies by running "python -m padmint make", so the window can never do more
than the terminal. Nothing is uploaded.
"""
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
import webbrowser

from . import __version__, cli, tools
from .manifest import catalog
from .say import LANGUAGES, MESSAGES, language, localized, phrase

ROOT = Path(__file__).resolve().parent.parent


def strings(lang):
    return {key[2:]: value.get(lang, value["en"]) for key, value in MESSAGES.items() if key.startswith("w_")}


def player_data(lang):
    """Everything the page shows before a build: games, devices and game files found."""
    folder = cli.player_folder()
    games = []
    for game, name, platforms in cli.player_games():
        entry = catalog()[game]
        needs_file = entry.get("player_game_file", "build") != "in-app"
        files = cli.game_files(folder, entry.get("manifest")) if needs_file else []
        games.append({"id": game, "name": name, "needs_file": needs_file,
                      "about": entry.get("game") or (entry.get("manifest") or {}).get("game", ""),
                      "formats": sorted({f.upper() for item in (entry.get("manifest") or {}).get("inputs", [])
                                         for f in item.get("formats", [])}),
                      "ids": entry.get("game_ids") or [],
                      "platforms": [{"id": p, "label": cli.platform_label(p, lang),
                                     "short": phrase(f"w_short_{p}", lang) if f"w_short_{p}" in MESSAGES else p}
                                    for p in platforms],
                      "files": [str(path) for path in files[:8]],
                      "ready": ({"text": localized(entry["ready_to_play"], "text", lang),
                                 "url": entry["ready_to_play"]["url"]} if entry.get("ready_to_play") else None),
                      "issues": entry["repo_url"] + "/issues"})
    apps = [] if cli.on_android() else [
        {"id": app, "name": name, "intro": phrase("download_intro", lang, name=name).strip(),
         "steps": localized(catalog()[app]["download"], "steps", lang),
         "guide": catalog()[app].get("player_help") or catalog()[app]["repo_url"]}
        for app, name in cli.downloads()]
    return {"lang": lang, "version": __version__, "folder": str(folder),
            "saved_in": phrase("saved_in", lang, folder=folder), "games": games, "downloads": apps,
            "text": strings(lang), "picker": not cli.on_android(), "reveal": not cli.on_android()}


def plan(game, platform_name, lang):
    """What a build will do on this computer, before it starts: what it downloads and from
    where, how big, what the player installs first, and where the copy goes. Read from the
    catalog's copy of the game's recipe, so sizes are close, not exact."""
    entry = catalog()[game]
    manifest = entry.get("manifest") or {}
    target = (manifest.get("targets") or {}).get(platform_name) or {}
    host, table = cli.host_id(), tools.lock()
    any_host = bool(target.get("ios_module"))
    items = []
    for name in tools._with_companions([n for n in target.get("tools", []) if n in table], host, table, any_host):
        download = tools.host_entry(table[name], host, any_host)
        if download:
            items.append({"name": name, "version": tools.version(table[name], host), "size": download.get("size"),
                          "source": urlparse(download["url"]).hostname, "here": tools.installed(name, host)})
    needs = [{"label": cli.label(tool), "ok": cli.check_program(tool)[0], "note": tool.get("note", "")}
             for tool in cli.player_requirements(manifest)]
    name = manifest.get("name") or entry.get("name", game)
    key = f"w_output_{platform_name}"
    return {"repo": entry["repo_url"], "tools": items, "tools_folder": str(tools.tools_root()),
            "app": bool(target.get("published_app")), "space_gb": entry.get("free_space_gb"),
            "folder": str(cli.player_folder()), "needs": needs,
            "output": phrase(key, lang, name=name) if key in MESSAGES else ""}


PHASES = ("release", "source", "tools", "app", "build", "save")


def phases(events, code):
    """The build's phases from make's events file, as the page shows them."""
    found, tool_list, stage = {}, {}, None
    for line in events:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        kind = event.pop("phase", None)
        if kind in PHASES:
            found.setdefault(kind, {}).update(event)
        elif kind == "tool" and event.get("name"):
            tool_list.setdefault(event["name"], {}).update(event)
        elif kind == "stage":
            stage = event
    if code is not None and code != 0:
        for value in found.values():
            if value.get("state") == "running":
                value["state"] = "cancelled" if code == 130 else "failed"
    result = [dict(found[name], id=name) for name in PHASES if name in found]
    return result, list(tool_list.values()), stage


def pick_file(title, folder):
    """The system's own Open dialog: the chosen path, None if cancelled, False if there is none."""
    env = dict(os.environ, PADMINT_PICK_TITLE=title, PADMINT_PICK_FOLDER=str(folder))
    if sys.platform == "darwin":
        argv = ["osascript", "-e", 'POSIX path of (choose file with prompt (system attribute '
                '"PADMINT_PICK_TITLE") default location (POSIX file (system attribute "PADMINT_PICK_FOLDER")))']
    elif os.name == "nt":
        argv = ["powershell", "-NoProfile", "-STA", "-Command",
                "Add-Type -AssemblyName System.Windows.Forms;"
                "$f = New-Object System.Windows.Forms.Form -Property @{TopMost=$true};"
                "$d = New-Object System.Windows.Forms.OpenFileDialog;"
                "$d.Title = $env:PADMINT_PICK_TITLE; $d.InitialDirectory = $env:PADMINT_PICK_FOLDER;"
                "if ($d.ShowDialog($f) -eq 'OK') { [Console]::OutputEncoding = [Text.Encoding]::UTF8;"
                " [Console]::Write($d.FileName) }"]
    elif shutil.which("zenity"):
        argv = ["zenity", "--file-selection", "--title", title, "--filename", str(folder) + os.sep]
    elif shutil.which("kdialog"):
        argv = ["kdialog", "--getopenfilename", str(folder)]
    else:
        return False
    try:
        result = subprocess.run(argv, capture_output=True, env=env)
    except OSError:
        return False
    path = result.stdout.decode("utf-8", "replace").strip()
    return path if result.returncode == 0 and path else None


def check_file(game, path, lang):
    """None when the file can be used for game, else why not, in the player's words."""
    disc = cli.dropped_path(path)
    if not disc.is_file():
        return phrase("no_file", lang, path=disc)
    problem = cli.file_problem(disc)
    if problem:
        return problem
    # A player may pick the game's app (an APK or IPA) or a ZIP instead of the game file.
    manifest = catalog()[game].get("manifest") or {}
    formats = sorted({name for item in manifest.get("inputs", []) for name in item.get("formats", [])})
    if formats and disc.suffix.lower().lstrip(".") not in formats:
        return phrase("w_not_game_file", lang, file=disc.name, name=manifest.get("name", game),
                      formats=", ".join(name.upper() for name in formats))
    found = cli.game_from_file(disc, cli.player_games(), io.StringIO())
    if found and game not in found:
        name = (catalog()[game].get("manifest") or {}).get("name", game)
        return phrase("w_wrong_game", lang, name=name)
    return None


class Builds:
    """At most one copy made from the window at a time."""

    def __init__(self):
        self.lock = threading.Lock()
        self.process = self.log = self.job = self.events = None

    def start(self, game, platform_name, disc, lang):
        with self.lock:
            if self.process and self.process.poll() is None:
                raise ValueError("A build is already running")
            folder = Path(tempfile.mkdtemp(prefix="padmint-window-"))
            self.log = folder / "output.log"
            argv = [sys.executable, "-m", "padmint", "make", game, platform_name,
                    "--out", str(cli.player_folder()), "--result-file", str(folder / "result.json")]
            if disc:
                argv += ["--disc", str(disc)]
            self.events = folder / "events.jsonl"
            env = dict(os.environ, PADMINT_LANG=lang, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1",
                       PADMINT_EVENTS=str(self.events))
            # Its own process group, so Cancel (Ctrl-Break on Windows) reaches only the build.
            group = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
                     else {"start_new_session": True})
            with self.log.open("wb") as stream:
                self.process = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=stream,
                                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, **group)
            self.job = {"game": game, "platform": platform_name, "lang": lang, "folder": folder,
                        "device": cli.platform_label(platform_name, lang),
                        "started": time.time(), "result": None}

    def status(self, lang=None):
        """The build as the page shows it, in lang (the page's language now; the build's
        own messages stay in the language it started in)."""
        if self.process is None:
            return {"state": "idle"}
        job, code = self.job, self.process.poll()
        lines = self.log.read_text("utf-8", "replace").splitlines() if self.log.exists() else []
        step = "tools"
        header = phrase("step_build", job["lang"], jobs=0).strip().split(":")[0]
        if any(line.startswith(header) for line in lines):
            step = "build"
        # The newest line that says something: skip the "still running" heartbeat.
        now = next((line.strip() for line in reversed(lines)
                    if line.strip() and "build_progress:" not in line), "")
        state = {None: "running", 0: "done", 130: "cancelled"}.get(code, "failed")
        events = (self.events.read_text("utf-8", "replace").splitlines()
                  if self.events and self.events.exists() else [])
        found, tool_list, stage = phases(events, code)
        reply = {"state": state, "step": "done" if code == 0 else step, "now": now[-200:], "game": job["game"],
                 "device": job.get("device", ""), "elapsed": int(time.time() - job["started"]), "tail": lines[-60:],
                 "lines": len(lines), "exit_code": code, "phases": found, "tools": tool_list, "stage": stage}
        if code == 0:
            reply["result"] = self.result(lang)
        reply["device"] = cli.platform_label(job["platform"], lang) if lang else reply["device"]
        return reply

    def result(self, lang=None):
        job = self.job
        lang = lang or job["lang"]
        job.setdefault("results", {})
        if lang not in job["results"]:
            try:
                built = Path(json.loads((job["folder"] / "result.json").read_text())["file"])
            except (OSError, ValueError, KeyError):
                built = None
            steps, note, guide = cli.next_step_text(catalog()[job["game"]], job["platform"], built, lang)
            entry = catalog()[job["game"]]
            name = (entry.get("manifest") or {}).get("name") or entry.get("name", job["game"])
            key = f"w_output_{job['platform']}"
            job["results"][lang] = {"file": str(built) if built else None, "steps": steps, "note": note,
                                    "guide": guide, "private": phrase("keep_private", lang),
                                    "about": phrase(key, lang, name=name) if key in MESSAGES else ""}
        return job["results"][lang]

    def cancel(self):
        if self.process and self.process.poll() is None:
            # PadMint cancels and keeps finished work.
            self.process.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGINT)

    def reveal(self):
        if self.process and self.process.poll() == 0 and self.result()["file"]:
            cli.reveal(Path(self.result()["file"]))


def make_handler(token, builds):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def reply(self, code, body, kind="application/json"):
            data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline'")
            self.end_headers()
            self.wfile.write(data)

        def allowed(self):
            query = parse_qs(urlparse(self.path).query)
            supplied = self.headers.get("X-PadMint-Token") or query.get("token", [""])[0]
            host = (self.headers.get("Host") or "").split(":")[0]
            return host in ("127.0.0.1", "localhost") and secrets.compare_digest(supplied, token)

        def lang(self, form=None):
            chosen = (form or {}).get("lang") or parse_qs(urlparse(self.path).query).get("lang", [""])[0]
            return chosen if chosen in LANGUAGES else language()

        def do_GET(self):
            if not self.allowed():
                return self.reply(403, {"error": "Open the address printed in the PadMint window"})
            route = urlparse(self.path).path
            if route == "/":
                data = json.dumps(player_data(self.lang())).replace("</", "<\\/")
                return self.reply(200, PAGE.replace("__TOKEN__", token).replace("__DATA__", data),
                                  "text/html; charset=utf-8")
            if route == "/api/player":
                return self.reply(200, player_data(self.lang()))
            if route == "/api/build":
                return self.reply(200, builds.status(self.lang()))
            if route == "/api/plan":
                query = parse_qs(urlparse(self.path).query)
                game, platform_name = query.get("game", [""])[0], query.get("platform", [""])[0]
                if not any(id_ == game and platform_name in platforms
                           for id_, _name, platforms in cli.player_games()):
                    return self.reply(400, {"error": "That game cannot be made for that device on this computer"})
                return self.reply(200, plan(game, platform_name, self.lang()))
            return self.reply(404, {"error": "not found"})

        def do_POST(self):
            if not self.allowed():
                return self.reply(403, {"error": "forbidden"})
            try:
                length = min(int(self.headers.get("Content-Length") or 0), 65536)
                form = json.loads(self.rfile.read(length) or b"{}")
                route, lang = urlparse(self.path).path, self.lang(form)
                if route == "/api/pick":
                    path = pick_file(phrase("w_file", lang), cli.player_folder())
                    return self.reply(200, {"path": path or None, "available": path is not False})
                if route == "/api/file":
                    return self.reply(200, {"problem": check_file(form["game"], form["path"], lang)})
                if route == "/api/make":
                    game, platform_name = form["game"], form["platform"]
                    if not any(id_ == game and platform_name in platforms
                               for id_, _name, platforms in cli.player_games()):
                        raise ValueError("That game cannot be made for that device on this computer")
                    disc = cli.dropped_path(form["path"]).resolve() if form.get("path") else None
                    builds.start(game, platform_name, disc, lang)
                    return self.reply(200, builds.status())
                if route == "/api/cancel":
                    builds.cancel()
                    return self.reply(200, builds.status())
                if route == "/api/reveal":
                    builds.reveal()
                    return self.reply(200, {})
                return self.reply(404, {"error": "not found"})
            except (KeyError, ValueError, OSError) as error:
                return self.reply(400, {"error": str(error)})

    return Handler


def serve(port=0, open_browser=True):
    token = secrets.token_urlsafe(24)
    builds = Builds()
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(token, builds))
    url = f"http://127.0.0.1:{server.server_address[1]}/?token={token}"
    print(phrase("w_open", language(), version=__version__, url=url), flush=True)
    if open_browser:
        if cli.on_android():  # the phone's browser, through Termux
            subprocess.run([str(cli.TERMUX_OPEN_URL), url], check=False)
        else:
            webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        builds.cancel()
        server.server_close()
    return 0


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>PadMint</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root{--bg:#0f1714;--panel:#16211d;--panel2:#1c2a25;--line:#2a3c35;--text:#e8f1ec;--muted:#9db3a9;--mint:#3ddc97;--mint2:#1fa572;--bad:#ff7a7a;--warn:#f5c56b;
 font-family:-apple-system,"Segoe UI",Roboto,system-ui,sans-serif;color-scheme:dark}
@media (prefers-color-scheme:light){:root{--bg:#f3f7f5;--panel:#fff;--panel2:#eef5f1;--line:#d6e3dc;--text:#14211c;--muted:#5a6f66;--mint:#14945f;--mint2:#0f7a4e;--bad:#c62828;--warn:#9a6700;color-scheme:light}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);line-height:1.5}
a{color:var(--mint)}.wrap{max-width:860px;margin:0 auto;padding:1.4rem 1.2rem 3rem}
header{display:flex;justify-content:space-between;align-items:center;gap:1rem;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:.7rem}.brand h1{margin:0;font-size:1.6rem;letter-spacing:-.02em}
.brand .v{color:var(--muted);font-size:.85rem}.mark{width:38px;height:38px;border-radius:11px;background:linear-gradient(135deg,var(--mint),var(--mint2));display:grid;place-items:center}
.mark svg{width:22px;height:22px}
select,input{font:inherit;color:var(--text);background:var(--panel2);border:1px solid var(--line);border-radius:9px;padding:.55rem .7rem}
.hero{margin:1.4rem 0 1rem}.hero p{margin:.2rem 0 .8rem;font-size:1.08rem}
.chips{display:flex;gap:.5rem;flex-wrap:wrap}.chip{font-size:.85rem;color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:.2rem .7rem}
.chip:before{content:"✓ ";color:var(--mint)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:1.1rem 1.2rem;margin:1rem 0}
.card h2{margin:0 0 .7rem;font-size:1.1rem}.muted{color:var(--muted)}.small{font-size:.88rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:.6rem}
.pick{text-align:left;background:var(--panel2);border:1px solid var(--line);border-radius:11px;padding:.7rem .8rem;color:var(--text);cursor:pointer;font:inherit}
.pick:hover{border-color:var(--mint)}.pick.on{border-color:var(--mint);box-shadow:0 0 0 2px color-mix(in srgb,var(--mint) 35%,transparent)}
.pick b{display:block}.pick span{display:block;color:var(--muted);font-size:.82rem;margin-top:.15rem}
.tags{margin-top:.4rem;display:flex;gap:.3rem;flex-wrap:wrap}.tag{font-size:.72rem;border-radius:6px;padding:.05rem .4rem;background:color-mix(in srgb,var(--mint) 16%,transparent);color:var(--mint)}
.sub{margin:1rem 0 .5rem;font-size:.9rem;color:var(--muted);font-weight:600}
.list{display:flex;flex-direction:column;border:1px solid var(--line);border-radius:11px;overflow:hidden}
.item{display:grid;grid-template-columns:1fr auto;gap:.2rem .8rem;align-items:center;text-align:left;background:var(--panel2);border:0;border-bottom:1px solid var(--line);padding:.6rem .85rem;color:var(--text);cursor:pointer;font:inherit}
.item:last-child{border-bottom:0}.item:hover{background:color-mix(in srgb,var(--mint) 10%,var(--panel2))}
.item.on{background:color-mix(in srgb,var(--mint) 18%,var(--panel2));box-shadow:inset 3px 0 0 var(--mint)}
.item .t{font-weight:650}.item .s{color:var(--muted);font-size:.83rem;grid-column:1}.item .tags{grid-row:1/span 2;grid-column:2;margin:0;justify-content:flex-end}
.filters{display:flex;gap:.35rem;flex-wrap:wrap;margin:.2rem 0 .6rem}.filter{font:inherit;font-size:.82rem;border-radius:999px;padding:.2rem .7rem;border:1px solid var(--line);background:transparent;color:var(--muted);cursor:pointer}
.filter.on{background:var(--mint);border-color:var(--mint);color:#06281a;font-weight:600}
#search{width:100%;max-width:none;font-size:1rem;padding:.65rem .8rem}
button.btn{font:inherit;border-radius:10px;padding:.6rem 1.1rem;border:1px solid var(--line);background:var(--panel2);color:var(--text);cursor:pointer}
button.btn:hover{border-color:var(--mint)}button.main{background:var(--mint);border-color:var(--mint);color:#06281a;font-weight:700;font-size:1.05rem;padding:.75rem 1.4rem}
a.btn{display:inline-block;text-decoration:none;border-radius:10px;padding:.65rem 1.2rem}a.main{background:var(--mint);color:#06281a;font-weight:700}
.tag.ready{background:var(--mint);color:#06281a;font-weight:600}
button:disabled{opacity:.45;cursor:default}.row{display:flex;gap:.6rem;flex-wrap:wrap;align-items:center}
.file{display:flex;justify-content:space-between;gap:.6rem;width:100%;margin:.3rem 0}.file b{overflow-wrap:anywhere}
.state{margin:.6rem 0 0;font-weight:600}.ok{color:var(--mint)}.bad{color:var(--bad)}.warn{color:var(--warn)}
details summary{cursor:pointer;color:var(--muted)}
.plan ol{margin:.2rem 0 .4rem;padding-left:1.3rem}.plan li{margin:.35rem 0;overflow-wrap:anywhere}
.tools{list-style:none;padding:0;margin:.3rem 0}.tools li{display:flex;justify-content:space-between;gap:.8rem;border-bottom:1px dashed var(--line);padding:.25rem 0;font-size:.9rem}
.out{background:var(--panel2);border-radius:10px;padding:.6rem .8rem;margin:.6rem 0}
.hidden{display:none!important}
.steps{list-style:none;margin:0;padding:0}.steps li{display:grid;grid-template-columns:1.8rem 1fr;gap:.5rem;padding:.55rem 0;border-bottom:1px solid var(--line)}
.ico{width:1.4rem;height:1.4rem;border-radius:50%;display:grid;place-items:center;font-size:.8rem;border:2px solid var(--line);margin-top:.1rem}
.done .ico{background:var(--mint);border-color:var(--mint);color:#06281a}.running .ico{border-color:var(--mint);border-top-color:transparent;animation:spin 1s linear infinite}
.failed .ico{border-color:var(--bad);color:var(--bad)}.cancelled .ico{color:var(--muted)}@keyframes spin{to{transform:rotate(360deg)}}
.pending{color:var(--muted)}.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.78rem}.detail{font-size:.86rem;color:var(--muted);overflow-wrap:anywhere}
.bar{height:6px;background:var(--panel2);border-radius:99px;overflow:hidden;margin:.35rem 0 .1rem}.bar i{display:block;height:100%;background:var(--mint);width:0}
pre{background:#0a0f0d;color:#cfe3d8;border-radius:10px;padding:.8rem;white-space:pre-wrap;max-height:22rem;overflow:auto;font-size:.8rem;margin:.6rem 0}
.big{font-size:1.25rem;margin:0}.next li{margin:.5rem 0;overflow-wrap:anywhere}.banner{border-left:4px solid var(--mint)}.banner.badb{border-left-color:var(--bad)}
footer{margin-top:2rem;color:var(--muted);font-size:.82rem;display:flex;gap:1rem;flex-wrap:wrap;justify-content:space-between}
</style></head><body><div class="wrap">
<header><div class="brand"><div class="mark"><svg viewBox="0 0 24 24" fill="none" stroke="#06281a" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21c-5-3-8-7-8-11a8 8 0 0 1 16 0c0 4-3 8-8 11z"/><path d="M12 21V9"/><path d="M12 13l3-3"/></svg></div>
<div><h1>PadMint</h1><div class="v" id="ver"></div></div></div>
<select id="lang" aria-label="Language"><option value="en">English</option><option value="es">Español</option><option value="pt">Português</option></select></header>

<section class="hero"><p data-t="intro"></p><div class="chips"><span class="chip" data-t="trust_local"></span><span class="chip" data-t="trust_upload"></span><span class="chip" data-t="trust_open"></span></div></section>

<main id="form">
<section class="card"><div class="row" style="justify-content:space-between"><h2 data-t="step1"></h2><button class="btn hidden" id="changeGame" data-t="change"></button></div>
<div id="finder"><input id="search" type="search" autocomplete="off"><div class="filters" id="filters"></div></div>
<div class="sub" id="buildsHead"><span data-t="builds"></span> <span class="muted" id="count"></span></div><div class="list" id="games"></div><p class="muted hidden" id="noMatch" data-t="no_match"></p>
<div id="dlHead" class="sub" data-t="no_build"></div><div class="list" id="apps"></div></section>

<section class="card hidden" id="dlBox"><h2 id="dlName"></h2><p id="dlIntro"></p><ol class="next" id="dlSteps"></ol><p class="small" id="dlGuide"></p></section>

<section class="card banner hidden" id="readyBox"><h2 data-t="ready_title"></h2><p id="readyText"></p><div class="row"><a class="btn main" id="readyLink" target="_blank" data-t="ready_link"></a></div><p class="muted small" data-t="ready_or"></p></section>

<section class="card hidden" id="fileBox"><h2 data-t="step2"></h2><p id="fileHint" class="small"></p>
<div class="row"><button class="btn" id="choose" data-t="choose"></button></div>
<div id="foundBox"><p class="muted small" id="found"></p><div id="files"></div></div>
<details id="typeBox"><summary data-t="type_toggle"></summary><p class="muted small" data-t="type"></p>
<div class="row"><input id="path" style="flex:1;min-width:240px"><button class="btn" id="use" data-t="use"></button></div></details>
<p class="state" id="fileState"></p></section>
<p id="inApp" class="muted hidden"></p>

<section class="card hidden" id="deviceBox"><h2 data-t="step3"></h2><div class="grid" id="devices"></div></section>

<section class="card plan hidden" id="planBox"><h2 data-t="plan_title"></h2><div id="plan"></div>
<div class="row" style="margin-top:.8rem"><button class="btn main" id="make" data-t="make" disabled></button></div>
<p class="bad" id="makeError"></p></section>
</main>

<main id="progress" class="hidden">
<section class="card banner" id="headCard"><p class="big" id="making"></p><p class="muted small"><span data-t="elapsed"></span>: <b id="elapsed"></b></p></section>
<section class="card"><ul class="steps" id="phases"></ul>
<div class="row" style="margin-top:.8rem"><button class="btn" id="cancel" data-t="cancel"></button><span class="muted small" id="cancelNote" data-t="cancel_note"></span>
<button class="btn hidden" id="again" data-t="again"></button></div></section>
<section class="card hidden" id="finished"></section>
<section class="card"><details id="logBox"><summary><span data-t="log"></span> <span class="muted" id="lineCount"></span></summary>
<pre id="tail"></pre><button class="btn" id="copy" data-t="copy_log"></button></details></section>
</main>
<footer><span data-t="local_note"></span><span><a href="https://github.com/chrissotraidis/padmint" target="_blank" data-t="source"></a> · <a id="reportLink" href="https://github.com/chrissotraidis/padmint/issues" target="_blank" data-t="report"></a></span></footer>
</div>
<script>
const T="__TOKEN__";let D=__DATA__,S=D.text;const H={"Content-Type":"application/json","X-PadMint-Token":T};
const $=id=>document.getElementById(id);let file=null,reading=false,sel=null,dev=null,shown=false;
const fill=(k,v)=>Object.entries(v||{}).reduce((s,[a,b])=>s.split("{"+a+"}").join(b),S[k]||"");
for(const e of document.querySelectorAll("[data-t]"))e.textContent=S[e.dataset.t]||"";
document.documentElement.lang=D.lang;$("lang").value=D.lang;$("ver").textContent="v"+D.version;$("search").placeholder=S.search;
$("choose").classList.toggle("hidden",!D.picker);
let last=null;
function texts(){for(const e of document.querySelectorAll("[data-t]"))e.textContent=S[e.dataset.t]||"";document.documentElement.lang=D.lang;$("search").placeholder=S.search}
$("lang").onchange=async()=>{const lang=$("lang").value,r=await (await fetch("/api/player?lang="+lang,{headers:H})).json();
 if(r.error)return;D=r;S=D.text;texts();history.replaceState(null,"","?token="+T+"&lang="+lang);filters();cards();
 if(sel){const keep={file,dev};const g=game();if(g||app())redraw(keep)}
 if(last){shown=false;$("finished").replaceChildren();const r2=await (await fetch("/api/build?lang="+lang,{headers:H})).json();show(r2)}};
function redraw(keep){const was=keep.file,state=$("fileState").textContent;choose(sel);if(was){file=was;$("path").value=was;$("fileState").className="state ok";$("fileState").textContent="✓ "+fill("file_ok",{file:base(was)})}
 if(keep.dev&&game())pickDevice(keep.dev);ready()}
async function post(p,b){const r=await fetch(p,{method:"POST",headers:H,body:JSON.stringify(Object.assign({lang:D.lang},b||{}))});return r.json()}
const base=p=>p.split(/[\\/]/).pop();
function el(tag,text,cls){const e=document.createElement(tag);if(text!=null&&text!=="")e.textContent=text;if(cls)e.className=cls;return e}
const gb=b=>b?(b>=1e9?(b/1e9).toFixed(1)+" GB":Math.max(1,Math.round(b/1e6))+" MB"):"";
const game=()=>D.games.find(g=>g.id==sel),app=()=>D.downloads.find(a=>a.id==sel);
let system="";
const title=g=>(g.about||g.name).replace(/\s*\([^)]*\)\s*$/,"");
const systemOf=g=>{const m=(g.about||"").match(/\(([^),]+)/);return m?m[1].replace(/ prototype$/,""):""};
const sortKey=g=>title(g).replace(/^(The|A) /i,"").toLowerCase();
function filters(){const systems=[...new Set(D.games.map(systemOf).filter(Boolean))].sort();
 $("filters").replaceChildren(...["",...systems].map(s=>{const b=el("button",s||S.all,"filter"+(s==system?" on":""));b.onclick=()=>{system=s;filters();cards()};return b}))}
function row(x,isGame){const b=el("button",null,"item"+(x.id==sel?" on":""));
 b.append(el("span",isGame?title(x):x.name,"t"));const t=el("div",null,"tags");
 if(isGame&&x.ready)t.append(el("span",S.ready_tag,"tag ready"));if(isGame)for(const p of x.platforms)t.append(el("span",p.short||p.label,"tag"));b.append(t);
 if(isGame)b.append(el("span",x.name+(systemOf(x)?" · "+systemOf(x):""),"s"));b.onclick=()=>choose(x.id);return b}
function cards(){const q=$("search").value.trim().toLowerCase();
 const m=x=>sel?x.id==sel:(!q||(x.name+" "+(x.about||"")).toLowerCase().includes(q));
 $("finder").classList.toggle("hidden",!!sel);$("changeGame").classList.toggle("hidden",!sel);
 const games=D.games.filter(g=>m(g)&&(sel||!system||systemOf(g)==system)).sort((a,b)=>sortKey(a).localeCompare(sortKey(b)));
 $("games").replaceChildren(...games.map(g=>row(g,true)));$("games").classList.toggle("hidden",!games.length);
 $("buildsHead").classList.toggle("hidden",!!sel||!games.length);$("count").textContent="("+fill("count",{count:games.length})+")";
 const as=sel||system?D.downloads.filter(a=>a.id==sel):D.downloads.filter(m);
 $("dlHead").classList.toggle("hidden",!as.length||!!sel);$("apps").replaceChildren(...as.map(a=>row(a,false)));$("apps").classList.toggle("hidden",!as.length);
 $("noMatch").classList.toggle("hidden",!!(games.length||as.length))}
$("search").oninput=cards;$("changeGame").onclick=()=>{sel=null;file=null;dev=null;for(const id of ["fileBox","deviceBox","planBox","dlBox","readyBox","inApp"])$(id).classList.add("hidden");cards()};
function choose(id){sel=id;file=null;dev=null;$("fileState").textContent="";$("path").value="";cards();const g=game(),a=app();
 $("dlBox").classList.toggle("hidden",!a);
 $("readyBox").classList.toggle("hidden",!(g&&g.ready));if(g&&g.ready){$("readyText").textContent=g.ready.text;$("readyLink").href=g.ready.url}
 if(a){$("dlName").textContent=a.name;$("dlIntro").textContent=a.intro;$("dlSteps").replaceChildren(...a.steps.map(linked));
  const l=el("a",a.guide);l.href=a.guide;l.target="_blank";$("dlGuide").replaceChildren(S.guide+": ",l);$("dlBox").scrollIntoView({behavior:"smooth"})}
 for(const id of ["fileBox","deviceBox","planBox"])$(id).classList.add("hidden");$("inApp").classList.add("hidden");if(!g)return;
 if(g.needs_file){$("fileBox").classList.remove("hidden");
  const h=$("fileHint");h.replaceChildren(el("b",fill("file_hint",{game:g.about||g.name})));
  if(g.formats.length)h.append(" ",el("span",fill("file_formats",{formats:g.formats.join(", ")}),"muted"));
  if(g.ids.length)h.append(" · ",el("span",fill("file_ids",{ids:g.ids.join(", ")}),"muted"));$("foundBox").classList.toggle("hidden",!g.files.length);$("found").textContent=fill("found",{folder:D.folder});
  $("files").replaceChildren(...g.files.map(f=>{const b=el("button",null,"btn file");b.append(el("b",base(f)),el("span","→","muted"));b.title=f;b.onclick=()=>useFile(f);return b}))}
 else{$("inApp").textContent=fill("file_in_app",{name:g.name});$("inApp").classList.remove("hidden")}
 $("deviceBox").classList.remove("hidden");$("devices").replaceChildren(...g.platforms.map(p=>{const b=el("button",null,"pick");b.append(el("b",p.label));b.onclick=()=>pickDevice(p.id);b.dataset.id=p.id;return b}));
 if(g.platforms.length==1)pickDevice(g.platforms[0].id);($("fileBox").classList.contains("hidden")?$("deviceBox"):$("fileBox")).scrollIntoView({behavior:"smooth"});ready()}
async function pickDevice(id){dev=id;for(const b of $("devices").children)b.classList.toggle("on",b.dataset.id==id);$("planBox").classList.remove("hidden");$("plan").replaceChildren(el("p","…","muted"));
 const r=await (await fetch("/api/plan?game="+sel+"&platform="+id+"&lang="+D.lang,{headers:H})).json();if(dev!=id)return;showPlan(r);ready()}
let blocked=false;
function showPlan(p){const g=game(),box=$("plan");box.replaceChildren();if(p.error){box.append(el("p",p.error,"bad"));return}
 if(p.output)box.append(el("div",p.output,"out"));
 blocked=p.needs.some(n=>!n.ok);
 if(p.needs.length){box.append(el("p",S.plan_needs,"state"));const u=el("ul",null,"tools");for(const n of p.needs){const li=el("li");li.append(el("span",n.label),el("span",n.ok?S.needs_ok:S.needs_missing,n.ok?"ok":"bad"));u.append(li);if(!n.ok)u.append(el("li",n.note,"detail"))}box.append(u)}
 const o=el("ol");const repo=p.repo.replace("https://","");o.append(el("li",fill("plan_source",{name:g.name,repo})));
 const li=el("li",fill("plan_tools",{folder:p.tools_folder}));const u=el("ul",null,"tools");
 for(const t of p.tools){const r=el("li");r.append(el("span",t.name+" "+t.version+" · "+fill("from",{host:t.source})),el("span",t.here?S.tool_here:gb(t.size),t.here?"ok":"muted"));u.append(r)}
 li.append(u);o.append(li);if(p.app)o.append(el("li",fill("plan_app",{name:g.name})));
 o.append(el("li",S.plan_build),el("li",fill("plan_save",{folder:p.folder})));box.append(o);
 if(p.space_gb)box.append(el("p",fill("plan_space",{gb:p.space_gb}),"muted small"))}
function ready(){const g=game();$("make").disabled=!g||!dev||reading||blocked||(g.needs_file&&!file)}
async function useFile(path){if(!path)return;$("path").value=path;reading=true;file=null;ready();$("fileState").className="state";
 $("fileState").textContent="…";const r=await post("/api/file",{game:sel,path});reading=false;
 if(r.problem||r.error){$("fileState").className="state bad";$("fileState").textContent=r.problem||r.error}
 else{file=path;$("fileState").className="state ok";$("fileState").textContent="✓ "+fill("file_ok",{file:base(path)})}ready()}
$("choose").onclick=async()=>{const r=await post("/api/pick");if(r.path)useFile(r.path);else if(!r.available){$("typeBox").open=true;$("path").focus()}};
$("use").onclick=()=>useFile($("path").value.trim().replace(/^["']|["']$/g,""));
$("make").onclick=async()=>{$("make").disabled=true;const r=await post("/api/make",{game:sel,platform:dev,path:file});
 if(r.error){$("makeError").textContent=r.error;ready();return}show(r);poll()};
$("cancel").onclick=async()=>{$("cancel").disabled=true;await post("/api/cancel")};
$("again").onclick=()=>{location.search="?token="+T+"&lang="+D.lang};
$("copy").onclick=async()=>{const text="PadMint "+D.version+" ("+navigator.platform+")\n"+$("tail").textContent;
 try{await navigator.clipboard.writeText(text);$("copy").textContent=S.copied}catch(e){getSelection().selectAllChildren($("tail"))}};
const clock=s=>[Math.floor(s/3600),Math.floor(s/60)%60,s%60].map((n,i)=>i?String(n).padStart(2,"0"):n).join(":");
function linked(text){const li=el("li");for(const part of text.split(/(https:\/\/[^\s)]*[^\s).,;:])/)){if(/^https:\/\//.test(part)){const a=el("a",part);a.href=part;a.target="_blank";li.append(a)}else li.append(part)}return li}
function bar(pct){const b=el("div",null,"bar"),i=el("i");i.style.width=Math.max(0,Math.min(100,pct))+"%";b.append(i);return b}
function phaseRow(p,r,g){const li=el("li",null,p.state||"pending"),ico=el("div",p.state=="done"?"✓":p.state=="failed"?"✕":p.state=="cancelled"?"–":"","ico"),body=el("div");
 const name=g?g.name:r.game;body.append(el("div",fill("ph_"+p.id,{name})));
 const repo=(p.repo||"").replace("https://","");
 if(p.id=="release"&&p.version)body.append(el("div",fill("version_from",{version:p.version,repo}),"detail"));
 if(p.id=="source"&&p.folder)body.append(el("div",p.folder,"detail"));
 if(p.id=="tools"){for(const t of r.tools){const d=el("div",null,"detail");d.append(t.name+" "+(t.version||"")+" · "+fill("from",{host:t.source||""})+" · "+(t.state=="ready"?"✓":t.state=="unpacking"?S.unpacking:(t.percent||0)+"% "+gb(t.size)));
   body.append(d);if(t.state=="downloading")body.append(bar(t.percent||0))}}
 if(p.id=="app"&&p.name)body.append(el("div",p.name,"detail"));
 if(p.id=="build"&&r.stage&&p.state=="running"){const s=r.stage;body.append(el("div",fill("stage",{stage:s.stage})+(s.total?" · "+s.completed+" / "+s.total+(s.unit?" "+s.unit:""):""),"detail"));if(s.total)body.append(bar(100*s.completed/s.total))}
 if(p.id=="build"&&p.state=="running"&&r.now)body.append(el("div",r.now.slice(-160),"detail mono"));
 if(p.id=="save"&&p.file)body.append(el("div",p.file,"detail ok"));
 li.append(ico,body);return li}
function show(r){if(r.state=="idle")return;last=r;$("form").classList.add("hidden");$("progress").classList.remove("hidden");
 const g=D.games.find(x=>x.id==r.game);$("making").textContent=r.state=="done"?S.done_title:r.state=="failed"?S.failed_title:r.state=="cancelled"?S.cancelled:fill("making",{name:g?g.name:r.game,device:r.device||""});
 $("headCard").classList.toggle("badb",r.state=="failed");$("elapsed").textContent=clock(r.elapsed);
 const ids=["release","source","tools","app","build","save"],have={};for(const p of r.phases||[])have[p.id]=p;
 const list=ids.filter(id=>have[id]||(id!="app"&&r.state=="running")).map(id=>have[id]||{id,state:"pending"});
 $("phases").replaceChildren(...list.map(p=>phaseRow(p,r,g)));
 const pre=$("tail"),stick=pre.scrollTop+pre.clientHeight>=pre.scrollHeight-20;pre.textContent=r.tail.length?r.tail.join("\n"):S.log_empty;if(stick)pre.scrollTop=pre.scrollHeight;$("lineCount").textContent=r.lines?"("+r.lines+")":"";$("copy").disabled=!r.tail.length;
 const over=r.state!="running";$("cancel").classList.toggle("hidden",over);$("cancelNote").classList.toggle("hidden",over);$("again").classList.toggle("hidden",!over);
 if(!over||shown)return;shown=true;const f=$("finished");f.classList.remove("hidden");if(g)$("reportLink").href=g.issues;
 if(r.state=="failed"){const p=el("p",S.failed+" ","bad"),a=el("a",g?g.issues:"");a.href=g?g.issues:"";a.target="_blank";p.append(a);f.append(p);$("logBox").open=true}
 if(r.state=="cancelled")f.classList.add("hidden");
 if(r.state=="done"&&r.result){const x=r.result;$("headCard").after(f);
  f.append(el("h2",S.what_you_got));if(x.about)f.append(el("p",x.about));
  if(x.file){const row=el("div",null,"row out");row.append(el("span",x.file,"mono ok"));if(D.reveal){const b=el("button",S.show,"btn");b.onclick=()=>post("/api/reveal");row.append(b)}f.append(row)}
  if(x.steps.length){const o=el("ol",null,"next");for(const s of x.steps)o.append(linked(s));f.append(el("h2",S.next),o)}
  if(x.note)f.append(el("p",x.note,"muted"));
  const p=el("p",S.guide+": ","small"),a=el("a",x.guide);a.href=x.guide;a.target="_blank";p.append(a);f.append(p,el("p",x.private,"warn small"))}}
async function poll(){const r=await (await fetch("/api/build?lang="+D.lang,{headers:H})).json();show(r);if(r.state=="running")setTimeout(poll,1500)}
if(!D.games.length&&!D.downloads.length){$("form").replaceChildren(el("p",S.none,"bad"))}else{filters();cards();poll()}
</script></body></html>
"""
