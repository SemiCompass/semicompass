// 工程・用語・学習の解説（content/processes、content/glossary、content/learn）を読む（データ定義書 6.5、6.6、6.8）。ファイルがなければ、空。
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { parse } from 'yaml';
import type { Source } from './companies';

// ---- 理解度チェック（データ定義書 6.11、要求定義書 FR-904）----
// 本文の最後の「## 理解度チェック」を、問いの並びに分ける。形が崩れているものは、検査（V-24）で不合格になる。ここでは、読めたものだけを返す。
export const QUIZ_HEADING = '理解度チェック';

export interface QuizQuestion {
  prompt: string;
  choices: string[]; // 4つ
  answer: number; // 1〜4
  explanation: string;
}

/** 本文を、理解度チェックより前の部分と、問いの並びに分ける。チェックがなければ、questions は空 */
export function splitQuiz(body: string): { rest: string; questions: QuizQuestion[] } {
  const lines = body.replace(/\r\n/g, '\n').split('\n');
  const start = lines.findIndex((l) => l.trim() === `## ${QUIZ_HEADING}`);
  if (start < 0) return { rest: body, questions: [] };
  const rest = lines.slice(0, start).join('\n');
  const questions: QuizQuestion[] = [];
  let current: { prompt: string[]; choices: string[]; answer: number; explanation: string } | null = null;
  const flush = () => {
    if (current && current.choices.length === 4 && current.answer >= 1 && current.answer <= 4 && current.explanation) {
      questions.push({ prompt: current.prompt.join(''), choices: current.choices, answer: current.answer, explanation: current.explanation });
    }
  };
  for (const raw of lines.slice(start + 1)) {
    const line = raw.trim();
    if (/^###\s+問[0-9０-９]+/.test(line)) {
      flush();
      current = { prompt: [], choices: [], answer: 0, explanation: '' };
      continue;
    }
    if (!current || !line) continue;
    const choice = /^([1-4])\.\s+(.+)$/.exec(line);
    const answer = /^答え[：:]\s*([1-4])$/.exec(line);
    const explanation = /^解説[：:]\s*(.+)$/.exec(line);
    if (choice) current.choices.push(choice[2].trim());
    else if (answer) current.answer = Number(answer[1]);
    else if (explanation) current.explanation = explanation[1].trim();
    else if (current.choices.length === 0) current.prompt.push(line);
  }
  flush();
  return { rest, questions };
}

const root = process.cwd();

export interface Markdown<F> {
  front: F;
  sections: { heading: string; paragraphs: string[] }[];
  quiz: QuizQuestion[]; // 本文の最後の理解度チェック（データ定義書 6.11）。sections には含めない
}

export function parseMarkdown<F>(text: string): Markdown<F> {
  const match = /^---\n([\s\S]*?)\n---\n?([\s\S]*)$/.exec(text.replace(/\r\n/g, '\n'));
  if (!match) throw new Error('front matter がない');
  const front = parse(match[1]) as F;
  const { rest: body, questions: quiz } = splitQuiz(match[2]);
  const sections: Markdown<F>['sections'] = [];
  const blocks = body.split(/^## /m);
  const intro = blocks[0].trim();
  if (intro) sections.push({ heading: '', paragraphs: splitParagraphs(intro) });
  for (const block of blocks.slice(1)) {
    const [heading, ...rest] = block.split('\n');
    sections.push({ heading: heading.trim(), paragraphs: splitParagraphs(rest.join('\n')) });
  }
  return { front, sections, quiz };
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

// ---- 半導体を学ぶ（データ定義書 6.8）：content/learn/path.yaml と content/learn/{分野}/{slug}.md ----
export interface LearnUnit {
  type: 'learn' | 'process' | 'term';
  ref: string;
  /** learn のページが、分野と別のフォルダ（content/learn/{folder}/）にあるとき。公開済みのURLを変えずに分野を組み替えるため */
  folder?: string;
}
export interface LearnSection {
  slug: string;
  title: string;
  summary?: string;
  units: LearnUnit[];
}
export type LearnTierSlug = 'basic' | 'physics';
export interface LearnField {
  /** 基礎編の分野の番号（1〜9） */
  no?: number;
  /** 深掘り編のカードの記号（A〜） */
  label?: string;
  /** 基礎編（fields）か、深掘り編「半導体の物理」（physics.cards）か */
  tier: LearnTierSlug;
  /** 見出しに付ける番号か記号（「1」「A」） */
  mark: string;
  slug: string;
  title: string;
  summary: string;
  units: LearnUnit[];
  /** 分野の中の小分け（任意）。units の後に、この順で並べる */
  sections?: LearnSection[];
}
export interface LearnTier {
  slug: LearnTierSlug;
  title: string;
  summary: string;
  fields: LearnField[];
}
/** 深掘り編のページが、基礎編のどのページに効くか（データ定義書 6.8） */
export interface LearnAppliesTo extends LearnUnit {
  note: string;
}
export interface LearnContent extends Common {
  title: string;
  description: string;
  field: string;
  processes?: string[];
  related_terms?: string[];
  companies?: string[];
  applies_to?: LearnAppliesTo[];
}
export type LearnPage = Markdown<LearnContent> & { slug: string; field: string };

// 基礎編の段の名前と説明（深掘り編の名前と説明は path.yaml の physics に持つ）
const BASIC_TIER = { title: '基礎編', summary: '半導体の世界に何があり、どう作られ、どう使われるかを、分野ごとに学びます。' };

/** 一覧の段：基礎編（fields）と、あれば深掘り編「半導体の物理」（physics） */
export function loadLearnTiers(): LearnTier[] {
  const path = resolve(root, 'content/learn/path.yaml');
  if (!existsSync(path)) return [];
  type Raw = Omit<LearnField, 'tier' | 'mark'>;
  const data = parse(readFileSync(path, 'utf-8')) as {
    fields?: Raw[];
    physics?: { title: string; summary: string; cards?: Raw[] };
  };
  const basic = [...(data.fields ?? [])]
    .sort((a, b) => (a.no ?? 0) - (b.no ?? 0))
    .map((f) => ({ ...f, tier: 'basic' as const, mark: String(f.no) }));
  const tiers: LearnTier[] = [{ slug: 'basic', ...BASIC_TIER, fields: basic }];
  if (data.physics) {
    const cards = (data.physics.cards ?? []).map((c) => ({ ...c, tier: 'physics' as const, mark: c.label ?? '' }));
    tiers.push({ slug: 'physics', title: data.physics.title, summary: data.physics.summary, fields: cards });
  }
  return tiers;
}

/** 分野とカード（基礎編、深掘り編の順） */
export function loadLearnPath(): LearnField[] {
  return loadLearnTiers().flatMap((t) => t.fields);
}

/** 学習のページ（公開してよいものだけ）。分野のフォルダの名前を field とする */
export function loadLearnPages(preview: boolean): LearnPage[] {
  const base = resolve(root, 'content/learn');
  if (!existsSync(base)) return [];
  const pages: LearnPage[] = [];
  for (const field of readdirSync(base, { withFileTypes: true }).filter((d) => d.isDirectory()).map((d) => d.name).sort()) {
    for (const file of files(`content/learn/${field}`)) {
      const md = parseMarkdown<LearnContent>(readFileSync(resolve(base, field, file), 'utf-8'));
      if (visible(md.front, preview)) pages.push({ ...md, slug: file.replace(/\.md$/, ''), field });
    }
  }
  return pages;
}
