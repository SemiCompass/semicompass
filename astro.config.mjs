import { defineConfig, envField } from 'astro/config';

// 静的出力（要件定義書2.3、アーキテクチャ設計書ADR-02）。
// 公開URL（site）は、正規のURL（canonical）の元になる。独自ドメインは wrangler.jsonc の routes と合わせる。
export default defineConfig({
  site: 'https://semicompass.com',
  output: 'static',
  // ページは `/foo/index.html` として出力し、URLは末尾スラッシュに統一する（要件定義書3.1）。
  // wrangler.jsonc の assets.html_handling（auto-trailing-slash）と合わせる。
  trailingSlash: 'always',
  build: {
    format: 'directory',
    // CSSをファイルとして出力し、CSP（public/_headers）で style-src の 'unsafe-inline' を使わないようにする
    inlineStylesheets: 'never',
  },
  env: {
    schema: {
      // 環境（アーキテクチャ設計書6.2）。値が違えばビルドを失敗させる。
      // 指定がないときは、検索に登録させない側（preview）に倒す。本番のビルドは production を明示する
      BUILD_ENV: envField.enum({
        context: 'server',
        access: 'public',
        values: ['production', 'preview'],
        default: 'preview',
      }),
    },
  },
});
