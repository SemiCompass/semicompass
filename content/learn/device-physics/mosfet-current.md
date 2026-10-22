---
title: MOSFETの電流：ゲートの電圧の2乗で増え、下限は60 mV/桁
field: device-physics
description: MOSFETのドレイン電流が、ゲートの電圧としきい値の差の2乗で決まることを式から読む。しきい値より下では電流が指数で減り、室温で電圧が約60 mV下がるごとに10分の1になるという、原理の下限も確かめる。
applies_to:
- type: learn
  ref: mosfet
  folder: devices
  note: トランジスタの電流の大きさが、構造と電圧のどこで決まるかが読める。
- type: learn
  ref: digital-thinking
  folder: basics
  note: オンとオフの電流の差が、スイッチとして使える理由が分かる。
- type: learn
  ref: nanometer-scale
  folder: basics
  note: 微細化でゲートの電圧を下げにくい理由が読める。
basis: sources
draft: false
published_at: '2026-10-21'
ai_generated: true
sources:
- id: S1
  title: Lecture 4（MOS容量としきい値電圧、MOSFETの電流）
  publisher: カリフォルニア大学サンタバーバラ校（K. Banerjee）
  kind: web
  url: https://courses.ece.ucsb.edu/ECE225/225_S17Banerjee/Lectures/Lecture%204.pdf
  accessed_on: '2026-10-21'
- id: S2
  title: 6.012 Final Exam Formula Sheet
  publisher: MIT OpenCourseWare 6.012（Microelectronic Devices and Circuits）
  kind: web
  url: https://www.ocw.mit.edu/courses/6-012-microelectronic-devices-and-circuits-fall-2009/4e51bf077aaf59379bc1409f161dfa89_MIT6_012F09_final_formula.pdf
  accessed_on: '2026-10-21'
- id: S3
  title: 'Revised theoretical limit of subthreshold swing in field-effect transistors（arXiv:1811.09146）'
  publisher: arXiv
  kind: web
  url: https://arxiv.org/pdf/1811.09146
  accessed_on: '2026-10-21'
- id: S4
  title: 'CODATA Recommended Values of the Fundamental Physical Constants: 2018（NIST SP 961）'
  publisher: 米国国立標準技術研究所（NIST）
  kind: government
  url: https://physics.nist.gov/cuu/pdf/wall_2018.pdf
  accessed_on: '2026-10-21'
---

## 式

$$I_D = \frac{1}{2}\,\mu\,C_{ox}\,\frac{W}{L}\,(V_{GS}-V_T)^2$$

$I_D$ はドレイン電流、$\mu$ はチャネルの電子の移動度、$C_{ox}$ は酸化膜の単位面積あたりの容量である。$W$ はチャネルの幅、$L$ は長さ、$V_{GS}$ はゲートとソースの間の電圧、$V_T$ はしきい値電圧である。これは、ドレインの電圧が十分に高い飽和領域の式である[S1][S2]。

しきい値より下では、電流は指数で減る。ゲートの電圧を $V_{GS}$ から下げたとき、電流が10倍小さくなるのに必要な電圧 $S$ は、次の形で表せる[S3]。

$$S = \frac{kT}{q}\ln 10 \times m, \qquad m = 1 + \frac{C_{depl}}{C_{ox}}$$

$C_{depl}$ は空乏層の容量で、$m$ は1以上である[S3]。

## 式のどこを見るか

見るのは、$(V_{GS}-V_T)^2$ である。しきい値を超えた電圧が2倍になると、電流は4倍になる。電圧を上げるほど、電流は急に増える。

次に、$\mu\,C_{ox}\,W/L$ である。幅を広げるか、長さを縮めると、電流が増える。酸化膜を薄くして $C_{ox}$ を大きくしても、同じである。

トランジスタをスイッチに使うとき、オフのときの電流を、小さく抑えたい。しきい値より下の電流が、ゲートの電圧 $S$ ごとに10分の1になる。$S$ が小さいほど、短い電圧の変化でオフにできる。

$m$ は1より小さくならないため、$S$ には下限がある。$m=1$ のとき $S=(kT/q)\ln 10$ で、300 Kで約60 mV/桁になる[S3]。これはボルツマン限界と呼ばれ、通常のトランジスタの原理的な下限である[S3]。

## 数値例

ここでは、$t_{ox}=5$ nm、$W/L=10$、$\mu=400$ cm$^2$/(V·s) と仮定する。$C_{ox}$ は約 $6.9\times10^{-7}$ F/cm$^2$ である[S2]（本サイトで計算）。

$V_{GS}-V_T=1$ V のとき、$I_D=0.5\times400\times6.9\times10^{-7}\times10\times1$ から、約1.4 mA になる。$V_{GS}-V_T=0.5$ V なら約0.35 mA で、電圧を半分にすると、電流は4分の1になる（本サイトで計算）。

300 Kの熱電圧は、ボルツマン定数と電気素量[S4]から約25.9 mV である。$S=(kT/q)\ln 10$ は、約59.5 mV/桁になる（本サイトで計算）。オフの電流を5桁小さくするには、$m=1$ でも、約0.30 V のゲートの電圧の低下が必要である。

上の移動度、幅と長さ、酸化膜の厚さは、式の読み方を確かめるための仮定の値である。実際のトランジスタの値ではない。

## 理解度チェック

### 問1
MOSFETの飽和領域で、VGS − VT を2倍にすると、ドレイン電流はおよそ何倍になるか。

1. 2倍
2. 4倍
3. 8倍
4. 変わらない

答え：2
解説：電流は (VGS − VT) の2乗に比例する。2倍の2乗は4なので、電流は4倍になる。

### 問2
室温で、理想的なMOSFETのしきい値より下の電流を10分の1にするのに、必要なゲートの電圧の低下は、最小でおよそいくらか。

1. 約6 mV
2. 約60 mV
3. 約600 mV
4. 約6 V

答え：2
解説：下限は (kT/q) ln10 で、300 Kでは約60 mV/桁である。m が1より大きいと、これより大きくなる。
