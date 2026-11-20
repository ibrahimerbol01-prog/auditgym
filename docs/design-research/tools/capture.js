// Capture design samples: screenshots at 1440x900 (+ full page) and 390x844, plus measured design tokens.
// Usage: node capture.js <targets.json> <outdir>
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const [targetsFile, outDir] = process.argv.slice(2);
const targets = JSON.parse(fs.readFileSync(targetsFile, 'utf8'));
const shotDir = path.join(outDir, 'shots');
const dataDir = path.join(outDir, 'data');
fs.mkdirSync(shotDir, { recursive: true });
fs.mkdirSync(dataDir, { recursive: true });

const slug = s => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
const CONSENT = /^(accept all|accept all cookies|accept|accept cookies|allow all|allow all cookies|agree|i agree|i accept|got it|ok|okay|continue|reject all|decline|only necessary|necessary only)$/i;

async function dismissBanners(page) {
  for (const frame of page.frames()) {
    try {
      const buttons = await frame.$$('button, [role=button], a');
      for (const b of buttons.slice(0, 300)) {
        const t = ((await b.innerText().catch(() => '')) || '').trim();
        if (t && t.length < 30 && CONSENT.test(t) && await b.isVisible().catch(() => false)) {
          await b.click({ timeout: 1500 }).catch(() => {});
          await page.waitForTimeout(400);
          return t;
        }
      }
    } catch (e) { /* ignore frame errors */ }
  }
  return null;
}

