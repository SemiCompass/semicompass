"""AG-23 の確認の処理を確かめる見本。わざと誤りを入れた用語の解説（6件）と、誤りのない解説（3件）。

各見本は、下書きの本文（body）、AG-23 の1回目（reference）の模擬の応答、2回目（judge）の模擬の応答を持つ。
誤りのある見本は、直した本文（fixed_body）と、直した後の2回目の模擬の応答（judge_after）も持つ。
**モデルの精度を測るものではない**（応答は、手で書いた模擬）。処理（表の並び、書き直し、飛ばす条件）の確認と、
運営者が実際のAPIで精度を測る（scripts/draft/measure_ag23.py）ときの入力に使う。
本文には、数字・企業名・出典の番号を入れない（basis: reviewed の決まり）。ただし、数値の誤りの見本は、誤りの内容として数値を含む。
"""


def points(*rows, uncertain=()):
    return {"points": [{"point": p, "confidence": c} for p, c in rows], "uncertain": list(uncertain)}


def claim(text, verdict, reason, risk="low"):
    return {"claim": text, "verdict": verdict, "risk": risk, "reason": reason}


def judged(*claims, note=""):
    return {"claims": list(claims), "summary": {"has_conflict": any(c["verdict"] == "conflicting" for c in claims), "note": note}}


ALD_REF = points(("ALDは、原子層堆積と呼ばれる成膜法である", "high"),
                 ("原料ガスを交互に流し、原子の層を一層ずつ積み重ねて膜を作る", "high"),
                 ("膜の厚さを精密に制御でき、凹凸のある表面にも均一に付きやすい", "medium"),
                 ("エッチングは膜を削る工程で、ALDとは役割が逆である", "medium"))
HBM_REF = points(("HBMは、広帯域メモリーと呼ばれるメモリーである", "high"),
                 ("複数のDRAMチップを縦に積み重ね、シリコン貫通電極で接続する", "high"),
                 ("縦に積むことで、チップ間の配線が短くなり、多くのデータを転送できる", "high"),
                 ("GPUなどの演算チップの近くに載せて使う", "medium"))
CMP_REF = points(("CMPは、化学機械研磨と呼ばれる平坦化の工程である", "high"),
                 ("薬液と研磨剤を使い、ウエハーの表面を削って平らにする", "high"),
                 ("成膜は膜を積む工程で、CMPは表面をならす工程である", "medium"))
EUV_REF = points(("EUV露光は、極端紫外光を使う露光技術である", "high"),
                 ("EUVの光は、従来の紫外光より波長がはるかに短い", "high"),
                 ("波長が短いほど、細かい回路のパターンを描きやすい", "medium"))
OSAT_REF = points(("OSATは、半導体の後工程（組み立てとテスト）を請け負う企業の形態である", "high"),
                  ("設計や前工程（ウエハーの製造）を請け負う形態ではない", "high"),
                  ("ファブレス企業などが、後工程を委託する先になる", "medium"))

S = []


def add(**kw):
    S.append(kw)


# ---- 誤りのない解説（3件） ----
ALD_OK = ("ALDは、原子層堆積と呼ばれる成膜法である。原料ガスを交互に流し、ウエハーの表面に、原子の層を一層ずつ積み重ねて膜を作る。"
          "膜の厚さを精密に制御でき、凹凸のある表面にも均一に付きやすい。")
add(id="ok-ald", name="ALD", errors=[], body=ALD_OK, reference=ALD_REF,
    judge=judged(claim("ALDは、原子層堆積と呼ばれる成膜法である", "consistent", "要点と一致する", "high"),
                 claim("原料ガスを交互に流し、原子の層を一層ずつ積み重ねて膜を作る", "consistent", "要点と一致する", "high"),
                 claim("膜の厚さを精密に制御でき、凹凸のある表面にも均一に付きやすい", "consistent", "要点と一致する")))
HBM_OK = ("HBMは、広帯域メモリーと呼ばれるメモリーである。複数のDRAMチップを縦に積み重ね、シリコン貫通電極で接続する。"
          "チップ間の配線が短くなり、多くのデータを転送できる。GPUなどの演算チップの近くに載せて使う。")
