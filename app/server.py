"""LNAIME 脳サーバ（v0.2: 校正 + 変換 API）。コンテナ駆動・ローカル。"""
from __future__ import annotations

import os

from fastapi import FastAPI
from pydantic import BaseModel

from convert import input_katakana, zenz_convert
from koetsu import Koetsu

MASTER = os.environ.get("LNAIME_MASTER", "/app/dict/master.yaml")

app = FastAPI(title="LNAIME brain", version="0.2")
engine = Koetsu(MASTER)


class CheckReq(BaseModel):
    text: str


class ConvertReq(BaseModel):
    reading: str
    context: str = ""
    profile: str = ""


@app.get("/health")
def health():
    return {"ok": True, "terms": len(engine.terms), "master": MASTER}


@app.post("/dict/reload")
def reload_dict():
    return {"ok": True, "terms": engine.load()}


@app.post("/check")
def check(req: CheckReq):
    return {"diagnostics": engine.check(req.text)}


@app.post("/convert")
def convert(req: ConvertReq):
    # profile 未指定なら登録固有名詞を自動注入（= 固有辞書が変換も駆動する）
    profile = req.profile or (
        "固有名詞: " + "、".join(engine.proper_nouns) if engine.proper_nouns else "")
    try:
        converted = zenz_convert(req.reading, req.context, profile)
        out_reading = engine.reading_of(converted)
        return {"reading": req.reading, "converted": converted,
                "output_reading": out_reading,
                "faithful": out_reading == input_katakana(req.reading)}
    except Exception as e:   # convert サービス未起動など
        return {"error": str(e),
                "hint": "docker compose --profile gpu up -d convert"}
