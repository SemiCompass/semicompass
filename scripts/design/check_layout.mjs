// 画面の幅の自動確認（要件定義書3.5、10.2、DS-03）。dist/ を静的に配り、代表のページを5つの幅で開いて確かめる。
//  1. ページ全体が横にはみ出さない（表・グラフ・コードなど、自分のスクロール枠の中は除く）
//  2. 本文の段落の1行が、全角で45字を超えない（約35〜45字。要件定義書3.5）
// 使い方: npm run check:layout（先に npm run build:preview）。ブラウザは、環境変数 CHROME_PATH があればそれ、なければ Chrome（channel: chrome）。
import { chromium } from 'playwright-core';
import { createServer } from 'node:http';
import { readFile, readdir, stat } from 'node:fs/promises';
import { extname, join, normalize, sep } from 'node:path';

const DIST = new URL('../../dist/', import.meta.url).pathname;
const WIDTHS = [320, 360, 768, 1024, 1440];
const PER_SECTION = 3; // 1つの区分（companies、processes など）から開くページの数
const MAX_CHARS_PER_LINE = 45;
const TYPES = { '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript', '.json': 'application/json', '.svg': 'image/svg+xml', '.txt': 'text/plain' };

async function pages(dir, base = '') {
  const found = [];
  for (const name of (await readdir(join(dir, base))).sort()) {
    const rel = join(base, name);
    const info = await stat(join(dir, rel));
    if (info.isDirectory()) found.push(...(await pages(dir, rel)));
    else if (name === 'index.html') found.push('/' + base.split(sep).join('/') + (base ? '/' : ''));
  }
  return found;
}

function pick(all) {
  const bySection = new Map();
  for (const p of all) {
    const section = p.split('/')[1] || '';
    if (!bySection.has(section)) bySection.set(section, []);
    bySection.get(section).push(p);
  }
  const chosen = [];
  for (const [section, list] of bySection) {
    // 一覧（区分の直下）を先頭に、残りは、等間隔に選ぶ
    const top = list.filter((p) => p === `/${section}/` || p === '/');
    const rest = list.filter((p) => !top.includes(p));
    const step = Math.max(1, Math.floor(rest.length / Math.max(1, PER_SECTION - top.length)));
    const sample = rest.filter((_, i) => i % step === 0).slice(0, Math.max(0, PER_SECTION - top.length));
    chosen.push(...top, ...sample);
  }
  return chosen;
}

const server = createServer(async (req, res) => {
  const path = normalize(decodeURIComponent(new URL(req.url, 'http://x').pathname)).replace(/^(\.\.[/\\])+/, '');
  let file = join(DIST, path);
  if (!file.startsWith(DIST)) { res.writeHead(403).end(); return; }
  try {
    if ((await stat(file)).isDirectory()) file = join(file, 'index.html');
    res.writeHead(200, { 'content-type': TYPES[extname(file)] ?? 'application/octet-stream' }).end(await readFile(file));
  } catch {
    res.writeHead(404, { 'content-type': 'text/plain' }).end('not found');
  }
});
await new Promise((ok) => server.listen(0, '127.0.0.1', ok));
const origin = `http://127.0.0.1:${server.address().port}`;

const targets = pick(await pages(DIST));
const browser = await chromium.launch(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : { channel: 'chrome' });
const problems = [];
let checked = 0;

for (const width of WIDTHS) {
  const page = await browser.newPage({ viewport: { width, height: 900 } });
  for (const path of targets) {
    await page.goto(origin + path, { waitUntil: 'load' });
    const result = await page.evaluate((limit) => {
      const out = { overflow: [], lines: [] };
      const scrolls = (el) => { for (let n = el.parentElement; n && n !== document.body; n = n.parentElement) { const o = getComputedStyle(n).overflowX; if (o === 'auto' || o === 'scroll' || o === 'hidden' || o === 'clip') return true; } return false; };
      const name = (el) => el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '');
      if (document.documentElement.scrollWidth > window.innerWidth + 1) {
        for (const el of document.body.querySelectorAll('*')) {
          const r = el.getBoundingClientRect();
          if (r.width > 0 && r.right > window.innerWidth + 1 && !scrolls(el) && getComputedStyle(el).position !== 'fixed') { out.overflow.push(`${name(el)}（右端 ${Math.round(r.right)}px）`); if (out.overflow.length >= 3) break; }
        }
        if (!out.overflow.length) out.overflow.push(`ページ全体が ${document.documentElement.scrollWidth}px（画面 ${window.innerWidth}px）`);
      }
      for (const p of document.querySelectorAll('main p, main li')) {
        if (p.closest('table, figure, nav, header, footer, pre, code, [role="tablist"]')) continue;
        if ((p.textContent || '').trim().length < 60) continue;
        const cs = getComputedStyle(p);
        // 実際に描かれた行の幅（枠の幅ではなく、文字が並んだ幅）の最大値
        const range = document.createRange();
        range.selectNodeContents(p);
        let widest = 0;
        for (const r of range.getClientRects()) widest = Math.max(widest, r.width);
        const chars = widest / parseFloat(cs.fontSize);
        if (chars > limit) { out.lines.push(`${name(p)}（全角 ${chars.toFixed(1)}字分）`); if (out.lines.length >= 3) break; }
      }
      return out;
    }, MAX_CHARS_PER_LINE);
    checked += 1;
    for (const o of result.overflow) problems.push(`横にはみ出す  ${width}px  ${path}  ${o}`);
    for (const l of result.lines) problems.push(`1行が長すぎる  ${width}px  ${path}  ${l}`);
  }
  await page.close();
}

await browser.close();
server.close();
console.log(`画面の幅の確認：${targets.length}ページ × ${WIDTHS.length}幅（${WIDTHS.join('、')}px）、${checked}回`);
if (problems.length) {
  console.error(`不合格 ${problems.length}件`);
  for (const p of problems) console.error(`* ${p}`);
  process.exit(1);
}
console.log('合格');
