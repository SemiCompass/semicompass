---
title: 量子閉じ込め：井戸の幅を半分にすると、準位は4倍になる
field: device-physics
description: 薄い層に電子を閉じ込めると、エネルギーがとびとびの準位になる。壁が無限に高い井戸の式から、準位が井戸の幅の2乗に反比例し、有効質量に反比例することを読む。幅10 nmのヒ化ガリウムの井戸で、準位の値と準位の間隔を確かめる。
applies_to:
- type: learn
  ref: optoelectronics
  folder: devices
  note: 発光や受光のデバイスで、薄い層の厚みが光のエネルギーを決める仕組みが分かる。
- type: learn
  ref: what-is-semiconductor
  folder: basics
  note: 結晶が十分に小さいと、エネルギーが連続でなくなることが分かる。
basis: sources
draft: false
published_at: '2026-10-21'
ai_generated: true
sources:
- id: S1
  title: 'Intersubband absorption of an infinite quantum well'
  publisher: nextnano（nextnano GmbH）
  kind: web
  url: https://www.nextnano.com/docu/nextnanoplus/tutorials/1D_intersubband_infinite_QW.html
  accessed_on: '2026-10-21'
- id: S2
  title: 'Nano-optics 演習問題 第5回'
  publisher: バーゼル大学 Poggio 研究室
  kind: web
  url: https://poggiolab.unibas.ch/full/Nanooptics/NOExerciseSheet5.pdf
  accessed_on: '2026-10-21'
- id: S3
  title: 'CODATA Recommended Values of the Fundamental Physical Constants: 2018（NIST SP 961）'
  publisher: 米国国立標準技術研究所（NIST）
  kind: government
  url: https://physics.nist.gov/cuu/pdf/wall_2018.pdf
  accessed_on: '2026-10-21'
---

## 式

$$E_n = \frac{n^{2}\pi^{2}\hbar^{2}}{2\,m^{*}L^{2}}\qquad (n=1,2,3,\dots)$$

$L$ は井戸の幅、$m^{*}$ は電子の有効質量、$n$ は準位の番号、$\hbar$ は換算プランク定数である[S2]。壁が無限に高い井戸の場合の式である。電子は、この式のとびとびのエネルギーだけを取れる。

## 式のどこを見るか

見るのは、$L^2$ が分母にあることである。井戸の幅を半分にすると、準位は4倍に上がる。幅が狭いほど、電子は狭い場所に押し込まれ、エネルギーが高くなる。

次に、$m^{*}$ が分母にあることである。電子が軽い（有効質量が小さい）材料ほど、同じ幅でも準位は高くなる。有効質量は、「有効質量」のページで見たとおり、バンドの曲がりで決まる。

最後に、$n^2$ が掛かることである。準位の間隔は、上の準位ほど広がる。1番目の準位に対して、2番目は4倍、3番目は9倍である。

この式は無限に高い壁の場合である。実際の井戸の壁は有限の高さで、出典の計算でも、無限井戸は壁の高さを1000 eVと置いて近似している[S1]。

## 数値例

幅 $L=10$ nm、有効質量 $m^{*}=0.0665\,m_0$（ヒ化ガリウムの電子）の井戸を考える[S1]。換算プランク定数、電子の質量、電気素量[S3]を式に入れると、1番目の準位は約56.5 meV、2番目の準位は約226 meV になる（本サイトで計算）。出典の厳密解も、56.5 meV と 226 meV で、一致した[S1]。

準位の差は約169.6 meV で、出典の厳密解は169.5 meV である[S1]。

同じ有効質量で、幅を5 nm にすると、1番目の準位は約226 meV（4倍）、20 nm にすると約14.1 meV（4分の1）になる（本サイトで計算）。

## 理解度チェック

### 問1
無限井戸で、井戸の幅を半分にすると、1番目の準位はどうなるか。

1. 半分になる
2. 2倍になる
3. 4倍になる
4. 変わらない

答え：3
解説：準位は L² に反比例する。幅が半分になると、L² は4分の1になり、準位は4倍になる。

### 問2
同じ幅の井戸で、有効質量が小さい材料ほど、準位はどうなるか。

1. 低くなる
2. 高くなる
3. 変わらない
4. 質量とは関係なく、間隔だけが変わる

答え：2
解説：準位は m* に反比例する。電子が軽いほど、同じ幅の井戸でも準位は高くなる。
