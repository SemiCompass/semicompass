---
title: 逆格子とブリルアンゾーン：シリコンの伝導帯の底は、Γ点からX点までの約85％にある
field: solid-state
description: 結晶の波数の世界を表す逆格子と、その基本の領域であるブリルアンゾーンを、シリコンで読む。面心立方の結晶の逆格子は体心立方で、格子定数0.543 nmから、Γ点、L点、X点の波数の大きさを求め、伝導帯の底の位置を波数の値で確かめる。
applies_to:
- type: learn
  ref: energy-band
  folder: basics
  note: バンド図の横軸にある波数が、結晶のどの範囲を表すかが分かる。
- type: learn
  ref: crystal
  folder: silicon
  note: 結晶の原子の並びと、波数の世界との対応が読める。
basis: sources
draft: false
published_at: '2026-10-21'
ai_generated: true
sources:
- id: S1
  title: 'Brillouin zone and band structure of silicon（学位論文の解説ページ）'
  publisher: ウィーン工科大学（Dhar の学位論文）
  kind: web
  url: https://www.iue.tuwien.ac.at/phd/dhar/node18.html
  accessed_on: '2026-10-21'
- id: S2
  title: 'ECE 6451 Lecture 7: Three-dimensional crystals and band structure'
  publisher: ジョージア工科大学
  kind: web
  url: https://alan.ece.gatech.edu/ECE6451/Lectures/ECE6451L7ThreeDCrystalsandBandStructure.pdf
  accessed_on: '2026-10-21'
- id: S3
  title: 'ECE 340 Lecture 2: Crystal structure'
  publisher: イリノイ大学アーバナ・シャンペーン校
  kind: web
  url: https://ursemiconductors.web.illinois.edu/ECE340/Lecture02.pdf
  accessed_on: '2026-10-21'
---

## 式

$$\mathbf{G}\cdot\mathbf{R}=2\pi n\quad(n\text{は整数}),\qquad k_X=\frac{2\pi}{a}$$

$\mathbf{R}$ は結晶の格子点を結ぶベクトル、$\mathbf{G}$ は逆格子ベクトルで、すべての $\mathbf{R}$ に対して、内積が $2\pi$ の整数倍になるものをいう[S2]。逆格子の点が並ぶ空間は、波数 $\mathbf{k}$ の空間である。

シリコンのような面心立方の結晶の逆格子は、体心立方になる[S1]。その基本の領域がブリルアンゾーンで、体心立方の格子点の周りの領域（ウィグナー・ザイツセル）として、切頭八面体の形になる[S1]。

## 式のどこを見るか

見るのは、ゾーンの特別な点である。$\Gamma$ 点は原点（$k=0$）、$X$ 点は $(1,0,0)$、$L$ 点は $(1/2,1/2,1/2)$ の位置にある（単位は $2\pi/a$）[S1]。$X$ 点は正方形の面の中心、$L$ 点は六角形の面の中心である[S1]。$\Gamma$ から $X$ までの距離は $2\pi/a$ で、$\Gamma$ から $L$ までは $\sqrt{3}/2$ 倍になる（本サイトで計算）。

シリコンの伝導帯の底は、$\Gamma$ 点ではなく、$\Gamma$ から $X$ に向かう $\langle100\rangle$ 方向の約85％の位置にある[S1]。同じ形の谷が、$[100]$、$[010]$、$[001]$ とその反対向きで、全部で6個ある[S1]。

$k=2\pi/a$ に対応する電子波の波長は、$\lambda=2\pi/k=a$ で、格子定数に等しい（本サイトで計算）。

## 数値例

格子定数 $a=5.43$ Å（0.543 nm）[S3]を入れると、$2\pi/a$ は約11.57 nm⁻¹ になる（本サイトで計算）。

$X$ 点の波数は約11.57 nm⁻¹、$L$ 点は約10.02 nm⁻¹ である（本サイトで計算）。伝導帯の底は、$X$ 点の約85％で、約9.84 nm⁻¹ になる（本サイトで計算。約85％は出典の記述で、概数である）。

## 理解度チェック

### 問1
シリコンのような面心立方の結晶の逆格子は、どの格子か。

1. 単純立方格子
2. 体心立方格子
3. 面心立方格子
4. 六方格子

答え：2
解説：面心立方の結晶の逆格子は、体心立方である。逆格子の基本の領域が、ブリルアンゾーンになる。

### 問2
シリコンの伝導帯の底は、波数のどこにあるか。

1. Γ点
2. L点
3. Γ点からX点に向かう方向の、X点の手前（約85％の位置）
4. X点より外側

答え：3
解説：伝導帯の底は、Γ点ではなく、〈100〉方向でX点の約85％の位置にある。同じ谷が6個ある。
