---
title: 加速試験：高温で寿命を縮めて確かめる
field: materials-physics
description: 故障が熱で進む現象なら、高い温度で試験をすると、使う温度での寿命を短い時間で見積もれる。アレニウスの式で表す加速係数から、活性化エネルギーの違いで見積もりがどう変わるかを、試験と使用の温度の例で読む。
applies_to:
- type: learn
  ref: reliability-tests
  folder: test
  note: 高温で長時間動かす試験の時間が、使用時の何年分にあたるかを見積もれる。
- type: learn
  ref: manufacturing-reliability
  folder: power
  note: パワー半導体の寿命を、温度の条件から読む考え方が分かる。
- type: learn
  ref: doping-and-anneal
  folder: process
  note: 熱で進む現象の式が、工程でも試験でも同じ形であることが分かる。
basis: sources
draft: true
published_at: '2026-10-21'
ai_generated: true
sources:
- id: S1
  title: Calculation of Semiconductor Failure Rates
  publisher: ルネサス エレクトロニクス
  kind: web
  url: https://renesas.com/us/en/document/qsg/calculation-semiconductor-failure-rates
  accessed_on: '2026-10-21'
- id: S2
  title: 'CODATA Recommended Values of the Fundamental Physical Constants: 2018（NIST SP 961）'
  publisher: 米国国立標準技術研究所（NIST）
  kind: government
  url: https://physics.nist.gov/cuu/pdf/wall_2018.pdf
  accessed_on: '2026-10-21'
---

## 式

$$AF = \exp\left[\frac{E_a}{k}\left(\frac{1}{T_{use}} - \frac{1}{T_{stress}}\right)\right]$$

$AF$ は加速係数で、高温の試験が、使用時の何倍の速さで故障を進めるかを表す[S1]。$E_a$ は故障を進める現象の活性化エネルギー、$k$ はボルツマン定数である。$T_{use}$ は使用時、$T_{stress}$ は試験時の温度で、どちらも絶対温度（K）で入れる。

使用時の寿命は、試験で故障が出るまでの時間に $AF$ を掛けて見積もる。

$$t_{use} = AF \times t_{stress}$$

## 式のどこを見るか

見るのは、指数の中の括弧である。$1/T_{use}$ のほうが $1/T_{stress}$ より大きいので、括弧の中は正になり、$AF$ は1より大きくなる。試験の温度を使用時より高くするほど、$AF$ は大きくなる。

この形は、拡散や酸化の速さを表すアレニウスの式の比と同じである。故障が熱で進む現象であれば、同じ式で温度の影響を読める。

重要なのは $E_a$ である。$E_a$ が分子にあるため、$E_a$ が大きいほど $AF$ は大きく変わる。試験の結果を使用時の寿命に直すとき、$E_a$ の値の選び方で、見積もりが桁で変わる。故障の原因によって $E_a$ は異なるので、原因ごとの値を使う[S1]。

この式が成り立つのは、試験の温度でも、使用時と同じ現象で故障が進む場合だけである。温度を上げすぎて別の現象が起きると、見積もりは当てにならない。

## 数値例

ルネサス エレクトロニクスの資料の例では、使用時を55℃、試験時を150℃とし、どちらも素子内部の温度が周囲より20℃高いとして、$T_{use}=348$ K（75℃）、$T_{stress}=443$ K（170℃）とする[S1]。ボルツマン定数は $8.63\times10^{-5}$ eV/K である[S1]。

$E_a=0.7$ eV（フォトレジストの欠陥による故障）では、$AF=148.2$ になる[S1]。$E_a=0.3$ eV（酸化膜の欠陥による故障）では、$AF=8.52$ になる[S1]。同じ温度の組み合わせでも、$E_a$ の違いで約17倍の差が出る。

$E_a=0.7$ eV で試験を1,000時間続けたとすると、使用時の見積もりは約148,000時間になる。1年は約8,760時間なので、約17年分にあたる（本サイトで計算）。

NISTの値 $8.617\times10^{-5}$ eV/K[S2]で計算し直しても、$AF$ は約149で、ほぼ変わらない（本サイトで計算）。

## 理解度チェック

### 問1
試験の温度を使用時より高くすると、加速係数はどうなるか。

1. 小さくなる
2. 変わらない
3. 大きくなる
4. 活性化エネルギーによって、大きくなったり小さくなったりする

答え：3
解説：括弧の中が正の値で大きくなるため、AF は1より大きくなる。温度差が大きいほど AF は大きい。

### 問2
同じ温度の組み合わせで、活性化エネルギーが 0.7 eV の故障と 0.3 eV の故障を比べると、加速係数はどうなるか。

1. 0.7 eV のほうが大きい
2. 0.3 eV のほうが大きい
3. 同じである
4. 比べられない

答え：1
解説：Ea は指数の分子にあるので、大きいほど AF が大きい。資料の例では、0.7 eV で148.2、0.3 eV で8.52である。
