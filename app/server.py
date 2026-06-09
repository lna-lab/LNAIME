"""LNAIME 脳サーバ（v0.2: 校正 + 変換 API）。コンテナ駆動・ローカル。"""
from __future__ import annotations

import difflib
import os

from fastapi import FastAPI
from pydantic import BaseModel

from convert import faithful_convert, input_katakana, zenz_convert
from koetsu import Koetsu
from romaji import romaji_to_hiragana

MASTER = os.environ.get("LNAIME_MASTER", "/app/dict/master.yaml")

app = FastAPI(title="LNAIME brain", version="0.2")
engine = Koetsu(MASTER)


class CheckReq(BaseModel):
    text: str


class ConvertReq(BaseModel):
    reading: str = ""          # ひらがな読み
    input: str = ""            # ローマ字（指定時は かな化して reading に）
    context: str = ""          # 左文脈
    right_context: str = ""    # 右文脈（v3.2）
    profile: str = ""
    topic: str = ""
    style: str = ""
    preference: str = ""
    faithful: bool = False     # true = 純lattice(忠実保証, CPU)。既定=ハイブリッド


@app.get("/health")
def health():
    return {"ok": True, "terms": len(engine.terms), "master": MASTER}


@app.post("/dict/reload")
def reload_dict():
    return {"ok": True, "terms": engine.load()}


@app.post("/check")
def check(req: CheckReq):
    return {"diagnostics": engine.check(req.text)}


def _lattice_convert(req: ConvertReq) -> dict:
    """Tier-2: 読み忠実ラティス（固有辞書を lattice に注入、読みを構造的に破らない）。"""
    userdict = [{"word": t["canonical"], "reading": t["reading"]}
                for t in engine.terms if t.get("pos") == "固有名詞"]
    r = faithful_convert(req.reading, userdict=userdict,
                         left_context=req.context, profile=req.profile)
    return {"reading": req.reading, "converted": r.get("best"),
            "candidates": [c.get("text") for c in r.get("candidates", [])],
            "faithful": r.get("faithful"), "engine": "lattice"}


@app.post("/convert")
def convert(req: ConvertReq):
    if req.input and not req.reading:      # ローマ字 → ひらがな
        req.reading = romaji_to_hiragana(req.input)
    if req.faithful:                       # 純 lattice（忠実保証）を明示指定
        try:
            return _lattice_convert(req)
        except Exception as e:
            return {"error": str(e), "hint": "docker compose up -d convert-faithful"}

    # ハイブリッド: 生成(品質・context活用) → 読み忠実ゲート → 破れたら lattice(保証)へ
    profile = req.profile or (
        "固有名詞: " + "、".join(engine.proper_nouns) if engine.proper_nouns else "")
    gen = None
    try:
        gen = zenz_convert(req.reading, req.context, profile,
                           req.topic, req.style, req.preference, req.right_context)
        target = input_katakana(req.reading)
        gr = engine.reading_of(gen)
        ratio = 1.0 if gr == target else difflib.SequenceMatcher(None, gr, target).ratio()
        if ratio >= 0.9:   # 完全一致 / Sudachi多重読み(私=わたし/わたくし 等)の許容差
            return {"reading": req.reading, "converted": gen, "faithful": True,
                    "engine": "generative", "reading_match": round(ratio, 3)}
    except Exception:
        pass
    try:                                   # 生成が読みを破った/不可 → lattice へフォールバック
        out = _lattice_convert(req)
        out["engine"] = "lattice(fallback)"
        return out
    except Exception as e:
        if gen is not None:                # 両不可ではない: 生成は出たが lattice 不可 → 未保証で返す
            return {"reading": req.reading, "converted": gen,
                    "faithful": False, "engine": "generative(unverified)"}
        return {"error": str(e), "hint": "convert / convert-faithful を起動してください"}
