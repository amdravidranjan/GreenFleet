// Quick visual check: open each scene and screenshot it at a few points in time.
//   node shots.mjs [outDir] [sceneIndex...]
import { chromium } from "playwright-core";
import { mkdirSync } from "node:fs";

const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const out = process.argv[2] ?? "shots";
const only = process.argv.slice(3).map(Number);
mkdirSync(out, { recursive: true });

const browser = await chromium.launch({ executablePath: CHROME, headless: false, args: ["--window-size=1920,1080", "--force-device-scale-factor=1"] });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
page.on("console", (m) => { if (m.text().startsWith("[DEMO]") || m.type() === "error") console.log(m.type(), m.text().slice(0, 200)); });
page.on("pageerror", (e) => console.log("PAGEERROR", e.message));
await page.goto(process.env.SHOTS_URL ?? "http://localhost:5173/", { waitUntil: "networkidle" });
await page.waitForFunction(() => window.__demoReady === true);
await page.waitForTimeout(2500);
const buttons = page.locator(".nav button");
const n = await buttons.count();
for (let i = 0; i < n; i++) {
  if (only.length && !only.includes(i)) continue;
  await buttons.nth(i).click();
  for (const s of [3, 9, 17]) {
    await page.waitForTimeout(s === 3 ? 3000 : s === 9 ? 6000 : 8000);
    await page.screenshot({ path: `${out}/s${String(i).padStart(2, "0")}_${s}s.jpg`, quality: 70 });
  }
}
await browser.close();
