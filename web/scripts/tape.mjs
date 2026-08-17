import puppeteer from "puppeteer-core";
const browser = await puppeteer.launch({ executablePath: "/usr/bin/google-chrome-stable", headless: "new", args: ["--no-sandbox", "--disable-gpu"] });
const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 1100 });
await page.goto("http://localhost:8517/", { waitUntil: "domcontentloaded", timeout: 20000 });
try { await page.waitForSelector(".rail", { timeout: 15000 }); } catch {}
const info = await page.evaluate(() => {
  const rail = document.querySelector(".rail");
  const secs = [...rail.querySelectorAll(".rail-sec")].map(s => ({
    label: s.querySelector(".sec-lab")?.textContent,
    ticks: s.querySelectorAll(".tick").length,
    dots: s.querySelectorAll(".tone-dot").length,
    htmlLen: s.innerHTML.length,
  }));
  return secs;
});
console.log(JSON.stringify(info, null, 1));
await browser.close();
