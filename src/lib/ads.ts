// 広告の設定（config/ads.yaml）を読み、広告の部品（AdSlot）が出すものを決める（要件定義書 4.13 の「広告の表示の切り替え」、
// アーキテクチャ設計書 6.2）。切り替えの場所は config/ads.yaml の enabled の1か所だけ。環境変数は足さない。
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { parse } from 'yaml';

export interface AdPage {
  limit: number;
  positions: Record<string, { slot: string }>;
}
export interface Ads {
  enabled: boolean;
  client: string;
  pages: Record<string, AdPage>;
}
/** off：何も出さない（本番で enabled: false）。sample：見本の枠（プレビュー）。live：広告のタグと枠（本番で enabled: true） */
export type AdMode = 'off' | 'sample' | 'live';

const fail = (message: string): never => {
  throw new Error(`config/ads.yaml：${message}`);
};

export function parseAds(text: string): Ads {
  const data = (parse(text) ?? {}) as Record<string, unknown>;
  if (typeof data.enabled !== 'boolean') fail('enabled は true か false にする');
  const client = data.client ?? '';
  if (typeof client !== 'string' || (client !== '' && !/^ca-pub-\d{16}$/.test(client))) {
    fail('client は、空か、ca-pub- と16桁の数字にする');
  }
  const rawPages = data.pages;
  if (typeof rawPages !== 'object' || rawPages === null) fail('pages がない');
  const pages: Record<string, AdPage> = {};
  for (const [name, value] of Object.entries(rawPages as Record<string, unknown>)) {
    const page = value as { limit?: unknown; positions?: unknown };
    if (!Number.isInteger(page?.limit) || (page.limit as number) < 1) fail(`pages.${name}.limit は1以上の整数にする`);
    if (typeof page.positions !== 'object' || page.positions === null) fail(`pages.${name}.positions がない`);
    const positions: Record<string, { slot: string }> = {};
    for (const [position, spec] of Object.entries(page.positions as Record<string, unknown>)) {
      const slot = (spec as { slot?: unknown } | null)?.slot ?? '';
      if (typeof slot !== 'string' || (slot !== '' && !/^\d{6,12}$/.test(slot))) fail(`pages.${name}.positions.${position}.slot は、空か、数字にする`);
      positions[position] = { slot };
    }
    pages[name] = { limit: page.limit as number, positions };
  }
  const ads: Ads = { enabled: data.enabled as boolean, client: client as string, pages };
  if (ads.enabled && ads.client === '') fail('enabled が true のときは、client（サイト運営者ID）が必須');
  return ads;
}

let cached: Ads | undefined;
export function loadAds(): Ads {
  cached ??= parseAds(readFileSync(resolve(process.cwd(), 'config/ads.yaml'), 'utf-8'));
  return cached;
}

/** 環境と設定から、広告の部品が出すものを決める。プレビュー（と開発）は、常に見本の枠 */
export function adMode(buildEnv: string, ads: Ads): AdMode {
  if (buildEnv !== 'production') return 'sample';
  return ads.enabled ? 'live' : 'off';
}

/** 置いてよい位置かを確かめ、広告ユニットのIDを返す。置けない位置ならビルドを失敗させる */
export function slotFor(ads: Ads, page: string, position: string, mode: AdMode): string {
  const spec = ads.pages[page]?.positions[position];
  if (!spec) fail(`ページの種類「${page}」の位置「${position}」には、広告の枠を置けない（運用ルール書 5.1）`);
  if (mode === 'live' && spec!.slot === '') fail(`enabled が true のときは、pages.${page}.positions.${position}.slot が必須`);
  return spec!.slot;
}
