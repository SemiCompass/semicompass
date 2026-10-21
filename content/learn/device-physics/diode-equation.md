---
title: ダイオードの電流式：電圧0.06 Vで電流が10倍になる
field: device-physics
description: pn接合ダイオードの電流を、電圧の指数で表すショックレーの式から、順方向では電圧が約60 mV増えるごとに電流が10倍になり、逆方向では飽和電流の大きさで頭打ちになることを読む。実際のダイオードの測定例で、理想の式とのずれも確かめる。
applies_to:
- type: learn
  ref: pn-junction
  folder: basics
  note: pn接合が、一方向にだけ電流を流す性質を、式で読める。
- type: learn
  ref: circuit-elements
  folder: basics
  note: ダイオードの電圧と電流の関係が、指数の形であることが分かる。
- type: learn
  ref: diode
  folder: power
  note: パワーダイオードで、順方向の電圧が決まる仕組みが読める。
basis: sources
draft: false
published_at: '2026-10-21'
ai_generated: true
sources:
- id: S1
  title: 'Measurements and analysis of current-voltage characteristic of a pn diode for an undergraduate physics laboratory（arXiv:1608.05638）'
  publisher: arXiv
  kind: web
  url: https://arxiv.org/pdf/1608.05638
  accessed_on: '2026-10-21'
- id: S2
  title: 'CODATA Recommended Values of the Fundamental Physical Constants: 2018（NIST SP 961）'
  publisher: 米国国立標準技術研究所（NIST）
  kind: government
  url: https://physics.nist.gov/cuu/pdf/wall_2018.pdf
  accessed_on: '2026-10-21'
---

## 式

$$I = I_S\left[\exp\left(\frac{V}{n V_T}\right) - 1\right]$$

$I$ はダイオードを流れる電流、$V$ は両端にかける電圧である[S1]。$I_S$ は飽和電流で、ダイオードの作りで決まる[S1]。$n$ は理想係数で、理想的なpn接合では1、実際のダイオードでは1より大きい[S1]。$V_T=kT/q$ は熱電圧で、室温で約25.8 mV である[S1]。

## 式のどこを見るか

見るのは、指数の中の $V/(nV_T)$ である。$V$ が $V_T$ の数倍以上の順方向では、$-1$ が無視でき、電流は $I_S\exp(V/nV_T)$ にほぼ比例する。電圧が少し増えるだけで、電流は桁で変わる。

電流を10倍にするのに必要な電圧の増加は、$nV_T\ln 10$ である。$n=1$ なら約60 mV で、$n$ が大きいほど、より大きな電圧が要る。

逆方向（$V$ が負で、絶対値が $V_T$ の数倍以上）では、指数の項が0に近づき、$I\approx -I_S$ になる。電流は、飽和電流の大きさで頭打ちになる。逆向きには、ほとんど電流が流れない。

$I_S$ は、温度や材料で変わる。「真性キャリア濃度と温度」のページで見たとおり、熱で生まれるキャリアは温度で増えるため、逆方向のリークは温度とともに増える。

式は、順方向で、ある電圧を境に電流が急に流れ始める振る舞いを、すでに表している。

## 数値例

300 Kの熱電圧は、ボルツマン定数と電気素量[S2]から、約25.9 mV になる（本サイトで計算）。$n=1$ のとき、電流が10倍になる電圧の増加は約59.5 mV（$V_T\ln10$）である（本サイトで計算）。

$V=0.6$ V では、$I/I_S=\exp(0.6/0.0259)$ から約 $1.2\times10^{10}$ 倍になる。0.1 V 増やして0.7 V にすると約 $5.7\times10^{11}$ 倍で、約48倍になる（本サイトで計算）。

実際のダイオードの測定例では、47.8℃で、飽和電流 $I_S$ が約10.5 nA、理想係数 $n$ が約1.79 と報告されている[S1]。この値を式に入れると、0.3 V で約4.5 μA、0.5 V で約0.26 mA になる（本サイトで計算）。この場合、電流が10倍になる電圧の増加は、$n V_T\ln10$ から約114 mV で、300 Kの理想（約60 mV）の約1.9倍である（本サイトで計算）。

## 理解度チェック

### 問1
理想的なpn接合（n = 1）の順方向で、電流を10倍にするには、室温でおよそ何 mV 電圧を上げればよいか。

1. 約6 mV
2. 約60 mV
3. 約600 mV
4. 約6 V

答え：2
解説：電流は exp(V/VT) に比例する。10倍にする電圧の増加は VT ln10 で、室温では約60 mV である。

### 問2
十分に大きな逆方向の電圧をかけたとき、電流はおよそいくつになるか。

1. 電圧に比例して増える
2. 飽和電流の大きさで頭打ちになる
3. 0 になる
4. 順方向と同じ大きさになる

答え：2
解説：逆方向では、指数の項が0に近づき、I はほぼ −IS になる。電流は IS の大きさで頭打ちになる。
