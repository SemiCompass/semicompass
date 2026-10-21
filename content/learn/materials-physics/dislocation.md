---
title: 転位：シリコンのバーガースベクトルは0.384 nm、格子定数の約0.71倍
field: materials-physics
description: 結晶の中の線状の欠陥である転位を、向きと大きさを表すバーガースベクトルで読む。シリコンでは、大きさが格子定数の1/√2倍の0.384 nmで、原子の密な{111}面ですべることを、格子定数0.543 nmの値で確かめる。
applies_to:
- type: learn
  ref: crystal-defects
  folder: silicon
  note: 点のほかに、線の形の欠陥があり、結晶の変形に関わることが読める。
- type: learn
  ref: crystal
  folder: silicon
  note: 結晶の原子の並びが、どの面とどの向きですべりやすいかを決めることが分かる。
basis: sources
draft: true
published_at: '2026-10-21'
ai_generated: true
sources:
- id: S1
  title: 'Generalized Stacking Fault Energy Surfaces and Dislocation Properties of Silicon: A First-Principles Theoretical Study（arXiv:mtrl-th/9604006）'
  publisher: arXiv
  kind: web
  url: https://arxiv.org/pdf/mtrl-th/9604006
  accessed_on: '2026-10-21'
- id: S2
  title: 'Lecture 12: Materials Science 2021-22 - Dislocations'
  publisher: トリエステ大学
  kind: web
  url: https://moodle2.units.it/pluginfile.php/438582/mod_resource/content/1/Lecture%2012%20-%20Materials%20Science%202021-22%20-Dislocations.pdf
  accessed_on: '2026-10-21'
- id: S3
  title: 'ECE 340 Lecture 2: Crystal structure'
  publisher: イリノイ大学アーバナ・シャンペーン校
  kind: web
  url: https://ursemiconductors.web.illinois.edu/ECE340/Lecture02.pdf
  accessed_on: '2026-10-21'
---

## 式

$$|\mathbf{b}| = \frac{a}{\sqrt{2}}$$

転位は、結晶の中の線状の欠陥で、結晶の対称性を局所的に乱し、塑性変形（力を除いても戻らない変形）を担う[S2]。余分な半面の原子が入った形を刃状転位、結晶がずれて原子の面がらせん状につながった形をらせん転位という[S2]。両方の性格をもつものが混合転位である[S2]。

向きと大きさを表すのが、バーガースベクトル $\mathbf{b}$ である。転位の線に対して、刃状では垂直、らせんでは平行になる[S2]。シリコンの完全な転位では、$|\mathbf{b}|$ は0.384 nm（3.84 Å）で、格子定数 $a$ の $1/\sqrt{2}$ に当たる[S1]。

## 式のどこを見るか

見るのは、$|\mathbf{b}|$ が格子定数で決まることである。$a$ が分かれば、転位のずれの大きさも分かる。

すべりは、原子が密な面で、原子が密な向きに、すべりの量（$|\mathbf{b}|$）が小さいほど起きやすい[S2]。シリコンの計算では、{111} 面の上の60°転位とらせん転位が調べられている[S1]。

転位が2つの部分転位に分かれる場合の大きさは、0.222 nm（2.22 Å）とされる[S1]。

## 数値例

格子定数 $a=5.43$ Å[S3]を $|\mathbf{b}|=a/\sqrt{2}$ に入れると、約3.84 Å になり、出典の値と一致する（本サイトで計算）。$a/\sqrt{6}$ からは約2.22 Å で、部分転位の値とも一致する（本サイトで計算）。

結合の長さ（最も近い原子の距離）は2.35 Å である[S3]。バーガースベクトルは、その約1.63倍である（本サイトで計算）。

## 理解度チェック

### 問1
刃状転位で、バーガースベクトルは転位の線に対してどの向きか。

1. 平行
2. 垂直
3. 45度
4. 向きは決まっていない

答え：2
解説：刃状転位では、バーガースベクトルは転位の線に垂直である。らせん転位では平行になる。

### 問2
格子定数が5.43 Å のシリコンで、完全な転位のバーガースベクトルの大きさはおよそいくつか。

1. 約1.9 Å
2. 約2.35 Å
3. 約3.84 Å
4. 約5.43 Å

答え：3
解説：大きさは a/√2 で、5.43 Å を√2で割った約3.84 Å になる。
