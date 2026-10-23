---
theme: advanced-packaging
title: 先端パッケージとチップレット
description: 複数のチップを1つのパッケージにまとめる先端パッケージが、AI向けの半導体で広がる。装置の市場の動き、中継の基板の大型化とパネルへの移行、日本企業の位置と論点をまとめたレポート。
criteria: 先端パッケージやチップレットに使う材料・基板、露光や組み立ての装置、設計に関わることを、公開資料で確かめられる企業を載せる。共同の開発の枠組みJOINT3の参加企業も含める。
groups:
  - label: チップレットの設計
    process: circuit-design
    companies:
      - company: socionext
        role: チップレットや先端パッケージに対応した設計に取り組む。
        basis: [S12]
    others:
      - name: シノプシス
        name_en: Synopsys
        region: 米国
        role: 設計のツールの企業として、JOINT3に参加する。
        basis: [S3]
  - label: インターポーザーと基板の材料
    process: advanced-packaging
    companies:
      - company: resonac
        role: 感光性のフィルムで有機のインターポーザーの細かい配線を作る。JOINT3の中心となる。
        basis: [S3, S8]
      - company: kyocera
        role: チップレット向けのセラミックを芯にした基板や、大型で層の多い有機のパッケージを開発する。
        basis: [S9]
  - label: 配線を描く露光と組み立ての装置
    process: advanced-packaging
    companies:
      - company: tokyo-electron
        role: 先端パッケージ向けの装置を手がけ、JOINT3に参加する。
        basis: [S3, S13]
      - company: nikon
        role: 先端パッケージ向けに、大型の基板に対応するデジタルの露光装置を開発する。
        basis: [S11]
      - company: ushio
        role: JOINT3に参加する。
        basis: [S3]
      - company: screen
        role: 先端パッケージ向けの直接描画の露光装置「DW-3100」を開発した。
        basis: [S10]
    others:
      - name: ASMPT
        region: シンガポール
        role: JOINT3に参加する。
        basis: [S3]
  - label: 先端パッケージを作る企業
    others:
      - name: TSMC
        name_en: Taiwan Semiconductor Manufacturing Company
        region: 台湾
        role: 先端パッケージ「CoWoS」を手がけ、樹脂と銅の配線の層を使う形にも広げた。
        basis: [S2]
      - name: Rapidus
        region: 日本
        role: 600ミリメートル角のパネルを使う配線の層を試作し、2028年度に先端パッケージの量産を始める計画である。
        basis: [S5]
processes: [advanced-packaging, circuit-design]
terms: [chiplet, interposer, bump, tsv]
learn:
  - { folder: process, ref: advanced-packaging }
  - { folder: process, ref: interconnect }
published_at: '2026-10-23'
draft: true
ai_generated: true
sources:
  - id: S1
    title: Global Semiconductor Equipment Sales Forecast to Reach a Record $229 Billion in 2028, SEMI Reports
    publisher: SEMI
    url: https://www.semi.org/en/semi-press-release/global-semiconductor-equipment-sales-forecast-to-reach-a-record-229-billion-dollars-in-2028-semi-reports
    published_on: '2026-07-14'
    accessed_on: '2026-10-23'
  - id: S2
    title: CoWoS
    publisher: TSMC
    url: https://3dfabric.tsmc.com/english/dedicatedFoundry/technology/cowos.htm
    accessed_on: '2026-10-23'
  - id: S3
    title: "NEDOの手を離れ本格ビジネスへ レゾナックが27社参画の「JOINT3」設立：大型有機インターポーザー開発加速"
    publisher: EE Times Japan
    url: https://eetimes.itmedia.co.jp/ee/articles/2509/08/news094.html
    published_on: '2025-09-08'
    accessed_on: '2026-10-23'
  - id: S4
    title: "NEDOの手を離れ本格ビジネスへ レゾナックが27社参画の「JOINT3」設立（2ページ目）"
    publisher: EE Times Japan
    url: https://eetimes.itmedia.co.jp/ee/spv/2509/08/news094_2.html
    published_on: '2025-09-08'
    accessed_on: '2026-10-23'
  - id: S5
    title: "経産省、Rapidusへの4000億円追加出資計画を明かす：2nm量産に向け自己資本強化"
    publisher: EE Times Japan
    url: https://eetimes.itmedia.co.jp/ee/spv/2610/20/news052_2.html
    published_on: '2026-10-20'
    accessed_on: '2026-10-23'
  - id: S6
    title: Status of the Advanced Packaging Industry 2025
    publisher: Yole Group
    url: https://www.yolegroup.com/product/report/status-of-the-advanced-packaging-industry-2025/
    accessed_on: '2026-10-23'
  - id: S7
    title: Advanced Packaging Market Set to Reach $79.4B by 2030
    publisher: Microwave Journal（Yole Groupの発表）
    url: https://www.microwavejournal.com/articles/44658-advanced-packaging-market-set-to-reach-794b-by-2030
    published_on: '2025-09-02'
    accessed_on: '2026-10-23'
  - id: S8
    title: 有価証券報告書（2025年12月期）
    publisher: レゾナック・ホールディングス
    url: https://disclosure2dl.edinet-fsa.go.jp/searchdocument/pdf/S100XTT8.pdf
    published_on: '2026-03-25'
    accessed_on: '2026-10-23'
    doc_id: S100XTT8
  - id: S9
    title: 有価証券報告書（2026年3月期）
    publisher: 京セラ
    url: https://disclosure2dl.edinet-fsa.go.jp/searchdocument/pdf/S100YF47.pdf
    published_on: '2026-06-19'
    accessed_on: '2026-10-23'
    doc_id: S100YF47
  - id: S10
    title: 有価証券報告書（2026年3月期）
    publisher: SCREENホールディングス
    url: https://disclosure2dl.edinet-fsa.go.jp/searchdocument/pdf/S100YK9N.pdf
    published_on: '2026-06-25'
    accessed_on: '2026-10-23'
    doc_id: S100YK9N
  - id: S11
    title: 有価証券報告書（2026年3月期）
    publisher: ニコン
    url: https://disclosure2dl.edinet-fsa.go.jp/searchdocument/pdf/S100YKBP.pdf
    published_on: '2026-06-25'
    accessed_on: '2026-10-23'
    doc_id: S100YKBP
  - id: S12
    title: 有価証券報告書（2026年3月期）
    publisher: ソシオネクスト
    url: https://disclosure2dl.edinet-fsa.go.jp/searchdocument/pdf/S100YHHK.pdf
    published_on: '2026-06-23'
    accessed_on: '2026-10-23'
    doc_id: S100YHHK
  - id: S13
    title: 有価証券報告書（2026年3月期）
    publisher: 東京エレクトロン
    url: https://disclosure2dl.edinet-fsa.go.jp/searchdocument/pdf/S100YEOO.pdf
    published_on: '2026-06-22'
    accessed_on: '2026-10-23'
    doc_id: S100YEOO
