---
theme: generative-ai
title: 生成AIと半導体
description: 生成AIを支えるデータセンター投資で、半導体の市場はどう動き、どこに供給の制約があるのか。後工程を中心に、日本企業の位置と論点をまとめたレポート。
criteria: AI向けの半導体（最先端のロジック、HBM、先端パッケージ）の製造・検査に使う装置・材料・部品、またはその受託を、公開資料で確かめられる企業を載せる。
groups:
  - label: 演算チップとHBMの組み立て
    process: advanced-packaging
    companies:
      - company: towa
        role: 半導体を樹脂で封止する装置を作る。HBMやAI・データセンター向けの需要で受注が伸びた。
        basis: [S6, S7]
    others:
      - name: SKハイニックス
        name_en: SK hynix
        region: 韓国
        role: AI向けのHBMを製造する。第6世代のHBM4の開発を終えた。
        basis: [S2]
      - name: 台湾積体電路製造（TSMC）
        name_en: TSMC
        region: 台湾
        role: 演算チップとHBMを1つにまとめる先端パッケージCoWoSを手がける。
        basis: [S3]
  - label: ウェーハの研削と切断
    process: dicing
    companies:
      - company: disco
        role: ウェーハを薄く削る研削装置と、切り分ける切断装置を作る。生成AI向けの出荷が伸びた。
        basis: [S5]
  - label: パッケージ基板と材料
    process: packaging
    companies:
      - company: ibiden
        role: AIサーバー向けの高機能ICパッケージ基板を作り、生産能力を増やす計画を公表した。
        basis: [S9]
      - company: ajinomoto
        role: パッケージ基板の層間絶縁材ABFを作る。CPUやGPUなどの高性能チップに使われる。
        basis: [S10, S11]
      - company: resonac
        role: 半導体の後工程の材料を作る。AI需要などで後工程材料の売上が伸びた。
        basis: [S12]
  - label: 試験と検査
    process: final-test
    companies:
      - company: advantest
        role: AIや高性能計算（HPC）向けのチップの試験に使う、SoCテスタなどの試験装置を作る。
        basis: [S4]
      - company: micronics-japan
        role: HBMを含むDRAMの検査に使うプローブカードを作る。
        basis: [S8]
processes: [advanced-packaging, dicing, packaging, final-test]
terms: [hbm, interposer, chiplet, back-grinding, mold-compound, semiconductor-tester, prober]
learn:
  - { folder: process, ref: advanced-packaging }
  - { folder: devices, ref: memory }
  - { folder: logic, ref: processor }
published_at: '2026-10-23'
draft: false
ai_generated: true
sources:
  - id: S1
    title: WSTS 2026年春季半導体市場予測
    publisher: WSTS日本協議会（電子情報技術産業協会）
    url: https://www.jeita.or.jp/japanese/stat/wsts/docs/20260602WSTS.pdf
    published_on: '2026-06-02'
    accessed_on: '2026-10-22'
    kind: association
  - id: S2
    title: SK hynix completes HBM4 development, mass production ready
    publisher: The Korea Times
    url: https://www.koreatimes.co.kr/amp/business/tech-science/20250912/sk-hynix-completes-hbm4-development-mass-production-ready
    published_on: '2025-09-12'
    accessed_on: '2026-10-22'
  - id: S3
    title: CoWoS
    publisher: 台湾積体電路製造（TSMC）
    url: https://3dfabric.tsmc.com/english/dedicatedFoundry/technology/cowos.htm
    accessed_on: '2026-10-22'
  - id: S4
    title: インベスターズガイド
    publisher: アドバンテスト
    url: https://www.advantest.com/document/ja/investors/ir-library/investors-guide/Investors_Guide_2604J.pdf
    published_on: '2026-04-27'
    accessed_on: '2026-10-22'
    pages: 5〜7、13
  - id: S5
    title: ディスコは6期連続最高益、売上高は初の4000億円突破：AI関連需要追い風で
    publisher: EE Times Japan
    url: https://eetimes.itmedia.co.jp/ee/articles/2604/23/news056.html
    published_on: '2026-04-23'
    accessed_on: '2026-10-22'
  - id: S6
    title: 四半期報告書（第46期第2四半期）
    publisher: TOWA
    url: https://disclosure2dl.edinet-fsa.go.jp/searchdocument/pdf/S100S66K.pdf
    published_on: '2023-11-09'
    accessed_on: '2026-10-22'
    doc_id: S100S66K
    pages: '3'
  - id: S7
    title: TOWA、4~9月期減収減益 通期見通しは据え置き増収増益
    publisher: 電波新聞
    url: https://dempa-digital.com/?p=700633
    published_on: '2025-11-12'
    accessed_on: '2026-10-22'
  - id: S8
    title: 日本マイクロニクス、メモリ向けプローブカードの売上高が過去最高を更新 生成AI市場拡大を背景に旺盛な需要続く
    publisher: ログミーFinance
    url: https://finance.logmi.jp/articles/385573
    published_on: '2026-08-14'
    accessed_on: '2026-10-22'
  - id: S9
    title: 高機能ICパッケージ基板生産増強に5000億円、イビデン
    publisher: EE Times Japan
    url: https://eetimes.itmedia.co.jp/ee/articles/2602/05/news037.html
    published_on: '2026-02-05'
    accessed_on: '2026-10-22'
  - id: S10
    title: ABF｜イノベーションストーリー
    publisher: 味の素
    url: https://www.ajinomoto.co.jp/company/jp/rd/our_innovation/abf/
    accessed_on: '2026-10-22'
  - id: S11
    title: 味の素、岐阜に半導体材料新工場用地取得
    publisher: LOGISTICS TODAY
    url: https://www.logi-today.com/947806
    published_on: '2026-05-07'
    accessed_on: '2026-10-22'
  - id: S12
    title: レゾナック26年度上期は156.5%増益 後工程材料が大幅成長
    publisher: EE Times Japan
    url: https://eetimes.itmedia.co.jp/ee/spv/2608/12/news038_2.html
    published_on: '2026-08-12'
    accessed_on: '2026-10-22'
  - id: S13
    title: SK Hynix Sells Full 2026 Chip Slate in Strong AI Demand Sign
    publisher: Bloomberg
    url: https://www.bloomberg.com/news/articles/2025-10-28/sk-hynix-posts-record-profit-after-ai-boom-fuels-chip-demand
    published_on: '2025-10-28'
    accessed_on: '2026-10-22'
  - id: S14
    title: TSMC's CoPoS equipment set for mid-2026; overseas suppliers shake up Taiwan firms
    publisher: DIGITIMES Asia
    url: https://www.digitimes.com/news/a20251222PD213.html
    published_on: '2025-12-22'
    accessed_on: '2026-10-22'
