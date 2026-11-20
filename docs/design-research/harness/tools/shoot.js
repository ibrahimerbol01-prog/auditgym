// Screenshots of the three options at 1440x900 (and B with the "new run" drawer open). Prints page errors.
// Usage: node shoot.js <dir with option-*.html> <out dir> [scale]
const path = require('path'); const { chromium } = require('playwright');
const [dir, out, scale] = process.argv.slice(2);
const shots = [['option-a-workspace.html', 'option-a.png', 4000], ['option-b-console.html', 'option-b.png', 3000],
  ['option-b-console.html#new', 'option-b-new-run.png', 2000], ['option-c-terminal.html', 'option-c.png', 9500]];
(async () => {
  const b = await chromium.launch();
  for (const [f, png, wait] of shots) {
    const p = await b.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: +(scale || 1) });
    p.on('pageerror', e => console.log('ERR', f, e.message)); p.on('console', m => m.type() === 'error' && console.log('CONSOLE', f, m.text()));
    await p.goto('file://' + path.resolve(dir, f)); await p.waitForTimeout(wait);
    await p.screenshot({ path: path.join(out, png) }); await p.close(); console.log('ok', png);
  }
  await b.close();
})();
