// グラフの操作（仕様書 10.4）：棒や点を選ぶ（タップ、クリック、キーボード）と、その近くに数値を出す。
// マウスを重ねたときだけに出る情報にしない。スクリプトがなくても、フォーカスで数値が出る。Escape で閉じる。
const SELECTED = 'is-selected';

function select(datum: SVGGElement | null) {
  for (const other of document.querySelectorAll<SVGGElement>(`.chart-datum.${SELECTED}`)) {
    if (other !== datum) {
      other.classList.remove(SELECTED);
      other.setAttribute('aria-pressed', 'false');
    }
  }
  if (!datum) return;
  const on = !datum.classList.contains(SELECTED);
  datum.classList.toggle(SELECTED, on);
  datum.setAttribute('aria-pressed', String(on));
}

document.addEventListener('click', (event) => {
  const datum = (event.target as Element).closest<SVGGElement>('.chart-datum');
  select(datum);
});
document.addEventListener('keydown', (event) => {
  const target = event.target as Element;
  const datum = target.closest<SVGGElement>('.chart-datum');
  if (datum && (event.key === 'Enter' || event.key === ' ')) {
    event.preventDefault();
    select(datum);
  } else if (event.key === 'Escape') {
    select(null);
  }
});
