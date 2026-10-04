"""Step 1 of the video pipeline: narration audio + word timings + scene timeline.

For every scene in narration.json this synthesises speech with edge-tts, records each word's
start/end, resolves the scene's marks (the word that should trigger an on-screen action) and
writes:
    build/audio/<scene>.mp3          narration clip
    build/words.json                 word timings per scene (seconds from clip start)
    ../frontend/public/timeline.json scene durations + marks (seconds from scene start)

    python tts.py
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import edge_tts

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
AUDIO = BUILD / "audio"
TIMELINE = HERE.parent / "frontend" / "public" / "timeline.json"


async def synth(text: str, voice: str, rate: str, out: Path) -> list[dict]:
    for attempt in range(4):
        try:
            return await _synth(text, voice, rate, out)
        except edge_tts.exceptions.NoAudioReceived:
            await asyncio.sleep(2 + 3 * attempt)
    raise RuntimeError(f"edge-tts gave no audio for {out.name}")


async def _synth(text: str, voice: str, rate: str, out: Path) -> list[dict]:
    words = []
    comm = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    with out.open("wb") as f:
        async for ch in comm.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                s = ch["offset"] / 1e7
                words.append({"w": ch["text"], "s": round(s, 3), "e": round(s + ch["duration"] / 1e7, 3)})
    return words


def norm(w: str) -> str:
    return re.sub(r"[^\w\-']", "", w).lower()


def find_mark(words: list[dict], word: str, occurrence: int) -> float:
    n = 0
    for w in words:
        if norm(w["w"]) == norm(word) or norm(w["w"]).startswith(norm(word)):
            n += 1
            if n == occurrence:
                return w["s"]
    raise KeyError(f"mark word {word!r} #{occurrence} not found in {[w['w'] for w in words]}")


async def main():
    cfg = json.loads((HERE / "narration.json").read_text(encoding="utf-8"))
    AUDIO.mkdir(parents=True, exist_ok=True)
    timeline, allwords = [], {}
    for sc in cfg["scenes"]:
        out = AUDIO / f"{sc['id']}.mp3"
        words = await synth(sc["text"], cfg["voice"], cfg["rate"], out)
        speech_end = words[-1]["e"]
        lead, tail = cfg["lead"], sc.get("tail", cfg["tail"])
        marks = {k: round(lead + find_mark(words, w, occ), 3) for k, (w, occ) in sc["marks"].items()}
        dur = round(lead + speech_end + tail, 3)
        timeline.append({"id": sc["id"], "dur": dur, "speech_at": lead, "marks": marks})
        allwords[sc["id"]] = words
        print(f"{sc['id']:10s} speech {speech_end:5.1f}s  scene {dur:5.1f}s  marks {marks}")
    TIMELINE.write_text(json.dumps({"scenes": timeline}, indent=1))
    (BUILD / "words.json").write_text(json.dumps(allwords, indent=1))
    print("total", round(sum(s["dur"] for s in timeline), 1), "s")


if __name__ == "__main__":
    asyncio.run(main())
