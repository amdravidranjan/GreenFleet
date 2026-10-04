"""Step 3 of the video pipeline: frames + narration + subtitles -> MP4.

Uses the console-logged event times from record.mjs as the single source of truth:
  * video starts at the `demo:start` event and ends at `demo:end`
  * each scene's narration clip starts at its logged `scene:<id>` time + speech_at
  * subtitles use the TTS word timings, shifted by the same logged scene time

    python build_video.py <framesDir> [out.mp4]
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

HERE = Path(__file__).resolve().parent
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
FPS = 30


def run(args, cwd=None):
    print(">", " ".join(str(a) for a in args[:6]), "...")
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args], check=True, cwd=cwd)


def srt_time(t: float) -> str:
    t = max(t, 0)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s % 1) * 1000)) % 1000:03d}"


def attach_punctuation(text: str, words: list[dict]) -> list[dict]:
    """edge-tts word tokens carry no punctuation; recover it from the script text."""
    out, i, low = [], 0, text.lower()
    for w in words:
        tok = w["w"]
        j = low.find(tok.lower(), i)
        if j < 0:
            out.append({**w, "txt": tok})
            continue
        k = j + len(tok)
        while k < len(text) and text[k] in ".,:;!?'’\"":
            k += 1
        out.append({**w, "txt": text[j:k]})
        i = k
    return out


def wrap2(s: str, width: int = 46) -> str:
    if len(s) <= width:
        return s
    mid = len(s) // 2
    cut = min((abs(m.start() - mid), m.start()) for m in re.finditer(" ", s))[1]
    return s[:cut] + "\n" + s[cut + 1:]


def cues_for_scene(text: str, words: list[dict], offset: float, display: dict) -> list[tuple[float, float, str]]:
    ws = attach_punctuation(text, words)
    cues, cur = [], []
    for k, w in enumerate(ws):
        cur.append(w)
        line = " ".join(x["txt"] for x in cur)
        end_sentence = w["txt"].endswith((".", "!", "?", ":"))
        soft = w["txt"].endswith((",", ";")) and len(line) > 42
        if end_sentence or soft or len(line) > 78 or k == len(ws) - 1:
            for a, b in display.items():
                line = line.replace(a, b)
            cues.append([offset + cur[0]["s"], offset + cur[-1]["e"] + 0.3, wrap2(line)])
            cur = []
    for a, b in zip(cues, cues[1:]):          # never overlap the next cue
        a[1] = min(a[1], b[0] - 0.05)
    return [tuple(c) for c in cues]


def main():
    fdir = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else HERE / "GreenFleet-Q_demo.mp4"
    frames = json.loads((fdir / "frames.json").read_text())
    events = {e["ev"]: e["at"] / 1000 for e in json.loads((fdir / "events.json").read_text())}
    cfg = json.loads((HERE / "narration.json").read_text(encoding="utf-8"))
    words = json.loads((HERE / "build" / "words.json").read_text())
    timeline = {s["id"]: s for s in json.loads((HERE.parent / "frontend" / "public" / "timeline.json").read_text())["scenes"]}
    t0, t1 = events["demo:start"], events["demo:end"]
    print(f"demo {t1 - t0:.2f}s, {len(frames)} frames")

    # ---- video: record.mjs already encoded a constant-30-fps video whose frame 0 is demo:start
    silent = fdir / "video_silent.mp4"
    assert silent.exists() and abs(frames[0]["ts"] - t0) < 1e-3, "expected video_silent.mp4 starting at demo:start"

    # ---- audio: each narration clip at (logged scene start - t0 + speech_at)
    inputs, filters, labels = [], [], []
    report = []
    for k, sc in enumerate(cfg["scenes"]):
        sid = sc["id"]
        at = events[f"scene:{sid}"] - t0 + timeline[sid]["speech_at"]
        report.append((sid, round(events[f"scene:{sid}"] - t0, 3)))
        inputs += ["-i", str(HERE / "build" / "audio" / f"{sid}.mp3")]
        ms = int(round(at * 1000))
        filters.append(f"[{k}:a]adelay={ms}|{ms},aresample=48000[a{k}]")
        labels.append(f"[a{k}]")
    filters.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0,apad,atrim=0:{t1 - t0:.3f}[mix]")
    audio = fdir / "narration.wav"
    run([*inputs, "-filter_complex", ";".join(filters), "-map", "[mix]", "-ac", "2", str(audio)])
    print("scene starts (s):", report)

    # ---- subtitles from TTS word timings, shifted by logged scene times
    cues = []
    for sc in cfg["scenes"]:
        off = events[f"scene:{sc['id']}"] - t0 + timeline[sc["id"]]["speech_at"]
        cues += cues_for_scene(sc["text"], words[sc["id"]], off, cfg["display"])
    srt = "\n".join(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{txt}\n" for i, (a, b, txt) in enumerate(cues, 1))
    (fdir / "subs.srt").write_text(srt, encoding="utf-8")
    out.with_suffix(".srt").write_text(srt, encoding="utf-8")

    # ---- final: burn subtitles, mux narration
    style = ("FontName=Segoe UI Semibold,FontSize=12,PrimaryColour=&H00F2EEE8,OutlineColour=&H00382210,"
             "BackColour=&H66382210,BorderStyle=3,Outline=6,Shadow=0,MarginV=10,Alignment=2")
    run(["-i", "video_silent.mp4", "-i", "narration.wav", "-vf", f"scale=in_range=pc:out_range=tv,format=yuv420p,subtitles=subs.srt:force_style='{style}'",
         "-c:v", "libx264", "-preset", "slow", "-crf", "23", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
         "-shortest", str(out)], cwd=fdir)
    print("wrote", out, f"{out.stat().st_size / 1e6:.1f} MB,", len(cues), "subtitle cues")


if __name__ == "__main__":
    main()
