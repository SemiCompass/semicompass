// 半導体を学ぶ（要求定義書 FR-901、データ定義書 6.8）：分野と単元の並び（content/learn/path.yaml）から、一覧と前後のリンクを作る。
// まだページのない単元は、一覧にも前後のリンクにも出さない。
import { loadSupply } from './companies';
import { loadLearnPages, loadLearnPath, loadTerms, type LearnField, type LearnPage, type LearnUnit } from './content';

export interface UnitLink {
  href: string;
  title: string;
  summary: string;
  kind: '学習' | '工程' | '用語';
}

export function learnIndex(preview: boolean): { field: LearnField; units: UnitLink[] }[] {
  const pages = loadLearnPages(preview);
  const terms = loadTerms(preview);
  const processes = loadSupply().processes as { slug: string; name: string; short_description?: string }[];
  const resolveUnit = (field: LearnField, unit: LearnUnit): UnitLink | null => {
    if (unit.type === 'learn') {
      const page = pages.find((p) => p.field === field.slug && p.slug === unit.ref);
      return page ? { href: learnHref(page), title: page.front.title, summary: page.front.description, kind: '学習' } : null;
    }
    if (unit.type === 'process') {
      const p = processes.find((x) => x.slug === unit.ref);
      return p ? { href: `/processes/${p.slug}/`, title: p.name, summary: p.short_description ?? '', kind: '工程' } : null;
    }
    const t = terms.find((x) => x.slug === unit.ref);
    return t ? { href: `/glossary/${t.slug}/`, title: t.front.term, summary: t.front.short_definition, kind: '用語' } : null;
  };
  return loadLearnPath().map((field) => ({
    field,
    units: field.units.map((u) => resolveUnit(field, u)).filter((u): u is UnitLink => u !== null),
  }));
}

export const learnHref = (page: Pick<LearnPage, 'field' | 'slug'>) => `/learn/${page.field}/${page.slug}/`;

/** 同じ分野の中の、前と次の単元（ページのあるものだけで数える） */
export function neighbors(preview: boolean, page: LearnPage): { previous?: UnitLink; next?: UnitLink } {
  const entry = learnIndex(preview).find((e) => e.field.slug === page.field);
  if (!entry) return {};
  const at = entry.units.findIndex((u) => u.href === learnHref(page));
  if (at < 0) return {};
  return { previous: entry.units[at - 1], next: entry.units[at + 1] };
}

/** 学習のページの図（src/figures/learn/{分野}/{slug}.astro）。本サイトで作るSVGの図（仕様書 7章） */
const figureModules = import.meta.glob<{ default: unknown }>('../figures/learn/*/*.astro', { eager: true });
export function learnFigure(page: Pick<LearnPage, 'field' | 'slug'>): unknown | null {
  return figureModules[`../figures/learn/${page.field}/${page.slug}.astro`]?.default ?? null;
}
