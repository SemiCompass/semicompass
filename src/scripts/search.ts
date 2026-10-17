// 検索（FR-701、仕様書 8.6、9.7）：検索用データ（/search-index.json）を、最初に使うときに読み、入力のたびに候補を出す。
// 上下の矢印のキーで候補を選び、Enter で開く。Escape で閉じる。選んでいない Enter は、検索の結果（/search/?q=…）へ移る。
// /search/ のページでは、結果を、種類（企業、工程、用語、ニュース）ごとの見出しで並べる。
import { search, type SearchEntry } from '../lib/normalize';

const TYPE_LABEL: Record<SearchEntry['type'], string> = { company: '企業', process: '工程', term: '用語', news: 'ニュース' };
let indexPromise: Promise<SearchEntry[]> | null = null;
const loadIndex = () => (indexPromise ??= fetch('/search-index.json').then((r) => (r.ok ? (r.json() as Promise<SearchEntry[]>) : [])).catch(() => []));

function metaText(entry: SearchEntry): string {
  return [TYPE_LABEL[entry.type], entry.code].filter(Boolean).join('　');
}

for (const form of document.querySelectorAll<HTMLFormElement>('form[data-search]')) {
  const input = form.querySelector<HTMLInputElement>('input[type="search"]')!;
  const list = form.querySelector<HTMLUListElement>('[role="listbox"]')!;
  let active = -1;
  let items: SearchEntry[] = [];

  const close = () => {
    list.hidden = true;
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
    active = -1;
  };
  const setActive = (index: number) => {
    const options = list.querySelectorAll<HTMLLIElement>('[role="option"]');
    options.forEach((o, i) => o.setAttribute('aria-selected', String(i === index)));
    active = index;
    if (index >= 0) {
      input.setAttribute('aria-activedescendant', options[index].id);
      options[index].scrollIntoView({ block: 'nearest' });
    } else input.removeAttribute('aria-activedescendant');
  };
  const render = async () => {
    const query = input.value.trim();
    if (!query) return close();
    items = search(await loadIndex(), query, 8);
    list.replaceChildren();
    if (items.length === 0) {
      const li = document.createElement('li');
      li.className = 'suggest__empty';
      li.setAttribute('role', 'presentation');
      li.textContent = '候補がありません。Enterで、検索の結果を開きます。';
      list.append(li);
    }
    items.forEach((entry, i) => {
      const li = document.createElement('li');
      li.setAttribute('role', 'option');
      li.id = `${list.id}-${i}`;
      li.setAttribute('aria-selected', 'false');
      const a = document.createElement('a');
      a.href = entry.url;
      const name = document.createElement('span');
      name.className = 'suggest__name';
      name.textContent = entry.name;
      const meta = document.createElement('span');
      meta.className = 'suggest__meta';
      meta.textContent = metaText(entry);
      a.append(name, meta);
      li.append(a);
      list.append(li);
    });
    list.hidden = false;
    input.setAttribute('aria-expanded', 'true');
    active = -1;
  };

  input.addEventListener('input', render);
  input.addEventListener('focus', () => void loadIndex());
  input.addEventListener('keydown', (event) => {
    const count = items.length;
    if (event.key === 'ArrowDown' && !list.hidden && count > 0) {
      event.preventDefault();
      setActive((active + 1) % count);
    } else if (event.key === 'ArrowUp' && !list.hidden && count > 0) {
      event.preventDefault();
      setActive(active <= 0 ? count - 1 : active - 1);
    } else if (event.key === 'Enter' && active >= 0 && items[active]) {
      event.preventDefault();
      location.href = items[active].url;
    } else if (event.key === 'Escape') {
      close();
    }
  });
  document.addEventListener('click', (event) => {
    if (!form.contains(event.target as Node)) close();
  });
}

// ---- 検索の結果のページ（/search/） ----
const results = document.querySelector<HTMLElement>('[data-search-results]');
if (results) {
  const query = new URLSearchParams(location.search).get('q')?.trim() ?? '';
  // 検索のページの大きな検索欄（なければ、最初の検索欄）に、入力した語を入れる
  const box = document.querySelector<HTMLInputElement>('#search-page') ?? document.querySelector<HTMLInputElement>('form[data-search] input[type="search"]');
  if (box && query) box.value = query;
  const status = results.querySelector<HTMLElement>('[data-search-status]')!;
  const target = results.querySelector<HTMLElement>('[data-search-groups]')!;
  void loadIndex().then((entries) => {
    target.replaceChildren();
    if (!query) {
      status.textContent = '検索する語を入力してください。例：企業名、証券コード、用語';
      return;
    }
    const found = search(entries, query, 200);
    status.textContent = `「${query}」の検索結果：${found.length}件`;
    if (found.length === 0) {
      const p = document.createElement('p');
      p.textContent = '該当するものは見つかりませんでした。企業名、証券コード、用語の一部を入力してみてください。例：東京エレクトロン、8035、CMP';
      target.append(p);
    }
    // 種類ごとのまとまりと、種類の絞り込みのチップ（件数つき。結果のない種類は出さない）
    const chips = results.querySelector<HTMLElement>('[data-search-chips]');
    const sections: { type: string; el: HTMLElement }[] = [];
    // 名前の中の、入力した語と同じ部分に印を付ける（大文字と小文字は区別しない。見つからなければ印なし）
    const marked = (name: string) => {
      const frag = document.createDocumentFragment();
      const at = name.toLowerCase().indexOf(query.toLowerCase());
      if (at < 0) {
        frag.append(name);
        return frag;
      }
      const mark = document.createElement('mark');
      mark.textContent = name.slice(at, at + query.length);
      frag.append(name.slice(0, at), mark, name.slice(at + query.length));
      return frag;
    };
    for (const type of ['company', 'process', 'term', 'news'] as const) {
      const group = found.filter((e) => e.type === type);
      if (group.length === 0) continue;
      const section = document.createElement('section');
      section.className = 'sres';
      const h2 = document.createElement('h2');
      const count = document.createElement('small');
      count.textContent = `${group.length}件`;
      h2.append(TYPE_LABEL[type], count);
      const ul = document.createElement('ul');
      for (const entry of group) {
        const li = document.createElement('li');
        const a = document.createElement('a');
        a.href = entry.url;
        a.append(marked(entry.name));
        li.append(a);
        const detail = [entry.code && `証券コード ${entry.code}`, entry.detail].filter(Boolean).join('・');
        if (detail) {
          const span = document.createElement('span');
          span.className = 'sres__detail';
          span.textContent = detail;
          li.append(span);
        }
        ul.append(li);
      }
      section.append(h2, ul);
      target.append(section);
      sections.push({ type, el: section });
    }
    if (chips && sections.length > 1) {
      const make = (label: string, n: number, type: string) => {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'chip';
        b.setAttribute('aria-pressed', String(type === ''));
        const c = document.createElement('span');
        c.className = 'chip__n';
        c.textContent = String(n);
        b.append(label, c);
        b.addEventListener('click', () => {
          chips.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
          for (const s of sections) s.el.hidden = !!type && s.type !== type;
        });
        return b;
      };
      chips.append(make('すべて', found.length, ''), ...sections.map((s) => make(TYPE_LABEL[s.type as SearchEntry['type']], found.filter((e) => e.type === s.type).length, s.type)));
      chips.hidden = false;
    }
  });
}
