---
title: 真性キャリア濃度と温度：指数の中のEgとT
field: solid-state
description: 不純物を入れない半導体で熱によって生まれる電子と正孔の濃度（真性キャリア濃度）の式から、温度が上がるとリークが増える理由と、バンドギャップの大きい材料が高い温度で動ける理由を読む。シリコンの値で桁を確かめる。
applies_to:
- type: learn
  ref: electrons-and-holes
  folder: basics
  note: 熱で生まれる電子と正孔の数を、温度と材料から見積もれる。
- type: learn
  ref: power
  folder: devices
  note: 炭化ケイ素や窒化ガリウムが高い温度でも動ける理由が、指数の中の値で読める。
- type: learn
  ref: reliability-tests
  folder: test
  note: 高い温度でリークの電流が増える理由が、この濃度の温度変化で読める。
basis: sources
draft: true
published_at: '2026-10-17'
ai_generated: true
sources:
- id: S1
  title: Intrinsic Carrier Concentration
  publisher: PVEducation（C. Honsberg、S. Bowden）
  kind: web
  url: https://www.pveducation.org/pvcdrom/pn-junctions/intrinsic-carrier-concentration
  accessed_on: '2026-10-17'
- id: S2
  title: 半導体デバイス・プロセス工学（2017年版、Web掲載用の見本版）
  publisher: 広島大学（横山新）
  kind: web
  url: https://www.hiroshima-u.ac.jp/system/files/88561/%E5%8D%8A%E5%B0%8E%E4%BD%93%E3%83%87%E3%83%90%E3%83%97%E3%83%AD%E6%95%99%E7%A7%91%E6%9B%B8Web%E7%94%A8%E6%A8%AA%E5%B1%B12017%E5%89%8D%E5%8D%8A.pdf
  accessed_on: '2026-10-17'
- id: S3
  title: ワイドバンドギャップ半導体とは
  publisher: 東芝デバイス＆ストレージ株式会社
  kind: web
  url: https://toshiba.semicon-storage.com/jp/semiconductor/knowledge/faq/diode_sic-sbd/sic-sbd001.html
  accessed_on: '2026-10-17'
- id: S4
  title: 'CODATA Recommended Values of the Fundamental Physical Constants: 2018（NIST SP 961）'
  publisher: 米国国立標準技術研究所（NIST）
  kind: government
  url: https://physics.nist.gov/cuu/pdf/wall_2018.pdf
  accessed_on: '2026-10-17'
---

## 式

$$n_i = \sqrt{N_c N_v}\,\exp\left(-\frac{E_g}{2kT}\right)$$

$n_i$ は真性キャリア濃度で、不純物を入れない半導体の中で、熱によって伝導帯に上がった電子の濃度である。価電子帯には同じ数の正孔が残る。$N_c$ と $N_v$ は、伝導帯と価電子帯に電子と正孔が入れる席の数の目安（実効状態密度）である。$E_g$ はバンドギャップ、$k$ はボルツマン定数、$T$ は絶対温度である。

$N_c$ と $N_v$ は、それぞれ温度の1.5乗に比例する。まとめると、次の形になる。

$$n_i \propto T^{3/2}\exp\left(-\frac{E_g}{2kT}\right)$$

## 式のどこを見るか

見るのは、指数の中の $E_g/2kT$ である。$E_g$ が分子、$T$ が分母にある。指数の外の $T^{3/2}$ も温度で増えるが、指数の変化に比べるとゆるやかで、振る舞いをほぼ決めるのは指数のほうである。

分母に2があるのは、電子と正孔が対で生まれるためである。電子の濃度と正孔の濃度の積が $\exp(-E_g/kT)$ に比例し、$n_i$ はその平方根になる。

温度を上げると、指数の中の値が小さくなり、$n_i$ は桁で増える。不純物を入れた半導体でも、熱で生まれる電子と正孔は同じように増える。pn接合に逆向きの電圧をかけたときに流れる小さな電流（リークの電流）は、この熱で生まれるキャリアが元になる。そのため、温度が上がるとリークが増える。さらに温度が上がり、$n_i$ が不純物の濃度に近づくと、n型とp型の区別が薄れ、素子として働かなくなる。

$E_g$ が大きい材料では、同じ温度でも指数の中の値が大きく、$n_i$ は桁違いに小さい。バンドギャップの大きい炭化ケイ素や窒化ガリウムが、シリコンより高い温度で動ける理由の一つが、ここにある。

## 数値例

300 Kのシリコンの $n_i$ は $9.65\times10^{9}$ cm$^{-3}$ で、およそ $1\times10^{10}$ cm$^{-3}$ である[S1]。シリコンの原子は1 cm$^3$に $5.0\times10^{22}$ 個ある[S2]。熱で伝導帯に上がる電子は、原子およそ5兆個に1個という少なさである（本サイトで計算）。

温度の効き方は、PVEducationが示すシリコンの $n_i$ の近似式[S1]で確かめられる。この式で計算すると、300 K（約27℃）から400 K（約127℃）に上げたとき、$n_i$ は約560倍の $5.5\times10^{12}$ cm$^{-3}$ になる（本サイトで計算）。100 Kの差で、2桁以上増える。

材料の違いは、指数の部分だけで比べられる。バンドギャップをシリコン1.12 eV、炭化ケイ素（4H-SiC）3.26 eVとし[S3]、300 Kの $kT$ を約0.026 eV[S4]とする。$N_c$ と $N_v$ の違いを無視して指数の部分だけを比べると、炭化ケイ素の $n_i$ はシリコンの約 $10^{-18}$ 倍になる（本サイトで計算）。

## 理解度チェック

### 問1
真性キャリア濃度の式で、温度による変化をほぼ決めているのはどこか。

1. 指数の外の、温度の1.5乗の部分
2. 指数の中の、バンドギャップを2kTで割った部分
3. 式の前にある平方根の記号
4. 温度によらず、変化しない

答え：2
解説：温度の1.5乗も増えるが、指数の変化に比べるとゆるやかである。振る舞いをほぼ決めるのは、指数の中の Eg/2kT である。

### 問2
バンドギャップの大きい材料が、高い温度でも素子として働きやすい理由はどれか。

1. 熱で生まれる電子と正孔の濃度が、同じ温度で桁違いに小さいため
2. 原子の数が、シリコンより桁違いに多いため
3. 温度が上がると、バンドギャップが大きくなるため
4. 不純物を入れなくても、n型になるため

答え：1
解説：Eg が大きいと、指数の中の値が大きくなり、真性キャリア濃度は桁違いに小さくなる。温度を上げても、不純物の濃度に近づきにくい。
