---
theme: leading-edge-2nm
title: 2ナノの最先端半導体
description: 回路の線幅が2ナノメートル級の半導体が量産の段階に入った。受託生産の市場の動き、EUV露光を中心にした回路を描く工程の段階、日本の装置・材料の企業の位置と論点をまとめたレポート。
criteria: 2ナノの世代やEUV露光に使う装置・材料を作っていることを、公開資料で確かめられる企業を載せる。2ナノの半導体を作る企業と露光装置の企業は、掲載企業の外として名前で載せる。
groups:
  - label: マスクブランクスとマスク
    process: photomask
    companies:
      - company: shin-etsu-chemical
        role: EUV用のマスクブランクスとフォトレジストを開発する。2ナノ世代のフォトレジストは量産に移った。
        basis: [S9]
      - company: hoya
        role: 半導体用のマスクブランクスを作り、EUV向けの先端品を開発する。
        basis: [S12]
      - company: agc
        role: EUV用のマスクブランクスを扱う。
        basis: [S13]
      - company: mitsui-chemicals
        role: EUV露光でマスクを守る、カーボンナノチューブを使うペリクルの生産設備を設けた。
        basis: [S14]
  - label: マスクの検査
    process: inspection-metrology
    companies:
      - company: lasertec
        role: EUVのマスクやマスクブランクスの欠陥を検査する装置を作る。
        basis: [S11]
  - label: 塗布・露光・現像
    process: lithography
    companies:
      - company: tokyo-electron
        role: 塗布・現像の装置を作り、EUV露光向けのレジストの技術の開発も行う。
        basis: [S8]
      - company: tokyo-ohka-kogyo
        role: EUV用のフォトレジストを作る。郡山工場に新しい製造棟を完成させた。
        basis: [S10, S16]
    others:
      - name: ASML
        region: オランダ
        role: EUV露光装置を作る。Rapidusの千歳の工場にも納めた。
        basis: [S4]
  - label: 洗浄
    process: cleaning
    companies:
      - company: screen
        role: 洗浄の装置を作り、洗浄の工程の開発でIBMと追加の契約を結んでいる。
        basis: [S15]
  - label: 2ナノの半導体を作る企業
    others:
      - name: TSMC
        name_en: Taiwan Semiconductor Manufacturing Company
        region: 台湾
        role: 2025年10〜12月期に2ナノの量産を始めた。子会社JASMの熊本第2工場では3ナノを計画する。
        basis: [S1, S2, S7]
      - name: Rapidus
        region: 日本
        role: 千歳の工場で2ナノの試作を進め、2027年度後半の量産を目指す。
        basis: [S5, S6]
      - name: IBM
        region: 米国
        role: 自社の2ナノの技術を、Rapidusと共同で開発する。
        basis: [S3]
processes: [photomask, lithography, inspection-metrology, cleaning]
terms: [euv, photomask, photoresist, coater-developer, process-node, foundry]
learn:
  - { folder: process, ref: resolution }
  - { folder: logic, ref: design-rules }
  - { folder: devices, ref: scaling }
