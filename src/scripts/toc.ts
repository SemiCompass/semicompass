// ページ内の目次（PCの右の列）：いま読んでいる中見出し（h2）の項目に、aria-current="location" を付ける（仕様書 8.4）。
// 操作の結果ではなく、読んでいる位置の表示だけ。動きは付けない。スクリプトがなくても、目次のリンクは使える。
const nav = document.querySelector<HTMLElement>('[data-toc]');
if (nav) {
  const links = Array.from(nav.querySelectorAll<HTMLAnchorElement>('a[href^="#"]'));
  const targets = links
    .map((link) => document.getElementById(decodeURIComponent(link.hash.slice(1))))
    .filter((el): el is HTMLElement => el !== null);
  const setCurrent = (id: string | null) => {
    for (const link of links) {
      if (id !== null && decodeURIComponent(link.hash.slice(1)) === id) {
        link.setAttribute('aria-current', 'location');
      } else {
        link.removeAttribute('aria-current');
      }
    }
  };
  const visible = new Set<string>();
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) visible.add(entry.target.id);
        else visible.delete(entry.target.id);
      }
      // 見えている見出しのうち、ページの上にあるものを、現在地とする
      const current = targets.find((el) => visible.has(el.id));
      if (current) setCurrent(current.id);
    },
    { rootMargin: '0px 0px -60% 0px' },
  );
  targets.forEach((el) => observer.observe(el));
}
