---
title: 点欠陥：温度で決まる、結晶の中の空孔の数
field: materials-physics
description: 結晶から原子が1個抜けた空孔などの点欠陥が、温度に応じて平衡でどれだけ存在するかを、形成エネルギーを含む指数の式で読む。高温で数が桁で増えることを、形成エネルギー1 eVの例で確かめる。シリコンの数値が定まっていない点にも触れる。
applies_to:
- type: learn
  ref: crystal-defects
  folder: silicon
  note: 原子が抜けた欠陥が、温度で増える仕組みが読める。
- type: learn
  ref: crystal
  folder: silicon
  note: 完全に見える結晶にも、熱で一定の欠陥が必ず含まれることが分かる。
- type: learn
  ref: doping-and-anneal
  folder: process
  note: 高温の熱処理で、原子が動きやすくなる背景が読める。
basis: sources
draft: false
published_at: '2026-10-21'
ai_generated: true
sources:
- id: S1
  title: 2. Properties of Point Defects
  publisher: キール大学（Föll ほか、Defects in Crystals）
  kind: web
  url: https://www.tf.uni-kiel.de/matwis/amat/def_en/kap_2/backbone/r2_1_1.html
  accessed_on: '2026-10-21'
- id: S2
  title: 2.3. Point Defects in Semiconductors like Silicon
  publisher: キール大学（Föll ほか、Defects in Crystals）
  kind: web
  url: https://www.tf.uni-kiel.de/matwis/amat/def_en/kap_2/backbone/r2_3_1.html
  accessed_on: '2026-10-21'
- id: S3
  title: 'CODATA Recommended Values of the Fundamental Physical Constants: 2018（NIST SP 961）'
  publisher: 米国国立標準技術研究所（NIST）
  kind: government
  url: https://physics.nist.gov/cuu/pdf/wall_2018.pdf
  accessed_on: '2026-10-21'
---

## 式

$$c_V = \exp\left(\frac{S_F}{k}\right)\exp\left(-\frac{H_F}{kT}\right)$$

$c_V$ は、結晶の中で原子の席のうち空孔になっている割合である。空孔は、原子が1個抜けて空いた席で、点欠陥の一種である。$H_F$ は空孔を1個作るのに必要なエネルギー（形成エンタルピー）、$S_F$ は形成エントロピー、$k$ はボルツマン定数、$T$ は絶対温度である[S1]。

$S_F$ は、空孔の周りで原子の振動が変わることによる項である。この項は、数を一定の倍数だけ変え、温度による変わり方は、第2の指数が決める。

## 式のどこを見るか

見るのは、第2の指数 $\exp(-H_F/kT)$ である。形はアレニウスの式と同じで、$H_F$ が壁の高さの役目をする。温度が上がると、空孔の割合は指数の形で増える。

この式は、結晶が温度に応じた平衡の状態に達したときの割合を表す。空孔は、結晶をどれだけ丁寧に作っても、0にはならない[S2]。温度があるかぎり、熱で一定の数の欠陥が含まれる。

$H_F$ が大きい欠陥ほど、作りにくく、割合は小さい。また、同じ $H_F$ でも、温度が低いと割合は桁違いに小さくなる。

シリコンでは、空孔のほかに、原子が席の間に入り込んだ自己格子間原子も考える必要がある[S2]。二つの数は、互いに結びついている[S2]。

ただし、シリコンの点欠陥の $H_F$ や濃度について、広く認められた確かな数値は、まだ得られていない[S2]。このため、本ページの数値例は、シリコンではなく、数値が示されている単純な金属の値を例に、式の読み方を確かめる。

## 数値例

単純な金属の空孔の形成エンタルピーは、およそ1 eV とされる[S1]。ここでは、$S_F=0$ と置き、$H_F=1$ eV として、式の読み方だけを確かめる。ボルツマン定数は $8.617\times10^{-5}$ eV/K である[S3]。

割合 $c_V$ は、300 K（約27℃）で約 $1.6\times10^{-17}$、1,000 K（約727℃）で約 $9.1\times10^{-6}$、1,500 K（約1,227℃）で約 $4.4\times10^{-4}$ になる（本サイトで計算）。300 K から 1,000 K で、約12桁増える。

融点の近くの金属では、空孔の割合は $10^{-4}$ から $10^{-3}$ とされる[S1]。1,500 K の計算結果は、この範囲に近い。

この例は、$H_F$ や $S_F$ を仮に置いた計算である。実際の金属や、シリコンの空孔の数を表すものではない。

## 理解度チェック

### 問1
温度を上げると、結晶の中の空孔の割合はどうなるか。

1. 変わらない
2. 指数関数の形で増える
3. 直線で増える
4. 減る

答え：2
解説：割合は exp(−HF/kT) に比例するため、温度とともに指数関数の形で増える。

### 問2
形成エンタルピー HF が大きい欠陥は、同じ温度で割合がどうなるか。

1. 小さい
2. 大きい
3. 同じである
4. 温度によって逆になる

答え：1
解説：HF は指数の中の壁の高さにあたる。大きいほど作りにくく、割合は小さくなる。
