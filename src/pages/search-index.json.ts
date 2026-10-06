// 検索用データ（ビルドのときに作る静的なJSON）。企業・工程・用語の名前、URL、検索の語。本文は含まない。
import { BUILD_ENV } from 'astro:env/server';
import { buildIndex } from '../lib/search';

export function GET() {
  return new Response(JSON.stringify(buildIndex(BUILD_ENV === 'preview')), { headers: { 'Content-Type': 'application/json; charset=utf-8' } });
}
