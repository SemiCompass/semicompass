// アクセス解析（Google Analytics 4）とCookieの同意（要件定義書 LG-03、FR-709）。
// 同意を得るまでは、Googleのプログラムを読み込まず、Cookieも設定しない。選択はブラウザ（localStorage）に残し、外部に送らない。
// 計測するのは本番のビルドだけ（<body data-ga-id> があるときだけ動く）。
const KEY = 'semicompass-consent-v1';
type Choice = 'granted' | 'denied';

declare global {
  interface Window {
    dataLayer?: unknown[];
    gtag?: (...args: unknown[]) => void;
  }
}

const gaId = document.body.dataset.gaId ?? '';
// 広告を出すビルド（<body data-ad-client>）でも、同じ1つの確認で選んでもらう（要件定義書 LG-03）。選んだ結果は、イベントで広告の読み込み（src/scripts/ads.ts）に伝える
const adsOn = Boolean(document.body.dataset.adClient);
export const CONSENT_EVENT = 'semicompass:consent';
const announce = (choice: Choice) => document.dispatchEvent(new CustomEvent<Choice>(CONSENT_EVENT, { detail: choice }));

export function readChoice(): Choice | null {
  try {
    const v = localStorage.getItem(KEY);
    return v === 'granted' || v === 'denied' ? v : null;
  } catch {
    return null;
  }
}
function saveChoice(v: Choice) {
  try {
    localStorage.setItem(KEY, v);
  } catch {
    /* 保存できないブラウザでは、毎回たずねる */
  }
}

let loaded = false;
function loadAnalytics() {
  if (loaded || !gaId) return;
  loaded = true;
  window.dataLayer = window.dataLayer ?? [];
  window.gtag = function gtag() {
    // eslint-disable-next-line prefer-rest-params
    window.dataLayer!.push(arguments);
  };
  window.gtag('js', new Date());
  // 広告の機能とGoogleシグナルは使わない
  window.gtag('config', gaId, { allow_google_signals: false, allow_ad_personalization_signals: false });
  const script = document.createElement('script');
  script.async = true;
  script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(gaId)}`;
  document.head.append(script);
}

// 同意を取り消したときは、アクセス解析のCookie（_ga、_ga_…）を消す
function clearAnalyticsCookies() {
  const host = location.hostname;
  for (const part of document.cookie.split(';')) {
    const name = part.split('=')[0].trim();
    if (name !== '_ga' && !name.startsWith('_ga_')) continue;
    for (const domain of ['', `; domain=${host}`, `; domain=.${host}`]) {
      document.cookie = `${name}=; Max-Age=0; path=/${domain}`;
    }
  }
}

/** イベントを送る。同意していないとき、計測しないビルドのときは、何もしない */
export function track(name: string, params: Record<string, string>) {
  if (!gaId || readChoice() !== 'granted') return;
  loadAnalytics();
  window.gtag?.('event', name, params);
}

if (gaId || adsOn) {
  const banner = document.querySelector<HTMLElement>('[data-consent]');
  const show = () => {
    if (banner) banner.hidden = false;
  };
  const hide = () => {
    if (banner) banner.hidden = true;
  };
  const choice = readChoice();
  if (choice === 'granted') loadAnalytics();
  if (choice === null) show();
  banner?.querySelector('[data-consent-accept-wrap] button')?.addEventListener('click', () => {
    saveChoice('granted');
    hide();
    loadAnalytics();
    announce('granted');
  });
  banner?.querySelector('[data-consent-reject-wrap] button')?.addEventListener('click', () => {
    const wasLoaded = loaded;
    saveChoice('denied');
    clearAnalyticsCookies();
    hide();
    announce('denied');
    if (wasLoaded) location.reload(); // 読み込み済みのプログラムを止める
  });
  for (const opener of document.querySelectorAll('[data-consent-open]')) {
    opener.addEventListener('click', () => {
      show();
      banner?.querySelector<HTMLElement>('[data-consent-accept-wrap] button')?.focus();
    });
  }
}
