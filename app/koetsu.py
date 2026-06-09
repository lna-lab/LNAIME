"""LNAIME 校正エンジン（決定的層 v0）。

L0 master 固有辞書を「正」として、文書を Sudachi で形態素解析し
  (a) 登録表記ゆれ : 登録された variant 表記 → canonical へ統一を指摘
  (b) 文書内表記ゆれ: 同一 normalized_form に複数表記が混在 → 割れを指摘（未登録の発見）
を返す。正の出所は常に L0 登録正規形（Sudachi 既定正規化は検出キーにのみ使う）。
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path

import yaml
from sudachipy import Dictionary, SplitMode


@dataclass
class Diagnostic:
    line: int
    col: int
    length: int
    surface: str
    rule: str        # "登録表記ゆれ" | "文書内表記ゆれ"
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
        self.variant_map: dict[str, str] = {}   # variant 表記 -> canonical
        self.canon_set: set[str] = set()
        for t in self.terms:
            self.canon_set.add(t["canonical"])
            for v in (t.get("variants") or []):
                self.variant_map[v] = t["canonical"]
        return len(self.terms)

    def check(self, text: str) -> list[dict]:
        # occ: (surface, line, col, norm, is_noun)
        occ: list[tuple[str, int, int, str, bool]] = []
        noun_counts: dict[str, Counter] = defaultdict(Counter)   # norm -> Counter(surface)  ※名詞のみ

        for li, line in enumerate(text.split("\n"), start=1):
            if not line.strip():
                continue
            for m in self.tok.tokenize(line, SplitMode.C):
                surf = m.surface()
                if not surf.strip():
                    continue
                norm = m.normalized_form()
                is_noun = m.part_of_speech()[0] == "名詞"   # 活用語の活用ゆれを拾わない
                occ.append((surf, li, m.begin() + 1, norm, is_noun))
                if is_noun:
                    noun_counts[norm][surf] += 1

        # normalized_form ごとの正規表記を決定：登録canonical優先 → なければ最頻（同数は長い方）
        canon_for_norm: dict[str, str] = {}
        for norm, counts in noun_counts.items():
            if len(counts) < 2:
                continue
            reg = next((s for s in counts if s in self.canon_set), None)
            canon_for_norm[norm] = reg or max(counts, key=lambda s: (counts[s], len(s)))

        diags: list[Diagnostic] = []

        # (a) 登録表記ゆれ — master の variant を canonical へ（決定的・最優先）
        for surf, li, col, _norm, _is_noun in occ:
            if surf in self.variant_map:
                diags.append(Diagnostic(
                    li, col, len(surf), surf, "登録表記ゆれ",
                    "登録正規形に統一してください", self.variant_map[surf]))

        # (b) 文書内表記ゆれ — 名詞のみ・割れている少数派だけを指摘（自己無指摘）
        for surf, li, col, norm, is_noun in occ:
            if not is_noun or surf in self.variant_map or surf in self.canon_set:
                continue
            canon = canon_for_norm.get(norm)
            if canon and surf != canon:
                variants = "／".join(sorted(noun_counts[norm]))
                diags.append(Diagnostic(
                    li, col, len(surf), surf, "文書内表記ゆれ",
                    f"文書内で表記が割れています（{variants}）", canon))

        seen: set[tuple] = set()
        out: list[dict] = []
        for d in sorted(diags, key=lambda d: (d.line, d.col)):
            k = (d.line, d.col, d.rule, d.surface)
            if k in seen:
                continue
            seen.add(k)
            out.append(asdict(d))
        return out
