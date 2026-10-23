---
theme: materials-geopolitics
title: 材料の地政学
description: 日本が強みを持つ半導体の材料は、輸出管理や原料の偏りの影響を受けやすい。市場の動き、工程ごとの材料と原料、日本企業の位置と論点をまとめたレポート。
criteria: 輸出管理や供給の偏りが公的機関の資料か報道で取り上げられた半導体材料（フォトレジスト、高純度のガス、ウェーハなど）を製造・供給していることを、公開資料で確かめられる企業を載せる。
groups:
  - label: シリコンウェーハ
    process: wafer
    companies:
      - company: shin-etsu-chemical
        role: 半導体用のシリコンウェーハ、フォトレジスト、マスクブランクスを作る。
        basis: [S10]
      - company: sumco
        role: 半導体用のシリコンウェーハ（鏡面のウェーハとエピタキシャルウェーハ）を作る。
        basis: [S11]
  - label: 露光の材料
    process: lithography
    companies:
      - company: tokyo-ohka-kogyo
        role: EUV用やArF用などのフォトレジストを作る。郡山工場に新しい製造棟を建てた。
        basis: [S12, S13]
  - label: マスクの材料
    process: photomask
    companies:
      - company: hoya
        role: 半導体用のマスクブランクスを作る。
        basis: [S14]
  - label: エッチングと洗浄の薬品・ガス
    process: etching
    companies:
      - company: stella-chemifa
        role: 半導体用の高純度フッ化水素を、国内とシンガポールで作る。
        basis: [S16]
      - company: kanto-denka-kogyo
        role: 回路のエッチングに使う特殊ガス（C4F6など）を作る。
        basis: [S17]
      - company: nippon-sanso
        role: グループの大陽日酸が、半導体の製造に使う特殊ガスを供給する。
        basis: [S18]
  - label: 研磨と後工程の材料
    process: cmp
    companies:
      - company: resonac
        role: 高純度ガス、CMPスラリー、封止材など、前工程と後工程の材料を作る。
        basis: [S15]
processes: [wafer, lithography, photomask, etching, cmp]
terms: [silicon-wafer, photoresist, photomask, dry-etching, slurry]
learn:
  - { folder: materials, ref: process-materials }
  - { folder: materials, ref: thin-film-materials }
