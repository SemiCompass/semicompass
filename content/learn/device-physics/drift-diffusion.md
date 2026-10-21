---
title: ドリフトと拡散：キャリアが動く二つの理由
field: device-physics
description: キャリアの電流が、電界によるドリフトと、濃度の差による拡散の二つで決まることを、式から読む。移動度と拡散係数がアインシュタインの関係で結ばれることを、シリコンの電子と正孔の値で確かめる。
applies_to:
- type: learn
  ref: carrier-motion
  folder: basics
  note: キャリアが動く二つの仕組みを、数式で確かめられる。
- type: learn
  ref: electricity-basics
  folder: basics
  note: 電流密度や導電率の意味を、キャリアの側から読める。
- type: learn
  ref: pn-junction
  folder: basics
  note: pn接合の電流が、拡散で決まる理由が読める。
basis: sources
draft: false
published_at: '2026-10-21'
ai_generated: true
sources:
- id: S1
  title: Semiconductor Chapter 2 スライド（キャリアの輸送）
  publisher: Tishk International University（物理学科）
  kind: web
  url: https://education.tiu.edu.iq/physics/wp-content/uploads/2018/10/semi-ch2-slides.pdf
  accessed_on: '2026-10-21'
- id: S2
  title: 'CODATA Recommended Values of the Fundamental Physical Constants: 2018（NIST SP 961）'
  publisher: 米国国立標準技術研究所（NIST）
  kind: government
  url: https://physics.nist.gov/cuu/pdf/wall_2018.pdf
  accessed_on: '2026-10-21'
---

## 式

$$J = q\,n\,\mu_n E + q\,D_n \frac{dn}{dx}$$

$J$ は電子による電流密度、$q$ は電気素量、$n$ は電子の濃度、$E$ は電界、$x$ は位置である[S1]。$\mu_n$ は電子の移動度で、電界1の単位あたりの速さの比例定数である。$D_n$ は拡散係数である。

第1項がドリフト（電界で動く電流）、第2項が拡散（濃度の高いほうから低いほうへ動く電流）である。

移動度と拡散係数は、アインシュタインの関係で結ばれる[S1]。

$$D_n = \frac{kT}{q}\,\mu_n$$

## 式のどこを見るか

見るのは、電流が二つの項の和であることである。電界がなければ第1項は0になり、濃度が一様なら第2項が0になる。pn接合では、濃度の差が大きいため、拡散の項が大きい。

ドリフトの速さは、$v=\mu E$ である[S1]。移動度が大きいほど、同じ電界で速く動く。電界が強くなると、速さは一定の値に近づき、この比例は成り立たなくなる[S1]。

アインシュタインの関係は、移動度が大きい材料は、拡散も速いことを示す。比例定数 $kT/q$ は熱電圧で、熱のエネルギーを電圧に直した量である。

導電率は、$\sigma=q\,n\,\mu_n+q\,p\,\mu_p$ で、その逆数が抵抗率である[S1]。電子と正孔の両方が、電流に寄与する。

## 数値例

300 Kの熱電圧は、ボルツマン定数と電気素量[S2]から、約25.9 mV である（本サイトで計算）。

シリコンの移動度は、電子が1,400 cm$^2$/(V·s)、正孔が470 cm$^2$/(V·s) である[S1]。アインシュタインの関係から、拡散係数は、電子が約36 cm$^2$/s、正孔が約12 cm$^2$/s になる（本サイトで計算）。

電界が $10^3$ V/cm のとき、電子のドリフトの速さは $1.4\times10^6$ cm/s である[S1]。1 μm（$10^{-4}$ cm）進むのにかかる時間は約71 ps（ピコ秒）である（本サイトで計算）。

電子の濃度が $10^{16}$ cm$^{-3}$ のとき、導電率は約2.2 S/cm、抵抗率は約0.45 Ω·cm である。正孔なら約0.75 S/cm、約1.3 Ω·cm である（本サイトで計算）。ただし、移動度は不純物の濃度でも変わるため、この計算は、上の移動度の値をそのまま使った目安である。

## 理解度チェック

### 問1
移動度が大きい材料では、同じ電界で、キャリアの速さはどうなるか。

1. 遅くなる
2. 速くなる
3. 変わらない
4. 電界の向きと逆に動く

答え：2
解説：ドリフトの速さは v = μE である。移動度 μ が大きいほど、同じ電界 E で速く動く。

### 問2
拡散係数と移動度を結ぶアインシュタインの関係の、比例定数はどれか。

1. 熱電圧 kT/q
2. 光の速さ
3. バンドギャップ
4. 電界

答え：1
解説：D = (kT/q)μ である。比例定数 kT/q は熱電圧で、300 Kで約25.9 mV である。
