#!/usr/bin/env python3
"""
THE BRIDGE — L0 master 固有辞書を 3つの成果物へ決定論的にコンパイルする。
  1レコード ──┬─▶ (a) prh YAML            … 表記ゆれ校正 (textlint-rule-prh)
              ├─▶ (b) Sudachi ユーザー辞書CSV … 変換 + 表記ゆれ検出 (11=読み, 12=正規化)
              └─▶ (c) azooKey 動的辞書JSON  … ライブ変換バイアス + Zenzai "辞書:" 条件付け

「1つの辞書を3人が食う」を実装する製品の心臓部（最初の骨）。
依存: pyyaml のみ。  使い方: python3 compile_dict.py [master.yaml]
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("pyyaml が必要です:  python3 -m pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MASTER = ROOT / "dict" / "master.yaml"
OUT = ROOT / "dict" / "build"

# POS -> (Sudachi 6列品詞, left_id, right_id, cost, azooKey cid名)
# ※ left/right/cost は SudachiDict 実 lexicon の接続IDへ要差し替え(TODO: sudachipy/ubuild で検証)。
POS_MAP = {
    "固有名詞": (["名詞", "固有名詞", "一般", "*", "*", "*"], 4786, 4786, 7000, "固有名詞"),
    "名詞":     (["名詞", "普通名詞", "一般", "*", "*", "*"], 5146, 5146, 8000, "普通名詞"),
}


def load_terms(master: Path) -> list[dict]:
    data = yaml.safe_load(master.read_text(encoding="utf-8")) or {}
    return data.get("terms", [])


def emit_prh(terms: list[dict]) -> int:
    """variants を持つ語のみ {expected=正規形, patterns=[ゆれ]} ルール化。"""
    rules = [
        {"expected": t["canonical"], "patterns": list(t["variants"])}
        for t in terms if t.get("variants")
    ]
    doc = {"version": 1, "rules": rules}
    (OUT / "prh.yml").write_text(
        yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return len(rules)


def _sudachi_row(surface: str, t: dict) -> str:
    pos6, lid, rid, cost, _ = POS_MAP.get(t["pos"], POS_MAP["名詞"])
    # 0:見出し 1:左ID 2:右ID 3:コスト 4:表示見出し 5-10:品詞 11:読み 12:正規化 13-17:*
    cols = [surface, str(lid), str(rid), str(cost), surface, *pos6,
            t["reading"], t["canonical"], "*", "*", "*", "*", "*"]
    assert len(cols) == 18, f"expected 18 cols, got {len(cols)}"
    return ",".join(cols)


def emit_sudachi(terms: list[dict]) -> int:
    """canonical と各 variant 表記を 1行ずつ。全行の正規化(12列)= canonical。"""
    rows = []
    for t in terms:
        for surface in [t["canonical"], *(t.get("variants") or [])]:
            rows.append(_sudachi_row(surface, t))
    (OUT / "sudachi_user.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return len(rows)


def emit_azookey(terms: list[dict]) -> int:
    """azooKey/Hazkey importDynamicUserDictionary 用 {word, reading, hint?}。
    取込側で DicdataElement(cid=固有名詞, value:-10) になり、Zenzai の "辞書:" にも乗る。"""
    items = []
    for t in terms:
        item = {"word": t["canonical"], "reading": t["reading"]}
        if t.get("comment"):
            item["hint"] = t["comment"]
        items.append(item)
    (OUT / "azookey_userdict.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(items)


def main() -> None:
    master = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_MASTER
    OUT.mkdir(parents=True, exist_ok=True)
    terms = load_terms(master)
    n_prh, n_sud, n_azk = emit_prh(terms), emit_sudachi(terms), emit_azookey(terms)
    print(f"master: {len(terms)} terms  <- {master}")
    print(f"  (a) prh.yml             : {n_prh} 表記ゆれルール")
    print(f"  (b) sudachi_user.csv    : {n_sud} 行 (11=読み / 12=正規化=canonical)")
    print(f"  (c) azookey_userdict.json: {n_azk} 項目 (cid=固有名詞 等, value:-10)")
    print(f"  -> {OUT}")


if __name__ == "__main__":
    main()
