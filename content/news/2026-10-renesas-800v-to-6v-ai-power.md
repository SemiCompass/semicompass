---
title: ルネサス、800Vを6Vへ直接変換するAI向け電源を開発
description: ルネサスがAIデータセンター向けに800Vを6Vへ直接変換する20kW級電源を開発し、主要メーカーにサンプルを提供している。変換段を減らす仕組みを解説する。
published_at: '2026-10-26'
draft: false
ai_generated: true
category: technology
source_article:
  title: 800Vを一気に6Vへ、ルネサスが開発するAIサーバ用20kW級電源：主要メーカーにサンプル提供中（1/2 ページ） - EE Times Japan
  publisher: EE Times Japan
  url: https://eetimes.itmedia.co.jp/ee/articles/2610/23/news043.html
  published_on: '2026-10-23'
  reporting: press
score:
  impact: 2
  supply_chain: 2
  novelty: 2
  reliability: 2
overseas: false
tags:
  companies:
  - renesas-electronics
  processes: []
  themes: []
  unlisted_companies:
  - name: NVIDIA
x_post: 'ルネサスが、AIデータセンター向けに800Vを6Vへ直接変換する20kW級電源を開発。650V耐圧GaNを使い、主要メーカーにサンプル提供中。 #ルネサス #パワー半導体 https://semicompass.com/news/2026/10/renesas-800v-to-6v-ai-power/'
---

## 何が起きたか

ルネサス エレクトロニクスは、AIデータセンターで使う20kW級の電源システムを開発している。800Vの直流電圧を、6Vまで直接変換する方式である[S1]。2026年10月時点で、AIデータセンター向けの主要メーカー（OEMおよびODM）に、このプラットフォームのサンプルを提供済みである[S1]。同月に米国サンノゼで開かれたOCP Global Summit 2026では、NVIDIAのエコシステムパートナーとして試作ハードウェアを展示した[S1]。

## なぜ重要か

背景には、GPUの処理能力の向上に伴うサーバラック当たりの消費電力の増加がある。配電電圧は従来の48Vから、800Vの高電圧直流へ切り替える動きが進んでいる[S1]。電圧を高めると、同じ電力を送る電流が小さくなり、配電経路の損失が減る[S1]。ただしGPUなどは低電圧かつ大電流で動くため、演算デバイスの近くで電圧を下げる必要がある[S1]。今回の方式は、48Vや12Vといった中間電圧を経由せず、変換の段数を減らす点が特徴である[S1]。構成は、耐圧650VのGaN（窒化ガリウム）を使ったパワー素子と、共振を利用するLLC方式の変換回路の組み合わせである[S1]。出力20kWでの変換効率は、部品ごとの損失からの計算で約96.3％と見込まれている[S1]。この値は予測であり、実機での評価は進行中である[S1]。

## 関係する企業・工程とサプライチェーン上の位置

ルネサスは電源システムを自ら開発し、650V耐圧のGaNパワーデバイスを使う構成を示している[S1]。パワー半導体は電力の変換や制御に使う素子で、微細化よりも高い耐圧と電力損失の小ささが重視される。サプライチェーンでは、電源に使う半導体を作る企業が、サーバ向けメーカーへ試作品を渡している段階にあたる[S1]。
