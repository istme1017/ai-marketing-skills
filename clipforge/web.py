"""Local web UI for clipforge.

    python -m clipforge.web            # then open http://localhost:8899

Stdlib only — no Flask, no build step, nothing to install beyond the
pipeline's own dependencies. Jobs run on a background thread and stream
progress to the page.
"""

from __future__ import annotations

import json
import os
import re
import threading
import traceback
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote

from .job import JobError, JobOptions, run_job

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
OUT_ROOT = os.environ.get("CLIPFORGE_OUT") or os.path.abspath("clips")

PAGE = r"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ClipForge</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#0b0b10;color:#e9e9f0;font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:820px;margin:0 auto;padding:24px 16px 64px}
h1{display:flex;align-items:center;gap:10px;font-size:26px;margin:0 0 4px}
.logo{width:38px;height:38px;border-radius:9px;background:linear-gradient(135deg,#7c3aed,#a855f7);display:grid;place-items:center;font-size:19px}
.sub{color:#9a9ab0;margin:0 0 18px}
.tags{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:20px}
.tag{background:#1a1a2e;border:1px solid #2a2a45;color:#c9c9e0;border-radius:999px;padding:5px 13px;font-size:13px}
.card{background:#14141f;border:1px solid #24243a;border-radius:14px;padding:20px;margin-bottom:18px}
label{display:block;font-size:13px;color:#9a9ab0;margin:0 0 6px}
input,select{width:100%;background:#0e0e17;border:1px solid #2a2a45;color:#e9e9f0;border-radius:9px;padding:12px;font-size:15px;font-family:inherit}
input:focus,select:focus{outline:none;border-color:#7c3aed}
.row{display:flex;gap:12px;margin-top:14px}.row>div{flex:1}
.check{display:flex;align-items:center;gap:10px;margin-top:16px;color:#c9c9e0;font-size:14px;cursor:pointer}
.check input{width:auto;flex:none;accent-color:#7c3aed;width:17px;height:17px}
button{width:100%;margin-top:18px;background:linear-gradient(135deg,#7c3aed,#a855f7);color:#fff;border:0;border-radius:10px;padding:15px;font-size:16px;font-weight:600;cursor:pointer;font-family:inherit}
button:disabled{opacity:.55;cursor:not-allowed}
#log{background:#0a0a12;border:1px solid #24243a;border-radius:10px;padding:14px;font:12.5px/1.7 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap;max-height:280px;overflow:auto;color:#b9b9d0}
.err{color:#ff8080;white-space:pre-wrap}
.clip{display:flex;gap:14px;align-items:center;background:#14141f;border:1px solid #24243a;border-radius:11px;padding:13px;margin-bottom:11px}
.score{flex:none;width:46px;height:46px;border-radius:10px;display:grid;place-items:center;font-weight:700;font-size:16px;background:#1e2a1e;color:#4ade80}
.score.mid{background:#2a2a1e;color:#facc15}.score.low{background:#2a1e1e;color:#f87171}
.meta{flex:1;min-width:0}.meta b{display:block;font-size:14px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.meta span{color:#8a8aa0;font-size:12.5px}
.dl{flex:none;background:#7c3aed;color:#fff;text-decoration:none;padding:9px 15px;border-radius:8px;font-size:13.5px;font-weight:600}
h2{font-size:15px;color:#9a9ab0;margin:24px 0 12px;font-weight:600}
.hide{display:none}
</style></head><body><div class="wrap">
<h1><span class="logo">▶</span> ClipForge</h1>
<p class="sub">Pega un link y recibe clips verticales listos para publicar.</p>
<div class="tags"><span class="tag">1080×1920 · 30 fps</span><span class="tag">Subtítulos quemados</span>
<span class="tag">Sigue a quien habla</span><span class="tag">Audio −14 LUFS</span></div>

<div class="card">
  <label for="url">Link del video (o ruta de archivo local)</label>
  <input id="url" placeholder="https://youtu.be/..." autocomplete="off">
  <div class="row">
    <div><label for="num">Cantidad de clips</label>
      <select id="num"><option>3</option><option>4</option><option selected>6</option><option>8</option><option>10</option></select></div>
    <div><label for="score">Exigencia</label>
      <select id="score"><option value="80">Alta (80+)</option><option value="70" selected>Normal (70+)</option><option value="55">Baja (55+)</option><option value="40">Mínima (40+)</option></select></div>
  </div>
  <div class="row">
    <div><label for="model">Calidad de transcripción</label>
      <select id="model"><option value="tiny">Rápida</option><option value="small" selected>Normal</option><option value="medium">Alta (lenta)</option></select></div>
    <div><label for="lang">Idioma</label>
      <select id="lang"><option value="">Automático</option><option value="es">Español</option><option value="en">Inglés</option></select></div>
  </div>
  <label class="check"><input type="checkbox" id="caps" checked> Subtítulos dinámicos sincronizados</label>
  <button id="go">Hacer clips</button>
</div>

<div class="card hide" id="prog"><div id="log"></div></div>
<div id="out"></div>

<h2>Trabajos anteriores</h2><div id="hist"></div>
</div><script>
const $=i=>document.getElementById(i); let timer=null;
function cls(s){return s>=70?'score':s>=50?'score mid':'score low'}
$('go').onclick=async()=>{
  const url=$('url').value.trim(); if(!url){$('url').focus();return}
  $('go').disabled=true; $('go').textContent='Procesando...';
  $('prog').classList.remove('hide'); $('log').textContent=''; $('out').innerHTML='';
  const r=await fetch('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({url,num:+$('num').value,min_score:+$('score').value,
      model:$('model').value,language:$('lang').value,captions:$('caps').checked})});
  const {id}=await r.json(); poll(id);
};
function poll(id){ clearInterval(timer); timer=setInterval(async()=>{
  const j=await(await fetch('/api/jobs/'+id)).json();
  $('log').textContent=j.log.join('\n'); $('log').scrollTop=1e9;
  if(j.status==='done'||j.status==='error'){ clearInterval(timer);
    $('go').disabled=false; $('go').textContent='Hacer clips';
    if(j.status==='error'){ $('out').innerHTML='<div class="card err">❌ '+esc(j.error)+'</div>'; }
    else render(j.clips,id);
    history();
  }},900);
}
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}
function render(clips,id){
  if(!clips||!clips.length){$('out').innerHTML='<div class="card">Sin clips.</div>';return}
  $('out').innerHTML='<h2>'+clips.length+' clips</h2>'+clips.map(c=>
    '<div class="clip"><div class="'+cls(c.score)+'">'+c.score+'</div><div class="meta"><b>'+esc(c.hook||c.file)+
    '</b><span>'+c.duration+'s · '+fmt(c.start)+' → '+fmt(c.end)+'</span></div>'+
    '<a class="dl" href="/clips/'+encodeURIComponent(id)+'/'+encodeURIComponent(c.file)+'" download>Descargar</a></div>').join('');
}
function fmt(s){const m=Math.floor(s/60),x=Math.floor(s%60);return m+':'+String(x).padStart(2,'0')}
async function history(){
  const h=await(await fetch('/api/jobs')).json();
  $('hist').innerHTML=h.length?h.map(j=>'<div class="clip"><div class="'+(j.status==='done'?'score':'score low')+'">'+
    (j.status==='done'?j.n:'!')+'</div><div class="meta"><b>'+esc(j.source)+'</b><span>'+j.when+' · '+j.status+'</span></div></div>').join('')
    :'<div class="card" style="color:#8a8aa0">Todavía no hay trabajos.</div>';
}
history();
</script></body></html>"""


def _job_dir(job_id: str) -> str:
    return os.path.join(OUT_ROOT, job_id)


def _run(job_id: str, payload: dict) -> None:
    def on(stage: str, msg: str) -> None:
        with JOBS_LOCK:
            JOBS[job_id]["log"].append(f"[{stage}] {msg}")

    try:
        opts = JobOptions(
            out_dir=_job_dir(job_id),
            num_clips=int(payload.get("num") or 6),
            min_score=int(payload.get("min_score") or 70),
            model=payload.get("model") or "small",
            language=payload.get("language") or None,
            burn_captions=bool(payload.get("captions", True)),
        )
        result = run_job(payload["url"], opts, on)
        with JOBS_LOCK:
            JOBS[job_id].update(status="done", clips=result.clips)
    except JobError as exc:
        with JOBS_LOCK:
            JOBS[job_id].update(status="error", error=str(exc))
            JOBS[job_id]["log"].append(f"[error] {exc}")
    except Exception as exc:                     # noqa: BLE001 - surfaced to the UI
        with JOBS_LOCK:
            JOBS[job_id].update(status="error",
                                error=f"{type(exc).__name__}: {exc}")
            JOBS[job_id]["log"].append(traceback.format_exc()[-1500:])


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):            # keep the console readable
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json")

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/":
            return self._send(200, PAGE.encode(), "text/html; charset=utf-8")

        if path == "/api/jobs":
            with JOBS_LOCK:
                out = [{"id": k, "source": v["source"][:70], "status": v["status"],
                        "when": v["when"], "n": len(v.get("clips", []))}
                       for k, v in sorted(JOBS.items(),
                                          key=lambda kv: kv[1]["when"], reverse=True)][:12]
            return self._json(out)

        m = re.match(r"^/api/jobs/([\w-]+)$", path)
        if m:
            with JOBS_LOCK:
                job = JOBS.get(m.group(1))
            if not job:
                return self._json({"error": "no such job"}, 404)
            return self._json({k: job[k] for k in
                               ("status", "log", "clips", "error") if k in job})

        m = re.match(r"^/clips/([\w-]+)/(.+)$", path)
        if m:
            job_id, name = m.group(1), unquote(m.group(2))
            # Resolve and confirm containment: never serve outside the job dir.
            base = os.path.realpath(_job_dir(job_id))
            target = os.path.realpath(os.path.join(base, name))
            if not target.startswith(base + os.sep) or not os.path.isfile(target):
                return self._json({"error": "not found"}, 404)
            with open(target, "rb") as fh:
                data = fh.read()
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Disposition",
                             f'attachment; filename="{os.path.basename(target)}"')
            self.end_headers()
            return self.wfile.write(data)

        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        if urlparse(self.path).path != "/api/jobs":
            return self._json({"error": "not found"}, 404)

        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")
        if not payload.get("url"):
            return self._json({"error": "url required"}, 400)

        job_id = uuid.uuid4().hex[:12]
        with JOBS_LOCK:
            JOBS[job_id] = {"status": "running", "log": [], "clips": [],
                            "source": payload["url"],
                            "when": datetime.now().strftime("%Y-%m-%d %H:%M")}
        threading.Thread(target=_run, args=(job_id, payload), daemon=True).start()
        return self._json({"id": job_id})


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(prog="clipforge.web")
    p.add_argument("--port", type=int, default=8899)
    p.add_argument("--host", default="0.0.0.0",
                   help="0.0.0.0 exposes it to your LAN/tailnet; 127.0.0.1 keeps it local")
    p.add_argument("--out", help="where clips are written")
    args = p.parse_args()

    global OUT_ROOT
    if args.out:
        OUT_ROOT = os.path.abspath(args.out)
    os.makedirs(OUT_ROOT, exist_ok=True)

    print(f"ClipForge — http://localhost:{args.port}")
    print(f"Clips: {OUT_ROOT}")
    print("Ctrl+C to stop.\n")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
