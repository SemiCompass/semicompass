// 検索用データ（FR-701）：ビルドのときに、企業・工程・用語・ニュースから作る。画面の検索（src/scripts/search.ts）が読む（/search-index.json）。
// 全角と半角、ひらがなとカタカナ、大文字と小文字は、同じものとして扱う（normalizeForSearch）。
import { loadCompanies, loadSupply } from './companies';
import { loadTerms } from './content';
import { dateLabel } from './format';
import { loadNews } from './news';
import { normalizeForSearch, type SearchEntry } from './normalize';

const keys = (...values: (string | undefined)[]): string[] =>
  [...new Set(values.filter((v): v is string => !!v).map(normalizeForSearch).filter(Boolean))];

export function buildIndex(preview: boolean): SearchEntry[] {
  const supply = loadSupply();
  const stageName = (slug: string) => supply.categories.find((c) => c.slug === slug)?.name;
  const entries: SearchEntry[] = [];
  for (const c of loadCompanies()) {
    entries.push({
      type: 'company', name: c.short_names[0] ?? c.name, url: `/companies/${c.slug}/`, code: c.securities_code, detail: c.name,
      keys: keys(c.name, ...c.short_names, (c as { name_en?: string }).name_en, (c as { name_kana?: string }).name_kana, c.securities_code),
    });
  }
  for (const p of supply.processes as { slug: string; name: string; stage?: string; short_description?: string }[]) {
    entries.push({ type: 'process', name: p.name, url: `/processes/${p.slug}/`, detail: p.short_description,
      keys: keys(p.name, p.slug, p.stage ? stageName(p.stage) : undefined) });
  }
  for (const t of loadTerms(preview)) {
    entries.push({ type: 'term', name: t.front.term, url: `/glossary/${t.slug}/`, detail: t.front.short_definition,
      keys: keys(t.front.term, t.front.reading, ...(t.front.aliases ?? []), t.front.name_en, t.front.abbreviation_of) });
  }
  const companies = loadCompanies();
  for (const n of loadNews(preview)) {
    const names = n.front.tags.companies.flatMap((slug) => companies.find((c) => c.slug === slug)?.short_names ?? []);
    entries.push({ type: 'news', name: n.front.title, url: n.url, detail: dateLabel(n.front.published_at),
      keys: keys(n.front.title, n.front.description, ...names) });
  }
  return entries;
}
