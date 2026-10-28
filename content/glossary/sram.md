---
term: SRAM
reading: エスラム
aliases:
- スタティックランダムアクセスメモリ
name_en: static random access memory
abbreviation_of: Static Random Access Memory
short_definition: 複数のトランジスタで組んだ回路で情報を保持し、リフレッシュが要らない、電源を切ると内容が消えるメモリ。
processes:
- circuit-design
related_terms:
- dram
- logic-semiconductor
- process-node
description: SRAMは、複数のトランジスタで組んだ回路で情報を保持するメモリ。リフレッシュが要らず読み書きが速いが、セルが大きい。プロセッサの中のキャッシュに使う。
basis: reviewed
published_at: '2026-10-28'
draft: true
ai_generated: true
sources: []
---

SRAM（スタティックランダムアクセスメモリ）は、複数のトランジスタを組み合わせた回路で情報を保持するメモリである。

メモリセルは、二つの状態のどちらかを保ち続ける回路（フリップフロップ）でできている。電源が入っている間は、状態がそのまま保たれるため、DRAMのような定期的な書き直し（リフレッシュ）が要らない。電源を切ると、内容は消える。

読み書きが速い一方で、ひとつのセルに使うトランジスタが多く、面積が大きい。そのため、大容量にすると高価になる。CPUやGPUなどのロジック半導体の中に作り込み、よく使うデータを一時的に置く高速の記憶（キャッシュ）として使う。

## 理解度チェック

### 問1
SRAMとDRAMの違いとして、正しいものはどれか。

1. SRAMはリフレッシュが要らない
2. SRAMは電源を切っても内容が残る
3. SRAMはセルが小さく安い
4. SRAMはキャパシタだけで記憶する

答え：1
解説：SRAMは、状態を保ち続ける回路で記憶するため、リフレッシュが要らない。一方、セルが大きく、電源を切ると内容は消える。
