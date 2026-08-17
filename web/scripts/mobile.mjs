import puppeteer from "puppeteer-core";
const browser = await puppeteer.launch({ executablePath: "/usr/bin/google-chrome-stable", headless: "new", args: ["--no-sandbox", "--disable-gpu"] });
const page = await browser.newPage();
await page.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
await page.goto("http://localhost:8517/", { waitUntil: "domcontentloaded", timeout: 20000 });
try { await page.waitForSelector(".glance", { timeout: 15000 }); } catch {}
await new Promise((r) => setTimeout(r, 1000));
const m = await page.evaluate(() => {
  const rx = (el) => { const r = el.getBoundingClientRect(); return { x: r.x | 0, y: r.y | 0, w: r.width | 0, h: r.height | 0 }; };
  const wide = [];
  document.querySelectorAll("body *").forEach((el) => { const r = el.getBoundingClientRect(); if (r.right > innerWidth + 2 || r.left < -2) wide.push(`${el.tagName}.${(el.className + "").slice(0, 24)}`); });
  return {
    overflowX: document.documentElement.scrollWidth > innerWidth,
    wide: wide.slice(0, 6),
    tools: rx(document.querySelector(".tools-in")),
    mast: rx(document.querySelector(".mast-row")),
    search: rx(document.querySelector("#search")),
    leadW: document.querySelector(".lead-h").getBoundingClientRect().width | 0,
    row: rx(document.querySelector(".g-row")),

    rail: rx(document.querySelector(".rail")),
    gridCols: getComputedStyle(document.querySelector(".grid")).gridTemplateColumns,
    contact: getComputedStyle(document.querySelector(".g-row")).flexWrap,
  };
});
await page.screenshot({ path: "/tmp/opencode/shots/mobile-tap.png" });
console.log(JSON.stringify(m, null, 1));
if (errors.length) console.log("ERRORS:", errors);
await browser.close();
