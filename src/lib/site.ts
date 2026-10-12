// config/site.yaml を読む（サイトの設定。問い合わせフォームのURLなど）。
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { parse } from 'yaml';

export interface Site {
  contact_form_url: string; // GoogleフォームのURL。空なら「準備中」と表示する
  ga4_measurement_id: string; // Google Analytics 4 の測定ID（G-…）。空なら計測しない
}

export function parseSite(text: string): Site {
  const data = parse(text) as { contact_form_url?: unknown; ga4_measurement_id?: unknown } | null;
  const url = data?.contact_form_url ?? '';
  if (typeof url !== 'string' || (url !== '' && !/^https:\/\/(docs\.google\.com\/forms|forms\.gle)\//.test(url))) {
    throw new Error('config/site.yaml の contact_form_url は、空か、GoogleフォームのURL（https://docs.google.com/forms/…、https://forms.gle/…）にする');
  }
  const ga = data?.ga4_measurement_id ?? '';
  if (typeof ga !== 'string' || (ga !== '' && !/^G-[A-Z0-9]{4,20}$/.test(ga))) {
    throw new Error('config/site.yaml の ga4_measurement_id は、空か、G- で始まる測定IDにする');
  }
  return { contact_form_url: url, ga4_measurement_id: ga };
}

export function loadSite(): Site {
  return parseSite(readFileSync(resolve(process.cwd(), 'config/site.yaml'), 'utf-8'));
}
