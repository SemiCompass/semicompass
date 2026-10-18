// 広告の読み込み（要件定義書 LG-03、AD-404。画面とデザインの仕様書 8.23）。本番で config/ads.yaml の enabled が true のときだけ、
// Base が <body data-ad-client> と AdLoader（このスクリプトを読み込む部品）を出す。enabled が false のビルドでは、どのページもこのスクリプトを読み込まない。
// * Cookieの確認をまだ選んでいない閲覧者には、広告を読み込まない（確認の帯が広告に重ならないように）。選んだ後に読み込む
// * 同意しない閲覧者には、非パーソナライズド広告（閲覧の履歴を使わない広告）を要求する
// * 本文の表示の後（load の後）に読み込む。見える直前まで遅らせる方法は、AdSenseが認める方法を確かめてから（要件定義書 12章の未決事項12）
// * PCの右の列の枠（data-ad-pc-only）は、PCの幅のときだけ要求する。要求した枠には data-ad-loaded を付け、以後は隠さない
import { CONSENT_EVENT, readChoice } from './analytics';

type Choice = 'granted' | 'denied';
declare global {
  interface Window {
    adsbygoogle?: unknown[] & { requestNonPersonalizedAds?: number };
  }
}

const client = document.body.dataset.adClient ?? '';
let started: Choice | null = null;

function isPc(): boolean {
  const bp = getComputedStyle(document.documentElement).getPropertyValue('--bp-pc').trim() || '1024px';
  return window.matchMedia(`(min-width: ${bp})`).matches;
}

function start(choice: Choice) {
  if (started) {
    // 同意を取り消したときは、読み込み済みの広告を止めるため、ページを読み直す
    if (started === 'granted' && choice === 'denied') location.reload();
    return;
  }
  started = choice;
  const pc = isPc();
  const all = [...document.querySelectorAll<HTMLElement>('[data-ad-frame]')];
  // 要求しない枠（PCより狭い幅の右の列）は、AdSenseが拾わないように、広告ユニットの印（adsbygoogle）を外す
  for (const frame of all) {
    if (!pc && frame.hasAttribute('data-ad-pc-only')) frame.querySelector('ins')?.classList.remove('adsbygoogle');
  }
  const frames = all.filter((f) => pc || !f.hasAttribute('data-ad-pc-only'));
  if (frames.length === 0) return;
  const queue = (window.adsbygoogle = window.adsbygoogle ?? []);
  if (choice === 'denied') queue.requestNonPersonalizedAds = 1;
  for (const frame of frames) {
    frame.setAttribute('data-ad-loaded', '');
    queue.push({});
  }
  const script = document.createElement('script');
  script.async = true;
  script.crossOrigin = 'anonymous';
  script.src = `https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${encodeURIComponent(client)}`;
  document.head.append(script);
}

function init() {
  if (!client) return;
  const choice = readChoice();
  if (choice) start(choice);
  document.addEventListener(CONSENT_EVENT, (event) => start((event as CustomEvent<Choice>).detail));
}

if (document.readyState === 'complete') init();
else window.addEventListener('load', init, { once: true });
