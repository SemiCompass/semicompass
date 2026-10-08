// 企業の表の指標（FR-309）：営業利益率と平均年間給与。値は data/auto/ から取り、ここでは、計算と「最新の期」の選び方だけを行う。
// 他のファイルを import しない（Node.js で、単体テストから直接読めるようにするため）。

export interface Reported {
  value: number | null;
  doc_id?: string;
}
export interface FinancialLike {
  fiscal_period_end: string;
  period_type: string;
  net_sales: Reported;
  operating_income: Reported;
}
export interface EmployeeLike {
  fiscal_period_end: string;
  non_consolidated: { average_annual_salary?: Reported };
}

/** 分子÷分母を、整数に丸める（四捨五入。0.5は切り上げ）。分母は、正の数。浮動小数点の誤差を避けるため、割り算を1回にする */
export function roundHalfUp(numerator: number, denominator: number): number {
  return Math.floor((2 * numerator + denominator) / (2 * denominator));
}

/** 最新の通期（period_type: annual）の行。半期の行は、新しくても選ばない */
export function latestAnnual<T extends FinancialLike>(rows: T[]): T | undefined {
  return rows.filter((r) => r.period_type === 'annual').reduce<T | undefined>((a, r) => (!a || r.fiscal_period_end > a.fiscal_period_end ? r : a), undefined);
}

/** 最新の期の行（fiscal_period_end が最も新しい行） */
export function latestPeriod<T extends { fiscal_period_end: string }>(rows: T[]): T | undefined {
  return rows.reduce<T | undefined>((a, r) => (!a || r.fiscal_period_end > a.fiscal_period_end ? r : a), undefined);
}

/**
 * 営業利益率（％）＝営業利益÷売上高×100（全社の連結、最新の通期。どちらも百万円）。小数第1位まで（四捨五入。負の値は、絶対値を丸めて符号を戻す）。
 * 営業利益か売上高が取れない（null）、売上高が0以下のときは null。営業損失（負の値）は、そのまま出す。
 */
export function operatingMargin(financials: FinancialLike[]): number | null {
  const latest = latestAnnual(financials);
  const profit = latest?.operating_income?.value;
  const sales = latest?.net_sales?.value;
  if (profit === null || profit === undefined || sales === null || sales === undefined || sales <= 0) return null;
  const sign = profit < 0 ? -1 : 1;
  const rounded = (sign * roundHalfUp(Math.abs(profit) * 1000, sales)) / 10;
  return rounded === 0 ? 0 : rounded; // -0 を出さない
}

/** 平均年間給与（万円）：最新の期の行の、提出会社の平均年間給与（円）÷10,000 を、整数に丸める。値がなければ null */
export function averageSalary(employees: EmployeeLike[]): number | null {
  const yen = latestPeriod(employees)?.non_consolidated?.average_annual_salary?.value;
  if (yen === null || yen === undefined) return null;
  const sign = yen < 0 ? -1 : 1;
  return sign * roundHalfUp(Math.abs(yen), 10000);
}
