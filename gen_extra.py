#!/usr/bin/env python3
"""兩種補充教材，都用 Codex 生：

  ~/.venvs/nihongo/bin/python gen_extra.py --reading W02 [W03 ...]   # 每週延伸閱讀（i+1：七成已學、三成新字附注音中文；回收當週曝光最少的字）→ extras/W02.json
  ~/.venvs/nihongo/bin/python gen_extra.py --alt W01D2 [W01D3 ...]  # 補強用的另一組小檢核（同樣的考點、換句子）→ lessons/W01D2.alt.json

延伸閱讀不考、不算進度，只為了「多遇到幾次」（蓮先生：記憶靠重複曝光）。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
import exposure  # noqa: E402
from gen_lesson import CUR, V, G, L, ORDER, fmt_vocab, fmt_grammar, PY, spec_section  # noqa: E402


def taught_through_week(week: int) -> list[str]:
    return [v for x in ORDER if L[x]["week"] <= week for v in L[x]["new_vocab"]]


def exposure_counts(upto_week: int) -> Counter:
    cnt: Counter = Counter()
    for x in ORDER:
        if L[x]["week"] > upto_week:
            continue
        p = ROOT / "lessons" / f"{x}.json"
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8")); d.pop("meta", None)
            for t in exposure.ja_strings(d):
                cnt.update(exposure.count_ids(t))
    return cnt


def reading_prompt(wk: str) -> str:
    week = int(wk[1:])
    taught = taught_through_week(week)
    cnt = exposure_counts(week)
    low = sorted([v for x in ORDER if L[x]["week"] == week for v in L[x]["new_vocab"]] + [v for v in taught if cnt.get(v, 0) < 2], key=lambda v: (cnt.get(v, 0), v))
    low = list(dict.fromkeys(low))[:12]
    grammar = [g for x in ORDER if L[x]["week"] <= week for g in L[x]["new_grammar"]]
    themes = "、".join(dict.fromkeys(L[x]["theme"].split("：")[0] for x in ORDER if L[x]["week"] == week))
    out = f"extras/{wk}.json"
    return f"""你是這個日文學習專案的教材作者。請寫一篇第 {week} 週的「延伸閱讀」，存成 `{out}`（只有 JSON、UTF-8、不要 markdown 圍欄），
寫完執行 `{PY} validate_extra.py {out}`，有問題就修到印出 ✓，最後把驗證輸出貼在回覆裡。

## 目的
學習者第 {week} 週學完了，這篇是課外的「多遇到幾次」：i+1 原則——**七成是已學的字和文法，三成是新字**（新字要列在 new_words 附假名與中文）。不考、不算進度。

## 規則
- 主角是成年的台灣人（學習者本人的視角：在日本旅行、購物、住飯店、上班族的日常），不要小孩視角
- 長度 {120 + 30 * (week - 1)}–{180 + 30 * (week - 1)} 個日文字，一個有頭有尾的小故事或情境（主題可從本週的 {themes} 延伸，寫真實生活裡會發生的事）
- **必須用到下面「回收字」至少 10 個**（這些字之前教過但很少再出現）
- 只能用到本週為止教過的文法（清單在下）；新字只能是名詞、い形容詞、片假名外來語，不要新文法、不要動詞變形
- new_words：3–8 個，每個 {{kanji, kana, zh, note}}，note 一句話說明（可空）；文中每個未教的實詞都必須在 new_words 裡，驗證器會查
- text_kana：整段全假名（含助詞），只能有平假名、片假名、長音、日文標點、換行
- zh：整段自然的台灣中文翻譯；title：日文標題＋中文
- questions：3 題理解題（中文題幹、3 選項、answer 0 起算、evidence 是原文片段）——只是幫助確認讀懂，不計分

## 回收字（至少用 10 個）
{fmt_vocab(low)}

## 本週為止教過的文法
{fmt_grammar(grammar)}

## 本週為止教過的全部單字（可自由使用）
{fmt_vocab(taught)}

