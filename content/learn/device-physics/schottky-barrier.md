---
title: ショットキー障壁：障壁が0.1 eV違うと、電流は約48倍変わる
field: device-physics
description: 金属と半導体をつないだ接触にできる障壁の高さ（ショットキー障壁）が、ダイオードの電流を指数で決めることを、熱電子放出の式から読む。障壁の高さを0.7 eVと0.8 eVと仮定した例で、飽和電流と電流が流れ始める電圧の違いを確かめる。
applies_to:
- type: learn
  ref: pn-junction
  folder: basics
  note: pn接合とは別に、金属と半導体の接触でも一方向に電流が流れることが分かる。
- type: learn
  ref: diode
  folder: power
  note: ショットキーバリアダイオードの電流が、障壁の高さで決まることが読める。
basis: sources
draft: true
published_at: '2026-10-21'
ai_generated: true
sources:
- id: S1
  title: 'Lecture notes on semiconductor devices（Schottky diode、2018年11月21日分）'
  publisher: グラーツ工科大学（W. Hadley）
  kind: web
  url: https://lampz.tugraz.at/~hadley/psd/lectures18/nov21.pdf
  accessed_on: '2026-10-21'
- id: S2
  title: '3.1.6.2 Schottky Contact'
  publisher: ウィーン工科大学（A. Ayalew の学位論文）
  kind: web
  url: https://iue.tuwien.ac.at/phd/ayalew/node56.html
  accessed_on: '2026-10-21'
- id: S3
  title: 'CODATA Recommended Values of the Fundamental Physical Constants: 2018（NIST SP 961）'
  publisher: 米国国立標準技術研究所（NIST）
  kind: government
  url: https://physics.nist.gov/cuu/pdf/wall_2018.pdf
  accessed_on: '2026-10-21'
---

## 式

$$J = A^{*}T^{2}\exp\left(-\frac{q\phi_B}{kT}\right)\left[\exp\left(\frac{qV}{kT}\right)-1\right]$$

$J$ は電流密度、$V$ は金属と半導体にかける電圧、$\phi_B$ はショットキー障壁の高さである[S1]。$A^{*}$ はリチャードソン定数で、有効質量に依存する[S2]。

n型半導体では、障壁の高さは金属の仕事関数 $\phi_m$ から半導体の電子親和力 $\chi$ を引いた値になる（$\phi_{Bn}=\phi_m-\chi$）[S2]。p型では $\phi_{Bp}=E_g/q+\chi-\phi_m$ である[S2]。

## 式のどこを見るか

見るのは、$\exp(-q\phi_B/kT)$ の項である。この項により、電流の飽和値は、障壁の高さで指数的に決まる。障壁が高いほど、飽和値は小さい。温度も、$T^2$ と指数の中の $kT$ を通して、飽和値に強く効く。

角括弧の中は、「ダイオードの電流式」のページで見た式と同じ形である。順方向では電流が電圧の指数で増え、逆方向では飽和値で頭打ちになる。違いは、飽和値の決まり方にある。ここでは、障壁を越える電子の数、すなわち熱電子放出で決まる[S1]。

式の理想係数は1で、ショットキーダイオードでは拡散による電流より熱電子放出が支配的である[S1]。

実際の測定値は、式からのずれが出る。炭化ケイ素（SiC）の接触では、測った障壁の高さが計算値と違う。理由として、界面の化学反応、界面準位、界面の層、面の向き、洗浄の手順が挙げられている[S2]。

## 数値例

n型シリコンのリチャードソン定数は 110 A/(K²·cm²) である[S1]。障壁の高さは、例示のために 0.7 eV と 0.8 eV と仮定する（実際の金属で決まる値ではない）。温度は300 Kとし、熱エネルギー $kT$ はボルツマン定数[S3]から約25.85 meV になる（本サイトで計算）。

飽和電流密度 $J_S=A^{*}T^2\exp(-q\phi_B/kT)$ は、0.7 eV で約 $1.7\times10^{-5}$ A/cm²、0.8 eV で約 $3.6\times10^{-7}$ A/cm² になる（本サイトで計算）。障壁が0.1 eV高いと、飽和電流は約48分の1である（本サイトで計算）。

順方向で電流密度が 1 A/cm² に達する電圧は、$V=(kT/q)\ln(J/J_S)$ から、0.7 eV で約0.28 V、0.8 eV で約0.38 V である（本サイトで計算）。障壁が0.1 eV高いと、同じ電流を流すのに約0.1 V多く要る。

## 理解度チェック

### 問1
金属と半導体の接触で、障壁の高さを大きくすると、飽和電流はどうなるか。

1. 指数的に小さくなる
2. 指数的に大きくなる
3. 変わらない
4. 障壁の高さの2乗に比例する

答え：1
解説：飽和電流は exp(−qφB/kT) に比例する。障壁が高いほど、越えられる電子が減り、飽和電流は指数的に小さくなる。

### 問2
室温で、障壁の高さが0.1 eV違うと、飽和電流はおよそ何倍違うか。

1. 約2倍
2. 約10倍
3. 約48倍
4. 約1,000倍

答え：3
解説：比は exp(0.1 eV / kT) である。室温の kT は約25.9 meV なので、exp(3.87) で約48倍になる。