published_at: '2026-10-23'
draft: false
ai_generated: true
sources:
  - id: S1
    title: 2025年の世界半導体材料市場、過去最高の732億ドルに到達
    publisher: SEMI
    url: https://www.semi.org/jp/news-resources/press/20260514
    published_on: '2026-05-14'
    accessed_on: '2026-10-23'
    kind: association
  - id: S2
    title: 24年の半導体材料市場は675億ドル 日本だけが市場縮小：SEMIが発表
    publisher: EE Times Japan
    url: https://eetimes.itmedia.co.jp/ee/spv/2505/02/news052.html
    published_on: '2025-05-02'
    accessed_on: '2026-10-23'
  - id: S3
    title: 半導体・デジタル産業戦略
    publisher: 経済産業省
    url: https://www.meti.go.jp/policy/mono_info_service/joho/conference/semicon_digital/20210603008-1.pdf
    published_on: '2021-06-04'
    accessed_on: '2026-10-23'
    kind: government
    pages: 3〜4
  - id: S4
    title: 経産省、韓国向け輸出管理の運用見直しを開始
    publisher: 日本貿易振興機構（ジェトロ）
    url: https://www.jetro.go.jp/biznews/2019/07/129214968482911f.html
    published_on: '2019-07-04'
    accessed_on: '2026-10-23'
    kind: government
  - id: S5
    title: 西村経済産業大臣の閣議後記者会見の概要（2023年3月17日）
    publisher: 経済産業省
    url: https://www.meti.go.jp/speeches/kaiken/2022/20230317001.html
    published_on: '2023-03-17'
    accessed_on: '2026-10-23'
    kind: government
  - id: S6
    title: 商務部、2種のレアメタル関連品目に輸出管理を実施、8月1日から（中国）
    publisher: 日本貿易振興機構（ジェトロ）
    url: https://www.jetro.go.jp/biznews/2023/07/74e08dd9a1764e80.html
    published_on: '2023-07-04'
    accessed_on: '2026-10-23'
    kind: government
  - id: S7
    title: レアアース関連品目など複数品目を輸出管理の対象に追加（中国）
    publisher: 日本貿易振興機構（ジェトロ）
    url: https://www.jetro.go.jp/biznews/2025/10/3a7a2bf6c59d3180.html
    published_on: '2025-10-14'
    accessed_on: '2026-10-23'
    kind: government
  - id: S8
    title: 半導体（経済安全保障推進法に基づく特定重要物資）
    publisher: 経済産業省
    url: https://www.meti.go.jp/policy/economy/economic_security/semicon/index.html
    accessed_on: '2026-10-23'
    kind: government
  - id: S9
    title: 第5回 半導体・デジタル産業戦略検討会議 資料3
    publisher: 経済産業省
    url: https://www.meti.go.jp/policy/mono_info_service/joho/conference/semicon_digital/0005/03.pdf
    published_on: '2022-04-01'
    accessed_on: '2026-10-23'
    kind: government
    pages: '4'
  - id: S10
    title: 有価証券報告書（2026年3月期）
    publisher: 信越化学工業
    url: https://disclosure2dl.edinet-fsa.go.jp/searchdocument/pdf/S100YE9I.pdf
    published_on: '2026-06-19'
    accessed_on: '2026-10-23'
    doc_id: S100YE9I
  - id: S11
    title: 有価証券報告書（2025年12月期）
    publisher: SUMCO
    url: https://disclosure2dl.edinet-fsa.go.jp/searchdocument/pdf/S100XRR5.pdf
    published_on: '2026-03-26'
    accessed_on: '2026-10-23'
    doc_id: S100XRR5
  - id: S12
    title: 有価証券報告書（2025年12月期）
    publisher: 東京応化工業
    url: https://disclosure2dl.edinet-fsa.go.jp/searchdocument/pdf/S100XT0N.pdf
    published_on: '2026-03-24'
    accessed_on: '2026-10-23'
    doc_id: S100XT0N
  - id: S13
    title: 「世界最大級」フォトレジスト製造棟が完成 東京応化工業
    publisher: EE Times Japan
    url: https://eetimes.itmedia.co.jp/ee/articles/2610/13/news027.html
    published_on: '2026-10-13'
    accessed_on: '2026-10-23'
  - id: S14
    title: 有価証券報告書（2026年3月期）
    publisher: HOYA
    url: https://disclosure2dl.edinet-fsa.go.jp/searchdocument/pdf/S100Y90T.pdf
    published_on: '2026-06-05'
    accessed_on: '2026-10-23'
    doc_id: S100Y90T
  - id: S15
    title: 有価証券報告書（2025年12月期）
    publisher: レゾナック・ホールディングス
    url: https://disclosure2dl.edinet-fsa.go.jp/searchdocument/pdf/S100XTT8.pdf
    published_on: '2026-03-25'
    accessed_on: '2026-10-23'
    doc_id: S100XTT8
  - id: S16
    title: 2025年3月期 決算説明資料
    publisher: ステラケミファ
    url: https://www2.jpx.co.jp/disc/41090/140120250509536311.pdf
    published_on: '2025-05-09'
    accessed_on: '2026-10-23'
    pages: 6、24〜27
  - id: S17
    title: 半導体ガス増産、関電化が400億円投資で需要急増に備え
    publisher: ニュースイッチ（日刊工業新聞）
    url: https://newswitch.jp/p/37282
    published_on: '2023-06-13'
    accessed_on: '2026-10-23'
  - id: S18
    title: 大陽日酸 AI投資拡大で特殊ガス事業堅調 26年に向け新たな商材にチャレンジ
    publisher: 電波新聞
    url: https://dempa-digital.com/?p=704124
    published_on: '2026-01-01'
    accessed_on: '2026-10-23'
