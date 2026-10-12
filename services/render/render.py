#!/usr/bin/env python3
"""invest-nyawit render service.

Turns a script (scenes of text + product images) into a 9:16 TikTok/Reels-ready
MP4 using edge-tts (free neural voices) + ffmpeg slideshow (Ken Burns zoom).

Modes:
  python render.py --job job.json --out ./out      # one-shot render (local test)
  python render.py --serve --port 8090 --media /media   # HTTP service for n8n

Job JSON:
{
  "id": "script_123",
  "language": "id",
  "voice": "id-ID-GadisNeural",
  "handle": "@primefinds.id",        # optional watermark, top-left
  "scenes": [
    {"text": "Hook in one line", "image": "https://.../img.jpg", "style": "hook"},
    {"text": "Scene 2 text", "image": "https://.../img2.jpg"}
  ]
}
"""

import argparse
import asyncio
import json
import math
import os
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import edge_tts

W, H, FPS = 1080, 1920, 30
MAX_IMG_BYTES = 25 * 1024 * 1024
ZOOM_STEP = 0.0015   # zoom increment per frame
ZOOM_MAX = 1.18

FFMPEG = os.environ.get("FFMPEG_BIN", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE_BIN", "ffprobe")
CAPTION_FONT = os.environ.get("CAPTION_FONT", "Arial")
TTS_RETRIES = 2

# ---------------------------------------------------------------- helpers

def run(cmd, cwd=None):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(
            "ffmpeg failed (%d):\nCMD: %s\nSTDERR: %s"
            % (p.returncode, " ".join(cmd), p.stderr[-2000:])
        )
    return p


def ffprobe_duration(path):
    p = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(p.stdout.strip())
    except ValueError:
        raise RuntimeError("ffprobe duration failed for %s: %s" % (path, p.stderr))


def fetch_image(url_or_path, dest):
    """Download URL to dest, or copy local path. Fallback: solid placeholder."""
    try:
        if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
            req = urllib.request.Request(
                url_or_path,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read(MAX_IMG_BYTES)
            dest.write_bytes(data)
        else:
            dest.write_bytes(Path(url_or_path).read_bytes())
        # verify it is a decodable image
        run([FFMPEG, "-y", "-i", str(dest), "-frames:v", "1", str(dest) + ".chk.png"])
        (dest.with_suffix(dest.suffix + ".chk.png")).unlink(missing_ok=True)
        return dest
    except Exception as e:  # noqa: BLE001 - fallback is the point
        print("[warn] image fetch failed (%s): %s -> placeholder" % (url_or_path, e))
        run([FFMPEG, "-y", "-f", "lavfi",
             "-i", "color=c=0x16213e:s=%dx%d" % (W * 2, H * 2),
             "-frames:v", "1", str(dest)])
        return dest


def ass_escape(text):
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", "\\N")


ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},72,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,2,2,120,120,340,1
Style: Hook,{font},90,&H0000FFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,2,2,90,90,340,1
Style: Handle,{font},40,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,3,1,7,70,70,110,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def ass_time(sec):
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return "%d:%02d:%05.2f" % (h, m, s)


def write_ass(path, text, dur, is_hook, handle):
    style = "Hook" if is_hook else "Cap"
    lines = [ASS_HEADER.format(font=CAPTION_FONT)]
    lines.append(
        "Dialogue: 0,%s,%s,%s,,0,0,0,,%s"
        % (ass_time(0), ass_time(max(dur - 0.05, 0.2)), style, ass_escape(text))
    )
    if handle:
        lines.append(
            "Dialogue: 1,%s,%s,Handle,,0,0,0,,%s"
            % (ass_time(0), ass_time(max(dur - 0.05, 0.2)), ass_escape(handle))
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def synthesize(text, voice, out_mp3):
    last_err = None
    for attempt in range(TTS_RETRIES + 1):
        try:
            asyncio.run(_tts_once(text, voice, out_mp3))
            if out_mp3.exists() and out_mp3.stat().st_size > 100:
                return
            last_err = RuntimeError("empty tts output")
        except Exception as e:  # noqa: BLE001
            last_err = e
        import time as _t
        _t.sleep(1.5 * (attempt + 1))
    raise RuntimeError("edge-tts failed after retries: %s" % last_err)


async def _tts_once(text, voice, out_mp3):
    com = edge_tts.Communicate(text, voice)
    await com.save(str(out_mp3))


def build_segment(workdir, idx, img_name, mp3_name, text, dur, is_hook, handle, out_seg):
    n_frames = int(math.ceil(dur * FPS)) + 3
    if idx % 2 == 0:
        zexpr = "min(1+%.4f*on,%.2f)" % (ZOOM_STEP, ZOOM_MAX)
    else:
        zexpr = "if(eq(on,1),%.2f,max(%.2f-%.4f*on,1.0))" % (ZOOM_MAX, ZOOM_MAX, ZOOM_STEP)
    ass_name = "scene_%02d.ass" % idx
    write_ass(workdir / ass_name, text, dur, is_hook, handle)
    fc = (
        "[0:v]scale=%d:%d:force_original_aspect_ratio=increase,"
        "crop=%d:%d,"
        "zoompan=z='%s':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        ":d=%d:s=%dx%d:fps=%d[v];"
        "[v]ass=%s[vout]"
        % (W * 2, H * 2, W * 2, H * 2, zexpr, n_frames, W, H, FPS, ass_name)
    )
    run([
        FFMPEG, "-y", "-i", img_name, "-i", mp3_name,
        "-filter_complex", fc,
        "-map", "[vout]", "-map", "1:a",
        "-t", "%.3f" % dur, "-r", str(FPS),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "44100", "-ac", "2",
        str(out_seg),
    ], cwd=str(workdir))


def render_job(job, media_dir):
    t_start = time.time()
    script_id = str(job.get("id") or "job")
    scenes = job.get("scenes") or []
    if len(scenes) < 2:
        raise ValueError("job.scenes must have >= 2 scenes")
    voice = job.get("voice") or ("id-ID-GadisNeural" if job.get("language") == "id" else "en-US-JennyNeural")
    handle = job.get("handle") or ""

    media_dir = Path(media_dir)
    media_dir.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix="render_%s_" % script_id))
    try:
        segments = []
        for i, sc in enumerate(scenes):
            text = (sc.get("text") or "").strip()
            if not text:
                continue
            img_name = "img_%02d.jpg" % i
            mp3_name = "voice_%02d.mp3" % i
            seg_name = "seg_%02d.mp4" % i
            fetch_image(sc.get("image") or "", workdir / img_name)
            synthesize(text, voice, workdir / mp3_name)
            dur = ffprobe_duration(workdir / mp3_name)
            dur = min(max(dur, 1.2), 12.0)  # clamp: hook punchy, scenes readable
            build_segment(workdir, i, img_name, mp3_name, text, dur,
                          is_hook=(sc.get("style") == "hook" or i == 0), handle=handle,
                          out_seg=workdir / seg_name)
            segments.append(seg_name)
            print("[render] scene %d ok (%.1fs)" % (i, dur))
        if not segments:
            raise ValueError("no renderable scenes")

        lst = workdir / "concat.txt"
        lst.write_text("".join("file '%s'\n" % s for s in segments), encoding="utf-8")
        out_name = "%s.mp4" % script_id
        out_path = media_dir / out_name
        run([
            FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", "concat.txt",
            "-c:v", "libx264", "-preset", "medium", "-crf", "19",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
            "-movflags", "+faststart",
            str(out_path),
        ], cwd=str(workdir))
        total = ffprobe_duration(out_path)
        size = out_path.stat().st_size
        elapsed = round(time.time() - t_start, 2)
        print("[render] done %s (%.1fs video, %.1f MB, %.1fs render)" % (out_name, total, size / 1e6, elapsed))
        return {"ok": True, "file": out_name, "duration": round(total, 2), "bytes": size, "elapsed": elapsed}
    finally:
        if os.environ.get("RENDER_KEEP_TMP") != "1":
            import shutil
            shutil.rmtree(workdir, ignore_errors=True)