add(id="ok-hbm", name="HBM", errors=[], body=HBM_OK, reference=HBM_REF,
    judge=judged(claim("HBMは、広帯域メモリーと呼ばれるメモリーである", "consistent", "要点と一致する", "high"),
                 claim("複数のDRAMチップを縦に積み重ね、シリコン貫通電極で接続する", "consistent", "要点と一致する", "high"),
                 claim("チップ間の配線が短くなり、多くのデータを転送できる", "consistent", "要点と一致する", "high"),
                 claim("GPUなどの演算チップの近くに載せて使う", "consistent", "要点と一致する")))
CMP_OK = ("CMPは、化学機械研磨と呼ばれる平坦化の工程である。薬液と研磨剤を使い、ウエハーの表面を削って平らにする。"
          "配線や絶縁膜を重ねる前に、表面の凹凸をならすために行う。")
add(id="ok-cmp", name="CMP", errors=[], body=CMP_OK, reference=CMP_REF,
    judge=judged(claim("CMPは、化学機械研磨と呼ばれる平坦化の工程である", "consistent", "要点と一致する", "high"),
                 claim("薬液と研磨剤を使い、ウエハーの表面を削って平らにする", "consistent", "要点と一致する", "high"),
                 claim("配線や絶縁膜を重ねる前に、表面の凹凸をならすために行う", "consistent", "要点の平坦化と一致する")))

# ---- わざと誤りを入れた解説（6件） ----
ERR1 = "ALDは、プラズマを使って、ウエハーの表面の膜を削り取るエッチング法である。"
add(id="err-fact-swap", name="ALD", errors=[{"type": "事実の取り違え（成膜を、エッチングと取り違えた）", "claim": ERR1}],
    body=ERR1 + "原料ガスを交互に流し、原子の層を一層ずつ扱う。膜の厚さを精密に制御できる。", reference=ALD_REF,
    judge=judged(claim(ERR1, "conflicting", "要点：ALDは成膜法。本文は、膜を削るエッチング法としている", "high"),
                 claim("原料ガスを交互に流し、原子の層を一層ずつ扱う", "consistent", "要点と一致する"),
                 claim("膜の厚さを精密に制御できる", "consistent", "要点と一致する")),
    fixed_body="ALDは、原子層堆積と呼ばれる成膜法である。原料ガスを交互に流し、原子の層を一層ずつ扱う。膜の厚さを精密に制御できる。",
    judge_after=judged(claim("ALDは、原子層堆積と呼ばれる成膜法である", "consistent", "要点と一致する", "high"),
                       claim("原料ガスを交互に流し、原子の層を一層ずつ扱う", "consistent", "要点と一致する"),
                       claim("膜の厚さを精密に制御できる", "consistent", "要点と一致する")))
ERR2 = "積層の方式には、逆相積層方式と呼ばれる専用の手法があり、すべての製品で使われている。"
add(id="err-invented-term", name="HBM", errors=[{"type": "存在しない用語の追加（逆相積層方式）", "claim": ERR2}],
    body=HBM_OK + ERR2, reference=HBM_REF,
    judge=judged(claim("HBMは、広帯域メモリーと呼ばれるメモリーである", "consistent", "要点と一致する", "high"),
                 claim("複数のDRAMチップを縦に積み重ね、シリコン貫通電極で接続する", "consistent", "要点と一致する", "high"),
                 claim("チップ間の配線が短くなり、多くのデータを転送できる", "consistent", "要点と一致する", "high"),
                 claim("GPUなどの演算チップの近くに載せて使う", "consistent", "要点と一致する"),
                 claim(ERR2, "not_in_reference", "要点にない。逆相積層方式という用語は、要点にない（幻覚の疑い）", "high")))
ERR3 = "チップを縦に積むことで、チップ間の配線が長くなるため、データの転送が速くなる。"
add(id="err-causality", name="HBM", errors=[{"type": "因果関係の逆転（配線は短くなる）", "claim": ERR3}],
    body="HBMは、広帯域メモリーと呼ばれるメモリーである。複数のDRAMチップを縦に積み重ね、シリコン貫通電極で接続する。" + ERR3
    + "GPUなどの演算チップの近くに載せて使う。", reference=HBM_REF,
    judge=judged(claim("HBMは、広帯域メモリーと呼ばれるメモリーである", "consistent", "要点と一致する", "high"),
                 claim("複数のDRAMチップを縦に積み重ね、シリコン貫通電極で接続する", "consistent", "要点と一致する", "high"),
                 claim(ERR3, "conflicting", "要点：縦に積むと配線は短くなる。本文は、長くなるとしている", "high"),
                 claim("GPUなどの演算チップの近くに載せて使う", "consistent", "要点と一致する")),
    fixed_body="HBMは、広帯域メモリーと呼ばれるメモリーである。複数のDRAMチップを縦に積み重ね、シリコン貫通電極で接続する。"
    "チップ間の配線が短くなり、データの転送が速くなる。GPUなどの演算チップの近くに載せて使う。",
    judge_after=judged(claim("HBMは、広帯域メモリーと呼ばれるメモリーである", "consistent", "要点と一致する", "high"),
                       claim("チップ間の配線が短くなり、データの転送が速くなる", "consistent", "要点と一致する", "high")))
