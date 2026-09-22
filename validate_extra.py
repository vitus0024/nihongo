#!/usr/bin/env python3
"""補充教材驗證：延伸閱讀（extras/Wxx.json）與補強題（lessons/Wxx.alt.json）。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from validate_structure import untaught_words, uses_word, VOCAB, GRAMMAR, LESSONS, ORDER, TAGGER, ALLOW, qs_in  # noqa: E402

ROOT = Path(__file__).parent
KANA = re.compile(r"^[ぁ-ゖァ-ヺーー〜、。！？「」『』・（）()\s]+$")


def taught_set(upto_lessons: list[str]) -> set[str]:
    s = set()
    for x in upto_lessons:
        for vid in LESSONS[x]["new_vocab"]:
            s.add(VOCAB[vid]["kanji"]); s.add(VOCAB[vid]["kana"])
        for gid in LESSONS[x]["new_grammar"]:
            for w in TAGGER(GRAMMAR[gid]["pattern"]):
                s.add(w.surface)
                if w.feature.lemma:
                    s.add(w.feature.lemma)
    return s


def validate(p: Path) -> list[str]:
    errs: list[str] = []
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"不是合法 JSON：{e}"]
    kind = d.get("meta", {}).get("kind")
    if kind == "reading":
        wk = d["meta"]["id"]; week = int(wk[1:])
        for f in ("title", "text_ja", "text_kana", "zh", "uses", "new_words", "questions"):
            if f not in d:
                errs.append(f"缺 {f}")
        if errs:
            return errs
        if not KANA.match(d["text_kana"]):
            errs.append("text_kana 含非假名字元")
        n = len(re.sub(r"[\s。、「」！？]", "", d["text_ja"]))
        lo, hi = 120 + 30 * (week - 1) - 30, 180 + 30 * (week - 1) + 40
        if not lo <= n <= hi:
            errs.append(f"長度 {n} 字，應在 {lo}–{hi}")
        nw = {w["kanji"] for w in d["new_words"]} | {w["kana"] for w in d["new_words"]}
        for w in d["new_words"]:
            if not KANA.match(w.get("kana", "")):
                errs.append(f"new_words「{w.get('kanji')}」kana 不合法")
        if not 3 <= len(d["new_words"]) <= 8:
            errs.append(f"new_words {len(d['new_words'])} 個，應 3–8")
        taught = taught_set([x for x in ORDER if LESSONS[x]["week"] <= week]) | nw
        for word, paths in untaught_words(taught, {"text_ja": d["text_ja"]}).items():
            errs.append(f"未教也不在 new_words 的詞「{word}」")
        # orthBase preserves spelling when the lemma differs (帰ります → lemma 返る).
        bases = {getattr(w.feature, "orthBase", None) for w in TAGGER(d["text_ja"])}
        low_used = [u for u in d["uses"] if u in VOCAB and (
            uses_word(d["text_ja"], VOCAB[u]["kanji"], VOCAB[u]["kana"])
            or VOCAB[u]["kanji"] in bases or VOCAB[u]["kana"] in bases
        )]
        if len(low_used) < 10:
            errs.append(f"回收字實際用到 {len(low_used)} 個（uses 宣稱 {len(d['uses'])}），要 ≥10")
        for i, q in enumerate(d["questions"]):
            if q["evidence"] not in d["text_ja"]:
                errs.append(f"questions[{i}] evidence 不在原文")
            if not 0 <= q["answer"] < len(q["options"]):
                errs.append(f"questions[{i}] answer 超出範圍")
        if len(d["questions"]) != 3:
            errs.append("questions 要 3 題")
    elif kind == "alt_check":
        lid = d["meta"]["id"]; cl = LESSONS[lid]
        qs = d.get("check", [])
        if len(qs) != 5:
            errs.append(f"check {len(qs)} 題，應 5")
        allowed = set(cl["new_vocab"]) | set(cl["new_grammar"])
        orig = json.loads((ROOT / "lessons" / f"{lid}.json").read_text(encoding="utf-8"))
        need = {q["tests"] for q in orig["check"]}
        got = {q.get("tests") for q in qs}
        for i, q in enumerate(qs):
            for f in ("q", "options", "answer", "explain", "tests"):
                if f not in q:
                    errs.append(f"check[{i}] 缺 {f}")
            if q.get("tests") not in allowed:
                errs.append(f"check[{i}] tests {q.get('tests')} 不是本課項目")
            if isinstance(q.get("options"), list) and (len(set(q["options"])) != len(q["options"]) or not 0 <= q.get("answer", -1) < len(q["options"])):
                errs.append(f"check[{i}] 選項重複或 answer 超出範圍")
            if any(oq["q"] == q.get("q") for oq in orig["check"]):
                errs.append(f"check[{i}] 跟原題一樣")
        if need - got:
            errs.append(f"原本考過的考點沒涵蓋：{sorted(need - got)}")
        idx = ORDER.index(lid)
        taught = taught_set(ORDER[: idx + 1])
        for word, paths in untaught_words(taught, {"check": [{"q": q.get("q", "")} for q in qs]}).items():
            errs.append(f"未學詞「{word}」")
    else:
        errs.append(f"meta.kind 不明：{kind}")
    return errs


def main() -> None:
    total = 0
    for a in sys.argv[1:]:
        errs = validate(Path(a)); total += len(errs)
        print(f"{'✗' if errs else '✓'} {Path(a).name}" + (f"：{len(errs)} 個問題" if errs else ""))
        for e in errs:
            print("   -", e)
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main()
