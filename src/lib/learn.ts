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

export interface PathStep {
  link: UnitLink;
  field: LearnField;
  /** 今のページと分野が違う（分野の境目をまたぐ） */
  crossesField: boolean;
}

/**
 * 学習の順（content/learn/path.yaml の分野と単元の並び）での、前と次の単元（ページのあるものだけで数える）。
 * 分野の最後の単元の「次」は、次の分野の最初の単元とする。最初から最後まで、次の案内だけでたどれるようにするため（要件定義書 AT-09）。
 * href が学習の順にないとき（学習の順に入っていない工程ページなど）は、inPath を false にする。
 */
export function pathNeighbors(preview: boolean, href: string): { inPath: boolean; isLast: boolean; previous?: PathStep; next?: PathStep } {
  const flat = learnIndex(preview).flatMap((e) => e.units.map((link) => ({ link, field: e.field })));
  const at = flat.findIndex((u) => u.link.href === href);
  if (at < 0) return { inPath: false, isLast: false };
  const here = flat[at].field.slug;
  const step = (u?: { link: UnitLink; field: LearnField }) => (u ? { ...u, crossesField: u.field.slug !== here } : undefined);
  return { inPath: true, isLast: at === flat.length - 1, previous: step(flat[at - 1]), next: step(flat[at + 1]) };
}

export function neighbors(preview: boolean, page: LearnPage) {
  return pathNeighbors(preview, learnHref(page));
}

/** 学習のページの図（src/figures/learn/{分野}/{slug}.astro）。本サイトで作るSVGの図（仕様書 7章） */
const figureModules = import.meta.glob<{ default: unknown }>('../figures/learn/*/*.astro', { eager: true });
export function learnFigure(page: Pick<LearnPage, 'field' | 'slug'>): unknown | null {
  return figureModules[`../figures/learn/${page.field}/${page.slug}.astro`]?.default ?? null;
}
