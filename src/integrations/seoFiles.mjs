// robots.txt と sitemap.xml を、ビルドの最後に出力する（要件定義書の検索への登録、アーキテクチャ設計書6.2）。
// - 本番（BUILD_ENV=production）：登録を許可し、サイトマップを出す。サイトマップには、検索に登録させるページだけを載せる
//   （出力したHTMLのうち、noindex を付けたページ、転送だけのページは載せない）
// - プレビュー：全体を登録させない。サイトマップは出さない
// 依存は増やさない（外部のパッケージを使わない）。
import { readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join, relative, sep } from 'node:path';

function htmlFiles(dir) {
  const found = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) found.push(...htmlFiles(path));
    else if (entry.name === 'index.html') found.push(path);
  }
  return found;
}

const escapeXml = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

export function seoFiles({ site, production }) {
  return {
    name: 'semicompass-seo-files',
    hooks: {
      'astro:build:done': ({ dir }) => {
        const root = fileURLToPath(dir);
        if (!production) {
          writeFileSync(join(root, 'robots.txt'), 'User-agent: *\nDisallow: /\n');
          return;
        }
        const urls = [];
        for (const file of htmlFiles(root)) {
          const head = readFileSync(file, 'utf-8').slice(0, 2000);
          if (/name="robots" content="[^"]*noindex/.test(head)) continue;
          if (head.includes('http-equiv="refresh"')) continue;
          const path = '/' + relative(root, file).split(sep).slice(0, -1).join('/');
          urls.push(new URL(path === '/' ? '/' : path + '/', site).href);
        }
        urls.sort();
        const body = urls.map((u) => `  <url><loc>${escapeXml(u)}</loc></url>`).join('\n');
        writeFileSync(
          join(root, 'sitemap.xml'),
          `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${body}\n</urlset>\n`,
        );
        writeFileSync(join(root, 'robots.txt'), `User-agent: *\nAllow: /\n\nSitemap: ${new URL('/sitemap.xml', site).href}\n`);
      },
    },
  };
}
