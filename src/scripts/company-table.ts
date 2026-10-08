// 企業の表：工程と企業区分の絞り込み、件数の表示、並べ替え（見出しを押す）。スクリプトがなくても、全件が表で読める。
for (const root of document.querySelectorAll<HTMLElement>('[data-company-table]')) {
  const body = root.querySelector('tbody')!;
  const rows = Array.from(body.querySelectorAll<HTMLTableRowElement>('tr[data-index]'));
  const count = root.querySelector<HTMLElement>('[data-count]');
  const empty = root.querySelector<HTMLElement>('[data-empty]');
  const processSelect = root.querySelector<HTMLSelectElement>('select[data-filter="process"]');
  const typeSelect = root.querySelector<HTMLSelectElement>('select[data-filter="type"]');
  const total = rows.length;

  root.querySelector<HTMLElement>('[data-filters]')?.removeAttribute('hidden'); // スクリプトがあるときだけ、絞り込みを見せる

  const apply = () => {
    const process = processSelect?.value ?? '';
    const type = typeSelect?.value ?? '';
    let shown = 0;
    for (const row of rows) {
      const ok = (!process || (row.dataset.process ?? '').split(' ').includes(process)) && (!type || row.dataset.type === type);
      row.hidden = !ok;
      if (ok) shown += 1;
    }
    if (count) count.textContent = shown === total ? `${total}社を表示しています` : `${total}社のうち、${shown}社を表示しています`;
    if (empty) empty.hidden = shown !== 0;
  };
  processSelect?.addEventListener('change', apply);
  typeSelect?.addEventListener('change', apply);

  // 並べ替え：見出しを押すと、昇順 → 降順 → 元の順。aria-sort で状態を示す。数値の列は、値のない行を、いつも末尾にする
  const headers = Array.from(root.querySelectorAll<HTMLTableCellElement>('th[data-sort-key]'));
  for (const th of headers) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'data-table__sort-button';
    button.append(...Array.from(th.childNodes));
    th.append(button);
    button.addEventListener('click', () => {
      const current = th.getAttribute('aria-sort');
      const next = current === 'ascending' ? 'descending' : current === 'descending' ? 'none' : 'ascending';
      for (const other of headers) other.setAttribute('aria-sort', other === th ? next : 'none');
      const key = th.dataset.sortKey!;
      const numeric = ['sales', 'ratio', 'margin', 'salary'].includes(key);
      const value = (row: HTMLTableRowElement) => row.dataset[`sort${key[0].toUpperCase()}${key.slice(1)}`] ?? '';
      const sorted = [...rows].sort((a, b) => {
        if (next === 'none') return Number(a.dataset.index) - Number(b.dataset.index);
        const [va, vb] = [value(a), value(b)];
        if (va === '' || vb === '') return va === vb ? 0 : va === '' ? 1 : -1;
        const cmp = numeric ? Number(va) - Number(vb) : va.localeCompare(vb, 'ja');
        return next === 'ascending' ? cmp : -cmp;
      });
      body.append(...sorted);
    });
  }
}