---
## 要旨

- 生成AIを支えるデータセンターへの投資で、世界の半導体市場は2026年に約1兆5,112億ドル（前年比＋89.9%）へ拡大すると予測されている。伸びの中心はメモリである[S1]。
- 生成AI向けの半導体は、演算チップとHBM（広帯域メモリ）を1つのパッケージにまとめて完成する。供給の制約は、回路の微細化だけでなく、HBMと先端パッケージの側にも表れている[S3][S13][S14]。
- 日本企業は、ウェーハの研削・切断、封止、パッケージ基板とその材料、試験と検査など、後工程の装置と材料で役割を担っている。

## 市場の動き

世界半導体市場統計（WSTS）の2026年春季予測によると、2025年の世界の半導体市場は7,956億ドル（実績）だった。2026年は約1兆5,112億ドル（前年比＋89.9%）、2027年は約1兆9,137億ドル（＋26.6%）に広がると予測されている[S1]。

伸びの中心はメモリである。メモリの市場は、2025年の2,300億ドルから、2026年に8,039億ドル（＋249.5%）へ広がると予測されている。ロジックは、2,995億ドルから4,114億ドル（＋37.3%）の予測である[S1]。WSTSは、要因として、大手のIT企業によるAIを中心としたデータセンターへの投資を挙げる。この投資で、AIサーバー向けのメモリと、GPUを中心とするロジックの需要が伸びるという見方である[S1]。

日本の市場も、2025年の447億ドルから、2026年に571億ドルへ広がると予測されている。円に直すと、6兆6,937億円から8兆9,626億円への拡大である[S1]。

需要の伸びは、装置と材料の企業の業績にも表れている。ディスコは、2026年3月期の売上高が4,368億円と過去最高になり、要因に生成AI向けのGPUやHBMの需要を挙げた。同期の第4四半期の装置の出荷額は1,216億円と、四半期で過去最高だった[S5]。レゾナックは、2026年1〜6月期に後工程の材料の売上が前年同期比＋46%となり、AI需要などを要因に挙げた[S12]。

## バリューチェーン

生成AIの計算には、GPUなどの演算用のチップ（AIアクセラレータ）と、HBMを組み合わせて使う。HBMは、DRAMのチップを何枚も積み重ね、データを速く受け渡せるようにしたメモリである[S2]。SKハイニックスが開発を終えた第6世代のHBM4は、データの出入り口（I/O）を2,048個に増やし、帯域を前の世代の2倍にしたとされる。同社は、電力の効率も前の世代より40%以上高めたとしている[S2]。同社は、HBM4でデータセンターのAIの処理の性能が最大69%上がると見積もっている[S2]。演算チップとHBMは、大きなシリコンの中継基板（インターポーザ）の上に並べ、1つのパッケージにまとめる。TSMCの先端パッケージ「CoWoS」は、この形の技術で、用途にAIとスーパーコンピュータを挙げている[S3]。

