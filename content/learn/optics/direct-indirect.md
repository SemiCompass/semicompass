---
title: 直接遷移と間接遷移：光を出せる材料と出せない材料
field: optics
description: 電子と正孔が結びついて光を出すとき、運動量をそろえる必要がある。バンドの底が同じ位置にある直接遷移型と、ずれている間接遷移型で、光の出やすさが約1,000倍違うことを読む。シリコンとヒ化ガリウムで、出せる波長も確かめる。
applies_to:
- type: learn
  ref: optoelectronics
  folder: devices
  note: LEDやレーザーに、シリコン以外の材料が使われる理由が読める。
- type: learn
  ref: compound
  folder: basics
  note: 化合物半導体が光の部品に使われる理由を、バンドの形で説明できる。
- type: learn
  ref: energy-band
  folder: basics
  note: バンドギャップの値のほかに、バンドの形が光の出やすさを決めることが分かる。
basis: sources
draft: true
published_at: '2026-10-21'
ai_generated: true
sources:
- id: S1
  title: Direct and indirect band gaps
  publisher: Wikipedia
  kind: web
  url: https://en.wikipedia.org/wiki/Direct_and_indirect_band_gaps
  accessed_on: '2026-10-21'
- id: S2
  title: Light Emission（Integrated Photonic Devices 講義資料）
  publisher: 国立清華大学（M.-C. Lee）
  kind: web
  url: https://www.ee.nthu.edu.tw/mclee/Lecture/Integrated%20Photonic%20Devices/Light%20Emission.pdf
  accessed_on: '2026-10-21'
- id: S3
  title: ワイドバンドギャップ半導体とは
  publisher: 東芝デバイス＆ストレージ株式会社
  kind: web
  url: https://toshiba.semicon-storage.com/jp/semiconductor/knowledge/faq/diode_sic-sbd/sic-sbd001.html
  accessed_on: '2026-10-21'
- id: S4
  title: 'CODATA Recommended Values of the Fundamental Physical Constants: 2018（NIST SP 961）'
  publisher: 米国国立標準技術研究所（NIST）
  kind: government
  url: https://physics.nist.gov/cuu/pdf/wall_2018.pdf
  accessed_on: '2026-10-21'
---

## 式

$$h\nu \approx E_g \quad（直接遷移）$$

$$h\nu \approx E_g \pm E_{ph} \quad（間接遷移）$$

$h\nu$ は光の粒（光子）1個のエネルギー、$E_g$ はバンドギャップである。$E_{ph}$ は、結晶の原子の振動の粒（フォノン）が持つエネルギーで、間接遷移では、このフォノンが加わる。

光を出すときは、電子が伝導帯から価電子帯に落ちて、正孔と結びつく。このとき、電子の運動量が保たれる必要がある。

## 式のどこを見るか

見るのは、フォノンの有無である。光子は、バンドギャップ付近のエネルギーでは、運動量がほぼ0である[S1]。伝導帯の底と価電子帯の頂上が同じ運動量の位置にあれば（直接遷移）、運動量を変えずに、光だけを出して結びつける[S1]。

二つの位置がずれていれば（間接遷移）、光子は運動量を渡せない。フォノンが差を埋めたときだけ、光を出して結びつける[S1]。フォノンが関わる段階が入るため、光を出す過程は、直接遷移より大幅に遅くなる[S1]。

結果として、間接遷移の材料では、電子と正孔が光を出さずに、結晶の振動などで熱になって失われる割合が増える[S2]。

発光ダイオード（LED）や半導体レーザーが、ほとんど直接遷移の材料で作られるのは、この違いによる[S1]。

式の $E_g$ から、出る光の波長の目安も読める。$\lambda\,[\mathrm{nm}] \approx 1240 / E_g\,[\mathrm{eV}]$ である。

## 数値例

結晶のシリコンとゲルマニウムは、間接遷移の材料である。ヒ化ガリウム（GaAs）は、直接遷移の材料である[S1]。

発光の効率の目安として、直接遷移の材料では約1、間接遷移の材料では約0.001とされる[S2]。約1,000倍の違いである。

バンドギャップは、シリコンが1.12 eV、GaAsが1.43 eV である[S3]。$hc$ は約1,240 eV·nm（プランク定数と光の速さは NIST の値[S4]から計算）なので、出せる光の波長の目安は、シリコンで約1,107 nm、GaAsで約867 nm になる（本サイトで計算）。どちらも近赤外である。

シリコンはバンドギャップから見て近赤外の光なら出せそうに見えるが、間接遷移のため、効率が桁違いに低い。光を出す部品に、シリコンではなくGaAsなどの化合物半導体が使われる理由は、ここにある。

## 理解度チェック

### 問1
間接遷移の材料で、光を出して電子と正孔が結びつくとき、運動量の差を埋めるのは何か。

1. 光子
2. フォノン
3. 不純物の原子
4. 電極

答え：2
解説：光子の運動量はほぼ0なので、差を埋められない。結晶の振動の粒であるフォノンが関わる必要があり、そのため光を出す過程が遅くなる。

### 問2
LEDやレーザーに、ほとんど直接遷移の材料が使われるのはなぜか。

1. 光を出す効率が高いから
2. バンドギャップが必ず大きいから
3. 光を吸収しないから
4. 電気を通さないから

答え：1
解説：直接遷移では、運動量を保ったまま光を出して結びつけるため、効率が高い。間接遷移とは、約1,000倍の違いがあるとされる。
