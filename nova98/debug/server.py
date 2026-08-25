"""Local visual debugger for the NOVA98 static dashboard.

Serves a single-page control panel on 127.0.0.1:

    GET  /                control panel (sliders + buttons)
    GET  /preview.png     rendered dashboard for the given values
    POST /upload          renders and uploads the frame via cmd 80
    GET  /metrics         fill the panel from real system readings

Debug tooling only: uploads are explicit user clicks, never scheduled.
"""

from __future__ import annotations

import io
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from PIL import Image

from nova98.device.hid_device import HidError, Nova98Hid
from nova98.device.profiles import NOVA98
from nova98.display.uploader import SafetyError, UploadError, upload_single_frame
from nova98.renderer.renderer import render
from nova98.renderer.state import StaticDisplayState

logger = logging.getLogger(__name__)

PAGE = """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>NOVA98 Screen Debugger</title>
<style>
  body { font-family: -apple-system, sans-serif; background:#141414; color:#eee;
         max-width: 640px; margin: 24px auto; padding: 0 16px; }
  h1 { font-size: 18px; } h2 { font-size: 14px; color:#9a9a9a; margin-bottom:4px;}
  .row { display:flex; align-items:center; gap:12px; margin:10px 0; }
  .row label { width:110px; }
  .row input[type=range] { flex:1; }
  .row output { width:90px; text-align:right; font-variant-numeric: tabular-nums; }
  #preview { border:1px solid #333; image-rendering: pixelated; width:480px; height:270px; background:#000;}
  button { padding:8px 18px; margin-right:8px; border:0; border-radius:6px;
           background:#2d7d46; color:white; font-size:14px; cursor:pointer;}
  button.gray { background:#444; }
  button:disabled { opacity:.5; cursor:default; }
  #status { min-height:20px; margin-top:10px; font-size:13px; color:#bbb; white-space:pre-wrap;}
  .section { margin-top:22px; padding-top:14px; border-top:1px solid #333;}
</style>
</head>
<body>
<h1>NOVA98 Screen 调试器 <span style="color:#666;font-size:12px">(localhost only)</span></h1>

<div class="section">
  <h2>实时预览（240×135 实际渲染结果）</h2>
  <img id="preview" src="/preview.png?nocache=1">
</div>

<div class="section">
  <h2>指标值</h2>
  <div class="row"><label>CPU %</label><input type="range" id="cpu" min="0" max="100" value="42"><output id="cpu-o">42%</output></div>
  <div class="row"><label>RAM %</label><input type="range" id="ram" min="0" max="100" value="60"><output id="ram-o">60%</output></div>
  <div class="row"><label>温度 °C</label><input type="range" id="temp" min="0" max="110" value="55"><output id="temp-o">55°C</output></div>
  <div class="row"><label>下载 KB/s</label><input type="range" id="down" min="0" max="10240" value="512"><output id="down-o">512 KB/s</output></div>
  <div class="row"><label>上传 KB/s</label><input type="range" id="up" min="0" max="10240" value="128"><output id="up-o">128 KB/s</output></div>
</div>

<div class="section">
  <button id="btn-upload">▶ 上传到键盘 (cmd 80)</button>
  <button id="btn-live" class="gray">从系统读取真实指标</button>
  <div id="status"></div>
</div>

<script>
const $ = id => document.getElementById(id);
const params = () => ({
  cpu: $("cpu").value, ram: $("ram").value,
  temp: $("temp").value, down: $("down").value, up: $("up").value,
});
function bind(id) {
  $(id).addEventListener("input", () => {
    $(id + "-o").value = $(id).value + ($(id) == $("temp") ? "°C" : id.includes("down")||id=="up" ? " KB/s" : "%");
    refresh();
  });
}
["cpu","ram","temp","down","up"].forEach(bind);
let t;
function refresh() { clearTimeout(t); t = setTimeout(() => {
  $("preview").src = "/preview.png?" + new URLSearchParams(params()) + "&nocache=" + Date.now();
}, 120); }

$("btn-upload").addEventListener("click", async () => {
  const b = $("btn-upload"); b.disabled = true;
  $("status").textContent = "上传中…";
  try {
    const r = await fetch("/upload", {method:"POST",
      headers:{"Content-Type":"application/json"}, body: JSON.stringify(params())});
    const j = await r.json();
    $("status").textContent = j.ok
      ? `✅ 上传成功：${j.pages} 块 / ${j.acks} 个 ACK，耗时 ${j.duration_s.toFixed(1)}s`
      : `❌ 失败：${j.error}`;
  } catch (e) { $("status").textContent = "❌ " + e; }
  b.disabled = false;
});

$("btn-live").addEventListener("click", async () => {
  const r = await fetch("/metrics");
  const m = await r.json();
  const set = (id, v) => { $(id).value = v; $(id).dispatchEvent(new Event("input")); };
  set("cpu", Math.round(m.cpu_percent || 0));
  set("ram", Math.round(m.memory_percent || 0));
  if (m.cpu_temperature != null) set("temp", Math.round(m.cpu_temperature));
  const k = v => v == null ? 0 : Math.min(10240, Math.round(v/1024));
  set("down", k(m.download_bytes_per_sec));
  set("up", k(m.upload_bytes_per_sec));
});
</script>
</body></html>"""