# ---------------------------------------------------------------- http server

_render_lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    media_dir = "./media"

    def log_message(self, fmt, *args):
        print("[http] %s - %s" % (self.address_string(), fmt % args))

    def _json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            return self._json(200, {"ok": True, "service": "invest-nyawit-render"})
        if self.path.startswith("/media/"):
            name = os.path.basename(self.path)
            fpath = Path(self.media_dir) / name
            if fpath.exists() and fpath.is_file():
                data = fpath.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
        self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if self.path != "/render":
            return self._json(404, {"ok": False, "error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            job = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            return self._json(400, {"ok": False, "error": "bad request: %s" % e})
        with _render_lock:  # one render at a time on a small VPS
            try:
                result = render_job(job, self.media_dir)
                return self._json(200, result)
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                return self._json(500, {"ok": False, "error": str(e)})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", help="job JSON file (one-shot mode)")
    ap.add_argument("--out", default="./out", help="output dir (one-shot mode)")
    ap.add_argument("--serve", action="store_true", help="run HTTP service")
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--media", default="./media", help="media dir (serve mode)")
    args = ap.parse_args()

    if args.serve:
        Handler.media_dir = args.media
        srv = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
        print("[serve] invest-nyawit render on :%d, media=%s" % (args.port, args.media))
        srv.serve_forever()
        return

    if not args.job:
        ap.error("--job required unless --serve")
    job = json.loads(Path(args.job).read_text(encoding="utf-8"))
    result = render_job(job, args.out)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
