---
title: 拡散長：寿命が100倍長いと、少数キャリアは10倍遠くまで届く
field: device-physics
description: 注入された少数キャリアが、結びついて消えるまでに進む距離（拡散長）を、拡散係数と寿命から求める式で読む。拡散長が寿命の平方根で決まること、距離とともに指数で減ることを、移動度1,500 cm²/(V·s)のシリコンの電子で確かめる。
applies_to:
- type: learn
  ref: pn-junction
  folder: basics
  note: pn接合で、注入された少数キャリアがどこまで届くかが分かる。
- type: learn
  ref: optoelectronics
  folder: devices
  note: 光で生まれたキャリアが、電極まで届く距離の目安が読める。
basis: sources
draft: false
published_at: '2026-10-21'
ai_generated: true
sources:
- id: S1
  title: 'Diffusion Length'
  publisher: PVEducation
  kind: web
  url: https://www.pveducation.org/node/85
  accessed_on: '2026-10-21'
- id: S2
  title: 'Lecture notes on semiconductor devices（2018年10月31日分）'
  publisher: グラーツ工科大学（W. Hadley）
  kind: web
  url: https://lampz.tugraz.at/~hadley/psd/lectures18/oct31.pdf
  accessed_on: '2026-10-21'
- id: S3
  title: 'CODATA Recommended Values of the Fundamental Physical Constants: 2018（NIST SP 961）'
  publisher: 米国国立標準技術研究所（NIST）
  kind: government
  url: https://physics.nist.gov/cuu/pdf/wall_2018.pdf
  accessed_on: '2026-10-21'
---

## 式

$$L=\sqrt{D\,\tau},\qquad D=\frac{kT}{q}\,\mu,\qquad \delta p(x)=\delta p(0)\,\exp\left(-\frac{x}{L}\right)$$

$L$ は拡散長で、少数キャリアが生まれてから結びついて消えるまでに進む、平均の距離である[S1]。$D$ は拡散係数、$\tau$ は少数キャリアの寿命である[S1]。$D$ は移動度 $\mu$ と熱電圧 $kT/q$ の積で表せる（アインシュタインの関係）[S2]。

表面でキャリアを生み、内部では生まれないとき、定常状態の過剰なキャリアの濃度 $\delta p$ は、$x$ とともに指数で減る[S2]。

## 式のどこを見るか

見るのは、$L$ が $\sqrt{\tau}$ に比例することである。寿命が100倍になっても、拡散長は10倍にしかならない。寿命を延ばしても、届く距離は、その平方根でしか伸びない。

もう1つは、指数の形である。距離 $x$ が $L$ に達したところで、過剰なキャリアは約37％（$e^{-1}$）に減る。$2L$ で約13.5％、$3L$ で約5.0％である（本サイトで計算）。キャリアが届く距離の目安は、$L$ の数倍までである。

$D$ は移動度に比例するので、移動度が大きい電子は、同じ寿命でも、正孔より遠くまで届く。

## 数値例

シリコンの電子の移動度は 1,500 cm²/(V·s) である[S2]。300 Kの熱電圧は、ボルツマン定数と電気素量[S3]から約25.9 mV で、拡散係数は $D\approx38.8$ cm²/s になる（本サイトで計算）。出典の資料も、約39 cm²/s と見積もっている[S2]。

寿命は、例示のために1 μs と100 μs と仮定する（実際のシリコンの値ではない）。拡散長は、1 μs で約62 μm、100 μs で約620 μm になる（本サイトで計算）。寿命が100倍で、拡散長は10倍である。

なお、結晶シリコン太陽電池では、拡散長は典型的に100〜300 μm とされ、シリコンの寿命は最大で1 ms 程度になりうる[S1]。

## 理解度チェック

### 問1
少数キャリアの寿命が100倍になると、拡散長は何倍になるか。

1. 約2倍
2. 約10倍
3. 約100倍
4. 約10,000倍

答え：2
解説：L = √(Dτ) なので、拡散長は寿命の平方根に比例する。寿命が100倍になると、拡散長は10倍になる。

### 問2
注入された少数キャリアの過剰な濃度は、拡散長 L だけ離れた場所で、もとの濃度のおよそ何％になるか。

1. 約5％
2. 約13％
3. 約37％
4. 約63％

答え：3
解説：濃度は exp(−x/L) で減る。x = L では exp(−1) で、約37％になる。
