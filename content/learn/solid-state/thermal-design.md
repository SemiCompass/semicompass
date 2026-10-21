---
title: 熱設計と接合温度：消費電力が温度に変わる式
field: solid-state
description: 半導体が消費する電力は熱になり、素子の内部の温度（接合温度）を上げる。熱抵抗を使った接合温度の式と、シリコンのチップ自体の熱抵抗の見積もりから、温度上昇を決める量を読む。
applies_to:
- type: learn
  ref: loss-and-heat
  folder: power
  note: パワー半導体の損失が、温度にどう変わるかを、式で読める。
- type: learn
  ref: reliability-tests
  folder: test
  note: 高温の試験で、素子内部の温度が周囲より高い理由が分かる。
- type: learn
  ref: advanced-packaging
  folder: process
  note: パッケージの熱抵抗が、素子の温度に効く関係が読める。
basis: sources
draft: true
published_at: '2026-10-21'
ai_generated: true
sources:
- id: S1
  title: 半導体の接合温度の計算方法
  publisher: 東芝デバイス＆ストレージ株式会社
  kind: web
  url: https://toshiba.semicon-storage.com/us/semiconductor/knowledge/faq/common/how-to-calculate-the-junction-temperature-of-a-semiconductor.html
  accessed_on: '2026-10-21'
- id: S2
  title: General Characteristics of Silicon
  publisher: CERN（半導体検出器の資料）
  kind: web
  url: https://ssd-rd.web.cern.ch/Data/Si-General.html
  accessed_on: '2026-10-21'
---

## 式

$$T_j = T_a + R_{th(j\text{-}a)} \times P$$

$T_j$ は接合温度で、素子の内部の温度である。$T_a$ は周囲の温度、$P$ は素子が消費する電力、$R_{th(j\text{-}a)}$ は接合から周囲までの熱抵抗（単位は ℃/W）である[S1]。右辺の第2項が、温度の上昇分 $\Delta T_j$ にあたる[S1]。

熱抵抗は、データシートの絶対最大定格から、次のように求められる[S1]。

$$R_{th(j\text{-}a)} = \frac{T_{j(max)} - 25\,℃}{P_C}$$

$T_{j(max)}$ は最大の接合温度、$P_C$ は周囲25℃での許容損失である[S1]。

## 式のどこを見るか

見るのは、$R_{th}$ が温度の上昇分を決めていることである。電力 $P$ が同じでも、$R_{th}$ が大きいほど、素子の内部は高温になる。$R_{th}$ が1 ℃/W なら、1 W の消費で1 ℃上がる。

温度の上昇は、熱の流れる道筋の熱抵抗の合計で決まる。素子が放熱板に取り付けてあるときは、接合からケースまでの熱抵抗 $R_{th(j\text{-}c)}$ を使う[S1]。

素材そのものの熱抵抗は、厚さ $L$、断面積 $A$、熱伝導率 $\kappa$ から、次のように見積もれる。

$$R = \frac{L}{\kappa A}$$

シリコンのチップ自身の熱抵抗は、この式で見積もれる（数値例）。

接合温度は、信頼性にも関わる。温度が上がると、劣化の進みが速くなる（「アレニウス則」「加速試験」のページ）。

## 数値例

シリコンの熱伝導率は、1.5 W/(cm·K) である[S2]。面積1 cm$^2$、厚さ0.05 cm（0.5 mm）のチップの熱抵抗は、$R=0.05/(1.5\times1)$ から、約0.033 ℃/W になる（本サイトで計算）。1 W を消費しても、チップの表と裏の差は約0.03 ℃である。次の仮定の値（100 ℃/W）に比べて、桁違いに小さい。

接合温度の式は、次の仮定の値で確かめる。データシートの値を、$T_{j(max)}=150$ ℃、$P_C=1.25$ W と仮定すると、$R_{th(j\text{-}a)}=(150-25)/1.25=100$ ℃/W になる。周囲が60 ℃、消費電力が0.5 W のとき、温度の上昇は $100\times0.5=50$ ℃で、$T_j=110$ ℃ である（いずれも本サイトで計算）。

この例の数値は、式の読み方を確かめるために置いた仮定である。実際の製品の値ではない。

## 理解度チェック

### 問1
消費電力が同じとき、熱抵抗が大きい素子は、接合温度がどうなるか。

1. 低くなる
2. 高くなる
3. 変わらない
4. 周囲の温度だけで決まる

答え：2
解説：温度の上昇分は R × P である。P が同じなら、R が大きいほど上昇分が大きく、接合温度は高くなる。

### 問2
熱抵抗が100 ℃/W の素子で、周囲が60 ℃、消費電力が0.5 W のときの接合温度はいくつか。

1. 60 ℃
2. 100 ℃
3. 110 ℃
4. 160 ℃

答え：3
解説：温度の上昇は 100 × 0.5 = 50 ℃ である。周囲の60 ℃ に足して、110 ℃ になる。
