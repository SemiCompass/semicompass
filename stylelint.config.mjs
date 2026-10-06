// CSSの検査（画面とデザインの仕様書 13章の1、運用ルール書 10.3.3、要件定義書 4.11 DS-09、CLAUDE.md 9章）。
// 実行：npm run lint:css
// 禁止すること：デザインの変数を使わない色・大きさ・余白の直接の指定、グラデーション、半透明のぼかし、影、紫・青紫の色、
//   幅の数値を書いた @media（@media (--tablet)、@media (--pc) を使う）、斜体、中央揃え
// tokens.css と breakpoints.css は、値を持つ場所のため、対象から外す。
const LENGTH_UNITS = 'px|rem|em|pt|pc|cm|mm|in|ex|ch|vw|vh|vmin|vmax|svw|svh|dvh|lvh';
const LITERAL_SIZE = new RegExp(`(^|[^\\w.-])-?\\d*\\.?\\d+(${LENGTH_UNITS})\\b`, 'i');
const LITERAL_TIME = /(^|[^\w.-])\d*\.?\d+m?s\b/i;
const VAR_ONLY = [/^var\(--[a-z0-9-]+\)$/, 'inherit', 'normal'];

const designRules = {
  // 色：16進、色の関数、色の名前（紫・青紫を含む）を、直接書かない。transparent と currentcolor は使える
  'color-no-hex': true,
  'color-named': 'never',
  'function-disallowed-list': [
    'rgb', 'rgba', 'hsl', 'hsla', 'hwb', 'lab', 'lch', 'oklab', 'oklch', 'color', 'color-mix', 'light-dark',
    'linear-gradient', 'radial-gradient', 'conic-gradient',
    'repeating-linear-gradient', 'repeating-radial-gradient', 'repeating-conic-gradient',
  ],
  // 影、半透明のぼかし
  'property-disallowed-list': ['box-shadow', 'text-shadow', 'backdrop-filter', '-webkit-backdrop-filter'],
  'declaration-property-value-disallowed-list': {
    // 大きさ、余白、時間は、変数だけ（0 と % は使える）
    '/^(?!--)/': [LITERAL_SIZE, LITERAL_TIME],
    // グラデーション（背景の指定の名前に関わらず）、ぼかし
    '/^(background|border-image|mask)/': [/gradient/i],
    filter: [/blur|drop-shadow/i],
    'font-style': [/italic|oblique/i],
    'text-align': [/^center$/i],
  },
  // 文字の大きさ、太さ、行間、字間は、変数だけ
  'declaration-property-value-allowed-list': {
    'font-size': VAR_ONLY,
    'font-weight': VAR_ONLY,
    'line-height': VAR_ONLY,
    'letter-spacing': VAR_ONLY,
  },
  // 画面の幅の区切りは、幅の数値を書かずに、@media (--tablet)、@media (--pc) と書く
  'media-feature-name-disallowed-list': [/width/, /height/, /^device-/],
  // 一般の検査
  'block-no-empty': true,
  'color-no-invalid-hex': true,
  'declaration-block-no-duplicate-properties': true,
  'property-no-unknown': [true, { ignoreProperties: ['word-break', 'text-wrap'] }],
  'unit-no-unknown': true,
};

export default {
  rules: designRules,
  overrides: [
    { files: ['**/*.astro', '**/*.html'], customSyntax: 'postcss-html' },
    {
      // 値を持つ場所。ここでだけ、値を直接書く
      files: ['src/styles/tokens.css', 'src/styles/breakpoints.css'],
      rules: Object.fromEntries(Object.keys(designRules).map((name) => [name, null])),
    },
  ],
};