published_at: '2026-10-23'
draft: false
ai_generated: true
sources:
  - id: S1
    title: 3Q26 Earnings Release
    publisher: TSMC
    url: https://pr.tsmc.com/system/files/newspdf/attachment/70d8a93214795fa88f83fb47e0e45e7b0435e52b/3Q26%20%28E%29_with%20gudiance_final_wmn.pdf
    published_on: '2026-10-15'
    accessed_on: '2026-10-23'
  - id: S2
    title: "2 nm Chip Ramp: TSMC Starts Volume Production"
    publisher: eeNews Europe
    url: https://www.eenewseurope.com/en/2nm-chip-ramp-tsmc-volume-production/
    published_on: '2026-01-05'
    accessed_on: '2026-10-23'
  - id: S3
    title: IBM and Rapidus Form Strategic Partnership to Build Advanced Semiconductor Technology and Ecosystem in Japan
    publisher: IBM
    url: https://newsroom.ibm.com/2022-12-12-IBM-and-Rapidus-Form-Strategic-Partnership-to-Build-Advanced-Semiconductor-Technology-and-Ecosystem-in-Japan
    published_on: '2022-12-12'
    accessed_on: '2026-10-23'
  - id: S4
    title: Rapidus、日本初となる最先端半導体量産向け製造設備を導入開始
    publisher: PC Watch
    url: https://pc.watch.impress.co.jp/docs/news/1649307.html
    published_on: '2024-12-20'
    accessed_on: '2026-10-23'
  - id: S5
    title: "Rapidusは31年度に上場目指す、27年度後半に2nm世代量産：経産省が1000億円出資へ"
    publisher: EE Times Japan
    url: https://eetimes.itmedia.co.jp/ee/articles/2511/21/news147.html
    published_on: '2025-11-21'
    accessed_on: '2026-10-23'
  - id: S6
    title: "経産省、Rapidusへの4000億円追加出資計画を明かす：2nm量産に向け自己資本強化"
    publisher: EE Times Japan
    url: https://eetimes.itmedia.co.jp/ee/spv/2610/20/news052_2.html
    published_on: '2026-10-20'
    accessed_on: '2026-10-23'
  - id: S7
    title: "TSMC熊本第2工場の3nm生産計画、経産省が認定：28年末生産開始"
    publisher: EE Times Japan
    url: https://eetimes.itmedia.co.jp/ee/articles/2610/19/news041.html
    published_on: '2026-10-19'
    accessed_on: '2026-10-23'
  - id: S8
    title: 有価証券報告書（2026年3月期）
    publisher: 東京エレクトロン
    url: https://disclosure2dl.edinet-fsa.go.jp/searchdocument/pdf/S100YEOO.pdf
    published_on: '2026-06-22'
    accessed_on: '2026-10-23'
    doc_id: S100YEOO
  - id: S9
    title: 有価証券報告書（2026年3月期）
    publisher: 信越化学工業
    url: https://disclosure2dl.edinet-fsa.go.jp/searchdocument/pdf/S100YE9I.pdf
    published_on: '2026-06-19'
    accessed_on: '2026-10-23'
    doc_id: S100YE9I
  - id: S10
    title: 有価証券報告書（2025年12月期）
    publisher: 東京応化工業
    url: https://disclosure2dl.edinet-fsa.go.jp/searchdocument/pdf/S100XT0N.pdf
    published_on: '2026-03-24'
    accessed_on: '2026-10-23'
    doc_id: S100XT0N
  - id: S11
    title: 有価証券報告書（2026年6月期）
    publisher: レーザーテック
    url: https://disclosure2dl.edinet-fsa.go.jp/searchdocument/pdf/S100Z32V.pdf
    published_on: '2026-09-24'
    accessed_on: '2026-10-23'
    doc_id: S100Z32V
  - id: S12
    title: 有価証券報告書（2026年3月期）
    publisher: HOYA
    url: https://disclosure2dl.edinet-fsa.go.jp/searchdocument/pdf/S100Y90T.pdf
    published_on: '2026-06-05'
    accessed_on: '2026-10-23'
    doc_id: S100Y90T
  - id: S13
    title: EUV Mask Blanks
    publisher: AGC Electronics America
    url: https://www.agcem.com/products/euv-mask-blanks
    accessed_on: '2026-10-23'
  - id: S14
    title: 三井化学、次世代EUV露光用CNTペリクルの生産設備を設置
    publisher: 三井化学
    url: https://jp.mitsuichemicals.com/content/dam/mitsuichemicals/sites/mci/documents/release/2024/240528_1.pdf
    published_on: '2024-05-28'
    accessed_on: '2026-10-23'
  - id: S15
    title: 有価証券報告書（2026年3月期）
    publisher: SCREENホールディングス
    url: https://disclosure2dl.edinet-fsa.go.jp/searchdocument/pdf/S100YK9N.pdf
    published_on: '2026-06-25'
    accessed_on: '2026-10-23'
    doc_id: S100YK9N
  - id: S16
    title: "「世界最大級」フォトレジスト製造棟が完成 東京応化工業：郡山工場で2026年11月から稼働"
    publisher: EE Times Japan
    url: https://eetimes.itmedia.co.jp/ee/articles/2610/13/news027.html
    published_on: '2026-10-13'
    accessed_on: '2026-10-23'
