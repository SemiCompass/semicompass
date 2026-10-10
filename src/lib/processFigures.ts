// 工程ページの解説図（仕様書 8.15）：仕組みを示す模式図。工程の slug ごとに、段階（パネル）の並びを持つ。
// 数値、企業名、寸法、年は入れない。図の形は src/components/ProcessFigure.astro が、パネルの kind で描く。
export type PanelKind = 'coat' | 'expose' | 'develop' | 'next';
export interface FigurePanel {
  kind: PanelKind;
  label: string; // 段階の名前
  text: string; // 段階の説明（1〜2文）
}
export interface ProcessFigureSpec {
  title: string; // 図の名前
  summary: string; // 図の内容を、図がなくても分かるように書いた文（figcaption）
  panels: FigurePanel[];
}

export const processFigures: Record<string, ProcessFigureSpec> = {
  lithography: {
    title: 'リソグラフィの流れ（断面の模式図）',
    summary: 'ウェーハにレジストを塗り、マスクを通した光で一部だけを感光させ、現像で感光した部分を除くと、レジストのパターンが残る。ポジ型の場合の流れである。',
    panels: [
      { kind: 'coat', label: '塗布', text: 'ウェーハの上に、感光する樹脂（フォトレジスト）を薄く広げる。' },
      { kind: 'expose', label: '露光', text: 'マスクを通して光を当て、レジストの一部だけを感光させる。' },
      { kind: 'develop', label: '現像', text: '現像液で、感光した部分を溶かして除く（ポジ型の場合）。パターンの形にレジストが残る。' },
      { kind: 'next', label: '次の工程', text: '残ったレジストを型にして、エッチングやイオン注入を行う。' },
    ],
  },
};
