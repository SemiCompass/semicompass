---
term: GPU
reading: ジーピーユー
aliases:
- グラフィックスプロセッサ
- 画像処理半導体
name_en: graphics processing unit
abbreviation_of: Graphics Processing Unit
short_definition: 多数の計算の回路で、同じ種類の計算を並列に行うプロセッサ。画像の処理やAIの計算に使う。
processes:
- circuit-design
related_terms:
- soc
- hbm
- interposer
- process-node
description: GPUは、多数の計算の回路で、同じ種類の計算を同時に並列で行うプロセッサ。画像の描画のために生まれ、AIの学習や推論、科学技術の計算にも使う。
basis: reviewed
published_at: '2026-10-28'
draft: true
ai_generated: true
sources: []
---

GPU（グラフィックスプロセッサ）は、多数の計算の回路を持ち、同じ種類の計算を同時に並列で行うプロセッサである。

画面の画像を描くには、多くの点（画素）について、同じ種類の計算を繰り返す必要がある。GPUは、この処理のために生まれた。CPUが、少数の高性能な回路で複雑な処理を順に進めるのに対し、GPUは、単純な回路を多数並べて、大量の計算をまとめて進める。

この性質は、行列の計算を大量に行うAIの学習や推論、科学技術の計算にも向いている。大量のデータを速く出し入れするため、HBMを、インターポーザの上でGPUのすぐ隣に置く構成が使われる。スマートフォンなどでは、SoCの中にGPUの回路が入る。

## 理解度チェック

### 問1
GPUが、AIの計算に向いている理由として、正しいものはどれか。

1. 回路の数が少ないため
2. 同じ種類の計算を、多数の回路で同時に並列で行えるため
3. 電源を切っても内容が残るため
4. 光で計算するため

答え：2
解説：GPUは、単純な計算の回路を多数並べて、同じ種類の計算をまとめて進める。AIの学習や推論で使う大量の行列の計算に向いている。