---
## 要旨

- AI向けの半導体では、複数のチップを1つのパッケージにまとめる先端パッケージが広がっている。国際的な業界団体のSEMIは、組立・パッケージングの装置の販売額が、2026年に前の年より9.6%増えて67億ドルになり、2028年に86億ドルに達すると予測する[S1]。
- 課題の中心は、チップを並べる中継の基板（インターポーザー）の大型化である。300ミリメートルのウェーハからは大きなインターポーザーが4個しか取れないが、510×515ミリメートルの角形のパネルなら24個取れる[S4]。
- 日本では、レゾナックが国内外の27社と共同の開発の枠組み「JOINT3」を立ち上げ、Rapidusも600ミリメートル角のパネルを使う配線の層の試作に成功した[S3][S5]。日本企業は、材料、露光、装置、設計で関わる。

## 市場の動き

SEMIの2026年7月の予測では、後工程の装置の販売が伸びる。組立・パッケージングの装置は、2025年に前の年より20.8%増え、2026年は9.6%増の67億ドル、2028年には86億ドルになる見込みである（図1）[S1]。試験の装置は、2025年に55.3%増え、2026年は31.0%増の153億ドル、2028年には208億ドルになる見込みである[S1]。SEMIは、伸びの理由として、AIに関わる需要、先端のパッケージや異なる種類のチップを組み合わせるパッケージの採用、AIとHBM（広帯域メモリ）に求められる性能と信頼性の厳しさを挙げる[S1]。

フランスの調査会社Yoleグループは、先端パッケージの市場が2030年に794億ドルになると見ている[S7]。分野別では、通信とインフラの分野が2024〜2030年の伸びが14.9%で最も高く、その理由に、AIのアクセラレータ、GPU、クラウドとデータセンターの需要、チップレットを使う設計を挙げる[S7]。

チップレットは、大きな回路を機能ごとの小さなチップに分けて作り、1つのパッケージの中で組み合わせて1つの製品として動かす方式である。機能ごとに合った製造の技術を選べ、小さなチップは不良の影響を受けにくい。この方式が広がるほど、チップどうしをつなぐパッケージの技術の重みが増す。パッケージは、チップを守って基板につなぐ部品から、製品の性能を決める部分の1つに変わりつつある。

## バリューチェーン

先端パッケージでは、チップを作る前の工程と、組み立てる後の工程の間に、新しい段階が加わる（図2）。演算のチップとメモリを並べ、細かい配線でつなぐ中継の基板（インターポーザー）を作る段階である。インターポーザーをパッケージの基板に載せ、最後に試験して完成する。

