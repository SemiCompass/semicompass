import { defineConfig } from 'astro/config';

// 静的出力（要件定義書2.3、アーキテクチャ設計書ADR-02）。
// 公開URL（site）は、ドメインが決まってから設定する。
export default defineConfig({
  output: 'static',
});
