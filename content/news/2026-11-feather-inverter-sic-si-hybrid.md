---
title: SiCとSiを混載したフェザーインバーターを公開
description: ロームのSiC MOSFETと三菱電機のSi IGBTを同一パッケージに載せたEV向けインバーターが、ドイツで公開された。パワー半導体モジュールと冷却器の重量が約70％減る。
published_at: '2026-11-17'
draft: false
ai_generated: true
category: technology
source_article:
  title: ロームのSiCと三菱のSiを混載「重さ7割減」日本発インバーター技術に迫る
  publisher: EE Times Japan
  url: https://eetimes.itmedia.co.jp/ee/articles/2611/17/news043.html
  published_on: '2026-11-17'
  reporting: press
score:
  impact: 2
  supply_chain: 2
  novelty: 1
  reliability: 2
overseas: false
tags:
  companies:
  - rohm
  - mitsubishi-electric
  - aoi-electronics
  processes:
  - packaging
  themes: []
  unlisted_companies:
  - name: 東レ
  - name: 大豊工業
  - name: ニチコン
  - name: パナソニック インダストリー
  - name: 北川工業
x_post: 'ロームと三菱電機のパワー半導体を同一パッケージに載せた「フェザーインバーター」が独の展示会で公開。モジュールと冷却器の重量はCybertruck用比で約70％減。実装はアオイ電子。 #パワー半導体 #SiC https://semicompass.com/news/2026/11/feather-inverter-sic-si-hybrid/'
---

## 何が起きたか

ロームは、2026年11月10〜13日にドイツのミュンヘンであった展示会electronica 2026に、名古屋大学と企業8社の産学連携で作る「フェザーインバーター」を出展した[S1]。800Vバッテリーを積むEV（電気自動車）向けで、230kW級の出力を想定する[S1]。パワー半導体モジュールと冷却器の重さは約300gで、Teslaの「Cybertruck」用の約1kgより約70％軽い[S1]。ただし制御基板やコンデンサーを含む全体の重さではない[S1]。2026年9月に初公開され、海外展示は今回が初めてである[S1]。

## なぜ重要か

SiとSiCを混載する理由は、素子ごとに得意な領域が違うからである。IGBT（絶縁ゲート型バイポーラトランジスタ）は大電流に強いが、高周波の入り切りは苦手である。SiC（炭化ケイ素）のMOSFET（金属酸化膜半導体電界効果トランジスタ）は高周波の入り切りに向く[S1]。SiCだけで大電流を扱うとチップ面積が増えてコストが上がり、Siだけでは高周波時の損失が課題になる[S1]。そこで発進や急加速など大きなトルクが要る場面ではIGBT、高速巡航など小さなトルクで足りる場面ではSiC MOSFETを使い分ける[S1]。

## 関係する企業・工程とサプライチェーン上の位置

ロームのSiC MOSFETと三菱電機のRC-IGBTを、アオイ電子のファンアウト型パッケージに実装する[S1]。チップを樹脂で封止し、表面に銅めっきで電極を作る。リードフレームを使わないので、パッケージを薄くできる[S1]。供給網では、チップを作った後の、パッケージング（封止）の工程に関わる。
