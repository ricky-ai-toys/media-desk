import puppeteer from "puppeteer-core";

const browser = await puppeteer.launch({ executablePath: "/usr/bin/google-chrome-stable", headless: "new", args: ["--no-sandbox", "--disable-gpu"] });
const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 1100 });
await page.goto("http://localhost:8517/", { waitUntil: "domcontentloaded", timeout: 20000 });
try { await page.waitForSelector(".glance", { timeout: 15000 }); } catch {}
await new Promise((r) => setTimeout(r, 900));

const info = await page.evaluate(() => {
  return [...document.querySelectorAll(".list-row")].slice(0, 3).map((row) => {
    const children = [...row.children].map((el) => {
      const r = el.getBoundingClientRect();
      return {
        tag: el.tagName.toLowerCase(),
        cls: (el.className + "").slice(0, 18),
        text: (el.textContent || "").slice(0, 40),
        x: r.left | 0, w: r.width | 0, top: r.top | 0, h: r.height | 0,
        disp: getComputedStyle(el).display,
      };
    });
    return children;
  });
});
console.log(JSON.stringify(info, null, 1));
await browser.close();
