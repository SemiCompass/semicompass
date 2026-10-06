// ページ内の目次（PCの右の列）：いま読んでいる中見出し（h2）の項目に、aria-current="location" を付ける（仕様書 8.4）。
// 読んでいる見出し＝画面の上端に最も近い、通り過ぎた見出し（上端から基準の位置までに入った、最後の見出し）。
// ページの最後までスクロールしたときは、最後の項目にする。動きは付けない。スクリプトがなくても、目次のリンクは使える。
const nav = document.querySelector<HTMLElement>('[data-toc]');
if (nav) {
  const links = Array.from(nav.querySelectorAll<HTMLAnchorElement>('a[href^="#"]'));
  const entries = links
    .map((link) => ({ link, id: decodeURIComponent(link.hash.slice(1)) }))
    .map((e) => ({ ...e, heading: document.getElementById(e.id) }))
    .filter((e): e is { link: HTMLAnchorElement; id: string; heading: HTMLElement } => e.heading !== null);

  const update = () => {
    // 基準の位置：画面の上端から、画面の高さの4分の1（最大160px）。この位置を通り過ぎた見出しのうち、最後のものが現在地
    const line = Math.min(160, window.innerHeight / 4);
    let current: string | null = null;
    for (const e of entries) {
      if (e.heading.getBoundingClientRect().top <= line) current = e.id;
    }
    const atEnd = window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 2;
    if (atEnd && entries.length > 0) current = entries[entries.length - 1].id;
    for (const e of entries) {
      if (e.id === current) e.link.setAttribute('aria-current', 'location');
      else e.link.removeAttribute('aria-current');
    }
  };

  let waiting = false;
  const schedule = () => {
    if (waiting) return;
    waiting = true;
    requestAnimationFrame(() => {
      waiting = false;
      update();
    });
  };
  window.addEventListener('scroll', schedule, { passive: true });
  window.addEventListener('resize', schedule);
  window.addEventListener('hashchange', schedule);
  update();
}
