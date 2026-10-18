// SNS共有用の画像（public/og-default.png、1200×630）を作る。仕様書 14章の未決事項4、DS-08。
// トップの帯（9.1）と同じ形：濃紺の地に回路の格子とウェーハの同心円、ロゴ（B案）とサイト名、大見出し。色は src/styles/tokens.css の値を読む。
// 使い方: node scripts/design/make_og.mjs [出力のPNG] [幅] [高さ]（既定は public/og-default.png、1200、630）。
// Xのヘッダー（1500×500）も同じ形で作れる（サイトには置かない）: node scripts/design/make_og.mjs x-header.png 1500 500
import { chromium } from 'playwright-core';
import { readFile } from 'node:fs/promises';

const out = process.argv[2] ?? new URL('../../public/og-default.png', import.meta.url).pathname;
const W = Number(process.argv[3] ?? 1200);
const H = Number(process.argv[4] ?? 630);
const tokens = await readFile(new URL('../../src/styles/tokens.css', import.meta.url), 'utf-8');
const v = (name) => {
  const m = tokens.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`));
  if (!m) throw new Error(`tokens.css に --${name} がない`);
  return m[1];
};
const c = {
  brand: v('color-brand'), grid: v('color-brand-grid'), ring: v('color-brand-ring'), on: v('color-on-brand'),
  lead: v('color-on-brand-lead'), accent: v('color-brand-accent'),
};
const wide = W / H > 2.5; // Xのヘッダー：文字を右に寄せる（左下はプロフィールの画像で隠れる）
const logo = `<svg width="${wide ? 64 : 72}" height="${wide ? 64 : 72}" viewBox="1.1 1.1 29.8 29.8" fill="none" stroke="${c.on}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="14" height="14" rx="1.5" transform="rotate(45 16 16)"/><path d="M16 2v3.2M16 26.8V30M2 16h3.2M26.8 16H30M9.2 9.2l1.6 1.6M22.8 9.2l-1.6 1.6M9.2 22.8l1.6-1.6M22.8 22.8l-1.6-1.6"/><g stroke="none"><path d="M16 8.6l2.9 7.4h-5.8z" fill="${c.accent}"/><path d="M16 23.4l2.9-7.4h-5.8z" fill="${c.on}"/></g></svg>`;
const html = `<!doctype html><html lang="ja"><meta charset="utf-8"><style>
html,body{margin:0}body{width:${W}px;height:${H}px;position:relative;overflow:hidden;background:${c.brand};color:${c.on};font-family:"Hiragino Sans","Noto Sans CJK JP","Noto Sans JP",sans-serif}
svg.bg{position:absolute;inset:0}
.in{position:absolute;${wide ? `right:96px;top:50%;transform:translateY(-50%);text-align:right` : `left:88px;top:72px`}}
.name{display:flex;align-items:center;gap:18px;${wide ? 'justify-content:flex-end;' : ''}font-weight:700;font-size:${wide ? 44 : 46}px;letter-spacing:.01em}
h1{margin:${wide ? 28 : 56}px 0 0;font-size:${wide ? 38 : 60}px;line-height:1.35;font-weight:700;font-feature-settings:"palt"}
h1 span{display:${wide ? 'inline' : 'block'}}em{font-style:normal;color:${c.accent}}
p{margin:${wide ? 16 : 28}px 0 0;font-size:${wide ? 22 : 26}px;color:${c.lead};font-feature-settings:"palt"}
</style><body>
<svg class="bg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}"><defs><pattern id="g" width="32" height="32" patternUnits="userSpaceOnUse"><path d="M32 0H0V32" fill="none" stroke="${c.grid}" stroke-width="1"/></pattern></defs>
<rect width="${W}" height="${H}" fill="url(#g)"/><g fill="none" stroke="${c.ring}" stroke-width="1.5">${[360, 300, 240, 180].map((r) => `<circle cx="${wide ? 160 : W - 120}" cy="${wide ? H / 2 : H / 2 + 10}" r="${r}"/>`).join('')}</g></svg>
<div class="in"><div class="name">${logo}<span>SemiCompass</span></div>
<h1><span>日本の半導体業界を、</span><span>企業・工程・ニュースで</span><span><em>つなげて</em>理解する</span></h1>
${wide ? '' : '<p>半導体ができるまでの工程と、そこに関わる日本の企業を、図と業績の数字でたどれます。</p>'}</div></body></html>`;

const browser = await chromium.launch(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : { channel: 'chrome' });
const page = await browser.newPage({ viewport: { width: W, height: H } });
await page.setContent(html);
await page.screenshot({ path: out, type: 'png' });
await browser.close();
console.log(`作成：${out}（${W}×${H}）`);