ERR4 = "EUV露光は、波長が約193ナノメートルの光を使う露光技術である。"
add(id="err-number", name="EUV露光", errors=[{"type": "数値の誤り（193ナノメートルは、別の露光の波長）", "claim": ERR4}],
    body=ERR4 + "波長が短いほど、細かい回路のパターンを描きやすい。", reference=EUV_REF,
    judge=judged(claim(ERR4, "conflicting", "要点：EUVは極端紫外光で、従来の紫外光より波長がはるかに短い。193は従来側の値", "high"),
                 claim("波長が短いほど、細かい回路のパターンを描きやすい", "consistent", "要点と一致する")),
    fixed_body="EUV露光は、極端紫外光を使う露光技術である。波長が短いほど、細かい回路のパターンを描きやすい。",
    judge_after=judged(claim("EUV露光は、極端紫外光を使う露光技術である", "consistent", "要点と一致する", "high"),
                       claim("波長が短いほど、細かい回路のパターンを描きやすい", "consistent", "要点と一致する")))
ERR5 = "OSATは、半導体の回路設計だけを請け負う企業の形態である。"
add(id="err-definition", name="OSAT", errors=[{"type": "定義の取り違え（OSATは後工程の受託）", "claim": ERR5}],
    body=ERR5 + "ファブレス企業などが、その委託先になる。", reference=OSAT_REF,
    judge=judged(claim(ERR5, "conflicting", "要点：OSATは後工程（組み立てとテスト）の受託。設計の受託ではない", "high"),
                 claim("ファブレス企業などが、その委託先になる", "consistent", "要点と一致する")),
    fixed_body="OSATは、半導体の後工程（組み立てとテスト）を請け負う企業の形態である。ファブレス企業などが、その委託先になる。",
    judge_after=judged(claim("OSATは、半導体の後工程（組み立てとテスト）を請け負う企業の形態である", "consistent", "要点と一致する", "high"),
                       claim("ファブレス企業などが、その委託先になる", "consistent", "要点と一致する")))
ERR6 = "CMPは、ウエハーの表面に膜を積み重ねる成膜の工程である。"
add(id="err-process-swap", name="CMP", errors=[{"type": "工程の取り違え（CMPは平坦化。成膜ではない）", "claim": ERR6}],
    body=ERR6 + "薬液と研磨剤を使い、表面を平らにする。", reference=CMP_REF,
    judge=judged(claim(ERR6, "conflicting", "要点：CMPは表面を削って平らにする工程。成膜は別の工程", "high"),
                 claim("薬液と研磨剤を使い、表面を平らにする", "consistent", "要点と一致する")),
    fixed_body="CMPは、化学機械研磨と呼ばれる平坦化の工程である。薬液と研磨剤を使い、表面を平らにする。",
    judge_after=judged(claim("CMPは、化学機械研磨と呼ばれる平坦化の工程である", "consistent", "要点と一致する", "high"),
                       claim("薬液と研磨剤を使い、表面を平らにする", "consistent", "要点と一致する")))

# 用語の本文の下限（100字。AG-14 の出力の形式）を満たすため、どの見本にも、誤りのない一文を足す
FILLER = "この用語は、半導体の製造や設計の説明で使われる。入門書でも、基本的な用語として扱われ、工程や関連する用語とあわせて説明される。"
FILLER_CLAIM = claim(FILLER, "consistent", "要点と矛盾しない一般的な説明")
for _s in S:
    _s["body"] += FILLER
    if "fixed_body" in _s:
        _s["fixed_body"] += FILLER
    for _key in ("judge", "judge_after"):
        if _key in _s:
            _s[_key] = {"claims": [*_s[_key]["claims"], FILLER_CLAIM], "summary": _s[_key]["summary"]}

SAMPLES = S
CORRECT = [s for s in S if not s["errors"]]
ERRONEOUS = [s for s in S if s["errors"]]
