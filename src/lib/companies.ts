// 企業ページの材料を、ファイル（data/companies、data/auto、data/segments、content/companies、data/supply-chain.yaml）から読む。
// 数値はここで直接書かず、ファイルの値を使う。ビルドは、リポジトリの直下で動かす（npm run build）。
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { parse } from 'yaml';
import { dateLabel, formatOku, formatNumber, millionToOku, periodLabel } from './format';
import { averageSalary, operatingMargin } from './metrics';
import type { Category, ChartSpec, Series } from './chart';

const root = process.cwd();
const read = (rel: string) => readFileSync(resolve(root, rel), 'utf-8');

export interface Reported {
  value: number | null;
  doc_id?: string;
}
export interface FinancialRow {
  fiscal_period_end: string;
  period_type: 'annual' | 'half';
  accounting_standard: string;
  doc_id: string;
  net_sales: Reported;
  operating_income: Reported;
  segments: { name: string; member: string; net_sales_external: Reported }[];
  regions: { name: string; member?: string; net_sales: Reported }[];
}
export interface EmployeeRow {
  fiscal_period_end: string;
  as_of: string;
  consolidated?: { employees: Reported };
  non_consolidated: {
    employees: Reported;
    average_age?: Reported;
    average_length_of_service?: Reported;
    average_annual_salary?: Reported;
  };
}
export interface Auto {
  updated_at: string;
  filings: { doc_id: string; doc_type: string; status: string; fiscal_period_end: string; url: string; submitted_at: string }[];
  financials: FinancialRow[];
  employees: EmployeeRow[];
}
export interface Source {
  id: string;
  title: string;
  publisher: string;
  url: string;
  published_on?: string;
  accessed_on: string;
  doc_id?: string;
  pages?: string;
}
export interface Company {
  slug: string;
  name: string;
  short_names: string[];
  type: string;
  securities_code?: string;
  categories: string[];
  processes: string[];
  listing: string;
  tagline: string;
  website_url?: string;
  ir_url?: string;
  recruit_url?: string;
  is_holding_company?: boolean;
}
export interface SegmentMap {
  segments: {
    name: string;
    xbrl_members?: string[];
    classification: 'semiconductor' | 'partial' | 'excluded';
    note?: string;
    rationale?: { source: string; pages: string };
  }[];
  sources?: Source[];
}
export interface Overview {
  front: { company: string; published_at: string; updated_at?: string; draft?: boolean; ai_generated: boolean; reviewed_filing?: string; sources: Source[] };
  sections: { heading: string; paragraphs: string[] }[];
}
export interface Supply {
  categories: { slug: string; name: string }[];
  processes: { slug: string; name: string }[];
}

