// 理解度チェック（仕様書 8.17）：選んだ選択肢と正しい選択肢に印を付け、「答えと解説」を開く。1問につき1回だけ答えられる。
// 結果は、Cookieの利用に同意しているときだけ、GA4のイベント quiz_answer として送る（analytics.ts の track）。
import { track } from './analytics';

for (const root of document.querySelectorAll<HTMLElement>('[data-quiz]')) {
  const icons = root.querySelector<HTMLTemplateElement>('template[data-icons]');
  const icon = (name: 'correct' | 'wrong') => icons?.content.querySelector(`[data-icon="${name}"]`)?.innerHTML ?? '';
  for (const item of root.querySelectorAll<HTMLElement>('[data-quiz-item]')) {
    const answer = item.dataset.answer ?? '';
    const buttons = [...item.querySelectorAll<HTMLButtonElement>('button[data-choice]')];
    const status = item.querySelector<HTMLElement>('[data-status]');
    const explain = item.querySelector<HTMLDetailsElement>('[data-explain]');
    const mark = (button: HTMLButtonElement, state: 'correct' | 'wrong') => {
      button.dataset.state = state;
      const m = button.querySelector<HTMLElement>('[data-mark]');
      const r = button.querySelector<HTMLElement>('[data-result]');
      if (m) m.innerHTML = icon(state);
      if (r) r.textContent = state === 'correct' ? '正解' : 'あなたの答え';
    };
    for (const button of buttons) {
      button.addEventListener('click', () => {
        const chosen = button.dataset.choice ?? '';
        const correct = chosen === answer;
        for (const b of buttons) {
          b.disabled = true;
          if (b.dataset.choice === answer) mark(b, 'correct');
        }
        if (!correct) mark(button, 'wrong');
        if (status) status.textContent = correct ? '正解です。' : `不正解です。正しい答えは${answer}です。`;
        if (explain) explain.open = true;
        track('quiz_answer', {
          page_type: root.dataset.pageType ?? '',
          page_path: location.pathname,
          question: item.dataset.question ?? '',
          correct: correct ? 'true' : 'false',
        });
      });
    }
  }
}
