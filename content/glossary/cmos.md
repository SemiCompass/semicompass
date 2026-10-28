---
term: CMOS
reading: シーモス
aliases:
- 相補型MOS
name_en: complementary metal-oxide-semiconductor
abbreviation_of: Complementary Metal-Oxide-Semiconductor
short_definition: nMOSとpMOSのトランジスタを対にして組み合わせる回路の方式。
processes:
- circuit-design
related_terms:
- mosfet
- process-node
description: CMOSは、nMOSとpMOSのトランジスタを対にして組み合わせる回路の方式。状態が変わらないときの電流が小さく、論理回路の基本になっている。
basis: reviewed
published_at: '2026-10-28'
draft: true
ai_generated: true
sources: []
---

CMOS（相補型MOS）は、nMOSとpMOSのトランジスタを対にして組み合わせる回路の方式である。

基本の回路では、電源の側にpMOS、接地の側にnMOSを置き、同じ入力の信号を両方のゲートに入れる。入力が変わると、どちらか一方だけが電流を通す状態になる。出力が変わらない間は、電源から接地へ抜ける電流の経路がほとんどないため、消費電力を小さくできる。

この性質から、CMOSは、プロセッサなどの論理回路の基本の方式になっている。CMOSの製造の技術で作るイメージセンサは、CMOSイメージセンサと呼ばれる。

## 理解度チェック

### 問1
CMOSの回路で、出力が変わらない間の消費電力が小さい理由として、正しいものはどれか。

1. トランジスタを1種類しか使わないため
2. 電源から接地へ抜ける電流の経路がほとんどないため
3. 電圧を常に高く保つため
4. 配線を使わないため

答え：2
解説：nMOSとpMOSのどちらか一方だけが電流を通す状態になるため、出力が変わらない間は、電源から接地へ電流が抜けにくい。
