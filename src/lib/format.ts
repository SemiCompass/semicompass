// 数値と期の表示（CLAUDE.md 5.1：3桁ごとにカンマ、金額は億円で小数第1位、期を示す）。数値はファイルから読み、ここでは形だけを整える。

/** 百万円 → 億円（小数第1位に四捨五入。負の値は絶対値で四捨五入する） */
export function millionToOku(million: number): number {
  const sign = million < 0 ? -1 : 1;
  return (sign * Math.round(Math.abs(million) / 10)) / 10;
}

export function formatNumber(value: number, decimals = 1): string {
  return value.toLocaleString('ja-JP', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

/** 百万円の値を「24,435.3億円」の形にする */
export function formatOku(million: number): string {
  return `${formatNumber(millionToOku(million), 1)}億円`;
}

/** 「2026-03」→「2026年3月期」 */
export function periodLabel(yearMonth: string, periodType: 'annual' | 'half' = 'annual'): string {
  const [y, m] = yearMonth.split('-').map(Number);
  return `${y}年${m}月期${periodType === 'half' ? '第2四半期' : ''}`;
}

/** 日付（YYYY-MM-DD か日時）→「2026年10月6日」 */
export function dateLabel(value: string): string {
  const [y, m, d] = value.slice(0, 10).split('-').map(Number);
  return `${y}年${m}月${d}日`;
}

/** 増減の表示：「＋12.3%」「−4.5%」（符号と矢印を添える。色だけで示さない） */
export function formatChange(current: number, previous: number): string | null {
  if (!previous) return null;
  const ratio = Math.round(((current - previous) / Math.abs(previous)) * 1000) / 10;
  const arrow = ratio > 0 ? '↑' : ratio < 0 ? '↓' : '→';
  const sign = ratio > 0 ? '＋' : ratio < 0 ? '−' : '';
  return `${sign}${formatNumber(Math.abs(ratio), 1)}%${arrow}`;
}
