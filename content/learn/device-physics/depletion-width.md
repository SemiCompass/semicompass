---
title: 空乏層と電界：電圧で広がる幅と、耐圧の目安
field: device-physics
description: pn接合の空乏層の幅が、不純物の濃度と電圧でどう決まるかを式から読む。逆方向の電圧で幅が広がり、電界の最大値も増える。シリコンの例で幅と電界を求め、絶縁破壊電界から耐圧の目安を見積もる。
applies_to:
- type: learn
  ref: pn-junction
  folder: basics
  note: 空乏層ができる理由と、その幅の決まり方が読める。
- type: learn
  ref: high-voltage
  folder: power
  note: 高い電圧に耐えるために、濃度と厚さをどう選ぶかの背景が読める。
- type: learn
  ref: diode
  folder: power
  note: 逆方向の電圧に耐える仕組みが、空乏層の幅で説明できる。
basis: sources
draft: false
published_at: '2026-10-21'
ai_generated: true
sources:
- id: S1
  title: Abrupt pn junctions in the depletion approximation
  publisher: グラーツ工科大学（W. Hadley）
  kind: web
  url: https://lampz.tugraz.at/~hadley/psd/L6/abrupt.html
  accessed_on: '2026-10-21'
- id: S2
  title: General Characteristics of Silicon
  publisher: CERN（半導体検出器の資料）
  kind: web
  url: https://ssd-rd.web.cern.ch/Data/Si-General.html
  accessed_on: '2026-10-21'
- id: S3
  title: 'CODATA Recommended Values of the Fundamental Physical Constants: 2018（NIST SP 961）'
  publisher: 米国国立標準技術研究所（NIST）
  kind: government
  url: https://physics.nist.gov/cuu/pdf/wall_2018.pdf
  accessed_on: '2026-10-21'
- id: S4
  title: ワイドバンドギャップ半導体とは
  publisher: 東芝デバイス＆ストレージ株式会社
  kind: web
  url: https://toshiba.semicon-storage.com/jp/semiconductor/knowledge/faq/diode_sic-sbd/sic-sbd001.html
  accessed_on: '2026-10-21'
---

## 式

$$W = \sqrt{\frac{2\epsilon\,(N_A+N_D)\,(V_{bi}-V)}{q\,N_A N_D}}$$

$W$ は空乏層の全体の幅、$\epsilon$ は半導体の誘電率、$N_A$ と $N_D$ はアクセプタとドナーの濃度、$V_{bi}$ は内蔵電位、$V$ は外からかけた電圧（順方向を正）、$q$ は電気素量である[S1]。

空乏層の最大の電界は、n型の側の端までの幅 $x_n$ を使って、次のように表せる[S1]。

$$E_{max} = \frac{q\,N_D\,x_n}{\epsilon}$$

## 式のどこを見るか

見るのは、平方根の中の $V_{bi}-V$ である。逆方向の電圧をかけると $V$ が負になり、$V_{bi}-V$ が大きくなって、幅 $W$ が広がる。電圧が4倍になれば、幅は約2倍である。

濃度は、分母に入っている。濃度が高いほど、幅は狭い。濃度が低い側ほど、空乏層は深くまで広がる[S1]。

電界の最大値 $E_{max}$ も、逆方向の電圧とともに大きくなる。この電界が、材料の絶縁破壊電界に達すると、電流が急に流れ始める。そこまでの電圧が、耐圧の目安になる。

片側の濃度がもう片側よりずっと低いpn接合では、近似で、$E_{max}=\sqrt{2qN(V_{bi}-V)/\epsilon}$ となり、耐圧は $\epsilon E_c^2/(2qN)$ で見積もれる。ここで $N$ は濃度の低い側の濃度、$E_c$ は絶縁破壊電界である。濃度を下げるほど、耐圧は高くなる。

## 数値例

シリコンの比誘電率は11.9である[S2]。真空の誘電率と電気素量の値は、NISTの値[S3]を使う。

$N_A=N_D=10^{16}$ cm$^{-3}$、$V_{bi}=0.72$ V（「内蔵電位」のページの値）とする。電圧がかかっていないとき、空乏層の幅は約0.44 μm、$E_{max}$ は約 $3.3\times10^{4}$ V/cm である。逆方向に5 V かけると、幅は約1.2 μm、$E_{max}$ は約 $9.3\times10^{4}$ V/cm に増える（本サイトで計算）。

シリコンの絶縁破壊電界の目安は、$3.0\times10^{5}$ V/cm である[S4]。この値と、片側の濃度 $10^{16}$ cm$^{-3}$ の近似式から、耐圧の目安は約30 V になる。濃度を $10^{15}$ cm$^{-3}$ に下げると約300 V、$10^{17}$ cm$^{-3}$ に上げると約3 V である（本サイトで計算）。濃度が10分の1になると、耐圧は10倍になる。

絶縁破壊電界は、濃度などによっても変わるため、この耐圧は目安として読む。

## 理解度チェック

### 問1
pn接合に逆方向の電圧をかけると、空乏層の幅はどうなるか。

1. 狭くなる
2. 広くなる
3. 変わらない
4. 0 になる

答え：2
解説：幅は √(Vbi − V) に比例する。逆方向では V が負になり、Vbi − V が大きくなるため、幅が広がる。

### 問2
片側の濃度を10分の1にすると、耐圧の目安はどうなるか。

1. 10分の1になる
2. 変わらない
3. 10倍になる
4. 100倍になる

答え：3
解説：耐圧の目安は ε Ec²/(2qN) で、濃度 N に反比例する。濃度が10分の1になると、10倍になる。
