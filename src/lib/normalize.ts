// 検索のための正規化（FR-701）：全角と半角、ひらがなとカタカナ、大文字と小文字を、同じものとして扱う。
// ビルドのときの検索用データと、画面の入力の両方が、この関数を使う（同じ結果になるように）。

/** NFKC（全角英数・半角カナを標準の形に）、小文字、ひらがな化、空白の除去 */
export function normalizeForSearch(text: string): string {
  return unicodeKatakanaToHiragana(text.normalize('NFKC').toLowerCase()).replace(/[\s　]+/g, '');
}

function unicodeKatakanaToHiragana(text: string): string {
  let out = '';
  for (const ch of text) {
    const code = ch.codePointAt(0) ?? 0;
    out += code >= 0x30a1 && code <= 0x30f6 ? String.fromCodePoint(code - 0x60) : ch;
  }
  return out;
}

export interface SearchEntry {
  type: 'company' | 'process' | 'term' | 'news';
  name: string; // 表示する名前（企業は略称）
  url: string;
  code?: string; // 証券コード
  detail?: string; // 補足（正式名称、読み、ニュースの公開日など。表示用）
  keys: string[]; // 正規化した検索の語（正式名称、略称、英語表記、読み、証券コード、別の表記など）
}

/** 検索の語（query）に当たるか。空白で区切った語のすべてが、どれかの keys に含まれること */
export function matchEntry(entry: SearchEntry, query: string): number {
  const tokens = query.split(/[\s　]+/).map(normalizeForSearch).filter(Boolean);
  if (tokens.length === 0) return -1;
  let score = 0;
  for (const token of tokens) {
    let best = -1;
    for (const key of entry.keys) {
      if (key === token) best = Math.max(best, 3);
      else if (key.startsWith(token)) best = Math.max(best, 2);
      else if (key.includes(token)) best = Math.max(best, 1);
    }
    if (best < 0) return -1;
    score += best;
  }
  return score;
}

export function search(entries: SearchEntry[], query: string, limit = 50): SearchEntry[] {
  return entries
    .map((entry) => ({ entry, score: matchEntry(entry, query) }))
    .filter((x) => x.score >= 0)
    .sort((a, b) => b.score - a.score || a.entry.type.localeCompare(b.entry.type))
    .slice(0, limit)
    .map((x) => x.entry);
}