def state_from_params(params) -> StaticDisplayState:
    def f(key: str, default: float | None = None) -> float | None:
        raw = params.get(key)
        if raw is None or raw == "":
            return default
        return float(raw)

    return StaticDisplayState(
        memory_percent=f("ram", 0.0),
        cpu_percent=f("cpu", 0.0),
        cpu_temperature=f("temp"),
        download_bytes_per_sec=(f("down", 0.0) or 0.0) * 1024,
        upload_bytes_per_sec=(f("up", 0.0) or 0.0) * 1024,
    )


class DebugServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int):
        super().__init__(("127.0.0.1", port), DebugHandler)
        self._hid: Nova98Hid | None = None
        self._lock = threading.Lock()

    @property
    def hid(self) -> Nova98Hid | None:
        return self._hid

    def ensure_device(self) -> Nova98Hid:
        with self._lock:
            if self._hid is None:
                hid_dev = Nova98Hid(NOVA98)
                hid_dev.open()
                self._hid = hid_dev
            return self._hid

    def drop_device(self) -> None:
        with self._lock:
            if self._hid is not None:
                try:
                    self._hid.close()
                except OSError:
                    pass
                self._hid = None


class DebugHandler(BaseHTTPRequestHandler):
    server: DebugServer  # type: ignore[assignment]

    def log_message(self, fmt, *args):  # quieter
        logger.debug(fmt, *args)

    def _send(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: dict, status: int = 200) -> None:
        self._send(json.dumps(obj).encode(), "application/json", status)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send(PAGE.encode(), "text/html; charset=utf-8")
        elif parsed.path == "/preview.png":
            params = parse_qs(parsed.query)
            flat = {k: v[0] for k, v in params.items()}
            image = render(state_from_params(flat))
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            self._send(buf.getvalue(), "image/png")
        elif parsed.path == "/metrics":
            from nova98.metrics.service import MetricsService

            service = MetricsService()
            service.read()
            import time

            time.sleep(1.1)
            m = service.read()
            self._json(
                {
                    "cpu_percent": m.cpu_percent,
                    "memory_percent": m.memory_percent,
                    "cpu_temperature": m.cpu_temperature,
                    "download_bytes_per_sec": m.download_bytes_per_sec,
                    "upload_bytes_per_sec": m.upload_bytes_per_sec,
                }
            )
        else:
            self._send(b"not found", "text/plain", 404)

    def do_POST(self):
        if urlparse(self.path).path != "/upload":
            self._send(b"not found", "text/plain", 404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        params = json.loads(self.rfile.read(length) or b"{}")
        state = state_from_params({k: str(v) for k, v in params.items()})
        image: Image.Image = render(state)

        try:
            device = self.server.ensure_device()
        except (HidError, OSError) as exc:
            self.server.drop_device()
            self._json({"ok": False, "error": f"打开键盘失败: {exc}"})
            return

        try:
            result = upload_single_frame(image, device)
            self._json(
                {
                    "ok": True,
                    "pages": result.pages,
                    "acks": result.acks,
                    "duration_s": round(result.duration_s, 2),
                }
            )
        except (UploadError, SafetyError, OSError) as exc:
            self.server.drop_device()
            self._json({"ok": False, "error": str(exc)})


def run_debug_server(port: int = 8765) -> None:
    server = DebugServer(port)
    url = f"http://127.0.0.1:{port}"
    print(f"NOVA98 Screen 调试器运行中: {url}")
    print("Ctrl+C 停止。上传为手动触发，每次都会写一次键盘 Flash。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.drop_device()
        server.server_close()