---
## 要旨

- 回路の線幅が2ナノメートル級の半導体は、量産の段階に入った。TSMCは、2025年10〜12月期に2ナノの量産を始め、2026年7〜9月期には、ウェーハの売上高の8%を2ナノが占めた[S1][S2]。
- 日本では、Rapidusが北海道千歳市の工場で試作を進め、2027年度後半の量産を目指す。国内初の量産向けのEUV（極端紫外線）露光装置を入れ、2025年7月にトランジスタの動作を確かめた[S4][S5][S6]。
- 回路を描く工程では、日本企業がEUV向けのマスクブランクス、マスクの検査装置、フォトレジスト、塗布・現像の装置を供給する[S8][S10][S11][S12]。2ナノの競争は、作る会社の競争であると同時に、日本の装置・材料の企業の需要の源でもある。

## 市場の動き

TSMCの2026年7〜9月期の売上高は467億2,000万ドルで、前の年の同じ期より41.2%増えた[S1]。ウェーハの売上高のうち、7ナノ以下の先端の技術が79%を占める[S1]。内訳は、3ナノが33%、5ナノが28%、7ナノが10%、2ナノが8%である（図1）[S1]。

2ナノは、TSMCで最も新しい世代である。TSMCは、2025年10〜12月期に2ナノの量産を始めたとしている[S2]。2ナノの売上高の比率は、量産を始めて1年たたないうちに8%に達した。TSMCの最高財務責任者は、2026年10〜12月期の事業は2ナノの急な立ち上がりに支えられるとの見通しを示した[S1]。

日本では、2つの動きがある。1つは、Rapidusの2ナノの量産の計画である。Rapidusは、2027年度後半に2ナノ世代の量産を始め、その後2〜3年ごとに1.4ナノ、1.0ナノの量産を目指す中期の計画を示している[S5]。もう1つは、TSMCの子会社JASMの熊本第2工場である。経済産業省は、2026年10月、この工場で3ナノのロジック半導体を2028年12月までに作り始める計画への変更を認めた[S7]。2ナノではないが、国内で作るロジック半導体の世代が、大きく進むことになる。

Rapidusは、2030年度には、2ナノ世代の半導体の供給が、世界の需要に対して10〜30%ほど足りなくなると見込んでいる[S5]。この見方は、量産を目指す会社の側の見方である点に注意が要る。

## バリューチェーン

2ナノの世代では、2つの技術が要になる。1つは、トランジスタの形である。TSMCは、2ナノで、これまでのフィンの形のトランジスタから、薄い板（ナノシート）を重ねてゲートで四方を囲む形（GAA）に切り替えた[S2]。Rapidusも、2025年7月に、2ナノのGAAトランジスタの動作を確かめた[S6]。

もう1つは、細かい回路を描くEUV露光である。回路を描くまでには、いくつもの段階がある（図2）。まず、マスクのもとになる板（マスクブランクス）を作る。その上に回路の模様を描いてマスクにし、欠陥がないかを検査する。ウェーハの上には、光に反応する材料（フォトレジスト）を塗り、マスクを通してEUVの光を当て、現像して模様を残す。

この流れの各段階に、日本企業が関わる。HOYAとAGCはEUV向けのマスクブランクスを手がけ、信越化学工業もEUV用のマスクブランクスを開発した[S9][S12][S13]。レーザーテックは、EUVのマスクやマスクブランクスの欠陥を検査する装置を作る[S11]。三井化学は、EUV露光でマスクを守る膜（ペリクル）として、カーボンナノチューブを使う製品の生産設備を設けた[S14]。フォトレジストでは、東京応化工業がEUV用の製品を作り、信越化学工業は2ナノ世代のフォトレジストが量産に移ったとしている[S9][S10]。東京エレクトロンは、レジストを塗って現像する装置を作り、EUV向けのレジストの技術の開発も行う[S8]。

