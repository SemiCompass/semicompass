// ニュース解説（content/news/{yyyy}-{mm}-{slug}.md。データ定義書 6.2）を読む。ファイルがなければ、空。
// 元記事の本文は持たない。表示するのは、front matter の元記事（見出し、発信元、URL、公表日）と、3つの中見出しの解説だけ。
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { parseMarkdown, visible, type Markdown } from './content';

export type NewsCategory = 'investment' | 'policy' | 'm_and_a' | 'earnings' | 'technology' | 'supply_demand';

/** 種別の表示名（運用ルール書 3.2） */
export const CATEGORY_LABEL: Record<NewsCategory, string> = {
  investment: '投資',
  policy: '政策・規制',
  m_and_a: 'M&A',
  earnings: '決算',
  technology: '技術',
  supply_demand: '供給・需要',
};

export interface NewsFront {
  title: string;
  description: string;
  published_at: string;
  updated_at?: string;
  draft?: boolean;
  ai_generated: boolean;
  under_review?: boolean;
  corrections?: { date: string; severity: 'major' | 'normal'; description: string; issue?: number }[];
  category: NewsCategory;
  source_article: { title: string; publisher: string; url: string; published_on: string; reporting: 'primary' | 'press' | 'speculative' };
  score: { impact: number; supply_chain: number; novelty: number; reliability: number };
  overseas: boolean;
  tags: { companies: string[]; unlisted_companies?: { name: string; name_en?: string }[]; processes: string[]; themes: string[] };
  x_post?: string;
}
export type NewsItem = Markdown<NewsFront> & { year: string; month: string; slug: string; url: string };

/** 一覧の読み込み元を、テストで差し替えられるようにする（既定は content/news/）。新しい順（公開日、同じ日はファイル名の逆順） */
export function loadNews(preview: boolean, dir = 'content/news'): NewsItem[] {
  const path = resolve(process.cwd(), dir);
  if (!existsSync(path)) return [];
  return readdirSync(path)
    .map((file) => ({ file, match: /^(\d{4})-(\d{2})-([a-z0-9]+(?:-[a-z0-9]+)*)\.md$/.exec(file) }))
    .filter((f): f is { file: string; match: RegExpExecArray } => f.match !== null)
    .map(({ file, match: [, year, month, slug] }) => ({
      ...parseMarkdown<NewsFront>(readFileSync(resolve(path, file), 'utf-8')),
      year, month, slug, url: `/news/${year}/${month}/${slug}/`,
    }))
    .filter((n) => visible(n.front, preview))
    .sort((a, b) => b.front.published_at.localeCompare(a.front.published_at) || b.url.localeCompare(a.url));
}