TSMCの先端パッケージ「CoWoS」は、この形の代表である。CoWoSは2012年に量産を始め、当初はシリコンのインターポーザーを使った。シリコンのインターポーザーの大きさは、回路を一度に焼き付ける範囲の3.3倍、約2,700平方ミリメートルまでである[S2]。より大きくするため、TSMCは、樹脂と銅で配線の層（RDL）を作る形を2023年に、小さなシリコンの部品を埋め込む形を2024年に量産に移した[S2]。CoWoSの用途は、GPUやAIのアクセラレータなどの高性能の計算である。これまでに使われた製品には、NVIDIAのGPUのほか、富士通のプロセッサ「A64FX」も含まれる[S2]。

インターポーザーの大型化は、作り方の変化を促す。AI向けの半導体では、載せるチップの数が増え、インターポーザーが大きくなる。レゾナックによると、300ミリメートルのウェーハからは、約73×108ミリメートルのインターポーザーが4個しか取れず、歩留まりも悪い。510×515ミリメートルのパネルなら、1枚から24個取れる[S4]。一方で、パネルにすると、反りが大きくなる、位置を合わせる精度を保ちにくい、樹脂を面の中で均一に塗りにくい、といった課題がある[S4]。この課題を解くため、材料、装置、設計の企業が組んで開発する場として、JOINT3が作られた[S4]。

## 日本企業の位置

JOINT3は、レゾナックが中心となり、国内外の27社が参加する。総事業費は260億円、期間は5年の予定で、東京エレクトロン、ウシオ電機、米国のシノプシス、シンガポールのASMPTなどが加わる[S3]。茨城県結城市のレゾナックの下館事業所に開発の拠点を設け、2026年に試作のラインを動かす予定である[S4]。2021年に日本企業14社で作った前の枠組み「JOINT2」の技術を土台にする[S3]。

材料では、レゾナックが、高い解像度の感光性のフィルムで、有機のインターポーザーの細かい銅の配線を作る[S8]。京セラは、チップレット向けのセラミックを芯にした基板や、大型で層の多い有機のパッケージを開発している[S9]。

配線を描く露光の装置では、SCREENホールディングスが先端パッケージ向けの直接描画の露光装置「DW-3100」を開発した[S10]。ニコンも、先端パッケージ向けに、大型の基板に対応するデジタルの露光装置を開発している[S11]。東京エレクトロンは、前の工程の装置に加えて、先端パッケージ向けの装置も手がける[S13]。設計では、ソシオネクストが、チップレットや先端パッケージに対応した設計に取り組む[S12]。

作る側では、Rapidusが、600ミリメートル角のパネルを使ったRDLのインターポーザーの試作に成功し、2028年度に先端パッケージの量産を始める計画である[S5]。千歳の拠点で、前の工程と後の工程を一貫して手がける形を目指す[S5]。

## 論点と今後の注目点

### 発表元の見方

SEMIは、AIに関わる需要と、先端のパッケージの採用が、後工程の装置の伸びを支えると見ている[S1]。

Yoleグループは、業界の取り組みが、チップレットの規格をそろえる方向に向かっていると指摘する。規格がそろえば、採用が広がり、各社の投資の負担も軽くなるとの見方である[S6]。

JOINT3は、国の助成を受けず、市場の動きに合わせて開発の目標を決め、直し、事業の獲得を主な目的とする[S3]。

### 本サイトの見方

1つ目の論点は、ウェーハからパネルへの移行の時期である。パネルは取れる数で有利だが、反りや位置合わせの課題がある。試作のラインの評価の結果と、実際の製品への採用の発表が、移行の速さを決める。パネルの大きさがそろわなければ、装置と材料の企業は複数の大きさに対応する負担を負う。TSMCのRDLの形のように、ウェーハのままで大型化を進める道もある[S2]。ウェーハの形とパネルの形が、当面は並んで使われる可能性もあり、装置と材料の企業は両方への備えを求められる。

2つ目の論点は、日本の共同の開発の形である。JOINT3は、材料の企業が中心となり、装置と設計の企業を海外からも集めた。国の助成に頼らず事業の獲得を目指す点は、前の枠組みと違う。参加企業の製品が、どの顧客の量産のラインに入るかが、成果を測る目安になる。

3つ目の論点は、前の工程と後の工程の境目が薄れることである。TSMCは前の工程の会社だが、先端パッケージも手がける。Rapidusも前後の工程の一貫を目指す。日本では、東京エレクトロンのような前の工程の装置の会社も、先端パッケージ向けの装置を手がける。後の工程の装置と材料の企業にとっては、取引先と競争相手の顔ぶれが変わる可能性がある。

4つ目の論点は、規格である。チップレットを異なる会社の間で組み合わせるには、チップどうしをつなぐ決まりをそろえる必要がある。規格がそろうほど、設計の会社が使えるチップの選択肢が広がる。日本の設計の会社と後の工程の会社にとって、規格づくりへの関わり方が問われる。
