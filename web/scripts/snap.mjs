/* Dev-only visual/console check — drive the system Chrome headless. */
import puppeteer from "puppeteer-core";
import { mkdirSync } from "node:fs";

const CHROME = "/usr/bin/google-chrome-stable";
const URL = process.env.MD_URL || "http://localhost:8517/";
const out = "/tmp/opencode/shots";
mkdirSync(out, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: "new",
  args: ["--no-sandbox", "--disable-gpu", "--hide-scrollbars"],
});

const errors = [];
const cls = [];

for (const [name, viewport, fullPage] of [
  ["desktop", { width: 1440, height: 1100 }, true],
  ["mid", { width: 900, height: 1100 }, true],
  ["mobile", { width: 390, height: 900 }, true],
]) {
  const page = await browser.newPage();
  await page.setViewport(viewport);
  page.on("console", (m) => { if (m.type() === "error") errors.push(`${name}: ${m.text()}`); });
  page.on("pageerror", (e) => errors.push(`${name}: pageerror ${e.message}`));
  page.on("requestfailed", (r) => errors.push(`${name}: reqfail ${r.url()} ${r.failure()?.errorText}`));
  await page.evaluateOnNewDocument(() => {
    const obs = new PerformanceObserver((l) => {
      for (const e of l.getEntries()) {
        if (e.entryType === "layout-shift" && !e.hadRecentInput) {
          (window).__cls = ((window).__cls || 0) + e.value;
        }
      }
    });
    obs.observe({ type: "layout-shift", buffered: true });
  });
  await page.goto(URL, { waitUntil: "domcontentloaded", timeout: 20000 });
  try { await page.waitForSelector(".glance", { timeout: 15000 }); } catch { /* report below */ }
  await new Promise((r) => setTimeout(r, 900));
  cls.push(`${name}: ${(await page.evaluate(() => (window).__cls || 0)).toFixed(4)}`);
  await page.screenshot({ path: `${out}/${name}.png`, fullPage });
  const errAttr = await page.evaluate(() => document.body.getAttribute("data-err"));
  const rejAttr = await page.evaluate(() => document.body.getAttribute("data-rej"));
  if (errAttr || rejAttr) errors.push(`${name}: body attr err=${errAttr} rej=${rejAttr}`);
  const glance = await page.$$eval(".glance", (els) => els.length);
  const lead = await page.evaluate(() => document.querySelector(".lead-h")?.textContent?.slice(0, 60) || "NO LEAD");
  console.log(`${name}: ${glance} glance rows | ${lead}`);
  await page.close();
}

console.log("CLS:", cls.join(" | "));
if (errors.length) { console.log("ERRORS:"); for (const e of errors) console.log(" -", e); }
else console.log("no console/page errors");
await browser.close();
