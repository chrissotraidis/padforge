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

from . import __version__, cli
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
                      "platforms": [{"id": p, "label": cli.platform_label(p, lang)} for p in platforms],
                      "files": [str(path) for path in files[:8]],
                      "issues": entry["repo_url"] + "/issues"})
    apps = [] if cli.on_android() else [
        {"id": app, "name": name, "intro": phrase("download_intro", lang, name=name).strip(),
         "steps": localized(catalog()[app]["download"], "steps", lang),
         "guide": catalog()[app].get("player_help") or catalog()[app]["repo_url"]}
        for app, name in cli.downloads()]
    return {"lang": lang, "version": __version__, "folder": str(folder),
            "saved_in": phrase("saved_in", lang, folder=folder), "games": games, "downloads": apps,
            "text": strings(lang), "picker": not cli.on_android(), "reveal": not cli.on_android()}


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
    found = cli.game_from_file(disc, cli.player_games(), io.StringIO())
    if found and game not in found:
        name = (catalog()[game].get("manifest") or {}).get("name", game)
        return phrase("w_wrong_game", lang, name=name)
    return None


class Builds:
    """At most one copy made from the window at a time."""

    def __init__(self):
        self.lock = threading.Lock()
        self.process = self.log = self.job = None

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
            env = dict(os.environ, PADMINT_LANG=lang, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
            # Its own process group, so Cancel (Ctrl-Break on Windows) reaches only the build.
            group = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
                     else {"start_new_session": True})
            with self.log.open("wb") as stream:
                self.process = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=stream,
                                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, **group)
            self.job = {"game": game, "platform": platform_name, "lang": lang, "folder": folder,
                        "started": time.time(), "result": None}

    def status(self):
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
        reply = {"state": state, "step": "done" if code == 0 else step, "now": now[-200:], "game": job["game"],
                 "elapsed": int(time.time() - job["started"]), "tail": lines[-60:], "exit_code": code}
        if code == 0:
            reply["result"] = self.result()
        return reply

    def result(self):
        job = self.job
        if job["result"] is None:
            try:
                built = Path(json.loads((job["folder"] / "result.json").read_text())["file"])
            except (OSError, ValueError, KeyError):
                built = None
            steps, note, guide = cli.next_step_text(catalog()[job["game"]], job["platform"], built, job["lang"])
            job["result"] = {"file": str(built) if built else None, "steps": steps, "note": note,
                             "guide": guide, "private": phrase("keep_private", job["lang"])}
        return job["result"]

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
                return self.reply(200, builds.status())
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
:root{font-family:-apple-system,"Segoe UI",system-ui,sans-serif;color-scheme:light dark;--accent:#1f8a5b}
body{max-width:720px;margin:2rem auto;padding:0 1.2rem;line-height:1.5}
header{display:flex;justify-content:space-between;align-items:baseline;gap:1rem;flex-wrap:wrap}
h1{margin:0}h2{font-size:1.1rem;margin:1.6rem 0 .5rem}p.note{color:GrayText;margin:.3rem 0}
select,input{padding:.5rem;font:inherit;box-sizing:border-box}#game{width:100%}
button{padding:.55rem 1rem;font:inherit;border-radius:6px;border:1px solid rgba(127,127,127,.5);cursor:pointer}
button.main{background:var(--accent);color:#fff;border-color:var(--accent);font-weight:600}
button:disabled{opacity:.5;cursor:default}.row{display:flex;gap:.5rem;flex-wrap:wrap;align-items:center}
.files button{display:block;width:100%;text-align:left;margin:.25rem 0;overflow-wrap:anywhere}
.device label{display:block;padding:.4rem 0}.ok{color:var(--accent)}.bad{color:#c62828}
pre{background:rgba(127,127,127,.12);padding:.8rem;white-space:pre-wrap;max-height:20rem;overflow:auto;font-size:.85rem}
ol li{margin:.4rem 0;overflow-wrap:anywhere}.hidden{display:none}#now{overflow-wrap:anywhere}
</style></head><body>
<header><h1>PadMint</h1><label><span data-t="language"></span>
<select id="lang"><option value="en">English</option><option value="es">Español</option><option value="pt">Português</option></select></label></header>
<p class="note" data-t="intro"></p>
<main id="form">
<h2 data-t="game"></h2><select id="game"></select>
<section id="fileBox"><h2 data-t="file"></h2>
<div class="row"><button id="choose" data-t="choose"></button></div>
<div id="foundBox"><p class="note" id="found"></p><div class="files" id="files"></div></div>
<p class="note" data-t="type"></p>
<div class="row"><input id="path" style="flex:1"><button id="use" data-t="use"></button></div>
<p id="fileState"></p></section>
<p id="inApp" class="note"></p>
<section id="dlBox" class="hidden"><p id="dlIntro"></p><ol id="dlSteps"></ol><p id="dlGuide"></p></section>
<section id="deviceBox"><h2 data-t="device"></h2><div class="device" id="devices"></div></section>
<section id="finish"><p class="note" id="savedIn"></p><p class="note" data-t="time"></p>
<div class="row"><button class="main" id="make" data-t="make" disabled></button></div><p id="makeError" class="bad"></p></section>
</main>
<main id="progress" class="hidden">
<h2 id="step"></h2><p><b data-t="elapsed"></b>: <span id="elapsed"></span></p>
<p id="nowRow"><b data-t="now"></b>: <span id="now"></span></p>
<div id="finished"></div>
<div class="row"><button id="cancel" data-t="cancel"></button><button id="again" class="hidden" data-t="again"></button></div>
<details id="detailsBox"><summary data-t="details"></summary><pre id="tail"></pre>
<button id="copy" data-t="copy"></button></details>
</main>
<script>
const T="__TOKEN__",D=__DATA__,S=D.text,H={"Content-Type":"application/json","X-PadMint-Token":T};
const $=id=>document.getElementById(id);let file=null,reading=false;
for(const el of document.querySelectorAll("[data-t]"))el.textContent=S[el.dataset.t];
document.documentElement.lang=D.lang;$("lang").value=D.lang;$("savedIn").textContent=D.saved_in;
$("choose").classList.toggle("hidden",!D.picker);
$("lang").onchange=()=>{location.search="?token="+T+"&lang="+$("lang").value};
async function post(p,b){const r=await fetch(p,{method:"POST",headers:H,body:JSON.stringify(Object.assign({lang:D.lang},b||{}))});return r.json()}
const game=()=>D.games.find(g=>g.id==$("game").value);
const app=()=>D.downloads.find(a=>a.id==$("game").value);
const base=p=>p.split(/[\\/]/).pop();
function el(tag,text,cls){const e=document.createElement(tag);if(text)e.textContent=text;if(cls)e.className=cls;return e}
function ready(){const g=game();$("make").disabled=!g||reading||(g.needs_file&&!file)||!document.querySelector("input[name=device]:checked")}
function showGame(){const g=game(),a=app();file=null;$("fileState").textContent="";$("path").value="";
 $("dlBox").classList.toggle("hidden",!a);
 if(a){$("dlIntro").textContent=a.intro;$("dlSteps").replaceChildren(...a.steps.map(s=>el("li",s)));
  const l=el("a",a.guide);l.href=a.guide;l.target="_blank";$("dlGuide").replaceChildren(S.guide+": ",l)}
 for(const id of ["fileBox","inApp","deviceBox","finish"])$(id).classList.toggle("hidden",!g);if(!g)return ready();
 $("fileBox").classList.toggle("hidden",!g.needs_file);$("inApp").textContent=g.needs_file?"":S.file_in_app.replace("{name}",g.name);
 $("foundBox").classList.toggle("hidden",!g.files.length);$("found").textContent=S.found.replace("{folder}",D.folder);$("files").innerHTML="";
 for(const f of g.files){const b=el("button",base(f));b.title=f;b.onclick=()=>useFile(f);$("files").append(b)}
 $("devices").innerHTML="";for(const p of g.platforms){const l=el("label"),r=el("input");
  r.type="radio";r.name="device";r.value=p.id;r.checked=g.platforms.length==1;r.onchange=ready;l.append(r," "+p.label);$("devices").append(l)}ready()}
async function useFile(path){if(!path)return;$("path").value=path;reading=true;file=null;ready();$("fileState").className="";
 $("fileState").textContent="…";const r=await post("/api/file",{game:game().id,path});reading=false;
 if(r.problem||r.error){$("fileState").className="bad";$("fileState").textContent=r.problem||r.error}
 else{file=path;$("fileState").className="ok";$("fileState").textContent=S.file_ok.replace("{file}",base(path))}ready()}
$("choose").onclick=async()=>{const r=await post("/api/pick");if(r.path)useFile(r.path);else if(!r.available)$("path").focus()};
$("use").onclick=()=>useFile($("path").value.trim().replace(/^["']|["']$/g,""));
$("make").onclick=async()=>{const d=document.querySelector("input[name=device]:checked");$("make").disabled=true;
 const r=await post("/api/make",{game:game().id,platform:d.value,path:file});if(r.error){$("makeError").textContent=r.error;ready();return}show(r);poll()};
$("cancel").onclick=async()=>{$("cancel").disabled=true;await post("/api/cancel")};
$("again").onclick=()=>{location.search="?token="+T+"&lang="+D.lang};
$("copy").onclick=async()=>{const text="PadMint "+D.version+" ("+navigator.platform+")\n"+$("tail").textContent;
 try{await navigator.clipboard.writeText(text);$("copy").textContent=S.copied}catch(e){getSelection().selectAllChildren($("tail"))}};
const clock=s=>[Math.floor(s/3600),Math.floor(s/60)%60,s%60].map((n,i)=>i?String(n).padStart(2,"0"):n).join(":");
let shown=false;
function show(r){if(r.state=="idle")return;$("form").classList.add("hidden");$("progress").classList.remove("hidden");
 $("step").textContent=r.state=="cancelled"?S.cancelled:{tools:S.step_tools,build:S.step_build,done:S.step_done}[r.step];
 $("elapsed").textContent=clock(r.elapsed);$("now").textContent=r.now||S.starting;$("tail").textContent=r.tail.join("\n");
 const over=r.state!="running";$("cancel").classList.toggle("hidden",over);$("again").classList.toggle("hidden",!over);$("nowRow").classList.toggle("hidden",over);
 if(!over||shown)return;shown=true;const f=$("finished"),g=D.games.find(x=>x.id==r.game)||{issues:""};
 if(r.state=="failed"){const p=el("p",S.failed+" ","bad"),a=el("a",g.issues);a.href=g.issues;a.target="_blank";p.append(a);f.append(p);$("detailsBox").open=true}
 if(r.state=="done"&&r.result){const x=r.result;
  if(x.file){f.append(el("p",x.file,"ok"));if(D.reveal){const b=el("button",S.show);b.onclick=()=>post("/api/reveal");f.append(b)}}
  if(x.steps.length){const o=el("ol");for(const s of x.steps)o.append(el("li",s));f.append(el("h2",S.next),o)}
  if(x.note)f.append(el("p",x.note));
  const p=el("p",S.guide+": "),a=el("a",x.guide);a.href=x.guide;a.target="_blank";p.append(a);f.append(p,el("p",x.private,"note"))}}
async function poll(){const r=await (await fetch("/api/build",{headers:H})).json();show(r);if(r.state=="running")setTimeout(poll,2000)}
if(!D.games.length&&!D.downloads.length){$("form").replaceChildren(el("p",S.none,"bad"))}
else{const pick=el("option",S.pick_game);pick.value="";$("game").append(pick);
 for(const g of D.games){const o=el("option",g.name);o.value=g.id;$("game").append(o)}
 if(D.downloads.length){const grp=el("optgroup");grp.label=S.no_build;
  for(const a of D.downloads){const o=el("option",a.name);o.value=a.id;grp.append(o)}$("game").append(grp)}
 $("game").onchange=showGame;showGame();poll()}
</script></body></html>"""
