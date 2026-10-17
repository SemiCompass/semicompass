// IR重要ポイント（content/ir-points/{slug}/{決算期}-q{四半期}.md、データ定義書 6.3）と、
// 「最新の決算は未反映」（CT-03、データ定義書 14章の表「最新の決算の反映」）の計算。
// 日付で変わる計算は、ビルドの日（BUILD_DATE）で行う（CLAUDE.md 9章）。
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { parse } from 'yaml';
import type { Source } from './companies';
import { parseMarkdown, visible, type Markdown } from './content';

const root = resolve(process.cwd());

export interface IrFront {
  company: string;
  fiscal_period_end: string;
  quarter: number;
  announced_on: string;
  uses_quarterly_figures: boolean;
  published_at: string;
  updated_at?: string;
  draft?: boolean;
  under_review?: boolean;
  sources: Source[];
}
export type IrPoint = Markdown<IrFront>;

export interface Announcement {
  fiscal_period_end: string;
  quarter: number;
  announced_on: string;
  documents: { type: 'tanshin' | 'presentation'; title: string; url: string; published_at: string }[];
}

export const IR_HEADINGS = ['業績の要点', '今期見通し', '注目材料'] as const;

const order = (a: { fiscal_period_end: string; quarter: number }, b: { fiscal_period_end: string; quarter: number }) =>
  a.fiscal_period_end === b.fiscal_period_end ? a.quarter - b.quarter : a.fiscal_period_end < b.fiscal_period_end ? -1 : 1;

/** 企業のIR重要ポイント（古い順）。draft: true は、プレビューのビルドでだけ含める。 */
export function loadIrPoints(slug: string, preview: boolean, base: string = root): IrPoint[] {
  const dir = resolve(base, 'content', 'ir-points', slug);
  if (!existsSync(dir)) return [];
  return readdirSync(dir)
    .filter((name) => /^\d{4}-\d{2}-q[1-4]\.md$/.test(name))
    .map((name) => parseMarkdown<IrFront>(readFileSync(resolve(dir, name), 'utf-8')))
    .filter((point) => visible(point.front, preview))
    .sort((a, b) => order(a.front, b.front));
}

/** 営業日を足す（土日をとばす。祝日の暦はまだ持たないため、祝日は営業日に数える）。 */
export function addBusinessDays(date: string, days: number): string {
  const d = new Date(`${date}T00:00:00Z`);
  let left = days;
  while (left > 0) {
    d.setUTCDate(d.getUTCDate() + 1);
    const w = d.getUTCDay();
    if (w !== 0 && w !== 6) left -= 1;
  }
  return d.toISOString().slice(0, 10);
}

export interface IrStatus {
  latest: Announcement | null; // ビルドの日までの、最新の決算発表
  point: IrPoint | null; // 表示するIR重要ポイント（最新）
  stale: boolean; // 最新の決算発表に対応するIR重要ポイントがなく、期限を過ぎた
  deadline: string | null; // 最新の決算発表の期限（発表日＋営業日）
}

/** 最新の決算の反映（CT-03）：最新の決算発表に対応するIR重要ポイントがなく、発表から businessDays 営業日を過ぎていれば未反映。 */
export function irStatus(announcements: Announcement[], points: IrPoint[], today: string, businessDays: number): IrStatus {
  const past = announcements.filter((a) => a.announced_on <= today).sort((a, b) => (a.announced_on < b.announced_on ? -1 : 1));
  const latest = past[past.length - 1] ?? null;
  const point = points[points.length - 1] ?? null;
  if (!latest) return { latest: null, point, stale: false, deadline: null };
  const deadline = addBusinessDays(latest.announced_on, businessDays);
  const covered = points.some((p) => p.front.fiscal_period_end === latest.fiscal_period_end && p.front.quarter === latest.quarter);
  return { latest, point, stale: !covered && today > deadline, deadline };
}

/** 業績のグラフ（年次・半期）が、IR重要ポイントの期をまだ含まないか（FR-307 の注記）。 */
export function chartBehind(point: IrPoint, periods: { fiscal_period_end: string; period_type: string }[]): boolean {
  const { fiscal_period_end: fpe, quarter } = point.front;
  if (quarter === 1 || quarter === 3) return true;
  const type = quarter === 4 ? 'annual' : 'half';
  return !periods.some((p) => p.fiscal_period_end === fpe && p.period_type === type);
}

/** 本文の出典の番号を、ページの出典の一覧の番号にずらす（[S1] → [S{1+offset}]）。 */
export function shiftCitations(text: string, offset: number): string {
  return text.replace(/\[S(\d+)\]/g, (_, n: string) => `[S${Number(n) + offset}]`);
}

export function irPeriodLabel(fiscalPeriodEnd: string, quarter: number): string {
  const [y, m] = fiscalPeriodEnd.split('-').map(Number);
  return quarter === 4 ? `${y}年${m}月期` : `${y}年${m}月期第${quarter}四半期`;
}

export function loadOperationsDays(base: string = root): number {
  const data = parse(readFileSync(resolve(base, 'config', 'operations.yaml'), 'utf-8')) as { deadlines?: { ir_business_days?: number } };
  return data.deadlines?.ir_business_days ?? 5;
}
