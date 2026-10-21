---
title: フェルミ分布：電子の席の埋まり方と、フェルミ準位
field: solid-state
description: 電子がエネルギーの席をどんな確率で埋めるかを表すフェルミ分布の式から、フェルミ準位の意味と、伝導帯の電子の濃度が指数で決まることを読む。シリコンで、濃度を10倍にするとフェルミ準位が約60 meV動くことを確かめる。
applies_to:
- type: learn
  ref: energy-band
  folder: basics
  note: 帯の図の中で、フェルミ準位がどこにあるかの意味が読める。
- type: learn
  ref: electrons-and-holes
  folder: basics
  note: 電子と正孔の濃度を、フェルミ準位の位置から見積もれる。
- type: learn
  ref: pn-junction
  folder: basics
  note: n型とp型で、フェルミ準位の位置が違う理由が分かる。
basis: sources
draft: true
published_at: '2026-10-21'
ai_generated: true
sources:
- id: S1
  title: 6.720J Lecture 3（キャリアの統計）
  publisher: MIT OpenCourseWare 6.720J（ocw.iti.hr 掲載の講義資料）
  kind: web
  url: https://ocw.iti.hr/courses/electrical-engineering-and-computer-science/6-720j-integrated-microelectronic-devices-spring-2007/lecture-notes/lecture3.pdf
  accessed_on: '2026-10-21'
- id: S2
  title: 'CODATA Recommended Values of the Fundamental Physical Constants: 2018（NIST SP 961）'
  publisher: 米国国立標準技術研究所（NIST）
  kind: government
  url: https://physics.nist.gov/cuu/pdf/wall_2018.pdf
  accessed_on: '2026-10-21'
---

## 式

$$f(E) = \frac{1}{1 + \exp\left(\dfrac{E - E_F}{kT}\right)}$$

$f(E)$ は、エネルギー $E$ の席が電子で埋まっている確率である[S1]。$E_F$ はフェルミ準位、$k$ はボルツマン定数、$T$ は絶対温度である。$E=E_F$ のとき、$f=1/2$ になる。

伝導帯の底 $E_C$ が $E_F$ よりも $kT$ の何倍も上にあるとき、伝導帯の電子の濃度は、次の形で近似できる[S1]。

$$n \approx N_c \exp\left(-\frac{E_C - E_F}{kT}\right)$$

$N_c$ は伝導帯の実効状態密度で、電子が入れる席の数の目安である。

## 式のどこを見るか

見るのは、$(E - E_F)/kT$ である。$E$ が $E_F$ より高いほど、この値は大きくなり、席が埋まる確率は小さくなる。$E$ が $E_F$ より低ければ、確率は1に近づく。

$E$ が $E_F$ より $kT$ の数倍以上高い領域では、分母の1が小さくなり、式は指数の形に近づく。近似の式の $\exp$ は、この領域の式である[S1]。濃度が $N_c$ に比べてずっと小さいときに成り立つ[S1]。

近似の式から、濃度 $n$ と $E_C - E_F$ の関係は、指数と対数で結ばれる。濃度が10倍になるたび、$E_C - E_F$ は $kT\ln 10$ だけ縮む。ドーピングで電子を増やすことは、フェルミ準位を伝導帯に近づけることと、同じ意味である。

フェルミ準位は、電子が実際にいるエネルギーの席ではなく、確率が1/2になる基準の位置である。バンドギャップの中に、席がなくても置ける。

## 数値例

300 Kでは、ボルツマン定数 $8.617\times10^{-5}$ eV/K[S2]から、$kT$ は約0.0259 eV（25.9 meV）になる（本サイトで計算）。

$E-E_F=kT$ の席が埋まっている確率は約0.27、0.1 eV 高い席では約0.020、0.56 eV 高い席（シリコンのバンドギャップ1.12 eV の半分）では約 $4\times10^{-10}$ になる（本サイトで計算）。

シリコンの $N_c$ は300 Kで約 $2.9\times10^{19}$ cm$^{-3}$ である[S1]。電子の濃度を $10^{16}$ cm$^{-3}$ にするには、$E_C-E_F=kT\ln(N_c/n)$ から、約0.206 eV だけ、$E_F$ が伝導帯の底より下にあればよい。濃度を $10^{17}$ cm$^{-3}$ に10倍にすると約0.147 eV、$10^{18}$ cm$^{-3}$ では約0.087 eV になる（本サイトで計算）。10倍ごとに約60 meV（$kT\ln 10$）ずつ近づく。

## 理解度チェック

### 問1
エネルギー E がフェルミ準位 EF に等しい席が、電子で埋まっている確率はいくつか。

1. 0
2. 1/2
3. 1
4. 温度で決まり、一定ではない

答え：2
解説：E = EF のとき、指数の中が0になり、f = 1/(1+1) = 1/2 になる。

### 問2
300 Kのシリコンで、伝導帯の電子の濃度を10倍にすると、フェルミ準位はおよそどれだけ動くか。

1. 約6 meV 伝導帯に近づく
2. 約60 meV 伝導帯に近づく
3. 約600 meV 伝導帯に近づく
4. 動かない

答え：2
解説：濃度が10倍になると、EC − EF は kT ln10、つまり約60 meV 縮む。
