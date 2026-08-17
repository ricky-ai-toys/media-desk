import puppeteer from "puppeteer-core";

const browser = await puppeteer.launch({ executablePath: "/usr/bin/google-chrome-stable", headless: "new", args: ["--no-sandbox", "--disable-gpu"] });
const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 1100 });
await page.goto("http://localhost:8517/", { waitUntil: "domcontentloaded", timeout: 20000 });
try { await page.waitForSelector(".glance", { timeout: 15000 }); } catch {}
await new Promise((r) => setTimeout(r, 900));

const info = await page.evaluate(() => {
  const out = [];
  [...document.querySelectorAll("details.glance")].forEach((d, i) => {
    const body = d.querySelector(".g-body");
    const r = body.getBoundingClientRect();
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    const topEl = document.elementFromPoint(cx, cy);
    const cs = getComputedStyle(body);
    const vis = getComputedStyle(body).visibility;
    out.push({
      i, open: d.open,
      bodyDisplay: cs.display, bodyVis: vis,
      bodyRect: `${r.width | 0}x${r.height | 0} @${r.top | 0}`,
      elementFromPoint: topEl ? `${topEl.tagName}.${(topEl.className + "").slice(0, 12)}` : "none",
      isBody: d.contains(topEl),
    });
  });
  return out;
});
console.log(JSON.stringify(info, null, 1));
await browser.close();
