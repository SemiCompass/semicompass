// 文節の切れ目（BudouX）：ビルドのときに、日本語の文を文節に分ける。<wbr> を入れて、Safariでも文節の切れ目で折り返す。
// （CSSの word-break: auto-phrase は残す。対応する閲覧ソフトでは、両方が働く）
import { loadDefaultJapaneseParser } from 'budoux';

const parser = loadDefaultJapaneseParser();

export function phrases(text: string): string[] {
  return parser.parse(text);
}

/** 数値と単位（「9,999,999.9億円」「12.3%」など）は、折り返さないひとまとまりにする */
export const NUMBER_WITH_UNIT = /[＋−+-]?[0-9][0-9,]*(?:\.[0-9]+)?(?:億円|百万円|万円|円|%|人|歳|年|倍|月期|月|日|期|字|件)?/g;

export type Piece = { kind: 'text'; phrases: string[] } | { kind: 'number'; text: string } | { kind: 'citation'; number: number };

/** 本文の1段落を、文節、数値と単位、出典の番号（[S1]）に分ける */
export function pieces(paragraph: string): Piece[] {
  const result: Piece[] = [];
  const pattern = new RegExp(`\\[S([0-9]+)\\]|${NUMBER_WITH_UNIT.source}`, 'g');
  let last = 0;
  for (const match of paragraph.matchAll(pattern)) {
    const index = match.index ?? 0;
    if (index > last) result.push({ kind: 'text', phrases: phrases(paragraph.slice(last, index)) });
    if (match[1] !== undefined) result.push({ kind: 'citation', number: Number(match[1]) });
    else result.push({ kind: 'number', text: match[0] });
    last = index + match[0].length;
  }
  if (last < paragraph.length) result.push({ kind: 'text', phrases: phrases(paragraph.slice(last)) });
  return result;
}
