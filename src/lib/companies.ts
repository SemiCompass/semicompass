// 企業ページの材料を、ファイル（data/companies、data/auto、data/segments、content/companies、data/supply-chain.yaml）から読む。
// 数値はここで直接書かず、ファイルの値を使う。ビルドは、リポジトリの直下で動かす（npm run build）。
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { parse } from 'yaml';
import { dateLabel, formatOku, formatNumber, millionToOku, periodLabel } from './format';
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
  segments: { name: string; xbrl_members?: string[]; classification: 'semiconductor' | 'partial' | 'excluded'; note?: string }[];
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

/** セグメント別の売上の積み上げ。区分は data/segments の classification。対応表がないときは null */
export function segmentSpec(rows: FinancialRow[], map: SegmentMap | null, colors: ChartColors): { spec: ChartSpec; ratio: { value: number; period: string } | null } | null {
  const withSeg = rows.filter((r) => r.segments.length > 0);
  if (!map || withSeg.length === 0) return null;
  const lookup = new Map<string, { name: string; classification: (typeof ORDER)[number] }>();
  for (const s of map.segments) for (const m of s.xbrl_members ?? []) lookup.set(m, { name: s.name, classification: s.classification });
  const latest = withSeg[withSeg.length - 1];
  const members = latest.segments.map((s) => s.member).filter((m) => lookup.has(m));
  if (members.length === 0) return null;
  const ordered = [...members].sort((a, b) => ORDER.indexOf(lookup.get(a)!.classification) - ORDER.indexOf(lookup.get(b)!.classification));
  const series: Series[] = ordered.map((member) => {
    const info = lookup.get(member)!;
    const c = colors.segment_classification[info.classification];
    return { name: info.name, color: c.color, pattern: c.pattern, note: c.legend,
      values: withSeg.map((r) => oku(r.segments.find((s) => s.member === member)?.net_sales_external)) };
  });
  // 半導体関連の比率：「半導体関連」の区分のセグメントの外部顧客への売上 ÷ 全セグメントの合計（最新の通期）
  const total = latest.segments.reduce((a, s) => a + (s.net_sales_external.value ?? 0), 0);
  const semi = latest.segments.filter((s) => lookup.get(s.member)?.classification === 'semiconductor').reduce((a, s) => a + (s.net_sales_external.value ?? 0), 0);
  const ratio = total > 0 ? { value: Math.round((semi / total) * 1000) / 10, period: periodLabel(latest.fiscal_period_end) } : null;
  return { spec: { kind: 'stacked', categories: withSeg.map((r) => category(r.fiscal_period_end)), series, unit: '億円', decimals: 1, labelLatest: true }, ratio };
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

export { dateLabel, formatNumber, formatOku, periodLabel };
