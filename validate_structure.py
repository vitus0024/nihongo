#!/usr/bin/env python3
"""教材結構驗證（PLAN §4.2 第一層）：JSON schema ＋ 跟 curriculum.json 的一致性。

  ~/.venvs/nihongo/bin/python validate_structure.py lessons/W01D1.json [更多檔]
任何問題列出全部、exit 1。Codex 生完教材自己跑這支，修到過為止。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import fugashi
import jsonschema

ROOT = Path(__file__).parent
TAGGER = fugashi.Tagger()
ALLOW = {ln.strip() for ln in (ROOT / "schema" / "allow_words.txt").read_text(encoding="utf-8").splitlines()
         if ln.strip() and not ln.startswith("#")}
CONTENT_POS = ("名詞", "動詞", "形容詞", "形状詞", "副詞", "連体詞", "接続詞", "代名詞")
SKIP_POS = ("固有名詞", "数詞", "非自立可能", "助数詞可能")
JA_KEYS = ("ja", "example_ja", "text_ja", "script_ja", "task_ja")
SCHEMA = json.loads((ROOT / "schema" / "lesson.schema.json").read_text(encoding="utf-8"))
CUR = json.loads((ROOT / "curriculum.json").read_text(encoding="utf-8"))
VOCAB = {v["id"]: v for v in CUR["vocab"]}
GRAMMAR = {g["id"]: g for g in CUR["grammar"]}
LESSONS = {l["id"]: l for l in CUR["lessons"]}
ORDER = [l["id"] for l in sorted(CUR["lessons"], key=lambda l: (l["week"], l["day"]))]


def qs_in(node, path=""):
    """走遍整份教材，找出所有題目（有 options＋answer 的物件），回傳 (路徑, 題目)。"""
    if isinstance(node, dict):
        if "options" in node and "answer" in node:
            yield path, node
        for k, v in node.items():
            yield from qs_in(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from qs_in(v, f"{path}[{i}]")


def ja_strings(node, path=""):
    """所有給學習者看的日文句子（不含 options：選項裡的錯誤讀音是故意的）。"""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in JA_KEYS and isinstance(v, str):
                yield f"{path}.{k}", v
            elif k != "options":
                yield from ja_strings(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from ja_strings(v, f"{path}[{i}]")


def untaught_words(taught: set[str], d: dict) -> dict[str, list[str]]:
    """斷詞後，每個實詞必須是教過的字（連續 token 拼起來、或 lemma 命中都算）、允許清單、或人名／數詞／助數詞。"""
    found: dict[str, list[str]] = {}
    for path, s in ja_strings(d):
        toks = list(TAGGER(s))
        i = 0
        while i < len(toks):
            hit = 0
            for j in range(min(len(toks), i + 4), i, -1):
                if "".join(t.surface for t in toks[i:j]) in taught:
                    hit = j
                    break
            if hit:
                i = hit
                continue
            w = toks[i]
            f = w.feature
            content = f.pos1 in CONTENT_POS and not any(x in SKIP_POS for x in (f.pos2, f.pos3))
            known = w.surface in taught or w.surface in ALLOW or (f.lemma or "") in taught or (f.lemma or "") in ALLOW
            if content and not known:
                found.setdefault(w.surface, []).append(path)
            i += 1
    return found


def uses_word(sentence: str, kanji: str, kana: str) -> bool:
    """例句有沒有用到這個字：直接包含，或斷詞後 lemma 命中（起きる → 起きます）。"""
    if kanji in sentence or kana in sentence:
        return True
    return any((w.feature.lemma or "") in (kanji, kana) for w in TAGGER(sentence))


def validate(p: Path) -> list[str]:
    errs: list[str] = []
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"不是合法 JSON：{e}"]
    lid = p.stem
    meta = d.get("meta", {})
    if meta.get("id") != lid:
        errs.append(f"meta.id「{meta.get('id')}」跟檔名 {lid} 不符")
    cl = LESSONS.get(lid)
    if not cl:
        return errs + [f"{lid} 不在 curriculum.json 裡"]
    if meta.get("day_type") != cl["day_type"]:
        errs.append(f"meta.day_type 應為 {cl['day_type']}，實際 {meta.get('day_type')}")
    if meta.get("curriculum_version") != CUR["version"]:
        errs.append(f"meta.curriculum_version 應為 {CUR['version']}，實際 {meta.get('curriculum_version')}")

    # ---- schema ----
    sub = {"$ref": f"#/$defs/{cl['day_type']}", "$defs": SCHEMA["$defs"]}
    v = jsonschema.Draft202012Validator(sub)
    for e in sorted(v.iter_errors(d), key=lambda e: list(e.path)):
        loc = "/".join(str(x) for x in e.path) or "(root)"
        errs.append(f"schema {loc}：{e.message[:160]}")
    if errs:
        return errs                                  # 結構都錯了，後面的一致性檢查沒意義

    # ---- 題目共同檢查：answer 在範圍內、選項不重複、evidence 在原文裡 ----
    for path, q in qs_in(d):
        if not 0 <= q["answer"] < len(q["options"]):
            errs.append(f"{path}：answer {q['answer']} 超出選項數 {len(q['options'])}")
        if len(set(q["options"])) != len(q["options"]):
            errs.append(f"{path}：選項重複")
    def check_evidence(block, text_key, path):
        text = block[text_key]
        for i, q in enumerate(block["questions"]):
            if q["evidence"] not in text:
                errs.append(f"{path}.questions[{i}]：evidence「{q['evidence'][:30]}」不在 {text_key} 裡")

    # ---- 依 day_type 的一致性 ----
    new_v, new_g, rev_v = set(cl["new_vocab"]), set(cl["new_grammar"]), set(cl["review_vocab"])
    idx = ORDER.index(lid)
    prev_g = {g for x in ORDER[:idx] for g in LESSONS[x]["new_grammar"]}          # 之前教過的文法
    prev_v = {vv for x in ORDER[:idx] for vv in LESSONS[x]["new_vocab"]}
    week_v = {vv for x in ORDER if LESSONS[x]["week"] == cl["week"] for vv in LESSONS[x]["new_vocab"]}
    week_g = {g for x in ORDER if LESSONS[x]["week"] == cl["week"] for g in LESSONS[x]["new_grammar"]}
    stage_v = {vv for x in ORDER if LESSONS[x]["stage"] == cl["stage"] for vv in LESSONS[x]["new_vocab"]}
    stage_g = {g for x in ORDER if LESSONS[x]["stage"] == cl["stage"] for g in LESSONS[x]["new_grammar"]}

    def tests_within(items, allowed, path):
        for i, q in enumerate(items):
            if q["tests"] not in allowed:
                errs.append(f"{path}[{i}]：tests {q['tests']} 不在允許範圍（{len(allowed)} 個項目）")

    if cl["day_type"] == "new":
        got = {x["id"] for x in d["vocab"]}
        if got != new_v:
            errs.append(f"vocab 的 id 集合跟課綱 new_vocab 不同：多 {sorted(got - new_v)} 少 {sorted(new_v - got)}")
        for x in d["vocab"]:
            c = VOCAB.get(x["id"])
            if c and (x["kanji"], x["kana"]) != (c["kanji"], c["kana"]):
                errs.append(f"vocab {x['id']}：寫法「{x['kanji']}／{x['kana']}」跟課綱「{c['kanji']}／{c['kana']}」不符")
            if not uses_word(x["example_ja"], x["kanji"], x["kana"]):
                errs.append(f"vocab {x['id']}：例句沒用到「{x['kanji']}」")
        got_g = {x["id"] for x in d["grammar"]}
        if got_g != new_g:
            errs.append(f"grammar 的 id 集合跟課綱 new_grammar 不同：多 {sorted(got_g - new_g)} 少 {sorted(new_g - got_g)}")
        for x in d["grammar"]:
            if x["id"] in GRAMMAR and x["pattern"] != GRAMMAR[x["id"]]["pattern"]:
                errs.append(f"grammar {x['id']}：pattern「{x['pattern']}」跟課綱「{GRAMMAR[x['id']]['pattern']}」不符")
        warm_pool = (rev_v | prev_g) or (new_v | new_g)                # 第一課沒東西可複習：改考今天的
        tests_within(d["warmup"], warm_pool, "warmup")
        tests_within(d["check"], new_v | new_g, "check")              # 小檢核只考今天的
        check_evidence(d["reading"], "text_ja", "reading")
        check_evidence(d["listening"], "script_ja", "listening")
        bad = set(d["busy_mode"]["vocab_review_ids"]) - (new_v | rev_v)
        if bad:
            errs.append(f"busy_mode.vocab_review_ids 含非本課／複習字：{sorted(bad)}")
    else:
        q = d["quiz"]
        pool_v, pool_g = (week_v, week_g) if cl["day_type"] == "review" else (stage_v, stage_g)
        tests_within(q["vocab"], pool_v, "quiz.vocab")
        tests_within(q["grammar"], pool_g, "quiz.grammar")
        if cl["day_type"] == "review":
            check_evidence(q["reading"], "text_ja", "quiz.reading")
            check_evidence(q["listening"], "script_ja", "quiz.listening")
        else:
            for i, pz in enumerate(q["reading"]["passages"]):
                check_evidence(pz, "text_ja", f"quiz.reading.passages[{i}]")
            for i, sc in enumerate(q["listening"]["scripts"]):
                check_evidence(sc, "script_ja", f"quiz.listening.scripts[{i}]")
        rp = d["review_pack"]
        if set(rp["vocab_ids"]) != pool_v:
            errs.append(f"review_pack.vocab_ids 應等於{'本週' if cl['day_type']=='review' else '本階段'}全部新字（{len(pool_v)} 個），實際 {len(rp['vocab_ids'])}")
        if set(rp["grammar_ids"]) != pool_g:
            errs.append(f"review_pack.grammar_ids 應等於全部新文法（{len(pool_g)} 個），實際 {len(rp['grammar_ids'])}")
        bad = set(d["busy_mode"]["vocab_review_ids"]) - pool_v
        if bad:
            errs.append(f"busy_mode.vocab_review_ids 含範圍外的字：{sorted(bad)}")
        # 測驗題只能用已教過的字（含本週）
    # 未學詞：到本課為止教過的字 ＋ 允許清單以外的實詞不准出現（PLAN §4.2 機械層之一，先擋在結構層讓 Codex 自修）
    taught = {sf for x in ORDER[: idx + 1] for vid in LESSONS[x]["new_vocab"] for sf in (VOCAB[vid]["kanji"], VOCAB[vid]["kana"])}
    for x in ORDER[: idx + 1]:                       # 教過的文法句型裡的詞也算教過（これ／この／行きます／いくら…）
        for gid in LESSONS[x]["new_grammar"]:
            for w in TAGGER(GRAMMAR[gid]["pattern"]):
                taught.add(w.surface)
                if w.feature.lemma:
                    taught.add(w.feature.lemma)
    for word, paths in untaught_words(taught, d).items():
        errs.append(f"未學詞「{word}」出現在 {paths[0]}" + (f" 等 {len(paths)} 處" if len(paths) > 1 else "") + "（改用已教的字，或真的必要就加進 schema/allow_words.txt）")
    # 所有 tests 引用必須存在
    for path, q in qs_in(d):
        t = q.get("tests")
        if t and t not in VOCAB and t not in GRAMMAR:
            errs.append(f"{path}：tests {t} 不存在於課綱")
    return errs


def main() -> None:
    files = [Path(a) for a in sys.argv[1:]]
    if not files:
        sys.exit(__doc__)
    total = 0
    for p in files:
        errs = validate(p)
        total += len(errs)
        if errs:
            print(f"✗ {p.name}：{len(errs)} 個問題")
            for e in errs:
                print("   -", e)
        else:
            print(f"✓ {p.name}")
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main()
