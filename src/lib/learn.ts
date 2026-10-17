// 半導体を学ぶ（要求定義書 FR-901、データ定義書 6.8）：分野と単元の並び（content/learn/path.yaml）から、一覧と前後のリンクを作る。
// 一覧は、基礎編（fields）と深掘り編「半導体の物理」（physics）の二段。学習の順は、段ごとに別々に作る。
// まだページのない単元は、一覧にも前後のリンクにも出さない。
import { loadSupply } from './companies';
import {
  loadLearnPages,
  loadLearnTiers,
  loadTerms,
  type LearnField,
  type LearnPage,
  type LearnSection,
  type LearnTier,
  type LearnUnit,
} from './content';

export interface UnitLink {
  href: string;
  title: string;
  summary: string;
  kind: '学習' | '工程' | '用語';
}

export interface SectionIndex {
  section: LearnSection;
  units: UnitLink[];
}
export interface FieldIndex {
  field: LearnField;
  /** 分野の小分けの前に並べる単元 */
  lead: UnitLink[];
  sections: SectionIndex[];
  /** 分野の全単元（lead と各小分けを、並びの順に） */
  units: UnitLink[];
}
export interface TierIndex {
  tier: LearnTier;
  fields: FieldIndex[];
}

/** 分野の見出しの名前（「1. 半導体工学の基礎」「A. 固体物理学」の形） */
export const fieldName = (field: Pick<LearnField, 'mark' | 'title'>) => `${field.mark}. ${field.title}`;

/** 単元（learn、process、term）を、リンク先の情報にする。ページのないものは null */
function unitResolver(preview: boolean) {
  const pages = loadLearnPages(preview);
  const terms = loadTerms(preview);
  const processes = loadSupply().processes as { slug: string; name: string; short_description?: string }[];
  return (unit: LearnUnit, defaultFolder: string): UnitLink | null => {
    if (unit.type === 'learn') {
      const folder = unit.folder ?? defaultFolder;
      const page = pages.find((p) => p.field === folder && p.slug === unit.ref);
      return page ? { href: learnHref(page), title: page.front.title, summary: page.front.description, kind: '学習' } : null;
    }
    if (unit.type === 'process') {
      const p = processes.find((x) => x.slug === unit.ref);
      return p ? { href: `/processes/${p.slug}/`, title: p.name, summary: p.short_description ?? '', kind: '工程' } : null;
    }
    const t = terms.find((x) => x.slug === unit.ref);
    return t ? { href: `/glossary/${t.slug}/`, title: t.front.term, summary: t.front.short_definition, kind: '用語' } : null;
  };
}

export function learnTiers(preview: boolean): TierIndex[] {
  const resolveUnit = unitResolver(preview);
  const resolve = (field: LearnField, units: LearnUnit[]) =>
    units.map((u) => resolveUnit(u, field.slug)).filter((u): u is UnitLink => u !== null);
  return loadLearnTiers().map((tier) => ({
    tier,
    fields: tier.fields.map((field) => {
      const lead = resolve(field, field.units);
      const sections = (field.sections ?? []).map((section) => ({ section, units: resolve(field, section.units) }));
      return { field, lead, sections, units: [...lead, ...sections.flatMap((s) => s.units)] };
    }),
  }));
}

/** 分野とカード（基礎編、深掘り編の順） */
export function learnIndex(preview: boolean): FieldIndex[] {
  return learnTiers(preview).flatMap((t) => t.fields);
}

/** そのページ（href）を並べた分野。パンくずリストと、一覧の分野へのリンクに使う */
export function fieldOf(preview: boolean, href: string): LearnField | undefined {
  return learnIndex(preview).find((e) => e.units.some((u) => u.href === href))?.field;
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
 * 順は段ごとに作る（基礎編の最後から、深掘り編へは進まない。初学者が基礎編だけで完結できるようにするため）。
 * 分野の最後の単元の「次」は、同じ段の次の分野の最初の単元とする。最初から最後まで、次の案内だけでたどれるようにするため（要件定義書 AT-09）。
 * isLast は、基礎編の最後の単元だけで true にする（企業分析とニュース解説へ案内する）。
 * href が学習の順にないとき（学習の順に入っていない工程ページなど）は、inPath を false にする。
 */
export function pathNeighbors(preview: boolean, href: string): { inPath: boolean; isLast: boolean; previous?: PathStep; next?: PathStep } {
  for (const { tier, fields } of learnTiers(preview)) {
    const flat = fields.flatMap((e) => e.units.map((link) => ({ link, field: e.field })));
    const at = flat.findIndex((u) => u.link.href === href);
    if (at < 0) continue;
    const here = flat[at].field.slug;
    const step = (u?: { link: UnitLink; field: LearnField }) => (u ? { ...u, crossesField: u.field.slug !== here } : undefined);
    return { inPath: true, isLast: tier.slug === 'basic' && at === flat.length - 1, previous: step(flat[at - 1]), next: step(flat[at + 1]) };
  }
  return { inPath: false, isLast: false };
}

export function neighbors(preview: boolean, page: LearnPage) {
  return pathNeighbors(preview, learnHref(page));
}

export interface DeeperLink {
  href: string;
  title: string;
  summary: string;
  /** 深掘り編のカード（「A. 固体物理学」） */
  card?: string;
}

/**
 * 「さらに深く」（基礎編のページの末尾）：そのページ（href）を applies_to に書いた、公開済みの深掘り編のページ。
 * 深掘り編のページがまだないときは、空（枠を出さない。準備中とも書かない）。
 */
export function deeperLinks(preview: boolean, href: string): DeeperLink[] {
  const resolveUnit = unitResolver(preview);
  const physics = learnTiers(preview).find((t) => t.tier.slug === 'physics');
  const physicsSlugs = new Set((physics?.tier.fields ?? []).map((f) => f.slug));
  return loadLearnPages(preview)
    .filter((page) => physicsSlugs.has(page.field))
    .filter((page) => (page.front.applies_to ?? []).some((a) => resolveUnit(a, '')?.href === href))
    .map((page) => {
      const card = fieldOf(preview, learnHref(page));
      return { href: learnHref(page), title: page.front.title, summary: page.front.description, card: card ? fieldName(card) : undefined };
    });
}

export interface AppliesToLink {
  link: UnitLink;
  note: string;
}

/** 深掘り編のページの「基礎編のどこに効くか」：applies_to のうち、ページのあるもの */
export function appliesToLinks(preview: boolean, page: LearnPage): AppliesToLink[] {
  const resolveUnit = unitResolver(preview);
  return (page.front.applies_to ?? [])
    .map((a) => ({ link: resolveUnit(a, ''), note: a.note }))
    .filter((a): a is AppliesToLink => a.link !== null);
}

/** 学習のページの図（src/figures/learn/{分野}/{slug}.astro）。本サイトで作るSVGの図（仕様書 7章） */
const figureModules = import.meta.glob<{ default: unknown }>('../figures/learn/*/*.astro', { eager: true });
export function learnFigure(page: Pick<LearnPage, 'field' | 'slug'>): unknown | null {
  return figureModules[`../figures/learn/${page.field}/${page.slug}.astro`]?.default ?? null;
}
