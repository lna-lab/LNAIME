"""LNAIME 校正エンジン（決定的層 v0）。

L0 master 固有辞書を「正」として、文書を Sudachi で解析し、決定的な指摘を返す:
  (a) 登録表記ゆれ  : 登録 variant 表記 → canonical へ
  (b) 文書内表記ゆれ: 同一 normalized_form に複数表記（名詞のみ＝活用ゆれを拾わない）
  (c) ら抜き / 用字用語 : rules.yaml の決定的ルール
  (d) 全角英数字     : 半角へ
正の出所は常に L0 登録正規形と規範（Sudachi 既定正規化は検出キーにのみ使う）。
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml
from sudachipy import Dictionary, SplitMode

RULES_PATH = Path(__file__).resolve().parent / "rules.yaml"

# 全角英数 → 半角
_Z2H = str.maketrans({chr(c): chr(c - 0xFEE0)
                      for c in list(range(0xFF21, 0xFF3B))
                      + list(range(0xFF41, 0xFF5B))
                      + list(range(0xFF10, 0xFF1A))})


@dataclass
class Diagnostic:
    line: int
    col: int
    length: int
    surface: str
    rule: str
    message: str
    suggestion: str


class Koetsu:
    def __init__(self, master_path: str):
        self.master_path = Path(master_path)
        self.tok = Dictionary().create()
        self.load()

    def load(self) -> int:
        data = yaml.safe_load(self.master_path.read_text(encoding="utf-8")) or {}
        self.terms = data.get("terms", [])
        self.variant_map: dict[str, str] = {}
        self.canon_set: set[str] = set()
        for t in self.terms:
            self.canon_set.add(t["canonical"])
            for v in (t.get("variants") or []):
                self.variant_map[v] = t["canonical"]
        self.proper_nouns = [t["canonical"] for t in self.terms if t.get("pos") == "固有名詞"]

        # 決定的ルール（ら抜き・用字用語）
        self.literal_rules: list[tuple[str, str, str, str]] = []   # (find, to, category, note)
        rdata = (yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))
                 if RULES_PATH.exists() else {}) or {}
        for cat, name in {"ranuki": "ら抜き", "yougo": "用字用語"}.items():
            for r in rdata.get(cat, []):
                self.literal_rules.append((r["find"], r["to"], name, r.get("note", "")))
        return len(self.terms)

    def check(self, text: str) -> list[dict]:
        lines = text.split("\n")
        occ: list[tuple[str, int, int, str, bool]] = []
        noun_counts: dict[str, Counter] = defaultdict(Counter)

        for li, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            for m in self.tok.tokenize(line, SplitMode.C):
                surf = m.surface()
                if not surf.strip():
                    continue
                norm = m.normalized_form()
                is_noun = m.part_of_speech()[0] == "名詞"
                occ.append((surf, li, m.begin() + 1, norm, is_noun))
                if is_noun:
                    noun_counts[norm][surf] += 1

        canon_for_norm: dict[str, str] = {}
        for norm, counts in noun_counts.items():
            if len(counts) < 2:
                continue
            reg = next((s for s in counts if s in self.canon_set), None)
            # 登録canonical優先 → なければ「送り仮名フル/長音あり＝長い方」を正とする（頻度ではない）
            canon_for_norm[norm] = reg or max(counts, key=lambda s: (len(s), counts[s]))

        diags: list[Diagnostic] = []

        # (a) 登録表記ゆれ
        for surf, li, col, _norm, _is_noun in occ:
            if surf in self.variant_map:
                diags.append(Diagnostic(li, col, len(surf), surf, "登録表記ゆれ",
                                        "登録正規形に統一してください", self.variant_map[surf]))

        # (b) 文書内表記ゆれ（名詞のみ・少数派のみ・自己無指摘）
        for surf, li, col, norm, is_noun in occ:
            if not is_noun or surf in self.variant_map or surf in self.canon_set:
                continue
            canon = canon_for_norm.get(norm)
            if canon and surf != canon:
                variants = "／".join(sorted(noun_counts[norm]))
                diags.append(Diagnostic(li, col, len(surf), surf, "文書内表記ゆれ",
                                        f"文書内で表記が割れています（{variants}）", canon))

        # (c) 決定的ルール（ら抜き・用字用語）
        for li, line in enumerate(lines, start=1):
            for find, to, cat, note in self.literal_rules:
                start = 0
                while (idx := line.find(find, start)) >= 0:
                    diags.append(Diagnostic(li, idx + 1, len(find), find, cat,
                                            note or f"「{find}」→「{to}」", to))
                    start = idx + len(find)

        # (d) 全角英数字 → 半角
        for li, line in enumerate(lines, start=1):
            for mo in re.finditer(r"[Ａ-Ｚａ-ｚ０-９]+", line):
                g = mo.group()
                diags.append(Diagnostic(li, mo.start() + 1, len(g), g, "全角英数",
                                        "半角に統一", g.translate(_Z2H)))

        seen: set[tuple] = set()
        out: list[dict] = []
        for d in sorted(diags, key=lambda d: (d.line, d.col)):
            k = (d.line, d.col, d.rule, d.surface)
            if k in seen:
                continue
            seen.add(k)
            out.append(asdict(d))
        return out
