// Step 2 of the video pipeline: render the demo frame by frame in Chrome.
//
// The page runs on a virtual clock (window.__setClock). For every video frame we set the clock to
// T0 + k/30 s, let React/deck.gl/MapLibre draw, and take a screenshot — so the video is perfectly
// smooth whatever the machine speed. Every on-screen action is logged by the page to the Chrome
// console as `[DEMO] {"ev": ..., "at": <virtual ms>}`; we collect those logs, and build_video.py
// places narration and subtitles at exactly those times. Frames are piped straight into ffmpeg
// (no frame files on disk).
//
//   node record.mjs <outDir> [url]
import { chromium } from "playwright-core";
import { mkdirSync, writeFileSync, rmSync } from "node:fs";
import { execSync, spawn } from "node:child_process";
import path from "node:path";

const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const FPS = 30;
const outDir = process.argv[2];
const url = process.argv[3] ?? "http://localhost:5173/?demo=1";
if (!outDir) throw new Error("usage: node record.mjs <outDir> [url]");
rmSync(outDir, { recursive: true, force: true });
mkdirSync(outDir, { recursive: true });
const FFMPEG = execSync('python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"').toString().trim();

const browser = await chromium.launch({
  executablePath: CHROME, headless: false,
  args: ["--window-size=1920,1160", "--force-device-scale-factor=1", "--hide-scrollbars", "--disable-infobars",
    "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding", "--disable-background-timer-throttling",
    "--disable-features=CalculateNativeWinOcclusion"],
});
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });

const events = [];
page.on("console", (m) => {
  const t = m.text();
  if (t.startsWith("[DEMO] ")) events.push(JSON.parse(t.slice(7)));
  else if (m.type() === "error") console.log("console error:", t.slice(0, 160));
});
page.on("pageerror", (e) => console.log("PAGEERROR", e.message));

await page.goto(url, { waitUntil: "networkidle" });
await page.waitForFunction(() => window.__demoReady === true && (window.__mapReady ?? 0) >= 1, null, { timeout: 60000 });
await page.evaluate(() => document.fonts.ready);
await page.waitForTimeout(4000);

const cdp = await page.context().newCDPSession(page);
const settle = () => page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r(null)))));
const T0 = Date.now();
await page.evaluate((t) => window.__setClock(t), T0);
events.length = 0;
await page.evaluate(() => window.__startDemo());
await settle();
await page.waitForTimeout(1500);

const enc = spawn(FFMPEG, ["-hide_banner", "-loglevel", "error", "-y", "-f", "image2pipe", "-framerate", String(FPS), "-c:v", "mjpeg",
  "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", path.join(outDir, "video_silent.mp4")],
  { stdio: ["pipe", "inherit", "inherit"] });
const encDone = new Promise((r) => enc.on("close", r));
const push = (buf) => new Promise((r) => (enc.stdin.write(buf) ? r(null) : enc.stdin.once("drain", r)));
const frames = [];
let scenes = 0, endFrame = null;
const wall = Date.now();
for (let k = 0; ; k++) {
  const t = T0 + (k * 1000) / FPS;
  await page.evaluate((ms) => window.__setClock(ms), t);
  await settle();
  const sc = events.filter((e) => e.ev.startsWith("scene:")).length;
  if (sc !== scenes) {            // new scene: give freshly mounted maps time to fetch tiles
    scenes = sc;
    await page.waitForTimeout(1500);
    await settle();
  }
  const shot = await cdp.send("Page.captureScreenshot", { format: "jpeg", quality: 92 });
  await push(Buffer.from(shot.data, "base64"));
  frames.push({ ts: t / 1000 });
  if (endFrame === null && events.some((e) => e.ev === "demo:end")) endFrame = k;
  if (endFrame !== null && k >= endFrame + FPS / 2) break;
  if (k % 300 === 0) {
    const last = events.filter((e) => e.ev.startsWith("scene:")).pop();
    console.log(`frame ${k} (${(k / FPS).toFixed(1)} s video, ${((Date.now() - wall) / 1000).toFixed(0)} s wall) ${last?.ev ?? ""}`);
  }
}
enc.stdin.end();
await encDone;
writeFileSync(path.join(outDir, "frames.json"), JSON.stringify(frames));
writeFileSync(path.join(outDir, "events.json"), JSON.stringify(events, null, 1));
for (const e of events) console.log(`${((e.at - T0) / 1000).toFixed(3).padStart(8)} s  ${e.ev}`);
console.log(`rendered ${frames.length} frames in ${((Date.now() - wall) / 1000).toFixed(0)} s`);
await browser.close();
