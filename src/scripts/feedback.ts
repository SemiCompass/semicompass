// 疑問の解決ボタン（要件定義書 FR-709、要求定義書 VM-01）：「はい／いいえ」を押すと、GA4にイベント page_feedback を送り、
// 「ありがとうございました」に変える。同じページで何度も送らない（このタブの間は、回答済みとして扱う）。
// 送るのは、Cookieの利用に同意しているときだけ（analytics.ts の track）。
import { track } from './analytics';

for (const root of document.querySelectorAll<HTMLElement>('[data-feedback]')) {
  const key = `semicompass-feedback:${location.pathname}`;
  const thanks = root.querySelector<HTMLElement>('[data-feedback-thanks]');
  const choices = root.querySelector<HTMLElement>('[data-feedback-choices]');
  const done = () => {
    if (choices) choices.hidden = true;
    if (thanks) thanks.hidden = false;
  };
  let answered = false;
  try {
    answered = sessionStorage.getItem(key) !== null;
  } catch {
    answered = false;
  }
  if (answered) done();
  for (const wrap of root.querySelectorAll<HTMLElement>('[data-feedback-wrap]')) {
    const button = wrap.querySelector('button');
    button?.addEventListener('click', () => {
      if (answered) return;
      answered = true;
      const answer = wrap.dataset.feedbackWrap ?? '';
      track('page_feedback', { page_type: root.dataset.pageType ?? '', page_url: location.pathname, answer });
      try {
        sessionStorage.setItem(key, answer);
      } catch {
        /* 保存できなくても、このページでは二度送らない */
      }
      done();
      thanks?.focus();
    });
  }
}
