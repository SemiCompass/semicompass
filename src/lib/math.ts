// 式（深掘り編「半導体の物理」のページ。データ定義書 6.8、仕様書 8.18）：本文の TeX の書き方の式を、ビルドのときに MathML にする。
// 閲覧ソフトが標準で描くため、JavaScript も Webフォントも使わない（CLAUDE.md 9章）。書き方の誤りは、ビルドを止める。
import temml from 'temml';

/** 段落全体が「$$ … $$」のとき、行の式（ブロック）とする */
const DISPLAY = /^\$\$([\s\S]+?)\$\$$/;
/** 文の中の「$ … $」 */
export const INLINE_MATH = /\$([^$\n]+?)\$/g;

export function renderMath(tex: string, display: boolean): string {
  return temml.renderToString(tex.trim(), { displayMode: display, throwOnError: true, xml: false });
}

/**
 * 段落が行の式なら、その MathML。そうでなければ null。
 * 行の式は左にそろえる（中央揃えにしない。CLAUDE.md 9章）ため、ブロックの math（閲覧ソフトが中央に置く）にせず、
 * 文の中の math を \\displaystyle の大きさで組み、呼ぶ側のブロック（.math-display）に入れる
 */
export function displayMath(paragraph: string): string | null {
  const match = DISPLAY.exec(paragraph.trim());
  return match ? renderMath(`\\displaystyle ${match[1].trim()}`, false) : null;
}

/** 文の中の式で、段落を分ける（式でない部分は、呼ぶ側で文節などに分ける） */
export function splitInlineMath(paragraph: string): ({ kind: 'text'; text: string } | { kind: 'math'; html: string })[] {
  const result: ({ kind: 'text'; text: string } | { kind: 'math'; html: string })[] = [];
  let last = 0;
  for (const match of paragraph.matchAll(INLINE_MATH)) {
    const index = match.index ?? 0;
    if (index > last) result.push({ kind: 'text', text: paragraph.slice(last, index) });
    result.push({ kind: 'math', html: renderMath(match[1], false) });
    last = index + match[0].length;
  }
  if (last < paragraph.length) result.push({ kind: 'text', text: paragraph.slice(last) });
  return result;
}
