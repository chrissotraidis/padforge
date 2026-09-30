"""`padmint ui`: a local browser page over the same commands the CLI runs.

Serves only on 127.0.0.1 with a random token, uses the Python standard library,
and starts builds as `python3 -m padmint build` subprocesses so the page can
never do more than the CLI. Nothing is uploaded.
"""
import contextlib
import io
import json
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
import webbrowser

from . import __version__, tools
from .manifest import catalog, host_id, manifest_for


def git_tool():
    return tools.executable("git", host_id())

ROOT = Path(__file__).resolve().parent.parent
STAGE_LINE = re.compile(r"backend_event: (\S+) (stage_\w+)")


class Builds:
    """At most one build started from the page at a time."""

    def __init__(self):
        self.lock = threading.Lock()
        self.process = None
        self.log = None

    def start(self, argv):
        with self.lock:
            if self.process and self.process.poll() is None:
                raise ValueError("A build is already running")
            handle, path = tempfile.mkstemp(prefix="padmint-ui-", suffix=".log")
            self.log = Path(path)
            stream = open(handle, "wb")
            self.process = subprocess.Popen([sys.executable, "-m", "padmint", *argv], cwd=ROOT,
                                            stdout=stream, stderr=subprocess.STDOUT)
            stream.close()

    def status(self):
        if self.process is None:
            return {"state": "idle"}
        text = self.log.read_text(errors="replace") if self.log and self.log.exists() else ""
        stages = {}
        for stage, event in STAGE_LINE.findall(text):
            stages[stage] = event.replace("stage_", "")
        code = self.process.poll()
        return {"state": "running" if code is None else "finished", "exit_code": code,
                "stages": stages, "tail": text.splitlines()[-40:]}

    def cancel(self):
        if self.process and self.process.poll() is None:
            self.process.send_signal(signal.SIGINT)  # PadMint cancels and keeps finished work


def run_cli(argv):
    from .cli import main
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return {"exit_code": code, "output": out.getvalue() + err.getvalue()}


def games():
    result = []
    for game, entry in sorted(catalog().items()):
        manifest = entry.get("manifest")
        result.append({"id": game, "repo_url": entry["repo_url"],
                       "name": manifest["name"] if manifest else game,
                       "status": manifest["status"] if manifest else "manifest in repository",
                       "targets": {name: info["hosts"] for name, info in manifest["targets"].items()}
                       if manifest else {}})
    return result


def build_argv(action, form):
    argv = [action, form["game"], "--repo", form["repo"], "--revision", form["revision"],
            "--target", form.get("target") or "ios"]
    if form.get("disc"):
        argv += ["--disc", form["disc"]]
    return argv


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

        def do_GET(self):
            if not self.allowed():
                return self.reply(403, {"error": "Open the address printed by padmint ui"})
            route = urlparse(self.path).path
            if route == "/":
                return self.reply(200, PAGE.replace("__TOKEN__", token), "text/html; charset=utf-8")
            if route == "/api/games":
                return self.reply(200, games())
            if route == "/api/build":
                return self.reply(200, builds.status())
            return self.reply(404, {"error": "not found"})

        def do_POST(self):
            if not self.allowed():
                return self.reply(403, {"error": "forbidden"})
            try:
                length = min(int(self.headers.get("Content-Length") or 0), 65536)
                form = json.loads(self.rfile.read(length) or b"{}")
                route = urlparse(self.path).path
                if route == "/api/doctor":
                    argv = ["doctor", form["game"], "--target", form.get("target") or "ios"]
                    if form.get("repo"):
                        argv += ["--repo", form["repo"]]
                    return self.reply(200, run_cli(argv))
                if route == "/api/head":
                    head = subprocess.run([git_tool(), "-C", form["repo"], "rev-parse", "HEAD"],
                                          capture_output=True, text=True)
                    dirty = subprocess.run([git_tool(), "-C", form["repo"], "status", "--porcelain"],
                                           capture_output=True, text=True).stdout.strip()
                    return self.reply(200, {"revision": head.stdout.strip(), "clean": not dirty,
                                            "error": head.stderr.strip()})
                if route == "/api/plan":
                    return self.reply(200, run_cli(build_argv("plan", form)))
                if route == "/api/build":
                    builds.start(build_argv("build", form))
                    return self.reply(200, builds.status())
                if route == "/api/cancel":
                    builds.cancel()
                    return self.reply(200, builds.status())
                return self.reply(404, {"error": "not found"})
            except (KeyError, ValueError, OSError) as error:
                return self.reply(400, {"error": str(error)})

    return Handler


