"""LNAIME 脳サーバ（v0: 校正 API）。コンテナ駆動・完全ローカル。"""
from __future__ import annotations

import os

from fastapi import FastAPI
from pydantic import BaseModel

from koetsu import Koetsu

MASTER = os.environ.get("LNAIME_MASTER", "/app/dict/master.yaml")

app = FastAPI(title="LNAIME brain", version="0.1")
engine = Koetsu(MASTER)


class CheckReq(BaseModel):
    text: str


@app.get("/health")
def health():
    return {"ok": True, "terms": len(engine.terms), "master": MASTER}


@app.post("/dict/reload")
def reload_dict():
    n = engine.load()
    return {"ok": True, "terms": n}


@app.post("/check")
def check(req: CheckReq):
    return {"diagnostics": engine.check(req.text)}