---
## 要旨

- 2025年の世界の半導体材料の市場は、過去最高の732億ドル（前年比＋6.8%）だった。材料を最も多く使う地域は台湾で、中国、韓国が続く[S1]。日本国内の材料の市場は、2024年に主要な地域で唯一縮んだ[S2]。
- 日本の材料メーカーは、シリコンウェーハ、フォトレジスト、マスクブランクス、高純度の薬品とガスを供給している。経済産業省は、日本の製造装置と材料を、半導体のサプライチェーンの「チョークポイント」と位置づける[S3]。
- 材料は、各国の輸出管理の対象になってきた。日本の韓国向けの3品目（2019年）、中国のガリウム・ゲルマニウム（2023年）など、材料の流れは政策で変わる[S4][S6]。日本は、半導体の材料と原料を、経済安全保障の対象に加えている[S8]。

## 市場の動き

国際半導体製造装置材料協会（SEMI）によると、2025年の世界の半導体材料の市場は732億ドルで、前年比＋6.8%と過去最高だった。このうち、ウェーハの上に回路を作る前工程の材料は458億ドル（＋5.4%）、チップを組み立てる後工程の材料は274億ドル（＋9.3%）だった[S1]。前工程の材料が市場の6割あまりを占めるが、2025年の伸びは後工程の材料のほうが大きかった。

地域別では、台湾が217億ドルで16年続けて最大の市場だった。中国が156億ドルで2位となり、2桁の伸びを示した。韓国は112億ドルで3位だった[S1]。材料の市場は、材料を使う工場のある地域で数えるため、半導体の工場が集まる東アジアに大きく偏る（図1）。

一方、日本国内の材料の市場は、2024年に65億ドル（前年比−3.2%）で5位だった。この年に市場が縮んだのは、主要な地域の中で日本だけだった[S2]。国内の工場で使う材料は少ないが、日本の材料メーカーは、海外の工場にも材料を供給している。

国内でも、生産能力を増やす動きがある。東京応化工業は、福島県の郡山工場に、フォトレジストの新しい製造棟を完成させた。EUV用やArF用のレジストを作り、2026年11月に稼働する予定で、投資額は約230億円である[S13]。関東電化工業は、エッチングに使う特殊ガス（C4F6）の生産量を1.5倍に増やす計画を、2023年に明らかにしている[S17]。

## バリューチェーン

半導体の材料は、工程ごとに種類が分かれる。回路を作る土台となるシリコンウェーハ、回路の形を写すフォトレジストとマスクの材料、不要な部分を削るエッチングのガスや洗浄の薬品、表面を平らにする研磨の材料（CMPスラリー）、そして後工程の封止材や基板の材料である（図2）。

これらの材料には、さらに上流の原料がある。経済産業省は、経済安全保障推進法の特定重要物資として半導体を指定し、供給を確保するための支援の対象に、半導体の材料・部品と、原料を含めた。原料として挙げられているのは、黄リンとその誘導品、ヘリウム、ネオン、クリプトン、キセノン、蛍石とその誘導品である[S8]。

原料の調達には、地政学の影響が表れやすい。経済産業省の2022年の資料によると、日本が輸入するネオン、クリプトン、キセノンの約6%は、ロシアとウクライナの地域からだった[S9]。信越化学工業も、有価証券報告書で、仕入れ先の国の貿易政策が変わると、調達や価格に影響が出るおそれがあるとしている。同社は、原料の調達先を分散して、この影響を抑えるとしている[S10]。

材料そのものも、輸出管理の対象になってきた。日本は2019年7月、韓国向けのフッ化ポリイミド、レジスト、フッ化水素の3品目について、包括的な許可の対象から外し、輸出ごとの許可を求めるようにした[S4]。この運用は、2023年3月に見直され、包括的な許可に戻った[S5]。

