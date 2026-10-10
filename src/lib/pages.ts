// 固定ページ（content/pages/*.md。要件定義書 3.1、FP-01〜FP-10）を読む。
// 本文は、`## 大見出し`、`### 小見出し {#識別名}`、段落、箇条書き（- または * ）、番号付き（1. ）、表（| ）だけを使う。
// draft: true は、プレビューのビルドだけ（企業ページと同じ決まり）。運営者が記入する欄は【運営者が記入】と書く（下書きのうちだけ）
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { parse } from 'yaml';
import { visible } from './content';

export interface PageFront {
  title: string;
  description: string;
  path: string; // 例：/about/（先頭と末尾が /）
  updated_at?: string;
  draft?: boolean;
  parent?: { label: string; href: string };
}
export type Block =
  | { kind: 'p'; text: string }
  | { kind: 'ul' | 'ol'; items: string[] }
  | { kind: 'h3'; text: string; id: string }
  | { kind: 'table'; head: string[]; rows: string[][] };
export interface Section {
  heading: string;
  id: string;
  blocks: Block[];
}
export interface StaticPage {
  front: PageFront;
  sections: Section[];
}

const cells = (line: string) => line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());

export function parseBlocks(text: string): Block[] {
  const blocks: Block[] = [];
  for (const raw of text.split(/\n{2,}/)) {
    const lines = raw.trim().split('\n').map((l) => l.trimEnd());
    if (lines.length === 0 || lines[0] === '') continue;
    const h3 = /^### (.+?)(?:\s+\{#([a-z0-9-]+)\})?$/.exec(lines[0]);
    if (h3 && lines.length === 1) {
      blocks.push({ kind: 'h3', text: h3[1], id: h3[2] ?? '' });
    } else if (lines.every((l) => /^[-*] /.test(l))) {
      blocks.push({ kind: 'ul', items: lines.map((l) => l.slice(2).trim()) });
    } else if (lines.every((l) => /^[0-9]+\. /.test(l))) {
      blocks.push({ kind: 'ol', items: lines.map((l) => l.replace(/^[0-9]+\. /, '').trim()) });
    } else if (lines.every((l) => l.startsWith('|')) && lines.length >= 3 && /^\|[\s:|-]+\|$/.test(lines[1])) {
      blocks.push({ kind: 'table', head: cells(lines[0]), rows: lines.slice(2).map(cells) });
    } else if (h3) {
      blocks.push({ kind: 'h3', text: h3[1], id: h3[2] ?? '' }, ...parseBlocks(lines.slice(1).join('\n')));
    } else {
      blocks.push({ kind: 'p', text: lines.join('') });
    }
  }
  return blocks;
}

export function parsePage(text: string): StaticPage {
  const match = /^---\n([\s\S]*?)\n---\n?([\s\S]*)$/.exec(text.replace(/\r\n/g, '\n'));
  if (!match) throw new Error('front matter がない');
  const front = parse(match[1]) as PageFront;
  if (!front?.path || !/^\/[a-z0-9/-]*\/$/.test(front.path)) throw new Error('path は、/ で始まり / で終わる');
  const parts = match[2].split(/^## /m);
  const sections: Section[] = [];
  if (parts[0].trim()) sections.push({ heading: '', id: '', blocks: parseBlocks(parts[0]) });
  parts.slice(1).forEach((part, i) => {
    const [heading, ...rest] = part.split('\n');
    sections.push({ heading: heading.trim(), id: `s${i}`, blocks: parseBlocks(rest.join('\n')) });
  });
  return { front, sections };
}

export function loadPages(preview: boolean): StaticPage[] {
  const dir = resolve(process.cwd(), 'content/pages');
  if (!existsSync(dir)) return [];
  return readdirSync(dir)
    .filter((f) => f.endsWith('.md'))
    .sort()
    .map((f) => parsePage(readFileSync(resolve(dir, f), 'utf-8')))
    .filter((p) => visible(p.front, preview));
}
