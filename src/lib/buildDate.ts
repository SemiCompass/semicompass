// ビルドの日（YYYY-MM-DD、日本時間）。日付で変わる計算は、現在の日付ではなく、この値を使う（CLAUDE.md 9章）。
// 環境変数 BUILD_DATE があればその値、なければビルドした日。
export function buildDate(env: string | undefined): string {
  if (env && /^\d{4}-\d{2}-\d{2}$/.test(env)) return env;
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Tokyo', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  return parts;
}
