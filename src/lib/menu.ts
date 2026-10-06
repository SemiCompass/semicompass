// config/menu.yaml を読む（主要メニューとフッターの項目。要件定義書 3.2）。
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { parse } from 'yaml';

export interface MenuItem {
  label: string;
  path: string;
}
export interface FooterGroup {
  title: string;
  links: MenuItem[];
}
export interface Menu {
  main: MenuItem[];
  footer: FooterGroup[];
}

function isItem(value: unknown): value is MenuItem {
  return (
    typeof value === 'object' && value !== null &&
    typeof (value as MenuItem).label === 'string' &&
    typeof (value as MenuItem).path === 'string' &&
    (value as MenuItem).path.startsWith('/') && (value as MenuItem).path.endsWith('/')
  );
}

export function parseMenu(text: string): Menu {
  const data = parse(text) as { main?: unknown; footer?: unknown } | null;
  const main = data?.main;
  const footer = data?.footer;
  if (!Array.isArray(main) || !main.every(isItem)) {
    throw new Error('config/menu.yaml の main は、label と path（/ で始まり、/ で終わる）を持つ項目の並びにする');
  }
  if (
    !Array.isArray(footer) ||
    !footer.every((g) => typeof g?.title === 'string' && Array.isArray(g?.links) && g.links.every(isItem))
  ) {
    throw new Error('config/menu.yaml の footer は、title と links を持つ組の並びにする');
  }
  return { main, footer };
}

// ビルドは、リポジトリの直下で動かす（npm run build）。ビルド後のファイルの位置に依らないよう、作業の場所から読む
export function loadMenu(): Menu {
  return parseMenu(readFileSync(resolve(process.cwd(), 'config/menu.yaml'), 'utf-8'));
}

/** 現在のページが属するメニューの項目か（その項目のパスで始まるURL） */
export function isCurrent(itemPath: string, pathname: string): boolean {
  return pathname === itemPath || pathname.startsWith(itemPath);
}
