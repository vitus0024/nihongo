#!/usr/bin/env python3
"""教材內容驗收：機械層（PLAN §4.2 第二層）。

  ~/.venvs/nihongo/bin/python validate_content.py lessons/W01D1.json [...]      # 讀音核對 → verdicts/<id>.warnings.json
  ~/.venvs/nihongo/bin/python validate_content.py --calibrate                     # 用課綱 200 字＋教材例句量誤報率

檢查：每個 *_kana 欄位是否等於斷詞器（fugashi＋UniDic）對對應日文的讀音。
不一致不代表教材錯——UniDic 對數字連濁、人名、外來語也會錯——所以只產生 reading_warning，
交給下一層（Claude 在 session 內逐筆裁決，寫 verdicts/<id>.json）；有未裁決或裁決為「LLM 錯」的課不得發布。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import fugashi

ROOT = Path(__file__).parent
OUT = ROOT / "verdicts"
TAGGER = fugashi.Tagger()
PAIRS = [("ja", "kana"), ("example_ja", "example_kana"), ("text_ja", "text_kana"), ("script_ja", "script_kana"), ("kanji", "kana")]
STRIP = re.compile(r"[\s、。！？!?「」『』・（）()［］\[\]…,.:：;；〜~－\-—]")


def kata2hira(s: str) -> str:
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s)


def norm(s: str) -> str:
    return kata2hira(STRIP.sub("", s or ""))


CUR = json.loads((ROOT / "curriculum.json").read_text(encoding="utf-8"))
KNOWN = {v["kanji"]: v["kana"] for v in CUR["vocab"] if v["kanji"] != v["kana"]}   # 課綱的讀音是權威：私→わたし、月曜日→げつようび
for ln in (ROOT / "schema" / "readings.txt").read_text(encoding="utf-8").splitlines():   # 人名、にほん、しちじ 等覆寫
    if ln.strip() and not ln.startswith("#") and "\t" in ln:
        k, v = ln.split("\t", 1); KNOWN[k.strip()] = v.strip()
KNOWN_MAXLEN = max((len(k) for k in KNOWN), default=1)


def mecab_kana(ja: str) -> str:
    """斷詞後逐 token 取讀音；連續 token 拼起來是課綱單字就直接用課綱讀音（UniDic 對 私／曜日／日期常挑另一種讀法）。"""
    toks = list(TAGGER(ja))
    out, i = [], 0
    while i < len(toks):
        hit = 0
        for j in range(min(len(toks), i + 5), i, -1):
            if "".join(t.surface for t in toks[i:j]) in KNOWN:
                out.append(KNOWN["".join(t.surface for t in toks[i:j])]); hit = j; break
        if hit:
            i = hit; continue
        w = toks[i]
        k = w.feature.kana                                   # UniDic 的表層讀音（は→ハ，不是發音ワ）
        out.append(k if k and k != "*" else w.surface)       # 記號、未知詞：照抄
        i += 1
    return norm("".join(out))


def walk(node, path=""):
    if isinstance(node, dict):
        for ja_k, kana_k in PAIRS:
            if ja_k in node and kana_k in node and isinstance(node[ja_k], str) and isinstance(node[kana_k], str):
                yield f"{path}.{kana_k}", node[ja_k], node[kana_k]
        for k, v in node.items():
            yield from walk(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, f"{path}[{i}]")


VOCAB = {v["id"]: v for v in CUR["vocab"]}


def answer_key_warnings(node, path=""):
    """單字題的答案可機械核對：問「讀音」且選項裡有課綱假名 → 正解必須是它；問「意思」且選項裡有課綱中文 → 同理。"""
    if isinstance(node, dict):
        t = node.get("tests"); opts = node.get("options"); q = node.get("q", "")
        if t in VOCAB and isinstance(opts, list) and "answer" in node:
            v = VOCAB[t]
            for kind, key, field in (("讀音", v["kana"], "kana"), ("讀法", v["kana"], "kana"), ("意思", v["zh"], "zh")):
                if kind in q and key in opts and opts.index(key) != node["answer"]:
                    yield {"path": path, "ja": q, "kana_llm": f"answer={node['answer']}（{opts[node['answer']]}）", "kana_mecab": f"課綱{field}={key} 在選項 {opts.index(key)}", "kind": "answer_key"}
        for k, v in node.items():
            yield from answer_key_warnings(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from answer_key_warnings(v, f"{path}[{i}]")


def check(d: dict) -> tuple[int, list[dict]]:
    n, warns = 0, []
    for path, ja, kana in walk(d):
        n += 1
        got, want = mecab_kana(ja), norm(kana)
        if got != want:
            warns.append({"path": path, "ja": ja, "kana_llm": kana, "kana_mecab": got, "kind": "reading"})
    warns += list(answer_key_warnings(d))
    return n, warns


def calibrate() -> None:
    """課綱單字（假設正確）＋五課教材例句：看機械層對已知正確資料吐多少警示 ＝ 誤報率的近似。"""
    n, warns = check({"vocab": CUR["vocab"]})
    print(f"課綱單字 {n} 筆，不一致 {len(warns)} 筆（{len(warns) / n:.0%}）——課綱讀音已當權威，這裡應為 0")
    total, allw = 0, []
    for p in sorted((ROOT / "lessons").glob("W*.json")):
        d = json.loads(p.read_text(encoding="utf-8")); d.pop("meta", None)
        n, warns = check(d); total += n; allw += [(p.stem, w) for w in warns]
    print(f"教材句子 {total} 個假名欄位，不一致 {len(allw)} 筆（{len(allw) / max(total, 1):.0%}）——逐筆看誰對：")
    for lid, w in allw:
        print(f"  {lid} {w['path']}\n     {w['ja']}\n     教材   {w['kana_llm']}\n     UniDic {w['kana_mecab']}")


def main() -> None:
    if "--calibrate" in sys.argv:
        return calibrate()
    files = [Path(a) for a in sys.argv[1:] if not a.startswith("--")]
    if not files:
        sys.exit(__doc__)
    OUT.mkdir(exist_ok=True)
    for p in files:
        d = json.loads(p.read_text(encoding="utf-8"))
        n, warns = check(d)
        (OUT / f"{p.stem}.warnings.json").write_text(json.dumps({"lesson": p.stem, "checked": n, "warnings": warns}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{p.stem}：{n} 個假名欄位，{len(warns)} 筆待裁決 → verdicts/{p.stem}.warnings.json")


if __name__ == "__main__":
    main()
