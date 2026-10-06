// グラフの形の計算（仕様書 10章）：ビルドのときに、SVGの図形の位置と大きさを計算する。数値はファイルから渡され、ここには書かない。
// 文字は、仕様書の最小の大きさ（--text-small = 14px）で読めるよう、SVGの座標を画面の画素と同じ大きさにする。
// 幅の違う2つの図（compact：スマートフォン、wide：タブレット以上）を作り、CSSで切り替える。
import { formatNumber } from './format';

export type Layout = 'compact' | 'wide';
export type Kind = 'bar' | 'stacked' | 'hbar' | 'line';

export interface Series {
  name: string;
  color: string; // CSSの変数の名前（--chart-single など。config/chart-colors.yaml）
  pattern?: boolean; // 斜線の模様
  note?: string; // 凡例に添える言葉（例：半導体関連）
  values: (number | null)[];
}
export interface Category {
  label: string; // 完全な名前（例：2026年3月期）
  short: string; // 軸の短い名前（例：26/3）
  lines: string[]; // 幅が広いときの軸の名前（2行）
}
export interface ChartSpec {
  kind: Kind;
  categories: Category[];
  series: Series[];
  unit: string; // 軸の単位（例：億円）
  decimals: number;
  labelLatest: boolean; // 最新の期の数値のラベルを付ける
  withChange?: boolean; // 前期比（＋／−と矢印）を吹き出しに付ける
  tableSeries?: Series[]; // 「表で見る」の表に出す系列（グラフの系列を、まとめているときの内訳）
  latestLabel?: string[]; // 積み上げ：最新の期の棒に付けるラベル（行ごと。合計は出さない）
  note?: string; // グラフの注記（です・ます調）
}

export interface Tip {
  x: number;
  y: number;
  w: number;
  h: number;
  lines: string[];
}
export interface Datum {
  id: string;
  shape: 'rect' | 'circle';
  x: number;
  y: number;
  w: number;
  h: number;
  r: number;
  color: string;
  pattern: boolean;
  aria: string;
  tip: Tip;
}
export interface Model {
  kind: Kind;
  layout: Layout;
  width: number;
  height: number;
  plot: { l: number; t: number; r: number; b: number };
  yTicks: { y: number; text: string }[];
  xTicks: { x: number; y: number; text: string[] }[];
  hTicks: { x: number; text: string }[]; // 横の棒の値の目盛り
  baseline: { x1: number; y1: number; x2: number; y2: number };
  data: Datum[];
  labels: { x: number; y: number; lines: string[]; anchor: 'start' | 'middle' | 'end'; value: boolean }[];
  polylines: { color: string; points: string; id: string }[];
  barWidth: number;
}

const SIZE = { compact: { w: 288, h: 300 }, wide: { w: 640, h: 340 } } as const;
const TOP = 28;
const TOP_STACKED_LABEL = 52; // 積み上げのラベル（2行）を置く上の余白
const CHAR_W = 9.2; // 半角の文字の幅の概算（14px。等幅の数字は広め）
const CJK_W = 14;
export function textWidth(text: string): number {
  let w = 0;
  for (const ch of text) w += ch.charCodeAt(0) < 0x2e80 ? CHAR_W : CJK_W;
  return w;
}

export function niceTicks(min: number, max: number, count = 4): number[] {
  const lo = Math.min(0, min);
  const hi = Math.max(0, max);
  const span = hi - lo || 1;
  const rough = span / count;
  const pow = 10 ** Math.floor(Math.log10(rough));
  const norm = rough / pow;
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10) * pow;
  const start = Math.floor(lo / step) * step;
  const ticks: number[] = [];
  for (let v = start; v <= hi + step * 0.999; v += step) ticks.push(Math.round(v / step) * step);
  const end = ticks.findIndex((t) => t >= hi);
  return end === -1 ? ticks : ticks.slice(0, end + 1);
}