このため、生成AI向けの半導体は、4つの段階を経て完成する。演算チップを最先端の工程で作る段階、DRAMのチップを薄く削って積み重ねHBMにする段階、演算チップとHBMを1つのパッケージにまとめる段階、そしてパッケージ基板に載せて試験する段階である（図2）。どの段階が詰まっても、最終の製品の数は増えない。

供給の制約は、後工程の側にも表れている。SKハイニックスは、2026年の分のメモリの供給について、すべての販売先が決まったと伝えられた[S13]。TSMCのCoWoSについては、AI向けのGPUなどの需要の急増で、供給が足りない状態が続き、同社の外の後工程の受託企業に仕事の一部が回っていると報じられている[S14]。パッケージ基板でも、イビデンが、AIサーバー向けの高機能ICパッケージ基板の生産能力を増やすため、2026〜2028年度に約5,000億円を投じる計画を公表した[S9]。

試験の工程も重くなっている。アドバンテストは、AIや高性能計算（HPC）の広がりで、回路の微細化と先端パッケージが進み、試験の量と工程が増えると説明している[S4]。アドバンテストは、チップを横に並べる2.5次元や、積み重ねる3次元のパッケージへの移行が加速しているとも述べている[S4]。日本マイクロニクスは、HBMを中心とするDRAM向けのプローブカードの需要が強いとしている[S8]。

## 日本企業の位置

日本企業は、生成AI向けの半導体のうち、後工程の装置と材料で役割を担う。下の表に、公開資料で生成AIやHBMとの関わりを確かめられた企業を、工程ごとにまとめた。

ウェーハを薄く削って切り分ける工程では、ディスコが研削と切断の装置を作る[S5]。チップを樹脂で封止する工程では、TOWAが装置を作る。TOWAは、2023年にHBMの増産の投資が受注の伸びに寄与したとし、2025年4〜9月期にもAI・データセンター向けの需要で受注が回復したとしている[S6][S7]。

パッケージ基板では、イビデンが基板を作る。同社の増産の計画は、第1期として約2,200億円を投じ、岐阜県の工場で2027年度から順に稼働させる内容である[S9]。味の素は、基板の層間の絶縁材ABFを作る。ABFは、CPUやGPUなどの高性能なチップのパッケージ基板に広く使われている[S10][S11]。レゾナックも、後工程の材料を手がける[S12]。

試験と検査では、アドバンテストが試験装置を、日本マイクロニクスがプローブカードを作る[S4][S8]。

表の企業の多くは、生成AI向け以外の半導体にも、装置と材料を売っている。生成AI向けの売上の割合は、各社の資料で示されていないことが多い。このため、表は生成AIとの関わりがあることを示すもので、その売上の大きさを示すものではない。

表には、構図を示すために、掲載企業の外から、HBMを製造するSKハイニックスと、先端パッケージを手がけるTSMCも載せた。

## 論点と今後の注目点

### 発表元の見方

WSTSは、2027年もAIへの投資が続き、汎用のサーバー、産業機器、自動車の需要も加わって、市場の拡大が続くと見ている。一方で、物価の上昇が長引くことと、地政学的な不確実性を、予測を下振れさせる要因に挙げている[S1]。アドバンテストは、2024年以降、半導体の複雑化で半導体と試験装置の市場が大きく伸び、自社の2025年度の売上と利益が過去最高になったとしている。そのうえで、中長期でも変動を伴いながら成長が続くと見ている[S4]。日本マイクロニクスは、生成AIが半導体の市場をけん引し、DRAMの数量が2026〜2030年に年平均16%伸びると見込んでいる（同社の試算）[S8]。

### 本サイトの見方

1つ目の論点は、生成AI向けの半導体の供給を決める場所が、回路の微細化から、HBMと先端パッケージに広がったことである。しかし、演算チップとHBMを1つにまとめる今の形では、後工程の能力が、そのまま最終の製品の数を左右する。後工程の装置と材料に強い日本企業にとって、関わる場面が増える変化といえる。

2つ目の論点は、需要の振れ幅である。2026年の市場の伸びの多くは、メモリによるものと予測されている[S1]。この伸びは、データセンターへの投資の勢いに大きく左右される。投資の勢いが変わったときに、メモリと、後工程の装置と材料の需要がどう動くかは、注目しておきたい点である。

3つ目の論点は、パッケージの大型化と新しい形である。演算チップとHBMを多く載せるほど、インターポーザとパッケージ基板は大きくなる。TSMCは、角形の大きなパネルを使う新しい先端パッケージ（CoPoS）の装置を、2026年半ばに入れると報じられている[S14]。ウェーハの形からパネルの形への移行が進めば、必要な装置と材料も変わる。日本の装置と材料の企業が、この変化にどう応じるかが、次の注目点である。
