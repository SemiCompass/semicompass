---
term: CPU
reading: シーピーユー
aliases:
- 中央処理装置
- プロセッサ
name_en: central processing unit
abbreviation_of: Central Processing Unit
short_definition: プログラムの命令を順に読み、計算や判断、機器全体の制御を行うプロセッサ。
processes:
- circuit-design
related_terms:
- gpu
- soc
- logic-semiconductor
- sram
description: CPUは、プログラムの命令を順に読み出して、計算や判断を行い、機器全体を制御するプロセッサ。コンピュータの中心となるロジック半導体である。
basis: reviewed
published_at: '2026-10-28'
draft: true
ai_generated: true
sources: []
---

CPU（中央処理装置）は、プログラムの命令をメモリから順に読み出し、計算や判断を行って、機器全体を制御するプロセッサである。

内部には、計算を行う回路、命令を解釈して各部に指示を出す回路、計算の途中の値を一時的に置く場所（レジスタ）などがある。よく使うデータを置くための高速の記憶（キャッシュ）として、SRAMも作り込まれる。

CPUは、複雑な処理を、少数の高性能な回路で順に素早く進めるのが得意である。同じ種類の単純な計算を大量に並列で行う処理は、GPUのほうが向いている。ひとつのチップに、複数の計算の中心（コア）を持つものが一般的である。パソコンやサーバのほか、スマートフォンではSoCの中にCPUの回路が入る。

## 理解度チェック

### 問1
CPUの働きとして、正しいものはどれか。

1. 光を電気に変える
2. プログラムの命令を読み、計算や判断をして機器を制御する
3. 電力を変換する
4. 回路を写す

答え：2
解説：CPUは、プログラムの命令を順に読み出して、計算や判断を行い、機器全体を制御する。
