import puppeteer from "puppeteer-core";

const browser = await puppeteer.launch({ executablePath: "/usr/bin/google-chrome-stable", headless: "new", args: ["--no-sandbox", "--disable-gpu"] });
const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 1100 });
await page.goto("http://localhost:8517/", { waitUntil: "domcontentloaded", timeout: 20000 });
try { await page.waitForSelector(".glance", { timeout: 15000 }); } catch {}
await new Promise((r) => setTimeout(r, 900));

const info = await page.evaluate(() => {
  return [...document.querySelectorAll("details.glance")].map((d, i) => {
    const s = d.querySelector("summary");
    const b = d.querySelector(".g-body");
    const sr = s.getBoundingClientRect(), br = b.getBoundingClientRect();
    return {
      i, open: d.open, title: (d.querySelector(".g-title")?.textContent || "").slice(0, 24),
      sum: { top: sr.top | 0, bottom: sr.bottom | 0, h: sr.height | 0 },
      body: { top: br.top | 0, bottom: br.bottom | 0, h: br.height | 0, display: getComputedStyle(b).display },
      gap: (br.top - sr.bottom) | 0,
    };
  });
});
console.log(JSON.stringify(info, null, 1));
await browser.close();
