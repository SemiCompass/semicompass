// 工程と用語の解説（content/processes、content/glossary）を読む（データ定義書 6.5、6.6）。ファイルがなければ、空。
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { parse } from 'yaml';
import type { Source } from './companies';

const root = process.cwd();

export interface Markdown<F> {
  front: F;
  sections: { heading: string; paragraphs: string[] }[];
}

export function parseMarkdown<F>(text: string): Markdown<F> {
  const match = /^---\n([\s\S]*?)\n---\n?([\s\S]*)$/.exec(text.replace(/\r\n/g, '\n'));
  if (!match) throw new Error('front matter がない');
  const front = parse(match[1]) as F;
  const body = match[2];
  const sections: Markdown<F>['sections'] = [];
  const blocks = body.split(/^## /m);
  const intro = blocks[0].trim();
  if (intro) sections.push({ heading: '', paragraphs: splitParagraphs(intro) });
  for (const block of blocks.slice(1)) {
    const [heading, ...rest] = block.split('\n');
    sections.push({ heading: heading.trim(), paragraphs: splitParagraphs(rest.join('\n')) });
  }
  return { front, sections };
}
function splitParagraphs(text: string): string[] {
  return text.split(/\n{2,}/).map((p) => p.trim().replace(/\n/g, '')).filter(Boolean);
}

interface Common {
  published_at: string;
  updated_at?: string;
  draft?: boolean;
  ai_generated: boolean;
  sources: Source[];
}
export interface ProcessContent extends Common {
  title: string;
  description: string;
  process: string;
  terms?: string[];
}
export interface Term extends Common {
  slug: string;
  term: string;
  reading: string;
  aliases?: string[];
  name_en?: string;
  abbreviation_of?: string;
  description?: string;
  short_definition: string;
  processes: string[];
  companies?: string[];
  related_terms?: string[];
}

function files(dir: string): string[] {
  const path = resolve(root, dir);
  return existsSync(path) ? readdirSync(path).filter((f) => f.endsWith('.md')).sort() : [];
}

/** 公開してよいか。draft: true は、プレビューのビルドだけ（企業ページと同じ決まり） */
export const visible = (front: { draft?: boolean }, preview: boolean) => !front.draft || preview;

export function loadProcessContent(slug: string, preview: boolean): Markdown<ProcessContent> | null {
  const path = resolve(root, `content/processes/${slug}.md`);
  if (!existsSync(path)) return null;
  const md = parseMarkdown<ProcessContent>(readFileSync(path, 'utf-8'));
  return visible(md.front, preview) ? md : null;
}

export function loadTerms(preview: boolean): (Markdown<Term> & { slug: string })[] {
  return files('content/glossary')
    .map((f) => ({ slug: f.replace(/\.md$/, ''), ...parseMarkdown<Term>(readFileSync(resolve(root, 'content/glossary', f), 'utf-8')) }))
    .filter((t) => visible(t.front, preview));
}

const ROWS: [string, string][] = [
  ['あ', 'あいうえおぁぃぅぇぉ'], ['か', 'かきくけこがぎぐげご'], ['さ', 'さしすせそざじずぜぞ'], ['た', 'たちつてとだぢづでどっ'],
  ['な', 'なにぬねの'], ['は', 'はひふへほばびぶべぼぱぴぷぺぽ'], ['ま', 'まみむめも'], ['や', 'やゆよゃゅょ'], ['ら', 'らりるれろ'], ['わ', 'わをんゎ'],
];
/** 用語集の見出し：読み（全角カタカナ）の最初の字から、五十音の行。それ以外は、英字なら「A〜Z」、そのほかは「その他」 */
export function glossaryHeading(reading: string): string {
  const first = [...reading.normalize('NFKC')][0] ?? '';
  const code = first.codePointAt(0) ?? 0;
  const hira = code >= 0x30a1 && code <= 0x30f6 ? String.fromCodePoint(code - 0x60) : first;
  const row = ROWS.find(([, chars]) => chars.includes(hira));
  if (row) return `${row[0]}行`;
  return /^[A-Za-z]$/.test(first) ? first.toUpperCase() : 'その他';
}
export const GLOSSARY_HEADING_ORDER = [...ROWS.map(([h]) => `${h}行`), ...'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split(''), 'その他'];
