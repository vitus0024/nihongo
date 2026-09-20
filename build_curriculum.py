#!/usr/bin/env python3
"""把 ChatGPT 輸出的「教學內容」合成帶 ID 的 curriculum.json（PLAN §2.1）。

用法：
  python build_curriculum.py --stage 1 prompts/out/grammar-stage1.json prompts/out/lessons-stage1*.json
  python build_curriculum.py --stage 2 prompts/out/grammar-stage2.json prompts/out/lessons-stage2*.json   # 續編，既有 ID 不變

ChatGPT 只負責教什麼；這支負責：ID 編號（既有的不變）、每課 10 個新字、跨課不重複、
文法引用存在、假名字元、複習排程（學後第 1／3／7／14／30 課重現，SPEC §4.2）、階段名稱、進度分母。
任何檢查不過就列出全部問題並以非 0 結束，不寫檔。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "curriculum.json"

STAGES = {1: "基礎建立", 2: "動詞核心", 3: "て形應用", 4: "普通形與表達", 5: "N5 整合衝刺"}   # SPEC §3，每階段 4 週
POS = {"名", "動Ⅰ", "動Ⅱ", "動Ⅲ", "い形", "な形", "副", "助", "接", "疑", "數", "感", "慣用"}
KANA = re.compile(r"^[ぁ-ゖァ-ヺーー〜・\s]+$")   # 平假名、片假名、長音、波浪、中點
LESSON_ID = re.compile(r"^W(\d{2})D([1-6])$")
REVIEW_OFFSETS = (1, 3, 7, 14, 30)          # 第 n 課教的字，在第 n+1、n+3… 課的暖身／複習再出現
NEW_VOCAB_PER_DAY = 10


def load(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"{p}: 不是合法 JSON（{e}）——ChatGPT 輸出可能被截斷，或前後有多餘文字")


def vkey(v: dict) -> tuple[str, str]:
    return (v["kanji"].strip(), v["kana"].strip())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", type=int, required=True, help="這批是第幾階段（1–5）")
    ap.add_argument("grammar", type=Path, help="ChatGPT 第一段輸出：文法清冊 JSON")
    ap.add_argument("lessons", type=Path, nargs="+", help="ChatGPT 第二段輸出：課程 JSON（可多個檔，會依 id 合併）")
    ap.add_argument("--dry-run", action="store_true", help="只檢查不寫檔")
    args = ap.parse_args()
    problems: list[str] = []

    # ---------- 既有課綱（續編時 ID 要穩定） ----------
    prev = load(OUT) if OUT.exists() else {"vocab": [], "grammar": [], "lessons": []}
    vocab_by_key = {vkey(v): v for v in prev["vocab"]}
    grammar_by_pat = {g["pattern"]: g for g in prev["grammar"]}
    lessons_by_id = {l["id"]: l for l in prev["lessons"]}
    next_v = max((int(v["id"][1:]) for v in prev["vocab"]), default=0) + 1
    next_g = max((int(g["id"][1:]) for g in prev["grammar"]), default=0) + 1

    # ---------- 文法清冊 ----------
    gdoc = load(args.grammar)
    for g in gdoc.get("grammar", []):
        pat = g["pattern"].strip()
        if pat in grammar_by_pat:
            continue                                   # 已有 → 沿用舊 ID
        grammar_by_pat[pat] = {"id": f"g{next_g:03d}", "pattern": pat, "meaning_zh": g.get("meaning_zh", ""),
                               "minna": g.get("minna"), "scene": g.get("scene", ""), "stage": args.stage}
        next_g += 1

    # ---------- 課程 ----------
    raw: dict[str, dict] = {}
    for p in args.lessons:
        for l in load(p).get("lessons", []):
            if l["id"] in raw:
                problems.append(f"{l['id']} 在多個檔案裡重複出現")
            raw[l["id"]] = l
    if not raw:
        sys.exit("沒有讀到任何課")

    weeks = range((args.stage - 1) * 4 + 1, args.stage * 4 + 1)
    expected = {f"W{w:02d}D{d}" for w in weeks for d in range(1, 7)}
    missing, extra = expected - raw.keys(), raw.keys() - expected
    if missing:
        problems.append(f"第 {args.stage} 階段缺課：{sorted(missing)}")
    if extra:
        problems.append(f"不屬於第 {args.stage} 階段的課：{sorted(extra)}")

    # 這批之前所有課教過的字（跨階段不重複）
    seen: dict[tuple[str, str], str] = {}
    for l in prev["lessons"]:
        if l["id"] not in raw:
            for vid in l["new_vocab"]:
                v = next(v for v in prev["vocab"] if v["id"] == vid)
                seen[vkey(v)] = l["id"]

    built: dict[str, dict] = {}
    for lid in sorted(raw):
        l = raw[lid]
        m = LESSON_ID.match(lid)
        if not m:
            problems.append(f"{lid}：id 格式錯")
            continue
        week, day = int(m.group(1)), int(m.group(2))
        want_type = "stage_test" if (day == 6 and week % 4 == 0) else ("review" if day == 6 else "new")
        if l.get("day_type") != want_type:
            problems.append(f"{lid}：day_type 應為 {want_type}，實際 {l.get('day_type')}")

        # 單字
        vids: list[str] = []
        for v in l.get("new_vocab", []):
            for f in ("kanji", "kana", "zh", "pos"):
                if not str(v.get(f, "")).strip():
                    problems.append(f"{lid}：單字 {v} 缺 {f}")
            k = vkey(v)
            if not KANA.match(v["kana"]):
                problems.append(f"{lid}：{v['kanji']} 的 kana「{v['kana']}」含非假名字元")
            if v["pos"] not in POS:
                problems.append(f"{lid}：{v['kanji']} 的 pos「{v['pos']}」不在允許清單")
            if k in seen:
                problems.append(f"{lid}：「{v['kanji']}／{v['kana']}」已在 {seen[k]} 教過")
                continue
            seen[k] = lid
            if k not in vocab_by_key:
                vocab_by_key[k] = {"id": f"v{next_v:04d}", "kanji": k[0], "kana": k[1], "zh": v["zh"].strip(),
                                   "pos": v["pos"], "minna": l.get("minna_lesson"), "first_lesson": lid}
                next_v += 1
            vids.append(vocab_by_key[k]["id"])
        if want_type == "new" and len(vids) != NEW_VOCAB_PER_DAY:
            problems.append(f"{lid}：new 課要 {NEW_VOCAB_PER_DAY} 個新字，實際 {len(vids)}")
        if want_type != "new" and vids:
            problems.append(f"{lid}：{want_type} 課不該有新字（有 {len(vids)} 個）")

        # 文法
        gids: list[str] = []
        for pat in l.get("new_grammar", []):
            pat = pat.strip()
            if pat not in grammar_by_pat:
                problems.append(f"{lid}：文法「{pat}」不在清冊裡")
                continue
            gids.append(grammar_by_pat[pat]["id"])
        if want_type == "new" and not 1 <= len(gids) <= 2:
            problems.append(f"{lid}：new 課要 1–2 個新文法，實際 {len(gids)}")
        if want_type != "new" and gids:
            problems.append(f"{lid}：{want_type} 課不該有新文法")

        for f in ("theme", "reading_type", "listening_type", "speaking_task"):
            if not str(l.get(f, "")).strip():
                problems.append(f"{lid}：缺 {f}")

        built[lid] = {"id": lid, "week": week, "day": day, "stage": args.stage, "stage_name": STAGES[args.stage],
                      "day_type": want_type, "theme": l.get("theme", ""), "minna_lesson": l.get("minna_lesson"),
                      "new_vocab": vids, "new_grammar": gids, "review_vocab": [],
                      "reading_type": l.get("reading_type", ""), "listening_type": l.get("listening_type", ""),
                      "speaking_task": l.get("speaking_task", "")}

    if problems:
        print(f"✗ {len(problems)} 個問題，未寫檔：", file=sys.stderr)
        for p in problems:
            print("  -", p, file=sys.stderr)
        sys.exit(1)

    # ---------- 合併、排序、算複習 ----------
    lessons_by_id.update(built)
    lessons = sorted(lessons_by_id.values(), key=lambda l: (l["week"], l["day"]))
    for n, l in enumerate(lessons):
        review: list[str] = []
        for off in REVIEW_OFFSETS:                      # 第 n−off 課教的字今天複習
            if n - off >= 0:
                review += lessons[n - off]["new_vocab"]
        if l["day_type"] != "new":                     # 週測／階段測：本週全部新字都進複習包
            wk = [x for x in lessons if x["week"] == l["week"] and x["day_type"] == "new"]
            review += [vid for x in wk for vid in x["new_vocab"]]
        l["review_vocab"] = list(dict.fromkeys(review))   # 去重、保序

    vocab = sorted(vocab_by_key.values(), key=lambda v: v["id"])
    grammar = sorted(grammar_by_pat.values(), key=lambda g: g["id"])
    today = date.today().isoformat()
    n_same_day = int(prev["version"].split(".")[-1]) + 1 if prev.get("version", "").startswith(today) else 1
    out = {"version": f"{today}.{n_same_day}", "stages": STAGES,
           "totals": {"lessons": len(lessons), "vocab": len(vocab), "grammar": len(grammar)},
           "vocab": vocab, "grammar": grammar, "lessons": lessons}

    print(f"✓ 第 {args.stage} 階段 {len(built)} 課通過檢查")
    for l in lessons:
        if l["id"] in built:
            print(f"  {l['id']} {l['day_type']:10s} 新字 {len(l['new_vocab']):2d} 文法 {len(l['new_grammar'])} 複習 {len(l['review_vocab']):2d}  {l['theme']}")
    print(f"累計：{len(lessons)} 課、{len(vocab)} 字、{len(grammar)} 文法（進度分母）")
    if args.dry_run:
        print("（--dry-run，未寫檔）")
        return
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"寫入 {OUT.name}（version {out['version']}）")


if __name__ == "__main__":
    main()
