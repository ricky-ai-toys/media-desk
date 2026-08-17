import puppeteer from "puppeteer-core";

const CHROME = "/usr/bin/google-chrome-stable";
const URL = "http://localhost:8517/";
const browser = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox", "--disable-gpu"] });

for (const [name, width, height] of [["desktop", 1440, 1100], ["mid", 900, 1100], ["mobile", 390, 900]]) {
  const page = await browser.newPage();
  await page.setViewport({ width, height });
  await page.goto(URL, { waitUntil: "domcontentloaded", timeout: 20000 });
  try { await page.waitForSelector(".glance", { timeout: 15000 }); } catch {}
  await new Promise((r) => setTimeout(r, 900));

  const overlap = await page.evaluate(() => {
    const hits = [];
    const vis = (el) => {
      const cs = getComputedStyle(el);
      const r = el.getBoundingClientRect();
      return cs.display !== "none" && cs.visibility !== "hidden" && r.width > 4 && r.height > 4;
    };
    const els = [...document.querySelectorAll("body *")].filter(vis);
    for (let i = 0; i < els.length; i++) {
      const a = els[i].getBoundingClientRect();
      for (let j = i + 1; j < els.length; j++) {
        if (els[i].contains(els[j]) || els[j].contains(els[i])) continue;
        const b = els[j].getBoundingClientRect();
        const x0 = Math.max(a.left, b.left), x1 = Math.min(a.right, b.right);
        const y0 = Math.max(a.top, b.top), y1 = Math.min(a.bottom, b.bottom);
        const w = x1 - x0, h = y1 - y0;
        if (w > 3 && h > 3) {
          const smaller = Math.min(a.width * a.height, b.width * b.height);
          if (w * h > 0.35 * smaller) {
            const tag = (el) => `${el.tagName.toLowerCase()}.${(el.className + "").split(" ").slice(0, 2).join(".")}`;
            hits.push(`${tag(els[i])} <-> ${tag(els[j])} ${w | 0}x${h | 0}`);
          }
        }
      }
    }
    return hits.slice(0, 12);
  });
  console.log(`\n== ${name} (${width}) ==`);
  if (overlap.length) { for (const h of overlap) console.log("  OVERLAP:", h); }
  else console.log("  no significant overlaps");
  await page.close();
}
await browser.close();
