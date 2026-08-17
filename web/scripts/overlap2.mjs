import puppeteer from "puppeteer-core";

const browser = await puppeteer.launch({ executablePath: "/usr/bin/google-chrome-stable", headless: "new", args: ["--no-sandbox", "--disable-gpu"] });

for (const [name, width, height] of [["desktop", 1440, 1100], ["mid", 900, 1100], ["mobile", 390, 900]]) {
  const page = await browser.newPage();
  await page.setViewport({ width, height });
  await page.goto("http://localhost:8517/", { waitUntil: "domcontentloaded", timeout: 20000 });
  try { await page.waitForSelector(".glance", { timeout: 15000 }); } catch {}
  await new Promise((r) => setTimeout(r, 900));

  const overlap = await page.evaluate(() => {
    const hits = [];
    const painted = (el) => {
      const cs = getComputedStyle(el);
      const r = el.getBoundingClientRect();
      if (cs.display === "none" || cs.visibility === "hidden" || cs.opacity === "0" || r.width < 5 || r.height < 5) return false;
      for (let a = el; a; a = a.parentElement) {
        if (a.tagName === "DETAILS" && !a.open) return false;
      }
      return true;
    };
    const els = [...document.querySelectorAll("body *")].filter(painted);
    for (let i = 0; i < els.length; i++) {
      const a = els[i].getBoundingClientRect();
      for (let j = i + 1; j < els.length; j++) {
        if (els[i].contains(els[j]) || els[j].contains(els[i])) continue;
        const b = els[j].getBoundingClientRect();
        const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
        const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
        if (w > 4 && h > 4) {
          const smaller = Math.min(a.width * a.height, b.width * b.height);
          if (w * h > 0.25 * smaller) {
            const tag = (el) => `${el.tagName.toLowerCase()}.${(el.className + "").split(" ").slice(0, 2).join(".")}`;
            hits.push(`${tag(els[i])} <-> ${tag(els[j])} ${w | 0}x${h | 0} @${a.top | 0}`);
          }
        }
      }
    }
    return hits.slice(0, 14);
  });
  console.log(`\n== ${name} ==`);
  if (overlap.length) { for (const h of overlap) console.log("  VISIBLE OVERLAP:", h); }
  else console.log("  no visible overlaps");
  await page.close();
}
await browser.close();
