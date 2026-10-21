---
title: 吸収係数と侵入長：光はシリコンの中をどこまで進むか
field: optics
description: 光が材料の中で弱まる様子を表す吸収係数の式から、光が1/eに弱まる深さである侵入長を読む。シリコンで波長が長いほど深くまで届くことを、400 nmから1,100 nmの値で確かめ、10 μmの層でどれだけ吸収されるかを見積もる。
applies_to:
- type: learn
  ref: image-sensor
  folder: devices
  note: 色によって光が届く深さが違うことが、センサーの層の設計の前提になる。
- type: learn
  ref: optoelectronics
  folder: devices
  note: 受光の部品で、必要な厚さを見積もる考え方が読める。
- type: learn
  ref: energy-band
  folder: basics
  note: バンドギャップより長い波長で、吸収が急に弱まる理由を数値で確かめられる。
basis: sources
draft: false
published_at: '2026-10-21'
ai_generated: true
sources:
- id: S1
  title: Optical Properties of Silicon
  publisher: PVEducation（C. Honsberg、S. Bowden）
  kind: web
  url: https://www.pveducation.org/pvcdrom/materials/optical-properties-of-silicon
  accessed_on: '2026-10-21'
- id: S2
  title: Absorption Coefficient
  publisher: PVEducation（C. Honsberg、S. Bowden）
  kind: web
  url: https://www.pveducation.org/pvcdrom/pn-junctions/absorption-coefficient
  accessed_on: '2026-10-21'
- id: S3
  title: Absorption Depth
  publisher: PVEducation（C. Honsberg、S. Bowden）
  kind: web
  url: https://pveducation.org/es/fotovoltaica/absorption-depth
  accessed_on: '2026-10-21'
---

## 式

$$I(x) = I_0 \exp(-\alpha x)$$

$I_0$ は表面での光の強さ、$I(x)$ は表面から深さ $x$ に届いた光の強さである。$\alpha$ は吸収係数で、材料と波長で決まり、単位は cm$^{-1}$ を使う[S2]。光は、深さとともに指数関数の形で弱まる。

光が表面の約36%（$1/e$）に弱まる深さを、侵入長と呼ぶ[S3]。

$$\delta = \frac{1}{\alpha}$$

吸収係数は、光の波長 $\lambda$ と、材料の消衰係数 $k$ から $\alpha = 4\pi k/\lambda$ と表せる[S2]。

## 式のどこを見るか

見るのは、指数の中の $\alpha x$ である。$\alpha$ が大きいほど、浅いところで光が吸収される。侵入長 $1/\alpha$ は、その深さの目安になる。

半導体の $\alpha$ は、波長で桁違いに変わる。バンドギャップより光子のエネルギーが小さい光は、価電子帯の電子を持ち上げられないので、吸収されにくい[S2]。バンドギャップの付近では、光に反応できる電子が限られるため、吸収は弱い。光子のエネルギーが大きくなるほど、反応できる電子が増え、吸収は強まる[S2]。

したがって、波長が短いほど表面の近くで吸収され、波長が長いほど深くまで届く。

層の厚さ $d$ で吸収される割合は、$1-\exp(-\alpha d)$ で求められる。光を電気に変える部品では、必要な厚さがこの式で見積もれる。

## 数値例

300 Kのシリコンの吸収係数は、400 nmで $9.52\times10^{4}$ cm$^{-1}$、600 nmで $4.14\times10^{3}$ cm$^{-1}$、800 nmで $8.5\times10^{2}$ cm$^{-1}$、1,000 nmで $6.4\times10^{1}$ cm$^{-1}$、1,100 nmで 3.5 cm$^{-1}$ である[S1]。

侵入長 $1/\alpha$ は、400 nmで約0.11 μm、600 nmで約2.4 μm、800 nmで約12 μm、900 nmで約33 μm、1,000 nmで約160 μm、1,100 nmで約2.9 mm になる（本サイトで計算）。波長が2.5倍になるだけで、侵入長は4桁以上長くなる。

厚さ10 μmの層で吸収される割合は、600 nmで約98%、800 nmで約57%、900 nmで約26%、1,000 nmで約6%である（本サイトで計算）。波長の短い光は薄い層でほぼ吸収され、波長の長い光は、10 μmでは大半が通り抜ける。

## 理解度チェック

### 問1
シリコンで、吸収係数が大きい光は、どう進むか。

1. 深くまで届く
2. 表面の近くで吸収される
3. 吸収されずに通り抜ける
4. 波長によらず、同じ深さまで届く

答え：2
解説：侵入長は 1/α である。α が大きいほど侵入長が短く、表面の近くで吸収される。

### 問2
シリコンに波長400 nmの光と1,000 nmの光を当てたとき、深くまで届くのはどちらか。

1. 400 nm
2. 1,000 nm
3. どちらも同じ
4. どちらも表面で反射される

答え：2
解説：400 nm の侵入長は約0.11 μm、1,000 nm は約160 μm である。波長が長いほど、深くまで届く。
