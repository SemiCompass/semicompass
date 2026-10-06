// 文節の切れ目（BudouX）：ビルドのときに、日本語の文を文節に分ける。<wbr> を入れて、Safariでも文節の切れ目で折り返す。
// （CSSの word-break: auto-phrase は残す。対応する閲覧ソフトでは、両方が働く）
import { loadDefaultJapaneseParser } from 'budoux';

const parser = loadDefaultJapaneseParser();

export function phrases(text: string): string[] {
  return parser.parse(text);
}

/** 数値と単位（「9,999,999.9億円」「12.3%」など）は、折り返さないひとまとまりにする */
export const NUMBER_WITH_UNIT = /[＋−+-]?[0-9][0-9,]*(?:\.[0-9]+)?(?:億円|百万円|万円|円|%|人|歳|年|倍|月期|月|日|期|字|件)?/g;

export type Piece =
  | { kind: 'text'; phrases: string[] }
  | { kind: 'number'; text: string }
  // 出典の番号：直前の1字（または数値と単位）と、直後の句読点を含めて、折り返さない一続きにする（行の頭に「。」「、」が来ない）
  | { kind: 'cite'; lead: string; numbers: number[]; after: string };

const PUNCTUATION = '。、，．）」』';

/**
 * 本文の出典の番号を整える。
 * ・番号の前の空白を除く（「である。 [S1]」→「である。[S1]」）
 * ・番号が句読点の後ろにある書き方（「〜である。[S1]」）は、句読点の前に移す（「〜である[S1]。」）
 */
export function normalizeCitations(paragraph: string): string {
  return paragraph
    .replace(/[ \t\u3000]+(\[S[0-9]+\])/g, '$1')
    .replace(/([。、，．])((?:\[S[0-9]+\])+)/g, '$2$1');
}

/** 本文の1段落を、文節、数値と単位、出典の番号（[S1]）に分ける */
export function pieces(paragraph: string): Piece[] {
  const text = normalizeCitations(paragraph);
  const result: Piece[] = [];
  const pattern = new RegExp(`((?:\\[S[0-9]+\\])+)([${PUNCTUATION}]*)|${NUMBER_WITH_UNIT.source}`, 'g');
  let last = 0;
  const pushText = (value: string) => {
    if (value) result.push({ kind: 'text', phrases: phrases(value) });
  };
  for (const match of text.matchAll(pattern)) {
    const index = match.index ?? 0;
    if (match[1] === undefined) {
      pushText(text.slice(last, index));
      result.push({ kind: 'number', text: match[0] });
    } else {
      const before = text.slice(last, index);
      let lead = '';
      let head = before;
      const previous = result[result.length - 1];
      if (before === '' && previous?.kind === 'number') {
        lead = previous.text; // 数値と単位の直後の番号：数値と一続きにする
        result.pop();
      } else if (before !== '') {
        const chars = [...before];
        lead = chars.pop() ?? '';
        head = chars.join('');
      }
      pushText(head);
      const numbers = [...match[1].matchAll(/\[S([0-9]+)\]/g)].map((m) => Number(m[1]));
      result.push({ kind: 'cite', lead, numbers, after: match[2] });
    }
    last = index + match[0].length;
  }
  pushText(text.slice(last));
  return result;
}
