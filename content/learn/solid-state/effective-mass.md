---
title: 有効質量と状態密度：バンドの曲がりが、電子の入れる席の数を決める
field: solid-state
description: 結晶の中の電子が、電界に対して軽く動くか重く動くかを表す有効質量が、バンドの曲がり具合で決まることを式から読む。有効質量が実効状態密度に3/2乗で効くことを、シリコンとヒ化ガリウムの値で確かめる。
applies_to:
- type: learn
  ref: energy-band
  folder: basics
  note: 帯の形が、電子の動きやすさと席の数を決めることが読める。
- type: learn
  ref: electrons-and-holes
  folder: basics
  note: 電子と正孔の濃度を決める席の数が、材料でどう違うかが分かる。
- type: learn
  ref: compound
  folder: basics
  note: ヒ化ガリウムで電子が速く動ける理由を、有効質量で説明できる。
basis: sources
draft: false
published_at: '2026-10-21'
ai_generated: true
sources:
- id: S1
  title: Semiconductor Physics Lectures（有効質量、実効状態密度）
  publisher: ペルージャ大学（検出器の講義資料）
  kind: web
  url: https://www.fisgeo.unipg.it/~fiandrin/didattica_fisica/rivelatori1617/bibliografia/SemiconductorPhysics_Lectures.pdf
  accessed_on: '2026-10-21'
- id: S2
  title: ECE 340 Lecture 8（有効質量と実効状態密度の表）
  publisher: イリノイ大学アーバナ・シャンペーン校
  kind: web
  url: https://ursemiconductors.web.illinois.edu/ECE340/Lecture08.pdf
  accessed_on: '2026-10-21'
- id: S3
  title: Effective mass in semiconductors
  publisher: ミッドスウェーデン大学
  kind: web
  url: https://apachepersonal.miun.se/~gorthu/halvledare/Effective%20mass%20in%20semiconductors.htm
  accessed_on: '2026-10-21'
- id: S4
  title: 'CODATA Recommended Values of the Fundamental Physical Constants: 2018（NIST SP 961）'
  publisher: 米国国立標準技術研究所（NIST）
  kind: government
  url: https://physics.nist.gov/cuu/pdf/wall_2018.pdf
  accessed_on: '2026-10-21'
---

## 式

$$m^* = \frac{\hbar^2}{d^2E/dk^2}$$

$m^*$ は有効質量、$\hbar$ はプランク定数を $2\pi$ で割った量、$E$ は電子のエネルギー、$k$ は結晶の中での電子の波数（運動量に比例する量）である[S1]。有効質量は、電子が結晶の中で電界を受けたとき、どれだけ加速されやすいかを表す。

有効質量は、実効状態密度にも入る[S1]。

$$N_c = 2\left(\frac{2\pi m^* kT}{h^2}\right)^{3/2}$$

$N_c$ は伝導帯の実効状態密度で、電子が入れる席の数の目安である。正孔の側の $N_v$ にも、同じ形の式が使われる[S1]。

## 式のどこを見るか

最初に見るのは、分母の $d^2E/dk^2$ である。これは、バンドの曲がり具合を表す。曲がりが急なバンドほど、有効質量は小さい。平らなバンドほど、有効質量は大きい[S1]。有効質量が小さい電子は、同じ電界で、大きく加速される。

次に見るのは、$N_c$ の中の $m^{*\,3/2}$ である。有効質量が大きいほど、$N_c$ は大きくなる[S1]。有効質量が4倍になれば、$N_c$ は8倍になる。バンドが平らなほど、同じエネルギーの範囲に、電子が入れる席が多い。

$N_c$ は、温度の $3/2$ 乗にも比例する。温度が上がるほど、席が増える。

シリコンの伝導帯の底は、結晶の中の6か所にある。そのため、状態密度の有効質量は、1か所分の質量から、谷の数を考えて求める[S3]。

## 数値例

シリコンの電子の状態密度の有効質量は、真空中の電子の質量 $m_0$ の1.08倍、ヒ化ガリウム（GaAs）は0.067倍である[S2]。$m^*$ が約16倍も違う。

300 Kの $N_c$ は、シリコンで $2.82\times10^{19}$ cm$^{-3}$、GaAsで $4.37\times10^{17}$ cm$^{-3}$ である[S2]。式で計算し直すと、プランク定数、ボルツマン定数と電子の質量[S4]から、それぞれ約 $2.82\times10^{19}$、$4.35\times10^{17}$ cm$^{-3}$ になり、表の値とほぼ一致する（本サイトで計算）。質量が約16倍違うと、$N_c$ は約65倍違う。

前のページ「フェルミ分布」の式で、電子の濃度を $10^{17}$ cm$^{-3}$ にするのに必要な $E_C-E_F$ を比べる。$kT\ln(N_c/n)$ から、シリコンは約0.146 eV、GaAsは約0.038 eV である（本サイトで計算）。GaAsは席が少ないため、少ない電子で、フェルミ準位が伝導帯に近づく。

温度が300 Kから400 K に上がると、$N_c$ は約1.54倍になる（本サイトで計算）。

## 理解度チェック

### 問1
バンドの曲がりが急なほど、有効質量はどうなるか。

1. 大きくなる
2. 小さくなる
3. 変わらない
4. 負になる

答え：2
解説：有効質量は ħ² を d²E/dk² で割った値である。曲がりが急（d²E/dk² が大きい）ほど、有効質量は小さい。

### 問2
有効質量が4倍になると、実効状態密度 Nc は何倍になるか。

1. 2倍
2. 4倍
3. 8倍
4. 16倍

答え：3
解説：Nc は有効質量の3/2乗に比例する。4の3/2乗は8なので、Nc は8倍になる。
