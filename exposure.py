#!/usr/bin/env python3
"""曝光次數檢查：每個單字在「教過之後」的課裡（例句、文法、句型、閱讀、聽力、測驗文本）再出現幾次。

  ~/.venvs/nihongo/bin/python exposure.py [--min 3] [--stage 1]

蓮先生：「同一個字抄 10 次不如在 5 篇文章遇到 5 次」——記憶靠重複曝光。低於門檻的字列出來，生下一階段教材時要求補進去。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import fugashi

ROOT = Path(__file__).parent
TAGGER = fugashi.Tagger()
CUR = json.loads((ROOT / "curriculum.json").read_text(encoding="utf-8"))
V = {v["id"]: v for v in CUR["vocab"]}
L = {l["id"]: l for l in CUR["lessons"]}
ORDER = [l["id"] for l in sorted(CUR["lessons"], key=lambda l: (l["week"], l["day"]))]
JA_KEYS = ("ja", "example_ja", "text_ja", "script_ja", "task_ja", "q")
SURF = {}                                                  # 表層／lemma → vocab id
for v in CUR["vocab"]:
    SURF[v["kanji"]] = v["id"]; SURF[v["kana"]] = v["id"]


def ja_strings(node):
    if isinstance(node, dict):
        for k, val in node.items():
            if k in JA_KEYS and isinstance(val, str):
                yield val
            elif k != "options":
                yield from ja_strings(val)
    elif isinstance(node, list):
        for x in node:
            yield from ja_strings(x)


def count_ids(text: str) -> Counter:
    """斷詞後最長匹配課綱單字（含 lemma：起きます→起きる）。"""
    toks = list(TAGGER(text)); c = Counter(); i = 0
    while i < len(toks):
        hit = 0
        for j in range(min(len(toks), i + 4), i, -1):
            s = "".join(t.surface for t in toks[i:j])
            if s in SURF:
                c[SURF[s]] += 1; hit = j; break
        if hit:
            i = hit; continue
        lem = toks[i].feature.lemma or ""
        if lem in SURF:
            c[SURF[lem]] += 1
        i += 1
    return c


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=int, default=3)
    ap.add_argument("--stage", type=int)
    a = ap.parse_args()
    intro = {vid: lid for lid in ORDER for vid in L[lid]["new_vocab"]}
    later: Counter = Counter()
    per_lesson: dict[str, Counter] = {}
    for lid in ORDER:
        p = ROOT / "lessons" / f"{lid}.json"
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8")); d.pop("meta", None)
        c = Counter()
        for s in ja_strings(d):
            c.update(count_ids(s))
        per_lesson[lid] = c
    for vid, lid in intro.items():
        for other in ORDER[ORDER.index(lid) + 1:]:
            later[vid] += per_lesson.get(other, Counter()).get(vid, 0)
    rows = [(vid, later[vid]) for vid in intro if (not a.stage or L[intro[vid]]["stage"] == a.stage)]
    low = sorted((r for r in rows if r[1] < a.min), key=lambda r: (r[1], r[0]))
    n = len(rows)
    print(f"{n} 個字；教過之後再出現 <{a.min} 次的有 {len(low)} 個（{len(low) / n:.0%}）；0 次的 {sum(1 for _, k in low if k == 0)} 個")
    dist = Counter(min(k, 10) for _, k in rows)
    print("分布：", " ".join(f"{k}{'+' if k == 10 else ''}次×{dist[k]}" for k in sorted(dist)))
    for vid, k in low:
        v = V[vid]; print(f"  {k} 次  {vid} {v['kanji']}（{v['kana']}）{v['zh']}  首次 {intro[vid]}")
    (ROOT / "verdicts" / "exposure.json").write_text(json.dumps({"min": a.min, "low": [{"id": vid, "later": k, "kanji": V[vid]["kanji"], "intro": intro[vid]} for vid, k in low]}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