一方、EUVの光を当てる露光装置そのものは、オランダのASMLが供給する。Rapidusが2024年12月に搬入を始めたEUV露光装置も、ASMLの製品である[S4]。

## 日本企業の位置

日本企業の強みは、回路を描く工程の周りの装置と材料に集まる。表には、EUV露光に関わるマスクブランクス、マスクの検査、ペリクル、フォトレジスト、塗布・現像の装置、そして洗浄の装置で、2ナノの世代やEUVとの関わりを公開資料で確かめられた企業を載せた。

材料の企業は、供給の力を広げている。東京応化工業は、福島県郡山市の工場に、フォトレジストの新しい製造棟を完成させた。投資額は約230億円で、2026年11月に稼働を始める予定である。この工場では、EUV露光装置用やArF用のレジストを作る[S16]。

洗浄の装置を作るSCREENホールディングスは、洗浄の工程の開発で、IBMとの間で追加の契約を結んでいる[S15]。IBMは、2022年12月に、自社の2ナノの技術をRapidusと共同で開発し、Rapidusが日本の工場で使う協力を発表した[S3]。

作る側では、Rapidusが、2025年4月に千歳の工場でパイロットラインの立ち上げを始め、同じ年の12月に、設計に使う情報の一式（PDK）を公開した[S6]。顧客の候補の60社以上と交渉しているとしている[S6]。Rapidusは、前の工程だけでなく、チップを組み立てる後の工程にも取り組み、600ミリメートル角のパネルを使った配線の層（RDLインターポーザー）の試作に成功した。2028年度には、先端パッケージの量産も始める計画である[S6]。Rapidusは本サイトの掲載企業に入っていないため、掲載企業の外として載せた。

## 論点と今後の注目点

### 発表元の見方

Rapidusは、まず生成AIのデータセンター向けの専用の半導体を設計する企業から受注し、その後、自動車やロボットなどの機器向けに広げるとしている[S5]。試作と改善の期間を短くする製造の方式で、2027年度後半までにトランジスタの性能と歩留まりを高める計画である[S5]。

TSMCは、2ナノの立ち上がりと、先端の工程への強い需要が続くと見ている[S1]。

### 本サイトの見方

1つ目の論点は、量産の時期の差である。TSMCは2025年10〜12月期に2ナノの量産を始めた。Rapidusの量産の目標は2027年度後半で、2年ほどの差がある。後から入る会社が顧客を得るには、短い期間で試作品を届けるなど、量の大きさとは別の強みを示す必要がある。Rapidusが交渉している顧客の候補のうち、実際に何社と契約できるかが、今後の注目点である。

2つ目の論点は、資金である。経済産業省は、Rapidusに、2027〜2029年度の3年間で計4,000億円を追加で出資する計画を示した[S6]。Rapidusは、民間の金融機関から2兆円の融資を受ける計画である[S6]。量産の規模を広げるほど、設備への投資は大きくなる。国の支援と民間の資金の組み合わせが続くかどうかが、計画の前提になる。

3つ目の論点は、日本の装置・材料の企業にとっての意味である。2ナノの量産がどの会社で進んでも、EUV露光の周りの装置と材料の需要は生まれる。日本の装置・材料の企業にとっては、国内の量産の計画だけでなく、世界の先端の工場の投資の動きが需要を左右する。一方で、JASMの熊本第2工場が3ナノに進み、Rapidusが2ナノの量産を始めれば、国内に先端のロジックの工場が2つ並ぶ。装置・材料の企業にとっては、顧客の工場が近くにあることで、立ち上げの支援や不具合への対応がしやすくなる利点がある。

4つ目の論点は、次の世代への移り変わりである。Rapidusは1.4ナノ、1.0ナノの量産を目指し、信越化学工業も1.4ナノより細かい世代の材料の開発を強めている[S5][S9]。装置・材料の企業にとっては、2ナノの量産の立ち上がりと、次の世代の開発が並行して進む。
