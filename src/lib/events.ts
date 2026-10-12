// 技術系のイベント（data/events.yaml。データ定義書 4.6、要求定義書 FR-206）。
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { parse } from 'yaml';

export interface TechEvent {
  id: string;
  name: string;
  kind: 'exhibition' | 'conference' | 'seminar';
  start_date: string;
  end_date: string;
  venue: string;
  city: string;
  organizer: string;
  url: string;
  source: string;
  checked_on: string;
}

export function loadEvents(): TechEvent[] {
  const path = resolve(process.cwd(), 'data/events.yaml');
  if (!existsSync(path)) return [];
  const data = parse(readFileSync(path, 'utf-8')) as { events?: TechEvent[] };
  return data.events ?? [];
}

/** 終わっていないイベントを、開催日の近い順に、最大 limit 件（要件定義書 3.3 の5）。終わったかどうかはビルドの日で判定する */
export function upcomingEvents(today: string, limit = 5): TechEvent[] {
  return loadEvents()
    .filter((e) => String(e.end_date) >= today)
    .sort((a, b) => String(a.start_date).localeCompare(String(b.start_date)))
    .slice(0, limit);
}

/** 開催日の表示：同じ日なら1日、続くなら「2026年12月9日〜11日」の形 */
export function eventDates(e: Pick<TechEvent, 'start_date' | 'end_date'>): string {
  const [sy, sm, sd] = String(e.start_date).split('-').map(Number);
  const [ey, em, ed] = String(e.end_date).split('-').map(Number);
  const start = `${sy}年${sm}月${sd}日`;
  if (String(e.start_date) === String(e.end_date)) return start;
  if (sy === ey && sm === em) return `${start}〜${ed}日`;
  if (sy === ey) return `${start}〜${em}月${ed}日`;
  return `${start}〜${ey}年${em}月${ed}日`;
}