// Runs in the page: measures typography, colour, shape and "AI template" signals.
function measure() {
  const H = innerHeight;
  const parse = c => { const m = c && c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(',').map(x => parseFloat(x)); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
  const hex = c => { const p = parse(c); if (!p) return null; return '#' + [p.r, p.g, p.b].map(v => Math.round(v).toString(16).padStart(2, '0')).join(''); };
  const sat = c => { const p = parse(c); if (!p) return 0; const mx = Math.max(p.r, p.g, p.b) / 255, mn = Math.min(p.r, p.g, p.b) / 255; const l = (mx + mn) / 2; if (mx === mn) return 0; return (mx - mn) / (1 - Math.abs(2 * l - 1)); };
  const visible = el => { const r = el.getBoundingClientRect(); if (r.width < 2 || r.height < 2) return false; if (r.top > H * 2.5 || r.bottom < 0) return false; const s = getComputedStyle(el); return s.visibility !== 'hidden' && s.display !== 'none' && parseFloat(s.opacity) > 0.05; };
  const all = Array.from(document.querySelectorAll('body *')).slice(0, 6000).filter(visible);
  const fonts = {}, textColors = {}, bgArea = {}, radii = [], accents = {};
  let gradients = 0, shadows = 0, glows = 0, blur = 0, capsLabels = 0, textEls = 0, serifChars = 0, monoChars = 0, chars = 0;
  for (const el of all) {
    const s = getComputedStyle(el);
    const own = Array.from(el.childNodes).filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join(' ').trim();
    if (own.length > 1) {
      textEls++;
      const n = Math.min(own.length, 300); chars += n;
      const fam = s.fontFamily.split(',')[0].replace(/["']/g, '').trim();
      fonts[fam] = (fonts[fam] || 0) + n;
      const stack = s.fontFamily.toLowerCase();
      if (/mono|code|courier|consolas|menlo/.test(stack)) monoChars += n;
      else if (/serif/.test(stack) && !/sans-serif/.test(stack.split(',')[0]) && !/sans/.test(stack.split(',')[0])) serifChars += n;
      textColors[hex(s.color)] = (textColors[hex(s.color)] || 0) + n;
      if (s.textTransform === 'uppercase' && parseFloat(s.letterSpacing) >= 0.5 && own.length < 40) capsLabels++;
    }
    const bg = s.backgroundColor; const p = parse(bg);
    if (p && p.a > 0.5) { const r = el.getBoundingClientRect(); const a = r.width * Math.min(r.height, H); bgArea[hex(bg)] = (bgArea[hex(bg)] || 0) + a;
      const isCtl = el.tagName === 'BUTTON' || el.getAttribute('role') === 'button' || (el.tagName === 'A' && r.height < 80 && r.width < 400);
      if (isCtl) { radii.push(parseFloat(s.borderTopLeftRadius) || 0); if (sat(bg) > 0.3) accents[hex(bg)] = (accents[hex(bg)] || 0) + 1; } }
    if (s.backgroundImage && s.backgroundImage.includes('gradient')) gradients++;
    if (s.boxShadow && s.boxShadow !== 'none') { shadows++; const m = s.boxShadow.match(/rgba?\([^)]+\)/g) || []; if (m.some(c => sat(c) > 0.35) && /\d+px \d+px (\d{2,})px/.test(s.boxShadow)) glows++; }
    if ((s.backdropFilter && s.backdropFilter !== 'none') || (s.webkitBackdropFilter && s.webkitBackdropFilter !== 'none')) blur++;
  }
  const top = (o, k) => Object.entries(o).sort((a, b) => b[1] - a[1]).slice(0, k);
  let pageBg = getComputedStyle(document.body).backgroundColor;
  if (!parse(pageBg) || parse(pageBg).a < 0.5) pageBg = getComputedStyle(document.documentElement).backgroundColor;
  const bgTop = top(bgArea, 1)[0];
  const baseBg = (parse(pageBg) && parse(pageBg).a >= 0.5) ? hex(pageBg) : (bgTop ? bgTop[0] : '#ffffff');
  const lum = h => { const p = parse('rgb(' + [1, 3, 5].map(i => parseInt(h.substr(i, 2), 16)).join(',') + ')'); const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(p.r) + 0.7152 * f(p.g) + 0.0722 * f(p.b); };
  const h1 = document.querySelector('h1');
  const h1s = h1 ? getComputedStyle(h1) : null;
  const bodyText = document.body.innerText || '';
  const emoji = (bodyText.match(/\p{Extended_Pictographic}/gu) || []).length;
  radii.sort((a, b) => a - b);
  const words = bodyText.toLowerCase();
  const count = re => (words.match(re) || []).length;
  return {
    title: document.title,
    description: (document.querySelector('meta[name=description]') || document.querySelector('meta[property="og:description"]') || {}).content || null,
    h1: h1 ? h1.innerText.trim().slice(0, 160) : null,
    h1_font: h1s ? h1s.fontFamily.split(',')[0].replace(/["']/g, '').trim() : null,
    h1_size_px: h1s ? parseFloat(h1s.fontSize) : null,
    h1_weight: h1s ? h1s.fontWeight : null,
    h1_letter_spacing: h1s ? h1s.letterSpacing : null,
    h1_italic_spans: h1 ? h1.querySelectorAll('em, i').length : 0,
    body_font: getComputedStyle(document.body).fontFamily.split(',')[0].replace(/["']/g, '').trim(),
    fonts_by_chars: top(fonts, 5),
    serif_share: chars ? +(serifChars / chars).toFixed(3) : 0,
    mono_share: chars ? +(monoChars / chars).toFixed(3) : 0,
    page_bg: baseBg,
    theme: lum(baseBg) < 0.2 ? 'dark' : 'light',
    bg_by_area: top(bgArea, 6).map(([c, a]) => [c, Math.round(a)]),
    text_colors: top(textColors, 5),
    accent: top(accents, 1).length ? top(accents, 1)[0][0] : null,
    control_radius_median: radii.length ? radii[Math.floor(radii.length / 2)] : null,
    signals: { gradients, shadows, colored_glows: glows, backdrop_blur: blur, caps_letterspaced_labels: capsLabels, emoji, text_elements: textEls },
    copy: { mentions_agent: count(/\bagents?\b/g), mentions_trust: count(/\b(trust|secure|security|privacy|compliance|soc ?2)\b/g), mentions_evidence: count(/\b(evidence|citation|cite|source|audit trail|traceab)/g) },
    scroll_height: document.documentElement.scrollHeight,
  };
}

async function captureOne(browser, [category, name, url]) {
  const id = slug(name);
  const rec = { id, name, category, url, captured_at: new Date().toISOString() };
  const t0 = Date.now();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1, locale: 'en-US', colorScheme: 'light' });
  const page = await ctx.newPage();
  try {
    const resp = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
    rec.status = resp ? resp.status() : null;
    await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {});
    await page.waitForTimeout(1500);
    rec.consent_clicked = await dismissBanners(page);
    rec.final_url = page.url();
    rec.metrics = await page.evaluate(measure);
    await page.screenshot({ path: path.join(shotDir, `${id}__desktop.jpg`), type: 'jpeg', quality: 80 });
    const h = Math.min(rec.metrics.scroll_height || 900, 6000);
    // nudge lazy content, then full page (capped)
    for (let y = 0; y < h; y += 800) { await page.mouse.wheel(0, 800); await page.waitForTimeout(120); }
    await page.evaluate(() => window.scrollTo(0, 0)); await page.waitForTimeout(400);
    await page.screenshot({ path: path.join(shotDir, `${id}__full.jpg`), type: 'jpeg', quality: 60, fullPage: true, clip: { x: 0, y: 0, width: 1440, height: h } }).catch(async () => {
      await page.screenshot({ path: path.join(shotDir, `${id}__full.jpg`), type: 'jpeg', quality: 60, fullPage: true });
    });
    const m = await ctx.newPage();
    await m.setViewportSize({ width: 390, height: 844 });
    await m.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 }).catch(() => {});
    await m.waitForTimeout(2000);
    await dismissBanners(m);
    await m.screenshot({ path: path.join(shotDir, `${id}__mobile.jpg`), type: 'jpeg', quality: 80 });
    rec.ok = true;
  } catch (e) {
    rec.ok = false; rec.error = String(e.message || e).split('\n')[0].slice(0, 200);
    await page.screenshot({ path: path.join(shotDir, `${id}__desktop.jpg`), type: 'jpeg', quality: 80 }).catch(() => {});
  }
  rec.seconds = +((Date.now() - t0) / 1000).toFixed(1);
  await ctx.close();
  fs.writeFileSync(path.join(dataDir, `${id}.json`), JSON.stringify(rec, null, 2));
  console.log(`${rec.ok ? 'ok ' : 'ERR'} ${rec.status ?? '-'} ${rec.seconds}s ${name}${rec.error ? ' :: ' + rec.error : ''}`);
}

(async () => {
  const browser = await chromium.launch({ proxy: { server: process.env.HTTPS_PROXY } });
  const queue = targets.slice();
  const workers = Array.from({ length: 3 }, async () => { while (queue.length) { const t = queue.shift(); await captureOne(browser, t).catch(e => console.log('FATAL', t[1], e.message)); } });
  await Promise.all(workers);
  await browser.close();
  console.log('DONE');
})();
