import puppeteer from "puppeteer-core";
import { readFileSync, writeFileSync } from "node:fs";
const browser = await puppeteer.launch({ executablePath: "/usr/bin/google-chrome-stable", headless: "new", args: ["--no-sandbox", "--disable-gpu"] });
const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 1100 });
await page.goto("http://localhost:8517/", { waitUntil: "domcontentloaded", timeout: 20000 });
try { await page.waitForSelector(".rail", { timeout: 15000 }); } catch {}
await new Promise(r => setTimeout(r, 900));
const firstTick = await page.evaluate(() => {
  const t = document.querySelector(".rail .tick");
  const s = getComputedStyle(t.querySelector("p"));
  const r = t.querySelector("p").getBoundingClientRect();
  return {
    text: t.querySelector("p").textContent.slice(0, 60),
    color: s.color, opacity: s.opacity, visible: s.visibility,
    rect: { x: r.x | 0, y: r.y | 0, w: r.width | 0, h: r.height | 0 },
    fontSize: s.fontSize,
  };
});
console.log(JSON.stringify(firstTick, null, 1));
await page.screenshot({ path: "/tmp/opencode/shots/rail-region.png", clip: { x: 1000, y: 150, width: 440, height: 900 } });
await browser.close();