## 輸出格式
{{"meta":{{"id":"{wk}","kind":"reading","curriculum_version":"{CUR['version']}","version":1,"generated_at":"{date.today().isoformat()}"}},
 "title":{{"ja":"…","zh":"…"}},"text_ja":"…","text_kana":"…","zh":"…",
 "uses":["v0018","v0047",…（實際用到的回收字 id）],
 "new_words":[{{"kanji":"…","kana":"…","zh":"…","note":"…"}}],
 "questions":[{{"q":"…","options":["…","…","…"],"answer":0,"evidence":"…"}}]}}

## SPEC 節錄
{spec_section('4\\.7 閱讀', 3)}
"""


def alt_prompt(lid: str) -> str:
    l = L[lid]
    d = json.loads((ROOT / "lessons" / f"{lid}.json").read_text(encoding="utf-8"))
    out = f"lessons/{lid}.alt.json"
    existing = "\n".join(f"  - {q['q']}（考 {q['tests']}）" for q in d["check"])
    return f"""你是這個日文學習專案的教材作者。請為 {lid} 寫一組**補強用**的小檢核，存成 `{out}`（只有 JSON、UTF-8、不要 markdown 圍欄），
寫完執行 `{PY} validate_extra.py {out}`，修到印出 ✓，把驗證輸出貼在回覆裡。

## 目的
學習者小檢核沒過，隔天要補強。蓮先生的原則：「同一個字抄 10 次不如在 5 篇文章遇到 5 次」——所以補強不重做原題，而是**同樣的考點、換情境換句子**。

## 原本的小檢核（不要重複這些句子和情境）
{existing}

## 規則
- 5 題，每題 {{q, options[3], answer, explain, tests}}；tests 只能是這課的新字或新文法 id：{', '.join(l['new_vocab'] + l['new_grammar'])}，五題要涵蓋原本考過的每個 tests 至少一次
- 只用到本課為止教過的字（未學詞驗證器會擋；人名、數字除外），情境用 {l['theme']} 以外的生活場景
- 中文台灣用語；日文句子若有漢字，選項或題幹不必附假名

## 本課的字與文法
{fmt_vocab(l['new_vocab'])}
{fmt_grammar(l['new_grammar'])}

## 輸出格式
{{"meta":{{"id":"{lid}","kind":"alt_check","curriculum_version":"{CUR['version']}","version":1,"generated_at":"{date.today().isoformat()}"}},
 "check":[{{"q":"…","options":["…","…","…"],"answer":1,"explain":"…","tests":"v0012"}}]}}
"""


def run(prompt: str, log: Path, out: Path) -> bool:
    r = subprocess.run(["codex", "exec", "--sandbox", "workspace-write", "--skip-git-repo-check", "-C", str(ROOT), prompt], capture_output=True, text=True)
    log.write_text(r.stdout + "\n--- stderr ---\n" + r.stderr, encoding="utf-8")
    v = subprocess.run([str(PY), str(ROOT / "validate_extra.py"), str(out)], capture_output=True, text=True)
    print(v.stdout.strip() or v.stderr.strip())
    return v.returncode == 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reading", nargs="*", default=[])
    ap.add_argument("--alt", nargs="*", default=[])
    ap.add_argument("--prompt-only", action="store_true")
    a = ap.parse_args()
    (ROOT / "extras").mkdir(exist_ok=True)
    failed = []
    for wk in a.reading:
        pr = reading_prompt(wk)
        if a.prompt_only:
            print(pr); continue
        print(f"▶ 延伸閱讀 {wk}", flush=True)
        if not run(pr, ROOT / "extras" / f"{wk}.codex.log", ROOT / "extras" / f"{wk}.json"):
            failed.append(wk)
    for lid in a.alt:
        pr = alt_prompt(lid)
        if a.prompt_only:
            print(pr); continue
        print(f"▶ 補強題 {lid}", flush=True)
        if not run(pr, ROOT / "lessons" / f"{lid}.alt.codex.log", ROOT / "lessons" / f"{lid}.alt.json"):
            failed.append(lid)
    if failed:
        sys.exit(f"未通過：{failed}")


if __name__ == "__main__":
    main()
