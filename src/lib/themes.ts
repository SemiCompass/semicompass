// テーマ（content/themes/{slug}.md。データ定義書 6.7、運用ルール書 4.6、仕様書 9.9）を読む。ファイルがなければ、空。
// テーマは業界レポートの形：要旨、市場の動き、バリューチェーン、日本企業の位置、論点と今後の注目点の5つの中見出し。
// 関連企業は、まとまり（groups）ごとに、掲載企業を証券コードの順（外資系日本法人などコードのない企業は末尾）、
// その後に掲載企業の外の企業（others）を名前の順に並べる。ファイルの中の企業の順番は表示に使わない（FR-602、AD-402）。
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { Company, Source } from './companies';
import { parseMarkdown, visible, type Markdown } from './content';

export interface ThemeCompany {
  company: string;
  role: string;
  basis: string[];
}
export interface ThemeOther {
  name: string;
  name_en?: string;
  region: string;
  role: string;
  basis: string[];
}
export interface ThemeGroup {
  label: string;
  process?: string;
  companies?: ThemeCompany[];
  others?: ThemeOther[];
}
export interface ThemeFront {
  theme: string;
  title: string;
  description: string;
  criteria: string;
  groups: ThemeGroup[];
  processes?: string[];
  terms?: string[];
  learn?: { folder: string; ref: string }[];
  published_at: string;
  updated_at?: string;
  draft?: boolean;
  ai_generated: boolean;
  sources: Source[];
}
export type Theme = Markdown<ThemeFront> & { slug: string; url: string; report: ReportSection[] };

// ---- レポートの本文（データ定義書 6.7、運用ルール書 4.6）：5つの中見出しと、その中の段落・小見出し・箇条書き ----
export const REPORT_HEADINGS = ['要旨', '市場の動き', 'バリューチェーン', '日本企業の位置', '論点と今後の注目点'] as const;
export const VIEW_HEADINGS = ['発表元の見方', '本サイトの見方'] as const;
export type ReportBlock = { kind: 'p'; text: string } | { kind: 'h3'; text: string } | { kind: 'ul'; items: string[] };
export interface ReportSection {
  heading: string;
  blocks: ReportBlock[];
}

/** 本文（front matter の後）を、中見出し（##）ごとの区分に分ける。段落は空行で区切り、行の折り返しはつなげる */
export function parseReport(body: string): ReportSection[] {
  const sections: ReportSection[] = [];
  let current: ReportSection | null = null;
  for (const chunk of body.replace(/\r\n/g, '\n').split(/\n{2,}/)) {
    const lines = chunk.split('\n').map((l) => l.trim()).filter(Boolean);
    if (lines.length === 0) continue;
    let rest = lines;
    while (rest.length > 0 && /^#{2,3}\s+/.test(rest[0])) {
      if (/^###\s+/.test(rest[0])) {
        current?.blocks.push({ kind: 'h3', text: rest[0].replace(/^###\s+/, '') });
      } else {
        current = { heading: rest[0].replace(/^##\s+/, ''), blocks: [] };
        sections.push(current);
      }
      rest = rest.slice(1);
    }
    if (rest.length === 0 || !current) continue;
    if (rest.every((l) => /^[-*]\s+/.test(l))) current.blocks.push({ kind: 'ul', items: rest.map((l) => l.replace(/^[-*]\s+/, '')) });
    else current.blocks.push({ kind: 'p', text: rest.join('') });
  }
  return sections;
}

/** 読み込み元を、テストで差し替えられるようにする（既定は content/themes/）。公開日の新しい順（同じ日は slug の順） */
export function loadThemes(preview: boolean, dir = 'content/themes'): Theme[] {
  const path = resolve(process.cwd(), dir);
  if (!existsSync(path)) return [];
  return readdirSync(path)
    .filter((f) => /^[a-z0-9]+(-[a-z0-9]+)*\.md$/.test(f))
    .map((f) => {
      const slug = f.replace(/\.md$/, '');
      const text = readFileSync(resolve(path, f), 'utf-8');
      const body = text.replace(/\r\n/g, '\n').replace(/^---\n[\s\S]*?\n---\n?/, '');
      return { ...parseMarkdown<ThemeFront>(text), slug, url: `/themes/${slug}/`, report: parseReport(body) };
    })
    .filter((t) => visible(t.front, preview))
    .sort((a, b) => b.front.published_at.localeCompare(a.front.published_at) || a.slug.localeCompare(b.slug));
}

export interface ThemeRow {
  kind: 'listed' | 'other';
  name: string;
  slug?: string; // 掲載企業だけ
  detailed?: boolean; // 掲載企業：詳しいページがあるか
  region?: string; // 掲載企業の外の企業
  role: string;
  basis: number[]; // 出典の番号（S3 → 3）
}

const number = (id: string) => Number(id.replace(/^S/, ''));

/** まとまりの中の行を、表示の順に並べる。企業マスタにない slug は出さない（検査 V-04 で不合格になる） */
export function groupRows(group: ThemeGroup, companies: Company[], detailedSlugs: Set<string>): ThemeRow[] {
  const listed = (group.companies ?? []).flatMap((c) => {
    const company = companies.find((x) => x.slug === c.company);
    return company ? [{ company, entry: c }] : [];
  });
  listed.sort((a, b) =>
    (a.company.securities_code ?? '99999').localeCompare(b.company.securities_code ?? '99999') || a.company.slug.localeCompare(b.company.slug));
  const others = [...(group.others ?? [])].sort((a, b) => a.name.localeCompare(b.name, 'ja'));
  return [
    ...listed.map(({ company, entry }): ThemeRow => ({
      kind: 'listed', name: company.short_names[0] ?? company.name, slug: company.slug, detailed: detailedSlugs.has(company.slug),
      role: entry.role, basis: entry.basis.map(number),
    })),
    ...others.map((o): ThemeRow => ({ kind: 'other', name: o.name, region: o.region, role: o.role, basis: o.basis.map(number) })),
  ];
}

/** テーマに載せた企業の数（掲載企業と、掲載企業の外の企業の合計） */
export const companyCount = (front: ThemeFront) =>
  front.groups.reduce((n, g) => n + (g.companies?.length ?? 0) + (g.others?.length ?? 0), 0);

/** ニュースの tags.themes から、テーマの名前を引く（公開済みのテーマだけ。ないものは出さない） */
export function themeTags(slugs: string[], themes: Theme[]): { slug: string; name: string }[] {
  return slugs.flatMap((slug) => {
    const t = themes.find((x) => x.slug === slug);
    return t ? [{ slug, name: t.front.title }] : [];
  });
}
