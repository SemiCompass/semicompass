---
title: 屈折率と全反射：光をシリコンの中に閉じ込める条件
field: optics
description: 屈折率の違う二つの材料の境目で光がどう曲がるかを表すスネルの法則と、光が外に出られなくなる臨界角を読む。シリコンと酸化シリコンの屈折率の差で、光を閉じ込められる角度の範囲を、波長1,000 nmと600 nmで確かめる。
applies_to:
- type: learn
  ref: optical-communication
  folder: communication
  note: 光ファイバーや光の配線で、光が外に漏れずに進む条件が読める。
- type: learn
  ref: optoelectronics
  folder: devices
  note: 光を出す部品で、光が材料の中に閉じ込められて外に出にくい理由が分かる。
- type: learn
  ref: image-sensor
  folder: devices
  note: 受光の部品の表面で、光が反射される条件を読める。
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
  title: Temperature-dependent absolute refractive index measurements of synthetic fused silica
  publisher: arXiv（0805.0091）
  kind: web
  url: https://arxiv.org/pdf/0805.0091
  accessed_on: '2026-10-21'
- id: S3
  title: Lecture 23（光ファイバーの講義資料）
  publisher: リーハイ大学（Lehigh University）
  kind: web
  url: https://www.lehigh.edu/imi/teched/OPG/lecture23.pdf
  accessed_on: '2026-10-21'
---

## 式

$$n_1 \sin\theta_1 = n_2 \sin\theta_2$$

$n_1$ と $n_2$ は、境目の両側の材料の屈折率である。$\theta_1$ と $\theta_2$ は、光の進む向きと、境目に垂直な線との間の角である。これがスネルの法則である。

屈折率の大きい側から小さい側へ光が進むとき、$\theta_2$ が90°になる角度を臨界角と呼ぶ[S3]。

$$\sin\theta_c = \frac{n_2}{n_1} \quad (n_1 > n_2)$$

$\theta_1$ が $\theta_c$ 以上になると、光は境目を通り抜けられず、すべて跳ね返される。これが全反射である[S3]。

## 式のどこを見るか

見るのは、比 $n_2/n_1$ である。この比が小さいほど、臨界角は小さくなり、全反射が起こる角度の範囲が広がる。つまり、屈折率の差が大きいほど、光を閉じ込めやすい。

全反射が起こるのは、屈折率の大きい材料の側から、小さい材料の側へ向かう光だけである[S3]。反対向きの光では、起こらない。光ファイバーは、屈折率の大きい中心部（コア）を、小さい外側（クラッド）が囲み、全反射でコアの中に光を進める[S3]。

閉じ込められるのは、臨界角より斜めに当たる光に限られる。

## 数値例

波長1,000 nmで、シリコンの屈折率は3.570[S1]、石英ガラスは1.451である[S2]。石英ガラスの値を、酸化シリコンの屈折率の代わりに使って、シリコンの中から境目に向かう光の臨界角を計算すると、$\sin\theta_c = 1.451/3.570 \approx 0.406$ から、約24.0°になる（本サイトで計算）。

境目に垂直な線から24°より斜めに当たる光は、すべて跳ね返される。シリコンの屈折率が大きいため、この角度は小さく、多くの向きの光がシリコンの中に閉じ込められる。

波長600 nmでは、シリコンが3.939[S1]、石英ガラスが1.4585[S2]で、臨界角は約21.7°になる（本サイトで計算）。波長によって、屈折率が少し変わるため、臨界角も少し変わる。

石英ガラスの屈折率は、温度でも変わる。300 Kでは、波長1.0 μmで1.45086、1.5 μmで1.44507である[S2]。

## 理解度チェック

### 問1
光が全反射を起こすのは、どちらの向きの場合か。

1. 屈折率の小さい材料から、大きい材料へ進む場合
2. 屈折率の大きい材料から、小さい材料へ進む場合
3. 屈折率が等しい材料どうしの場合
4. どの向きでも起こる

答え：2
解説：臨界角は sinθc = n2/n1（n1 > n2）で決まる。屈折率の大きい側から小さい側へ進む光だけが、臨界角より斜めに当たると全反射する。

### 問2
二つの材料の屈折率の差が大きいほど、臨界角はどうなるか。

1. 大きくなる
2. 小さくなる
3. 変わらない
4. 90°になる

答え：2
解説：sinθc = n2/n1 なので、差が大きいと比が小さくなり、臨界角は小さくなる。全反射が起こる角度の範囲が広がる。