中国は、2023年8月から、ガリウムとゲルマニウムの関連品目の輸出に許可を求めるようにした[S6]。さらに中国は、2025年11月から、中重希土類の一部や、人工ダイヤモンドとその製造装置などを、輸出管理の対象に加えた[S7]。

## 日本企業の位置

日本企業は、前工程の材料の多くの段階で、供給を担っている。下の表に、公開資料で半導体向けの材料を作っていることを確かめた企業を、工程ごとにまとめた。

ウェーハでは、信越化学工業とSUMCOが、半導体用のシリコンウェーハを作る[S10][S11]。信越化学工業の電子材料事業の外部顧客向けの売上高は、2026年3月期に1兆157億円で、連結売上高の39.5%を占める[S10]。SUMCOは、表面を鏡面に仕上げたウェーハと、その上に薄い単結晶の層を成長させたエピタキシャルウェーハを、メモリーやロジックのメーカーに供給する[S11]。露光では、東京応化工業がEUV用などのフォトレジストを作り、HOYAが半導体用のマスクブランクスを作る[S12][S14]。信越化学工業も、フォトレジストとマスクブランクスを手がける[S10]。

エッチングと洗浄では、ステラケミファが高純度のフッ化水素を、関東電化工業がエッチング用の特殊ガスを、日本酸素ホールディングスのグループが半導体用の特殊ガスを供給する[S16][S17][S18]。ステラケミファは、半導体用の高純度フッ化水素を、北九州、三宝（堺市）、シンガポールの3拠点で、年に約10万5千トン作れる体制を持つ[S16]。関東電化工業は、韓国と中国の拠点を含めて投資を進めている[S17]。日本酸素ホールディングスのグループの大陽日酸は、2024年に、北海道千歳市のラピダスの工場の敷地に、窒素や酸素などを供給する拠点を開いた[S18]。研磨と後工程では、レゾナックがCMPスラリーや高純度ガス、封止材などを手がける[S15]。

表は、半導体の材料を作っていることを示すもので、それぞれの材料の世界での順位や売上の大きさを示すものではない。また、ここに挙げた企業の多くは、半導体以外の素材や化学品も手がけている。

## 論点と今後の注目点

### 発表元の見方

経済産業省は、日本の製造装置と材料の産業を、半導体のサプライチェーンの「チョークポイント」とし、今も世界で競争力を保っていると評価している[S3]。そのうえで、経済安全保障推進法にもとづき、半導体の材料・部品と原料の供給を確保する計画を支援している。支援の条件には、10年以上の継続的な生産や、需給がひっ迫したときの対応などが含まれる[S8]。

SEMIは、2025年の材料の市場が、中国と北米を中心に、欧州を除く主な地域で伸びたとしている[S1]。

### 本サイトの見方

1つ目の論点は、強みと依存が表裏の関係にあることである。日本の材料メーカーは、海外の工場に材料を供給している一方で、国内の材料の市場は小さく、2024年には縮んだ。材料を使う工場の多くが台湾、中国、韓国にあるため、これらの地域の政策や需要の変化が、日本の材料メーカーにそのまま響く。

2つ目の論点は、上流の原料の偏りである。日本の材料メーカーが力を持つのは、原料を高い純度に精製し、加工する段階である。たとえば、ステラケミファは、不純物を1ppt（1兆分の1）まで減らしたフッ化水素を作るとしている[S16]。その原料の一部は、特定の国や地域から輸入している。経済産業省が原料を特定重要物資の対象に含めたのは、この段階の弱さを示している。中国のガリウム・ゲルマニウムの例のように、原料の輸出管理は、材料と半導体の供給に波及しうる。

3つ目の論点は、国内の生産能力の行方である。北海道千歳市のラピダスの工場のように、国内で新しい工場の立ち上げが進むと、国内で材料を使う量が増える[S18]。東京応化工業の新しい製造棟のように、国内での増産の動きもある。国内の工場の稼働と、材料の国内の生産が、どこまで歩調を合わせるかが、次の注目点である。
