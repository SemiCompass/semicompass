// スマートフォンのメニュー（<details>）：開閉の状態を、ボタン（summary）の aria-expanded に反映する（仕様書 8.1、11章）。
// スクリプトがなくても、メニューは開閉できる（<details> の働き）。
for (const details of document.querySelectorAll<HTMLDetailsElement>('details.site-header__fold')) {
  const button = details.querySelector<HTMLElement>('summary');
  if (!button) continue;
  const sync = () => button.setAttribute('aria-expanded', String(details.open));
  details.addEventListener('toggle', sync);
  sync();
}
