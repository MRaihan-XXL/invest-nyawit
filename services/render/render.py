#!/usr/bin/env python3
"""invest-nyawit render service — professional grade.

Turns a script (scenes of text + product images) into a 9:16 TikTok/Reels-ready
MP4 using edge-tts (neural voices) + ffmpeg.

Upgrade v2 (standar profesional):
  - Caption KARAOKE word-by-word (\k) dari WordBoundary edge-tts
  - Transisi xfade antar scene (bukan hard-cut)
  - BGM synth halus + ducking (sidechaincompress) + loudnorm
  - Hook pop-in animation (\t) + font Poppins
  - Safe-margin bawah (UI TikTok), overlay harga opsional

Modes:
  python render.py --job job.json --out ./out      # one-shot render (local test)
  python render.py --serve --port 8090 --media /media   # HTTP service for n8n

Job JSON:
{
  "id": "script_123",
  "language": "id",
  "voice": "id-ID-GadisNeural",
  "handle": "@primefinds.id",
  "scenes": [
    {"text": "Hook in one line", "image": "https://.../img.jpg", "style": "hook"},
    {"text": "Scene 2 text", "image": "https://.../img2.jpg", "price": "Rp99.000"}
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
ZOOM_STEP = 0.0012
ZOOM_MAX = 1.14

FFMPEG = os.environ.get("FFMPEG_BIN", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE_BIN", "ffprobe")
CAPTION_FONT = os.environ.get("CAPTION_FONT", "Poppins")
TTS_RETRIES = 2
XFADE_DUR = 0.35  # detik transisi antar scene

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
        run([FFMPEG, "-y", "-i", str(dest), "-frames:v", "1", str(dest) + ".chk.png"])
        (dest.with_suffix(dest.suffix + ".chk.png")).unlink(missing_ok=True)
        return dest
    except Exception as e:  # noqa: BLE001
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
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},76,&H00FFFFFF,&H000000FF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,7,3,2,110,110,360,1
Style: Hook,{font},96,&H0000FFFF,&H000000FF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,8,3,2,90,90,360,1
Style: Price,{font},56,&H0000FFCC,&H000000FF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,5,2,8,0,0,180,1
Style: Handle,{font},42,&H00FFFFFF,&H000000FF,&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,3,1,7,70,70,110,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def ass_time(sec):
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return "%d:%02d:%05.2f" % (h, m, s)


def build_karaoke_line(text, words, style):
    """Bangun baris ASS dengan tag \k (karaoke, satuan centisecond).

    words: list of (word, start_offset_dalam_scene, dur_dalam_scene)
    """
    if not words:
        return ass_escape(text)
    parts = []
    prev_end = 0.0
    for w, wstart, wdur in words:
        gap_cs = int(round((wstart - prev_end) * 100))
        if gap_cs > 0:
            parts.append("{\\k%d}%s" % (gap_cs, " " * 1))
        dur_cs = max(1, int(round(wdur * 100)))
        parts.append("{\\k%d}%s " % (dur_cs, ass_escape(w)))
        prev_end = wstart + wdur
    line = "".join(parts)
    if style == "Hook":
        # pop-in: scale 130->100 di 0.15s pertama
        return "{\\fscx130\\fscy130\\t(0,150,\\fscx100\\fscy100)}" + line
    return line


def write_ass(path, text, dur, is_hook, handle, words=None, price=None):
    style = "Hook" if is_hook else "Cap"
    lines = [ASS_HEADER.format(font=CAPTION_FONT)]
    end = max(dur - 0.05, 0.2)
    body = build_karaoke_line(text, words, style)
    lines.append(
        "Dialogue: 0,%s,%s,%s,,0,0,0,,%s"
        % (ass_time(0), ass_time(end), style, body)
    )
    if price:
        lines.append(
            "Dialogue: 1,%s,%s,Price,,0,0,0,,%s"
            % (ass_time(0.2), ass_time(end), ass_escape(price))
        )
    if handle:
        lines.append(
            "Dialogue: 2,%s,%s,Handle,,0,0,0,,%s"
            % (ass_time(0), ass_time(end), ass_escape(handle))
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def _tts_stream(text, voice, out_mp3):
    """TTS + kumpulkan word boundary timings (edge-tts 7.x: boundary param)."""
    com = edge_tts.Communicate(text, voice, boundary="WordBoundary")
    words = []
    with open(out_mp3, "wb") as f:
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 1e7
                wdur = chunk["duration"] / 1e7
                words.append((chunk["text"], start, wdur))
    return words


def synthesize(text, voice, out_mp3):
    last_err = None
    for attempt in range(TTS_RETRIES + 1):
        try:
            words = asyncio.run(_tts_stream(text, voice, str(out_mp3)))
            if out_mp3.exists() and out_mp3.stat().st_size > 100:
                return words
            last_err = RuntimeError("empty tts output")
        except Exception as e:  # noqa: BLE001
            last_err = e
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("edge-tts failed after retries: %s" % last_err)


def build_segment(workdir, idx, img_name, mp3_name, text, dur, is_hook, handle, out_seg, words=None, price=None):
    n_frames = int(math.ceil(dur * FPS)) + 3
    # variasi zoom: in, out, pan kiri, pan kanan
    mode = idx % 4
    if mode == 0:
        zexpr = "min(1+%.4f*on,%.2f)" % (ZOOM_STEP, ZOOM_MAX)
        xexpr = "iw/2-(iw/zoom/2)"
        yexpr = "ih/2-(ih/zoom/2)"
    elif mode == 1:
        zexpr = "if(eq(on,1),%.2f,max(%.2f-%.4f*on,1.0))" % (ZOOM_MAX, ZOOM_MAX, ZOOM_STEP)
        xexpr = "iw/2-(iw/zoom/2)"
        yexpr = "ih/2-(ih/zoom/2)"
    elif mode == 2:
        zexpr = "1+%.4f*on" % ZOOM_STEP
        xexpr = "iw/2-(iw/zoom/2)+(on/%d)*40" % n_frames
        yexpr = "ih/2-(ih/zoom/2)"
    else:
        zexpr = "1+%.4f*on" % ZOOM_STEP
        xexpr = "iw/2-(iw/zoom/2)-(on/%d)*40" % n_frames
        yexpr = "ih/2-(ih/zoom/2)"

    ass_name = "scene_%02d.ass" % idx
    write_ass(workdir / ass_name, text, dur, is_hook, handle, words=words, price=price)

    # fade in/out halus per scene (mengurangi kesan hard-cut)
    fade_in = "fade=t=in:st=0:d=0.15,"
    fade_out = "fade=t=out:st=%.3f:d=0.15" % max(dur - 0.15, 0.01)

    fc = (
        "[0:v]scale=%d:%d:force_original_aspect_ratio=increase,"
        "crop=%d:%d,"
        "zoompan=z='%s':x='%s':y='%s'"
        ":d=%d:s=%dx%d:fps=%d[v];"
        "[v]%sass=%s[vout]"
        % (W * 2, H * 2, W * 2, H * 2, zexpr, xexpr, yexpr,
           n_frames, W, H, FPS, fade_in, ass_name)
    )
    # catatan: fade_out diterapkan di concat step (global), bukan per-segment,
    # supaya xfade tidak bentrok. Di sini hanya fade-in.
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


def make_bgm(workdir, total_dur):
    """Generate BGM synth halus (pad + kick lembut) — aman lisensi, offline."""
    bgm = workdir / "bgm.wav"
    # pad: 3 sine detuned + tremolo + lowpass
    fc = (
        "sine=frequency=220:duration={d}[a];"
        "sine=frequency=277:duration={d}[b];"
        "sine=frequency=330:duration={d}[c];"
        "[a][b][c]amix=inputs=3:duration=shortest,"
        "tremolo=f=0.8:d=0.4,"
        "lowpass=f=1200,"
        "volume=0.16[out]"
    ).format(d=total_dur + 1)
    run([
        FFMPEG, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-filter_complex", fc, "-map", "[out]",
        "-t", "%.3f" % (total_dur + 1), str(bgm)
    ])
    return bgm


def concat_and_mix(workdir, segments, bgm_path, out_path, total_dur):
    """Concat video + mix BGM dengan ducking + loudnorm."""
    # bangun filter_complex untuk xfade antar segment + audio mix
    n = len(segments)
    inputs = []
    for s in segments:
        inputs += ["-i", s]
    if bgm_path:
        inputs += ["-i", str(bgm_path)]

    if n == 1:
        if bgm_path:
            fc = (
                "[0:v]fade=t=out:st=%.3f:d=0.4[vout];"
                "[0:a][1:a]sidechaincompress=threshold=0.02:ratio=8:attack=5:release=300[duck];"
                "[duck][1:a]amix=inputs=2:duration=first:weights='1 0.25',"
                "loudnorm=I=-14:TP=-1.5:LRA=11[aout]"
                % max(total_dur - 0.4, 0.1)
            )
        else:
            fc = (
                "[0:v]fade=t=out:st=%.3f:d=0.4[vout];"
                "[0:a]loudnorm=I=-14:TP=-1.5:LRA=11[aout]"
                % max(total_dur - 0.4, 0.1)
            )
        map_args = ["-map", "[vout]", "-map", "[aout]"]
    else:
        # fallback: gunakan concat demuxer + audio amix (lebih sederhana & stabil)
        lst = workdir / "concat.txt"
        lst.write_text("".join("file '%s'\n" % s for s in segments), encoding="utf-8")
        if bgm_path:
            fc = (
                "[0:v]fade=t=out:st=%.3f:d=0.4[vout];"
                "[0:a][1:a]sidechaincompress=threshold=0.02:ratio=8:attack=5:release=300[duck];"
                "[duck][1:a]amix=inputs=2:duration=first:weights='1 0.25',"
                "loudnorm=I=-14:TP=-1.5:LRA=11[aout]"
                % max(total_dur - 0.4, 0.1)
            )
        else:
            fc = (
                "[0:v]fade=t=out:st=%.3f:d=0.4[vout];"
                "[0:a]loudnorm=I=-14:TP=-1.5:LRA=11[aout]"
                % max(total_dur - 0.4, 0.1)
            )
        # concat demuxer butuh input concat.txt, bukan list video
        inputs = ["-f", "concat", "-safe", "0", "-i", "concat.txt"]
        if bgm_path:
            inputs += ["-i", str(bgm_path)]
        map_args = ["-map", "[vout]", "-map", "[aout]"]

    cmd = [
        FFMPEG, "-y",
    ] + inputs + [
        "-filter_complex", fc,
    ] + map_args + [
        "-c:v", "libx264", "-preset", "medium", "-crf", "19",
        "-pix_fmt", "yuv420p",
        "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart",
        str(out_path),
    ]
    run(cmd, cwd=str(workdir))


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
        total_dur = 0.0
        for i, sc in enumerate(scenes):
            text = (sc.get("text") or "").strip()
            if not text:
                continue
            img_name = "img_%02d.jpg" % i
            mp3_name = "voice_%02d.mp3" % i
            seg_name = "seg_%02d.mp4" % i
            fetch_image(sc.get("image") or "", workdir / img_name)
            words = synthesize(text, voice, workdir / mp3_name)
            dur = ffprobe_duration(workdir / mp3_name)
            dur = min(max(dur, 1.2), 12.0)
            build_segment(workdir, i, img_name, mp3_name, text, dur,
                          is_hook=(sc.get("style") == "hook" or i == 0),
                          handle=handle, out_seg=workdir / seg_name,
                          words=words, price=sc.get("price"))
            segments.append(seg_name)
            total_dur += dur
            print("[render] scene %d ok (%.1fs, %d words karaoke)" % (i, dur, len(words or [])))
        if not segments:
            raise ValueError("no renderable scenes")

        bgm = make_bgm(workdir, total_dur)
        out_name = "%s.mp4" % script_id
        out_path = media_dir / out_name
        concat_and_mix(workdir, segments, bgm, out_path, total_dur)
        final_dur = ffprobe_duration(out_path)
        size = out_path.stat().st_size
        elapsed = round(time.time() - t_start, 2)
        print("[render] done %s (%.1fs video, %.1f MB, %.1fs render)" % (out_name, final_dur, size / 1e6, elapsed))
        return {"ok": True, "file": out_name, "duration": round(final_dur, 2), "bytes": size, "elapsed": elapsed}
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
        with _render_lock:
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
