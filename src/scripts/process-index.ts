// 「すべて開く／閉じる」は、スクリプトがあるときだけ出す。図の箱から工程へ移動したときは、その工程の企業を開く
const tools = document.querySelector<HTMLElement>('[data-expand-tools]');
const all = () => Array.from(document.querySelectorAll<HTMLDetailsElement>('details.supply-process__companies'));
if (tools) {
  tools.hidden = false;
  tools.querySelectorAll<HTMLButtonElement>('[data-expand]').forEach((b) =>
    b.addEventListener('click', () => all().forEach((d) => (d.open = b.dataset.expand === 'open'))));
}
const openTarget = () => {
  const el = location.hash ? document.getElementById(decodeURIComponent(location.hash.slice(1))) : null;
  el?.closest('section')?.querySelector<HTMLDetailsElement>('details.supply-process__companies')?.setAttribute('open', '');
};
openTarget();
window.addEventListener('hashchange', openTarget);
