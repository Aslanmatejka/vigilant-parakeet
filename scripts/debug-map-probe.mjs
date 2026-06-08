import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const LOG_PATH = path.join(__dirname, '..', 'debug-bf1680.log');
const BASE_URL = process.env.MAP_PROBE_URL || 'http://127.0.0.1:5173';

function writeLog(entry) {
  fs.appendFileSync(LOG_PATH, `${JSON.stringify({ sessionId: 'bf1680', runId: 'probe-script', timestamp: Date.now(), ...entry })}\n`);
}

async function probe(page, trigger, viewportLabel) {
  return page.evaluate((triggerLabel) => {
    const rectsOverlap = (a, b) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
    const root = document.querySelector('.dogoods-food-map');
    const zoomEl = document.querySelector('.dogoods-food-map-zoom');
    const legendEl = document.querySelector('.dogoods-food-map-legend');
    if (!root || !zoomEl || !legendEl) {
      return { trigger: triggerLabel, missing: { root: !root, zoom: !zoomEl, legend: !legendEl } };
    }
    const rootRect = root.getBoundingClientRect();
    const zoomRect = zoomEl.getBoundingClientRect();
    const legendRect = legendEl.getBoundingClientRect();
    const zoomBtn = zoomEl.querySelector('button');
    const sampleAt = (el, label) => {
      const r = el.getBoundingClientRect();
      const cx = Math.round(r.left + r.width / 2);
      const cy = Math.round(r.top + r.height / 2);
      const topEl = document.elementFromPoint(cx, cy);
      return {
        label,
        cx,
        cy,
        topTag: topEl?.tagName || null,
        topClass: typeof topEl?.className === 'string' ? topEl.className.slice(0, 120) : null,
        hitSelf: !!(topEl && (el === topEl || el.contains(topEl))),
      };
    };
    const header = document.querySelector('header');
    const headerRect = header?.getBoundingClientRect();
    const fixedUi = [...document.querySelectorAll('.fixed')]
      .map((el) => {
        const r = el.getBoundingClientRect();
        if (r.width < 8 || r.height < 8) return null;
        return {
          tag: el.tagName,
          cls: typeof el.className === 'string' ? el.className.slice(0, 100) : '',
          overlapsZoom: rectsOverlap(r, zoomRect),
          overlapsLegend: rectsOverlap(r, legendRect),
          rect: { t: Math.round(r.top), b: Math.round(r.bottom), l: Math.round(r.left), r: Math.round(r.right) },
        };
      })
      .filter(Boolean);
    const rootStyle = window.getComputedStyle(root);
    const zoomStyle = window.getComputedStyle(zoomEl);
    return {
      trigger: triggerLabel,
      viewport: { w: window.innerWidth, h: window.innerHeight, scrollY: window.scrollY },
      zoomHit: sampleAt(zoomBtn || zoomEl, 'zoom'),
      legendHit: sampleAt(legendEl, 'legend'),
      zoomZ: zoomStyle.zIndex,
      legendZ: window.getComputedStyle(legendEl).zIndex,
      rootOverflow: rootStyle.overflow,
      clipZoom: zoomRect.top < rootRect.top - 1 || zoomRect.bottom > rootRect.bottom + 1 || zoomRect.left < rootRect.left - 1 || zoomRect.right > rootRect.right + 1,
      clipLegend: legendRect.top < rootRect.top - 1 || legendRect.bottom > rootRect.bottom + 1 || legendRect.left < rootRect.left - 1 || legendRect.right > rootRect.right + 1,
      headerOverlapsZoom: headerRect ? rectsOverlap(headerRect, zoomRect) : false,
      headerOverlapsLegend: headerRect ? rectsOverlap(headerRect, legendRect) : false,
      fixedUi,
      zoomBlockedByFixed: fixedUi.some((f) => f.overlapsZoom),
      legendBlockedByFixed: fixedUi.some((f) => f.overlapsLegend),
    };
  }, trigger);
}

async function main() {
  const puppeteer = await import('puppeteer');
  const browser = await puppeteer.default.launch({ headless: 'new' });
  const page = await browser.newPage();

  const scenarios = [
    { width: 1280, height: 900, label: 'desktop' },
    { width: 390, height: 844, label: 'mobile' },
  ];

  for (const scenario of scenarios) {
    await page.setViewport({ width: scenario.width, height: scenario.height });
    await page.goto(`${BASE_URL}/find`, { waitUntil: 'networkidle2', timeout: 60000 });
    await page.waitForSelector('.dogoods-food-map-zoom', { timeout: 60000 }).catch(() => null);
    await page.waitForTimeout(3000);

    const idle = await probe(page, `${scenario.label}-idle`, scenario.label);
    writeLog({ hypothesisId: 'ALL', location: 'scripts/debug-map-probe.mjs', message: 'layout probe idle', data: idle });

    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight / 2));
    await page.waitForTimeout(500);
    const scrolled = await probe(page, `${scenario.label}-scrolled`, scenario.label);
    writeLog({ hypothesisId: 'D', location: 'scripts/debug-map-probe.mjs', message: 'layout probe scrolled', data: scrolled });

    const chatBtn = await page.$('[aria-label="Open Nouri AI Assistant"]');
    if (chatBtn) {
      await chatBtn.click();
      await page.waitForTimeout(800);
      const chatOpen = await probe(page, `${scenario.label}-chat-open`, scenario.label);
      writeLog({ hypothesisId: 'F', location: 'scripts/debug-map-probe.mjs', message: 'layout probe chat open', data: chatOpen });
    }
  }

  await browser.close();
  console.log(`Wrote probe logs to ${LOG_PATH}`);
}

main().catch((err) => {
  writeLog({ hypothesisId: 'ERR', location: 'scripts/debug-map-probe.mjs', message: 'probe failed', data: { error: String(err) } });
  console.error(err);
  process.exit(1);
});
