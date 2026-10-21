---
title: 気相成長の速度：温度で決まる領域と、供給で決まる領域
field: materials-physics
description: 気体の原料から結晶を成長させるとき、成長の速さが温度にどう依存するかを読む。低い温度では表面の反応で決まり、アレニウスの式に従う。高い温度では原料の供給で決まり、温度にほとんど依存しない。低温のシリコンのエピタキシーの実測値で確かめる。
applies_to:
- type: learn
  ref: epitaxial-growth
  folder: materials
  note: 成長の温度を選ぶときの、速さと欠陥の兼ね合いが読める。
- type: learn
  ref: deposition-methods
  folder: process
  note: 化学反応を使う成膜で、温度が速さを決める理由が分かる。
- type: learn
  ref: doping-and-anneal
  folder: process
  note: 低い温度で成長させる理由を、不純物の広がりの面から読める。
basis: sources
draft: false
published_at: '2026-10-21'
ai_generated: true
sources:
- id: S1
  title: Low-temperature silicon epitaxy by chemical vapor deposition using neopentasilane（Applied Physics Letters 92, 113506）
  publisher: Chung ほか（プリンストン大学の公開ページ）
  kind: web
  url: https://sturm.scholar.princeton.edu/document/553
  accessed_on: '2026-10-21'
- id: S2
  title: ELEG667 課題6（化学気相成長の速度）
  publisher: デラウェア大学（Kolodzey）
  kind: web
  url: https://www.eecis.udel.edu/~kolodzey/courses/ELEG667_016F05/667_016HmwkF05/667f05hw6.pdf
  accessed_on: '2026-10-21'
- id: S3
  title: 'CODATA Recommended Values of the Fundamental Physical Constants: 2018（NIST SP 961）'
  publisher: 米国国立標準技術研究所（NIST）
  kind: government
  url: https://physics.nist.gov/cuu/pdf/wall_2018.pdf
  accessed_on: '2026-10-21'
---

## 式

$$G = G_0 \exp\left(-\frac{E_a}{kT}\right)$$

$G$ は結晶の成長の速さ（単位時間に増える厚さ）である。$G_0$ は温度によらない定数、$E_a$ は表面の反応の活性化エネルギー、$k$ はボルツマン定数、$T$ は絶対温度である。この式は、成長が表面の反応で決まる領域で成り立つ[S2]。

## 式のどこを見るか

気相成長の速さを決める段階は、温度によって入れ替わる。原料の気体は、まず基板の表面まで運ばれ、次に表面で反応して結晶になる。二つの段階のうち、遅いほうが全体の速さを決める。

温度が低い領域では、表面の反応が遅い。このとき成長の速さは、上の式のとおり $\exp(-E_a/kT)$ に比例し、温度に敏感である[S2]。ここでは、温度の管理が成長の速さの管理になる。

温度が高い領域では、表面の反応は速く、原料が基板まで運ばれる速さが全体を決める。この領域の速さは、温度にほとんど依存しない[S1]。

式で見るのは、指数の中の $E_a/kT$ と、領域の切り替わりである。$\ln G$ を $1/T$ に対して描くと、反応で決まる領域は右下がりの直線になる。供給で決まる領域に入ると、直線が寝て、傾きが小さくなる。

シリコンの成長では、不純物が広がらないよう、低い温度が求められることがある[S1]。その場合は、反応で決まる領域で動かすことになり、温度の管理が重要になる。

## 数値例

低温のシリコンのエピタキシーで、原料にネオペンタシラン（Si₅H₁₂）を使い、分圧を20 mtorr、水素の圧力を6 torr とした実測値がある。成長の速さは、600℃で約54 nm/分、650℃で約130 nm/分、700℃で約215 nm/分である[S1]。この範囲は、表面の反応で決まる領域とされている[S1]。

600℃から700℃への100℃の上昇で、速さは約4倍になる。ボルツマン定数 $8.617\times10^{-5}$ eV/K[S3]を使い、この2点から $E_a$ を見積もると、約1.0 eV になる（本サイトで計算）。

600〜650℃の区間では約1.2 eV、650〜700℃では約0.8 eV となり、温度が高いほど傾きが小さくなる（本サイトで計算）。供給で決まる領域に近づくことと合致するが、この資料は活性化エネルギーの値を示していないため、約1.0 eV は目安として読む。

同じ600℃で、原料を変えると速さは大きく変わる。シランは約0.6 nm/分、ジシラン（Si₂H₆）は約8 nm/分で、ネオペンタシランは約54 nm/分である[S1]。

## 理解度チェック

### 問1
成長が表面の反応で決まる低温の領域で、温度を上げると成長の速さはどうなるか。

1. ほとんど変わらない
2. 指数関数の形で大きくなる
3. 小さくなる
4. 直線で小さくなる

答え：2
解説：この領域の速さは exp(−Ea/kT) に比例するため、温度とともに指数関数の形で大きくなる。

### 問2
原料の供給で成長の速さが決まる高温の領域では、温度を上げると成長の速さはどうなるか。

1. 指数関数の形で大きくなる
2. 0になる
3. ほとんど変わらない
4. 急に小さくなる

答え：3
解説：この領域では、原料が基板まで運ばれる速さが全体を決める。この速さは、温度にほとんど依存しない。
