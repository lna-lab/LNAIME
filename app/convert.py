"""zenz かな漢字変換クライアント（Tier 1: model-only greedy）。

azooKey Zenzai の greedyDecoding と 1:1 のプロンプト protocol（PUAタグ）:
  [U+EE03 profile][U+EE02 left-context] U+EE00 <KATAKANA> U+EE01 → greedy → EOS まで
入力は必ずカタカナ。空白→全角、改行削除。convert コンテナ(llama-server)へ投げる。
※ model-only は概ね正しいが読みを破る場合あり（おだのぶなり→織田信長 等）。
   読み忠実の保証は Zenzai ラティス（Tier 2 / Swift azooKey エンジン）が必要。
"""
from __future__ import annotations

import json
import os
import socket
import urllib.request

CONVERT_URL = os.environ.get("LNAIME_CONVERT_URL", "http://convert:8000/completion")

# PUA 制御タグ（不可視なので codepoint で明示）
EE_IN = chr(0xEE00)       # inputTag
EE_OUT = chr(0xEE01)      # outputTag
EE_CTX = chr(0xEE02)      # left-context
EE_PROFILE = chr(0xEE03)  # profile


def hira_to_kata(s: str) -> str:
    return "".join(chr(ord(c) + 0x60) if 0x3041 <= ord(c) <= 0x3096 else c for c in s)


def _pre(s: str) -> str:
    return s.replace(" ", "　").replace("\n", "")


def input_katakana(reading: str) -> str:
    """変換に渡るカタカナ入力（読み忠実チェックの基準）。"""
    return _pre(hira_to_kata(reading))


def build_prompt(reading: str, left_context: str = "", profile: str = "") -> str:
    p = ""
    if profile:
        p += EE_PROFILE + _pre(profile)[-25:]      # 条件は .suffix(25)
    if left_context:
        p += EE_CTX + _pre(left_context)[-40:]     # 文脈は .suffix(40)
    p += EE_IN + _pre(hira_to_kata(reading)) + EE_OUT
    return p


def zenz_convert(reading: str, left_context: str = "", profile: str = "",
                 n_predict: int = 96) -> str:
    prompt = build_prompt(reading, left_context, profile)
    body = json.dumps({"prompt": prompt, "n_predict": n_predict,
                       "temperature": 0, "top_k": 1, "cache_prompt": True}).encode()
    req = urllib.request.Request(CONVERT_URL, body, {"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r).get("content", "")


# ---- Tier-2: faithful lattice converter (Swift Zenzai) over TCP JSON-Lines ----
FAITHFUL_ADDR = os.environ.get("LNAIME_FAITHFUL_ADDR", "convert-faithful:8000")


def faithful_convert(reading: str, userdict=None, left_context: str = "",
                     profile: str = "", n: int = 8) -> dict:
    host, _, port = FAITHFUL_ADDR.rpartition(":")
    req = {"reading": reading, "n": n}
    if userdict:
        req["userdict"] = userdict
    if left_context:
        req["left"] = left_context
    if profile:
        req["profile"] = profile
    payload = (json.dumps(req, ensure_ascii=False) + "\n").encode("utf-8")
    with socket.create_connection((host, int(port)), timeout=30) as s:
        s.sendall(payload)
        buf = b""
        while b"\n" not in buf:
            chunk = s.recv(4096)
            if not chunk:
                break
            buf += chunk
    return json.loads(buf.split(b"\n", 1)[0].decode("utf-8"))
