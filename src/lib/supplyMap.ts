// サプライチェーンマップの図の形の計算（FR-102、仕様書 10章）：ビルドのときに、SVGの図形の位置と大きさを計算する。
// 文字は、仕様書の最小の大きさ（--text-small = 14px）で読めるよう、SVGの座標を画面の画素と同じ大きさにする。
// 幅の違う2つの図（compact：スマートフォン＝縦に並べる、wide：タブレット以上＝段階を横に並べる）を作り、CSSで切り替える。

export type MapLayout = 'compact' | 'wide';

export interface MapProcess {
  slug: string;
  name: string;
  stage: string;
  order: number;
}
export interface MapStage {
  slug: string;
  name: string;
  order: number;
}
export interface MapBox {
  slug: string;
  x: number;
  y: number;
  w: number;
  h: number;
  lines: string[]; // 工程の名前（折り返し）
  count: number; // 掲載している企業の数
  countX: number;
  countY: number;
  textY: number; // 工程の名前の最初の行の位置（1行のときは、箱の中央）
  aria: string;
}
export interface MapColumn {
  slug: string;
  name: string;
  x: number;
  y: number; // 見出しの文字の位置（ベースライン）
  w: number;
  ruleY: number;
  boxes: MapBox[];
}
export interface MapArrow {
  d: string; // 矢印の線と先（path）
}
export interface MapModel {
  layout: MapLayout;
  width: number;
  height: number;
  columns: MapColumn[];
  arrows: MapArrow[];
}

const PAD = 4; // 枠線が切れないための余白
const HEAD = 36; // 段階の見出しの高さ
const BOX_H = 52; // 工程の箱の高さの最小（2行まで。3行以上は行数に合わせて高くする）
const GAP = 8; // 箱の間の隙間
const WIDE_COL = 216;
const WIDE_GAP = 28;
const COMPACT_W = 280;
const COMPACT_GAP = 28;
const LINE = 20; // 文字の行の高さ

/** 文字の幅（全角を1、半角の英数字と記号を0.5） */
const unit = (ch: string) => (ch.charCodeAt(0) < 0x100 ? 0.5 : 1);
const widthOf = (text: string) => [...text].reduce((sum, ch) => sum + unit(ch), 0);

/** 工程の名前を、括弧の前で区切り、1行の幅（全角の字数）を超えないよう折り返す。文字は省かない */
export function wrapName(name: string, max: number): string[] {
  const chunk = (text: string): string[] => {
    const out: string[] = [];
    let line = '';
    for (const ch of text) {
      if (line && widthOf(line) + unit(ch) > max) {
        out.push(line);
        line = '';
      }
      line += ch;
    }
    if (line) out.push(line);
    // 最後の行が1文字だけにならないよう、前の行の最後の文字を送る
    if (out.length > 1 && [...out[out.length - 1]].length === 1) {
      const prev = [...out[out.length - 2]];
      out[out.length - 1] = prev.pop() + out[out.length - 1];
      out[out.length - 2] = prev.join('');
    }
    return out;
  };
  if (widthOf(name) <= max) return [name];
  const open = name.indexOf('（');
  if (open > 0) return [...chunk(name.slice(0, open)), ...chunk(name.slice(open))];
  return chunk(name);
}

/** 段階を、含む工程の最小の順の順に並べる（材料→前工程→後工程の流れ）。工程のない段階は出さない */
export function orderedStages(stages: MapStage[], processes: MapProcess[]): { stage: MapStage; items: MapProcess[] }[] {
  return stages
    .map((stage) => ({ stage, items: processes.filter((p) => p.stage === stage.slug).sort((a, b) => a.order - b.order) }))
    .filter((s) => s.items.length > 0)
    .sort((a, b) => a.items[0].order - b.items[0].order);
}

export function buildSupplyMap(
  stages: MapStage[],
  processes: MapProcess[],
  counts: Record<string, number>,
  layout: MapLayout,
): MapModel {
  const groups = orderedStages(stages, processes);
  const wide = layout === 'wide';
  const colW = wide ? WIDE_COL : COMPACT_W;
  const max = wide ? 10 : 14; // 1行の全角の字数（右に「n社」を置く幅を除く）
  const columns: MapColumn[] = [];
  const arrows: MapArrow[] = [];
  let cursorX = PAD;
  let cursorY = PAD;
  let height = 0;
  groups.forEach((g, gi) => {
    const x = wide ? cursorX : PAD;
    const top = wide ? PAD : cursorY;
    let boxY = top + HEAD;
    const boxes: MapBox[] = g.items.map((p) => {
      const y = boxY;
      const lines = wrapName(p.name, max);
      const h = Math.max(BOX_H, 12 + lines.length * LINE + 8);
      boxY += h + GAP;
      const count = counts[p.slug] ?? 0;
      return {
        slug: p.slug, x, y, w: colW, h, lines, count,
        countX: x + colW - 12, countY: y + (lines.length === 1 ? 31 : 22), textY: y + (lines.length === 1 ? 31 : 22),
        aria: `${p.name}（${count}社）。この工程の企業の表へ移動`,
      };
    });
    columns.push({ slug: g.stage.slug, name: g.stage.name, x, y: top + 22, w: colW, ruleY: top + HEAD - 6, boxes });
    const bottom = boxY - GAP;
    height = Math.max(height, bottom + PAD);
    if (wide) {
      if (gi < groups.length - 1) {
        const x1 = x + colW + 10;
        const x2 = x + colW + WIDE_GAP - 10;
        const y = top + 18;
        arrows.push({ d: `M${x1} ${y}H${x2}M${x2 - 8} ${y - 6}L${x2} ${y}L${x2 - 8} ${y + 6}` });
      }
      cursorX += colW + WIDE_GAP;
    } else {
      if (gi < groups.length - 1) {
        const cx = PAD + colW / 2;
        const y1 = bottom + 4;
        const y2 = bottom + COMPACT_GAP - 4;
        arrows.push({ d: `M${cx} ${y1}V${y2}M${cx - 6} ${y2 - 8}L${cx} ${y2}L${cx + 6} ${y2 - 8}` });
      }
      cursorY = bottom + COMPACT_GAP;
    }
  });
  const width = wide ? cursorX - WIDE_GAP + PAD : COMPACT_W + PAD * 2;
  return { layout, width, height, columns, arrows };
}

export const lineHeight = LINE;