function tip(anchorX: number, anchorY: number, lines: string[], width: number, height: number): Tip {
  const w = Math.max(...lines.map(textWidth)) + 24;
  const h = lines.length * 20 + 8;
  const x = Math.min(Math.max(anchorX - w / 2, 2), width - w - 2);
  const above = anchorY - h - 6;
  const y = above >= 2 ? above : Math.min(anchorY + 6, height - h - 2);
  return { x, y, w, h, lines };
}

export function buildChart(spec: ChartSpec, layout: Layout, uid: string): Model {
  const { w: width, h: height } = SIZE[layout];
  const n = spec.categories.length;
  const horizontal = spec.kind === 'hbar';
  const stacked = spec.kind === 'stacked';
  const totals = spec.categories.map((_, i) => {
    const vals = spec.series.map((s) => s.values[i] ?? 0);
    return stacked ? vals.reduce((a, b) => a + b, 0) : Math.max(...vals);
  });
  const all = spec.series.flatMap((s) => s.values.filter((v): v is number => v !== null));
  const max = Math.max(...(stacked ? totals : all), 0);
  const min = Math.min(...all, 0);
  const ticks = niceTicks(min, max);
  const domMin = ticks[0];
  const domMax = ticks[ticks.length - 1];
  const tickText = (v: number) => formatNumber(v, 0);
  const labelW = Math.max(...ticks.map((t) => textWidth(tickText(t)))) + 10;

  const catW = horizontal ? Math.max(...spec.categories.map((c) => textWidth(c.short))) + 10 : 0;
  const plot = horizontal
    ? { l: Math.min(catW, layout === 'compact' ? 120 : 160), t: TOP, r: width - 12, b: height - 28 }
    : { l: labelW + 6, t: stacked && spec.latestLabel ? TOP_STACKED_LABEL : TOP, r: width - 12, b: height - (layout === 'compact' ? 30 : 48) };

  const model: Model = {
    kind: spec.kind, layout, width, height, plot, yTicks: [], xTicks: [], hTicks: [], baseline: { x1: 0, y1: 0, x2: 0, y2: 0 },
    data: [], labels: [], polylines: [], barWidth: 0,
  };
  const span = domMax - domMin || 1;
  const yOf = (v: number) => plot.b - ((v - domMin) / span) * (plot.b - plot.t);
  const xOfH = (v: number) => plot.l + ((v - domMin) / span) * (plot.r - plot.l);
  const changeText = (i: number, value: number): string | null => {
    if (!spec.withChange || i === 0) return null;
    const prev = spec.series[0].values[i - 1];
    if (prev === null || prev === undefined || prev === 0) return null;
    const ratio = Math.round(((value - prev) / Math.abs(prev)) * 1000) / 10;
    const arrow = ratio > 0 ? '↑' : ratio < 0 ? '↓' : '→';
    const sign = ratio > 0 ? '＋' : ratio < 0 ? '−' : '';
    return `前期比 ${sign}${formatNumber(Math.abs(ratio), 1)}%${arrow}`;
  };

  if (horizontal) {
    model.hTicks = ticks.map((t) => ({ x: xOfH(t), text: tickText(t) }));
    model.baseline = { x1: xOfH(0), y1: plot.t, x2: xOfH(0), y2: plot.b };
    const slot = (plot.b - plot.t) / n;
    const bar = Math.min(slot / 1.5 / 1.0, 28);
    model.barWidth = bar;
    spec.categories.forEach((c, i) => {
      const v = spec.series[0].values[i];
      if (v === null) return;
      const y = plot.t + slot * i + (slot - bar) / 2;
      const x0 = xOfH(Math.min(0, v));
      const w = Math.abs(xOfH(v) - xOfH(0));
      const text = `${formatNumber(v, spec.decimals)}${spec.unit}`;
      model.data.push({ id: `${uid}-${i}`, shape: 'rect', x: x0, y, w, h: bar, r: 0, color: spec.series[0].color, pattern: false,
        aria: `${c.label} ${text}`, tip: tip(x0 + w, y, [c.label, text], width, height) });
      model.labels.push({ x: plot.l - 6, y: y + bar / 2 + 5, lines: [c.short], anchor: 'end', value: false });
    });
    return model;
  }

  model.yTicks = ticks.map((t) => ({ y: yOf(t), text: tickText(t) }));
  model.baseline = { x1: plot.l, y1: yOf(0), x2: plot.r, y2: yOf(0) };
  const slot = (plot.r - plot.l) / n;
  const every = layout === 'compact' && slot < 40 ? 2 : 1;
  spec.categories.forEach((c, i) => {
    const cx = plot.l + slot * (i + 0.5);
    if (i % every === (n - 1) % every) {
      model.xTicks.push({ x: cx, y: plot.b + 4, text: layout === 'compact' ? [c.short] : c.lines });
    }
  });

  if (spec.kind === 'line') {
    spec.series.forEach((s, si) => {
      const pts: string[] = [];
      s.values.forEach((v, i) => {
        if (v === null) return;
        const cx = plot.l + slot * (i + 0.5);
        const cy = yOf(v);
        pts.push(`${cx},${cy}`);
        const text = `${formatNumber(v, spec.decimals)}${spec.unit}`;
        const change = changeText(i, v);
        model.data.push({ id: `${uid}-${si}-${i}`, shape: 'circle', x: cx, y: cy, w: 0, h: 0, r: 5, color: s.color, pattern: false,
          aria: `${spec.categories[i].label} ${s.name} ${text}`,
          tip: tip(cx, cy - 5, [spec.categories[i].label, ...(spec.series.length > 1 ? [s.name] : []), text, ...(change ? [change] : [])], width, height) });
        if (spec.labelLatest && i === n - 1) model.labels.push({ x: Math.min(cx, plot.r - textWidth(text) / 2), y: cy - 12, lines: [text], anchor: 'middle', value: true });
      });
      model.polylines.push({ color: s.color, points: pts.join(' '), id: `${uid}-line-${si}` });
    });
    return model;
  }

  // 縦の棒（1系列）と、積み上げの縦の棒
  const barW = Math.min(slot / 1.5, 56);
  model.barWidth = barW;
  spec.categories.forEach((c, i) => {
    const x = plot.l + slot * i + (slot - barW) / 2;
    let acc = 0;
    spec.series.forEach((s, si) => {
      const v = s.values[i];
      if (v === null || v === undefined) return;
      const from = stacked ? acc : 0;
      const to = stacked ? acc + v : v;
      acc = to;
      const yTop = yOf(Math.max(from, to));
      const yBottom = yOf(Math.min(from, to));
      const h = Math.max(yBottom - yTop, 0);
      const text = `${formatNumber(v, spec.decimals)}${spec.unit}`;
      const change = stacked ? null : changeText(i, v);
      const lines = stacked
        ? [c.label, s.name, `${text}（${formatNumber((v / (totals[i] || 1)) * 100, 1)}%）`]
        : [c.label, text, ...(change ? [change] : [])];
      model.data.push({ id: `${uid}-${si}-${i}`, shape: 'rect', x, y: yTop, w: barW, h, r: 0, color: s.color, pattern: !!s.pattern,
        aria: `${c.label} ${stacked ? `${s.name} ` : ''}${text}`, tip: tip(x + barW / 2, yTop, lines, width, height) });
    });
    if (i === n - 1) {
      if (stacked) {
        // 積み上げ：セグメントの合計は出さない（連結売上高と合わないため）。最新の期の半導体関連の値と比率だけをラベルにする
        if (spec.latestLabel) {
          const top = yOf(Math.max(totals[i], 0));
          model.labels.push({ x: plot.r, y: top - 6 - (spec.latestLabel.length - 1) * 20, lines: spec.latestLabel, anchor: 'end', value: true });
        }
      } else if (spec.labelLatest) {
        const v = spec.series[0].values[i] ?? 0;
        const text = formatNumber(v, spec.decimals);
        model.labels.push({ x: Math.min(x + barW / 2, plot.r - textWidth(text) / 2), y: yOf(Math.max(v, 0)) - 6, lines: [text], anchor: 'middle', value: true });
      }
    }
  });
  return model;
}