export function loadCompanies(): Company[] {
  return readdirSync(resolve(root, 'data/companies'))
    .filter((f) => f.endsWith('.yaml'))
    .sort()
    .map((f) => {
      const c = parse(read(`data/companies/${f}`)) as Company;
      return { ...c, categories: c.categories ?? [], processes: c.processes ?? [], short_names: c.short_names ?? [] };
    });
}
export function loadSupply(): Supply {
  return parse(read('data/supply-chain.yaml')) as Supply;
}
export function loadAuto(slug: string): Auto | null {
  return existsSync(resolve(root, `data/auto/${slug}.json`)) ? (JSON.parse(read(`data/auto/${slug}.json`)) as Auto) : null;
}
export function loadSegmentMap(slug: string): SegmentMap | null {
  return existsSync(resolve(root, `data/segments/${slug}.yaml`)) ? (parse(read(`data/segments/${slug}.yaml`)) as SegmentMap) : null;
}
export function parseOverview(text: string): Overview {
  const match = /^---\n([\s\S]*?)\n---\n?([\s\S]*)$/.exec(text.replace(/\r\n/g, '\n'));
  if (!match) throw new Error('front matter がない');
  const front = parse(match[1]) as Overview['front'];
  const sections: Overview['sections'] = [];
  for (const block of match[2].split(/^## /m).slice(1)) {
    const [heading, ...rest] = block.split('\n');
    sections.push({ heading: heading.trim(), paragraphs: rest.join('\n').split(/\n{2,}/).map((p) => p.trim().replace(/\n/g, '')).filter(Boolean) });
  }
  return { front, sections };
}
export function loadOverview(slug: string): Overview | null {
  return existsSync(resolve(root, `content/companies/${slug}.md`)) ? parseOverview(read(`content/companies/${slug}.md`)) : null;
}

/** 詳細掲載として出すか。本番：listing が detailed で、事業概要が公開（draft でない）のとき。プレビュー：draft: true の事業概要があれば、確認のため詳細掲載として出す */
export function isDetailed(company: Company, overview: Overview | null, auto: Auto | null, preview: boolean): boolean {
  if (!overview || !auto) return false;
  if (overview.front.draft) return preview;
  return company.listing === 'detailed';
}

// ---- グラフの材料 ----
export function annualRows(auto: Auto): FinancialRow[] {
  return auto.financials.filter((r) => r.period_type === 'annual').sort((a, b) => a.fiscal_period_end.localeCompare(b.fiscal_period_end));
}
export function category(fiscalPeriodEnd: string): Category {
  const [y, m] = fiscalPeriodEnd.split('-').map(Number);
  return { label: periodLabel(fiscalPeriodEnd), short: `${String(y).slice(2)}/${m}`, lines: [`${y}年`, `${m}月期`] };
}
const oku = (r: Reported | undefined): number | null => (r && r.value !== null && r.value !== undefined ? millionToOku(r.value) : null);

export function periodRange(rows: { fiscal_period_end: string }[]): string {
  return rows.length === 0 ? '' : `${periodLabel(rows[0].fiscal_period_end)}〜${periodLabel(rows[rows.length - 1].fiscal_period_end)}`;
}

export function barSpec(rows: FinancialRow[], key: 'net_sales' | 'operating_income', name: string, colors: { color: string }): ChartSpec | null {
  const used = rows.filter((r) => oku(r[key]) !== null);
  if (used.length === 0) return null;
  return {
    kind: 'bar', categories: used.map((r) => category(r.fiscal_period_end)), unit: '億円', decimals: 1, labelLatest: true, withChange: true,
    series: [{ name, color: colors.color, values: used.map((r) => oku(r[key])) }],
  };
}

const ORDER = ['semiconductor', 'partial', 'excluded'] as const;
export interface ChartColors {
  segment_classification: Record<string, { color: string; pattern: boolean; legend: string }>;
  metrics: Record<string, { color: string; line: string }>;
}
export function loadChartColors(): ChartColors {
  return parse(read('config/chart-colors.yaml')) as ChartColors;
}

const CATEGORY_COLORS = ['--chart-cat-1', '--chart-cat-2', '--chart-cat-3', '--chart-cat-4']; // 仕様書 4.3

export interface SegmentSource {
  title: string;
  publisher: string;
  accessedOn: string;
  pages: string;
}
export interface SegmentResult {
  /** 積み上げのグラフ。区分のあるセグメントの値がないときは null */
  spec: ChartSpec | null;
  /** 半導体関連の比率（%）と、その期。算出できないときは null */
  ratio: { value: number; period: string } | null;
  /** 報告セグメントが1つで、半導体関連の区分のとき（全社の売上が半導体関連）：セグメントの名前と、根拠（データ定義書 4.2 の rationale と sources） */
  single: { name: string; source: SegmentSource | null } | null;
  /** 対応表のファイルはあるが、グラフにできないときの理由 */
  reason: string | null;
}

/**
 * セグメント別の売上を作る。区分は data/segments の classification。
 * ・報告セグメントが1つで、semiconductor のとき：比率は100.0%、グラフは作らず、根拠を示す
 * ・半導体関連以外が2つ以上のとき：グラフでは「半導体関連以外（計）」の1つにまとめ、内訳は表に出す
 * ・半導体関連が2つ以上のとき：--chart-cat-1〜4 で分け、表を添える
 * ・積み上げの上に、セグメントの合計は出さない（連結売上高と合わないため）。最新の期の半導体関連の値と比率だけをラベルにする
 */
export function segmentSpec(rows: FinancialRow[], map: SegmentMap, colors: ChartColors, latestPeriod: string): SegmentResult {
  const reasonNone: SegmentResult = { spec: null, ratio: null, single: null, reason: 'この期のセグメント別の売上は、開示から取り込めていません。' };
  if (map.segments.length === 1 && map.segments[0].classification === 'semiconductor') {
    const only = map.segments[0];
    const src = map.sources?.find((x) => x.id === only.rationale?.source);
    return {
      spec: null, ratio: { value: 100, period: latestPeriod }, reason: null,
      single: { name: only.name, source: src ? { title: src.title, publisher: src.publisher, accessedOn: src.accessed_on, pages: only.rationale?.pages ?? '' } : null },
    };
  }
  const withSeg = rows.filter((r) => r.segments.length > 0);
  if (withSeg.length === 0) return reasonNone;
  const lookup = new Map<string, { name: string; classification: (typeof ORDER)[number] }>();
  for (const s of map.segments) for (const m of s.xbrl_members ?? []) lookup.set(m, { name: s.name, classification: s.classification });
  const latest = withSeg[withSeg.length - 1];
  const members = latest.segments.map((s) => s.member).filter((m) => lookup.has(m));
  if (members.length === 0) return reasonNone;
  const byClass = (c: (typeof ORDER)[number]) => members.filter((m) => lookup.get(m)!.classification === c);
  const valuesOf = (member: string) => withSeg.map((r) => oku(r.segments.find((s) => s.member === member)?.net_sales_external));

  const semis = byClass('semiconductor');
  const partials = byClass('partial');
  const others = byClass('excluded');
  let nextCategory = 0;
  const takeCategory = () => CATEGORY_COLORS[Math.min(nextCategory++, CATEGORY_COLORS.length - 1)];
  const series: Series[] = [];
  const detail: Series[] = [];
  const cls = (c: string) => colors.segment_classification[c];
  for (const m of semis) {
    const color = semis.length === 1 ? cls('semiconductor').color : takeCategory(); // 2つ以上：濃淡ではなく --chart-cat-1〜4
    const item = { name: lookup.get(m)!.name, color, note: cls('semiconductor').legend, values: valuesOf(m) };
    series.push(item);
    detail.push(item);
  }
  for (const m of partials) {
    const color = semis.length > 1 || nextCategory > 0 ? takeCategory() : cls('partial').color;
    const item = { name: lookup.get(m)!.name, color, note: cls('partial').legend, values: valuesOf(m) };
    series.push(item);
    detail.push(item);
  }
  const otherItems = others.map((m) => ({ name: lookup.get(m)!.name, color: cls('excluded').color, pattern: cls('excluded').pattern, note: cls('excluded').legend, values: valuesOf(m) }));
  detail.push(...otherItems);
  if (otherItems.length === 1) series.push(otherItems[0]);
  else if (otherItems.length >= 2) {
    series.push({ name: '半導体関連以外（計）', color: cls('excluded').color, pattern: cls('excluded').pattern,
      values: withSeg.map((_, i) => (otherItems.every((o) => o.values[i] === null) ? null : otherItems.reduce((a, o) => a + (o.values[i] ?? 0), 0))) });
  }

  // 半導体関連の比率：「半導体関連」の区分のセグメントの外部顧客への売上 ÷ 区分のあるセグメントの合計（最新の通期）。計算は百万円の値で行う
  const mappedTotal = members.reduce((a, m) => a + (latest.segments.find((s) => s.member === m)?.net_sales_external.value ?? 0), 0);
  const semiValue = semis.reduce((a, m) => a + (latest.segments.find((s) => s.member === m)?.net_sales_external.value ?? 0), 0);
  const ratioValue = mappedTotal > 0 && semis.length > 0 ? Math.round((semiValue / mappedTotal) * 1000) / 10 : null;
  const period = periodLabel(latest.fiscal_period_end);
  const unmapped = latest.segments.length > members.length;
  const note = `セグメントの合計は、調整額を含まないため、連結売上高と一致しません。${unmapped ? '区分の対応表にない項目は、含みません。' : ''}${others.length >= 2 ? '半導体関連以外の内訳は、「表で見る」に出ています。' : ''}${semis.length > 1 ? '半導体関連の区分ごとの数値は、「表で見る」に出ています。' : ''}`;
  const latestLabel = ratioValue !== null && semis.length > 0
    ? ['半導体関連', `${formatNumber(millionToOku(semiValue), 1)}億円（${formatNumber(ratioValue, 1)}%）`]
    : undefined;
  return {
    reason: null, single: null,
    ratio: ratioValue !== null ? { value: ratioValue, period } : null,
    spec: { kind: 'stacked', categories: withSeg.map((r) => category(r.fiscal_period_end)), series, tableSeries: detail, unit: '億円', decimals: 1,
      labelLatest: false, latestLabel, note },
  };
}

export function regionSpec(rows: FinancialRow[], colors: ChartColors): { spec: ChartSpec; period: string } | null {
  const latest = [...rows].reverse().find((r) => r.regions.length > 0);
  if (!latest) return null;
  const regions = [...latest.regions].filter((r) => oku(r.net_sales) !== null).sort((a, b) => (b.net_sales.value ?? 0) - (a.net_sales.value ?? 0));
  return { period: periodLabel(latest.fiscal_period_end),
    spec: { kind: 'hbar', unit: '億円', decimals: 1, labelLatest: false,
      categories: regions.map((r) => ({ label: r.name, short: r.name.length > 7 ? `${r.name.slice(0, 6)}…` : r.name, lines: [r.name] })),
      series: [{ name: '売上高', color: colors.metrics.region_sales.color, values: regions.map((r) => oku(r.net_sales)) }] } };
}

export function employeeValue(e: EmployeeRow): number | null {
  return (e.consolidated?.employees.value ?? e.non_consolidated.employees.value) ?? null;
}
export function employeeSpec(auto: Auto, colors: ChartColors): { spec: ChartSpec; rows: EmployeeRow[] } | null {
  const rows = [...auto.employees].filter((e) => employeeValue(e) !== null).sort((a, b) => a.fiscal_period_end.localeCompare(b.fiscal_period_end));
  if (rows.length === 0) return null;
  return { rows, spec: { kind: 'line', unit: '人', decimals: 0, labelLatest: true, withChange: true,
    categories: rows.map((r) => category(r.fiscal_period_end)),
    series: [{ name: '従業員数', color: colors.metrics.employees.color, values: rows.map((r) => employeeValue(r)) }] } };
}

export const typeLabel: Record<string, string> = {
  domestic_listed: '国内上場企業',
  conglomerate: '総合メーカー',
  foreign_subsidiary: '外資系日本法人',
};

export interface CompanyRow {
  company: Company;
  detailed: boolean; // 詳細掲載として出すか（本番：listing が detailed で、事業概要が公開のとき。プレビュー：draft の事業概要も）
  sales: number | null; // 売上高（億円。最新の通期）。詳細掲載でなければ null
  ratio: number | null; // 半導体関連の比率（%）。詳細掲載でなければ null
  margin: number | null; // 営業利益率（%。全社の連結、最新の通期）。取れない値と、詳細掲載でなければ null
  salary: number | null; // 平均年間給与（万円。提出会社、最新の期）。取れない値と、詳細掲載でなければ null
  period: string;
}

/** 企業一覧の行。企業は、証券コードの順（外資系日本法人など、コードのない企業は末尾） */
export function companyRows(preview: boolean): CompanyRow[] {
  const colors = loadChartColors();
  const rows = loadCompanies().map((company): CompanyRow => {
    const overview = loadOverview(company.slug);
    const auto = loadAuto(company.slug);
    const detailed = isDetailed(company, overview, auto, preview);
    if (!detailed || !auto) return { company, detailed, sales: null, ratio: null, margin: null, salary: null, period: '' };
    const annual = annualRows(auto);
    const latest = annual[annual.length - 1];
    const salary = averageSalary(auto.employees ?? []);
    if (!latest) return { company, detailed, sales: null, ratio: null, margin: null, salary, period: '' };
    const map = loadSegmentMap(company.slug);
    const segment = map ? segmentSpec(annual, map, colors, periodLabel(latest.fiscal_period_end)) : null;
    return { company, detailed, period: periodLabel(latest.fiscal_period_end),
      sales: latest.net_sales.value === null ? null : millionToOku(latest.net_sales.value), ratio: segment?.ratio?.value ?? null,
      margin: operatingMargin(auto.financials), salary };
  });
  return rows.sort((a, b) => (a.company.securities_code ?? '99999').localeCompare(b.company.securities_code ?? '99999') || a.company.slug.localeCompare(b.company.slug));
}

export { dateLabel, formatNumber, formatOku, periodLabel };
