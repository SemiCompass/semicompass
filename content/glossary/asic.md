---
term: ASIC
reading: エーシック
aliases:
- 特定用途向け集積回路
name_en: application-specific integrated circuit
abbreviation_of: Application Specific Integrated Circuit
short_definition: 特定の用途や機器のために、専用に設計して作る集積回路。
processes:
- circuit-design
related_terms:
- fpga
- soc
- logic-semiconductor
- eda
description: ASICは、特定の用途や機器のために、専用に設計して作る集積回路。決まった処理を、速く、少ない電力で行えるが、設計と製造の初期の費用が大きい。
basis: reviewed
published_at: '2026-10-28'
draft: true
ai_generated: true
sources: []
---

ASIC（特定用途向け集積回路）は、特定の用途や機器のために、専用に設計して作る集積回路である。

汎用のプロセッサは、プログラムを変えれば多くの種類の処理に使える一方、ひとつの処理だけを見ると無駄が多い。ASICは、決まった処理だけを行う回路を、初めから作り込む。そのため、同じ処理を、速く、少ない電力で、小さなチップで行える。

一方で、設計に時間がかかり、フォトマスクの作成などの初期の費用も大きい。作った後で回路を変えることもできない。そのため、同じものを大量に作る製品や、性能と電力の効率を特に求める用途に向く。データセンターでAIの計算を行う専用のチップも、ASICの一種である。回路を後から書き換えられる集積回路に、FPGAがある。

## 理解度チェック

### 問1
ASICの特徴として、正しいものはどれか。

1. 作った後で回路を自由に書き換えられる
2. 特定の用途のために専用に設計し、決まった処理を効率よく行う
3. 初期の費用がかからない
4. メモリだけを持つ

答え：2
解説：ASICは、特定の用途のために専用に設計する。決まった処理を効率よく行えるが、初期の費用が大きく、作った後で回路を変えられない。
