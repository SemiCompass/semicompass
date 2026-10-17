// 分類の絞り込み：スクリプトがあるときだけ、チップを見せる（なくても、全件が読める）
const root = document.querySelector<HTMLElement>('[data-news-filter]');
if (root) {
  root.hidden = false;
  const buttons = Array.from(root.querySelectorAll<HTMLButtonElement>('[data-category]'));
  const rows = Array.from(document.querySelectorAll<HTMLElement>('.news-list__item'));
  const count = document.querySelector<HTMLElement>('[data-news-count]');
  for (const b of buttons) {
    b.addEventListener('click', () => {
      const c = b.dataset.category ?? '';
      for (const x of buttons) x.setAttribute('aria-pressed', String(x === b));
      let shown = 0;
      for (const r of rows) {
        r.hidden = !!c && r.dataset.category !== c;
        if (!r.hidden) shown += 1;
      }
      if (count) count.textContent = shown === rows.length ? `${rows.length}件` : `${rows.length}件のうち、${shown}件`;
    });
  }
}