def serve(port=0, open_browser=True):
    token = secrets.token_urlsafe(24)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(token, Builds()))
    url = f"http://127.0.0.1:{server.server_address[1]}/?token={token}"
    print(f"PadMint {__version__} is open at {url}\nPress Ctrl-C to stop.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>PadMint</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root{font-family:-apple-system,system-ui,sans-serif;color-scheme:light dark}
body{max-width:880px;margin:2rem auto;padding:0 1rem;line-height:1.45}
h1{margin-bottom:.2rem}p.note{color:GrayText;margin-top:0}
label{display:block;margin:.6rem 0 .2rem;font-weight:600}
input,select{width:100%;padding:.45rem;font:inherit;box-sizing:border-box}
.row{display:flex;gap:.5rem;margin-top:1rem;flex-wrap:wrap}button{padding:.5rem .9rem;font:inherit}
pre{background:rgba(127,127,127,.12);padding:.8rem;white-space:pre-wrap;max-height:22rem;overflow:auto}
table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:.3rem;border-bottom:1px solid rgba(127,127,127,.3)}
.done{color:#2e7d32}.failed{color:#c62828}.started{color:#1565c0}
</style></head><body>
<h1>PadMint</h1><p class="note">Build your own copy on this computer from your own game files. Nothing is uploaded.</p>
<label for="game">Game</label><select id="game"></select>
<label for="repo">Game checkout folder</label><input id="repo" placeholder="/path/to/game-repository">
<label for="revision">Reviewed commit</label>
<div class="row" style="margin:0"><input id="revision" style="flex:1" placeholder="40-character commit"><button id="head">Use current commit</button></div>
<label for="disc">Your disc or ROM (only for games that read it during the build)</label><input id="disc" placeholder="/path/to/your game image">
<label for="target">Platform</label><select id="target"><option>ios</option><option>macos</option><option>android</option></select>
<div class="row"><button id="doctor">Check this computer</button><button id="plan">Show plan</button><button id="build">Build</button><button id="cancel">Cancel</button></div>
<h2>Stages</h2><table id="stages"><tr><td>No build started</td></tr></table>
<h2>Output</h2><pre id="out">Choose a game and check this computer first.</pre>
<script>
const T="__TOKEN__",H={"Content-Type":"application/json","X-PadMint-Token":T};
const $=id=>document.getElementById(id), form=()=>({game:$("game").value,repo:$("repo").value,revision:$("revision").value,disc:$("disc").value,target:$("target").value});
async function post(p,b){const r=await fetch(p,{method:"POST",headers:H,body:JSON.stringify(b)});return r.json()}
function show(r){$("out").textContent=r.error||r.output||(r.tail||[]).join("\n")||JSON.stringify(r,null,2)}
fetch("/api/games",{headers:H}).then(r=>r.json()).then(g=>{for(const x of g){const o=document.createElement("option");o.value=x.id;o.textContent=x.name+" ("+x.status+")";$("game").append(o)}});
$("head").onclick=async()=>{const r=await post("/api/head",form());$("revision").value=r.revision;$("out").textContent=r.error||(r.clean?"Checkout is clean.":"Checkout has local changes; builds need a clean checkout.")};
$("doctor").onclick=async()=>show(await post("/api/doctor",form()));
$("plan").onclick=async()=>show(await post("/api/plan",form()));
$("build").onclick=async()=>{show(await post("/api/build",form()));poll()};
$("cancel").onclick=async()=>show(await post("/api/cancel",{}));
async function poll(){const r=await (await fetch("/api/build",{headers:H})).json();show(r);
 const rows=Object.entries(r.stages||{}).map(([s,e])=>"<tr><td>"+s+"</td><td class='"+(e=="completed"?"done":e)+"'>"+e+"</td></tr>").join("");
 $("stages").innerHTML=rows||"<tr><td>"+(r.state=="running"?"Starting…":"No stages reported")+"</td></tr>";
 if(r.state=="running")setTimeout(poll,2000);else if(r.state=="finished")$("stages").insertAdjacentHTML("beforeend","<tr><td><b>Finished</b></td><td>exit "+r.exit_code+"</td></tr>")}
</script></body></html>"""
