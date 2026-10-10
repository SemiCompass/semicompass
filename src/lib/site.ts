// config/site.yaml を読む（サイトの設定。問い合わせフォームのURLなど）。
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { parse } from 'yaml';

export interface Site {
  contact_form_url: string; // GoogleフォームのURL。空なら「準備中」と表示する
}

export function parseSite(text: string): Site {
  const data = parse(text) as { contact_form_url?: unknown } | null;
  const url = data?.contact_form_url ?? '';
  if (typeof url !== 'string' || (url !== '' && !/^https:\/\/(docs\.google\.com\/forms|forms\.gle)\//.test(url))) {
    throw new Error('config/site.yaml の contact_form_url は、空か、GoogleフォームのURL（https://docs.google.com/forms/…、https://forms.gle/…）にする');
  }
  return { contact_form_url: url };
}

export function loadSite(): Site {
  return parseSite(readFileSync(resolve(process.cwd(), 'config/site.yaml'), 'utf-8'));
}
