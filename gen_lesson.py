#!/usr/bin/env python3
"""用 Codex CLI 生一課教材（PLAN §4.1）：展開課綱條目 → prompt → codex exec → validate_structure.py。

  ~/.venvs/nihongo/bin/python gen_lesson.py W01D1 [W01D2 ...]
  ~/.venvs/nihongo/bin/python gen_lesson.py W01D1 --prompt-only     # 只印 prompt 不跑
Codex 在 workspace-write 沙箱裡寫 lessons/<id>.json，並被要求自己跑驗證修到過；本程式最後再驗一次。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
CUR = json.loads((ROOT / "curriculum.json").read_text(encoding="utf-8"))
V = {v["id"]: v for v in CUR["vocab"]}
G = {g["id"]: g for g in CUR["grammar"]}
L = {l["id"]: l for l in CUR["lessons"]}
ORDER = [l["id"] for l in sorted(CUR["lessons"], key=lambda l: (l["week"], l["day"]))]
SPEC = (ROOT / "SPEC.md").read_text(encoding="utf-8")
PY = Path.home() / ".venvs" / "nihongo" / "bin" / "python"

SPEAKING_BY_WEEK = {1: "朗讀 或 替換（擇一填 type）", 2: "短答", 3: "角色扮演", 4: "自由敘述"}          # SPEC §4.6 進程（每階段內循環）
READING_LEN = {1: "1–3 個單句或一段 3 句以內的短對話（≤40 字）", 2: "一段短對話或菜單／價目表（40–70 字）",
               3: "短對話或簡訊（60–90 字）", 4: "生活短文或行程表（80–120 字）"}


def spec_section(title_re: str, level: int = 2) -> str:
    """抓 SPEC 裡某個標題段落的全文（含其子標題），到下一個同級或更高階標題為止。"""
    stop = "|".join(f"^{'#' * k} " for k in range(2, level + 1))
    m = re.search(rf"^({'#' * level} {title_re}.*?)(?={stop}|\Z)", SPEC, re.S | re.M)
    return m.group(1).strip() if m else ""


def fmt_vocab(ids) -> str:
    return "\n".join(f"  - {i}｜{V[i]['kanji']}｜{V[i]['kana']}｜{V[i]['zh']}｜{V[i]['pos']}" for i in ids)


def fmt_grammar(ids) -> str:
    return "\n".join(f"  - {i}｜{G[i]['pattern']}｜{G[i]['meaning_zh']}｜情境：{G[i]['scene']}" for i in ids)


def build_prompt(lid: str) -> str:
    l = L[lid]
    idx = ORDER.index(lid)
    week_in_stage = (l["week"] - 1) % 4 + 1
    prev_ids = ORDER[:idx]
    prev_g = [g for x in prev_ids for g in L[x]["new_grammar"]]
    prev_v = [v for x in prev_ids for v in L[x]["new_vocab"]]
    week_ids = [x for x in ORDER if L[x]["week"] == l["week"]]
    week_v = [v for x in week_ids for v in L[x]["new_vocab"]]
    week_g = [g for x in week_ids for g in L[x]["new_grammar"]]
    stage_ids = [x for x in ORDER if L[x]["stage"] == l["stage"]]
    stage_v = [v for x in stage_ids for v in L[x]["new_vocab"]]
    stage_g = [g for x in stage_ids for g in L[x]["new_grammar"]]
    out = f"lessons/{lid}.json"

    head = f"""你是這個日文學習專案的教材作者。請生成一課教材 `{out}`，只有 JSON、UTF-8、不要 markdown 圍欄。
寫完後執行：`{PY} validate_structure.py {out}`，有任何問題就修檔重跑，直到印出 ✓ 為止；最後把驗證輸出貼在回覆裡。
不要改 curriculum.json、schema、validate_structure.py。

## 這一課
- id：{lid}（第 {l['week']} 週 Day{l['day']}，{l['stage_name']}階段第 {week_in_stage} 週，day_type ＝ **{l['day_type']}**）
- 主題：{l['theme']}
- 《大家的日本語 初級Ⅰ》對應課次：{l['minna_lesson']}
- meta：{{"id":"{lid}","day_type":"{l['day_type']}","curriculum_version":"{CUR['version']}","lesson_version":1,"generated_at":"{date.today().isoformat()}","model":"<你的模型名>"}}

## 格式
- JSON schema 在 `schema/lesson.schema.json` 的 `$defs.{l['day_type']}`，請先讀它；欄位一個都不能少、不能多
- `validate_structure.py` 另外檢查：vocab 的 id 集合必須恰好等於課綱 new_vocab、kanji／kana 寫法必須跟課綱完全一致、例句必須用到該字、warmup 的 tests 只能是複習字或之前教過的文法、check 的 tests 只能是今天的字或文法、每題 evidence 必須是原文中一字不差的片段、answer 是 0 起算的選項索引、選項不可重複
- 所有 `*_kana` 欄位是**整句全假名**（含助詞），只能有平假名、片假名、長音、日文標點、空白；數字要寫成假名（さんびゃく）
- 給學習者看的任何文字（compare、usage、explain、note…）**不可出現 g001／v0012 這類 ID**，要引用就寫句型或單字本身
- 中文一律**台灣用語**（例：「錢包」不是「钱包」、「便利商店」不是「便利店」）
- 只能使用：今天的新字＋下面列的已學字＋助詞／です・ます 等基本功能詞＋人名地名。**不要用還沒教的單字或文法**——驗證器會用斷詞器檢查每一句日文，出現未教的實詞就不過（人名、數字、助數詞、`schema/allow_words.txt` 裡的詞除外）；選項裡的錯誤讀音不在此限

## 學習情境優先序（SPEC §2.3）
購物與詢價 ＞ 餐廳與點餐 ＞ 問路與交通 ＞ 飯店與住宿 ＞ 自我介紹與日常生活 ＞ 旅行計畫與經驗分享
"""
    if l["day_type"] == "new":
        body = f"""
## 今天要教的（必須全部用到，且 vocab 陣列恰好這 10 個 id）
單字：
{fmt_vocab(l['new_vocab'])}
文法：
{fmt_grammar(l['new_grammar'])}

## 複習字（warmup 只能考這些；busy_mode.vocab_review_ids 從今天的字＋這些裡挑 5–15 個）
{fmt_vocab(l['review_vocab']) or '  （第一課沒有複習字：warmup 改考假名辨讀，tests 仍須填一個今天的文法 id）'}

## 之前教過的文法（warmup 可考；例句與閱讀可用）
{fmt_grammar(prev_g) or '  （無）'}

## 之前教過的單字（可在例句、閱讀、聽力裡使用；不要當新字教）
{fmt_vocab(prev_v) or '  （無）'}

## 各模組要求（SPEC §4.1）
1. warmup 3–5 題：{'前課錯題優先，v1 固定從複習字與之前文法出題' if prev_ids else '假名辨讀'}
2. vocab 10 個：每個有例句（用今天的文法或已學文法）、`note` 寫使用提醒（可空字串）
3. grammar：`structure`（接續方式）、`meaning`（中文核心意思）、`usage`（使用情境）、`forms` 至少肯定／否定（有時態就加過去）、`mistakes` 常見錯誤 1–4 條、`compare` 相似句型比較（可空）、`examples` ≥3 句且至少 1 句是旅行或日常
4. patterns 5–10 句：可直接套用的實用句型，`swap_slots` 列出可替換的槽位（例：["職業","國籍"]）
5. reading：類型 ＝ {l['reading_type']}；長度 ＝ {READING_LEN[week_in_stage]}；題目 2–5 題含主旨／細節／資訊擷取
6. listening：類型 ＝ {l['listening_type']}；15–60 秒份量（約 30–80 字）的短對話或敘述；題目 2–4 題；`script_kana` 給跟讀用
7. speaking：type ＝ {SPEAKING_BY_WEEK[week_in_stage]}；任務 ＝ {l['speaking_task']}；`chatgpt_prompt` 是學習者會直接貼給 ChatGPT 的完整指令（繁體中文），要包含：角色設定、今天的句型、要練幾輪、請 ChatGPT 依 SPEC §4.6 五面向各 4 分評分並回饋
8. check 3–5 題：只考今天的字與文法，每題 `explain` 解釋為什麼
9. busy_mode：`vocab_review_ids` 5–15 個、`speaking_short` 一句話的 5 分鐘口說任務（SPEC §5.2）
"""
    elif l["day_type"] == "review":
        body = f"""
## 本週學過的（週測範圍；quiz 的 tests 只能引用這些；review_pack 必須列出全部）
單字（{len(week_v)} 個）：
{fmt_vocab(week_v)}
文法（{len(week_g)} 個）：
{fmt_grammar(week_g)}

## 更早教過的（可在題目文本裡出現，不當考點）
{fmt_vocab([v for v in prev_v if v not in week_v]) or '  （無）'}

## 週測要求（SPEC §8.1，五分項各 20 分）
- quiz.vocab 10 題：認讀、選詞、日中互譯混合；quiz.grammar 10 題：助詞、變化、選句
- quiz.reading：一段 {READING_LEN[week_in_stage]} 的文本 ＋ 5 題（主旨、細節、指涉、順序、資訊擷取各至少一題）
- quiz.listening：30–80 字對話 ＋ 5 題
- quiz.speaking：type ＝ {SPEAKING_BY_WEEK[week_in_stage]}；任務 ＝ {l['speaking_task']}（1–3 分鐘）；`rubric` 五面向各寫出「4 分的標準」；`chatgpt_prompt` 要請 ChatGPT 依 rubric 評分並在最後輸出 n5-feedback 區塊（格式：```n5-feedback 圍欄內 JSON {{"week":"W{l['week']:02d}","speaking":<0–20>,"weak_add":[{{"id":"<v/g id 或省略>","text":"…","note":"…"}}],"weak_remove":[],"suggest":"…"}}```）
- review_pack：本週全部單字 id 與文法 id（給錯題訂正頁）
- busy_mode：5–15 個本週單字、一句 5 分鐘口說
"""
    else:  # stage_test
        body = f"""
## 本階段學過的（階段測驗範圍；quiz 的 tests 只能引用這些；review_pack 必須列出全部）
單字（{len(stage_v)} 個）：
{fmt_vocab(stage_v)}
文法（{len(stage_g)} 個）：
{fmt_grammar(stage_g)}

## 階段測驗要求（SPEC §8.2；第 {l['stage']} 階段驗收重點：{l['theme']}）
- quiz.vocab 20 題、quiz.grammar 20 題，覆蓋各週，難度略高於週測
- quiz.reading.passages 2 篇（各 {READING_LEN[4]}，各 3–5 題）；quiz.listening.scripts 2 段（各 40–100 字，各 3–5 題）
- quiz.speaking：type ＝ 自由敘述；任務 ＝ {l['speaking_task']}（3 分鐘情境對話）；`rubric` 五面向 4 分標準；`chatgpt_prompt` 同週測，n5-feedback 的 week 填 "W{l['week']:02d}"
- n5_mock：{str(l['week'] == 20).lower()}
- review_pack：本階段全部單字與文法 id；busy_mode 同前
"""
    tail = f"""
## SPEC 原文節錄（依此寫，不要自創規格）
{spec_section('4\\. 內容結構', 2)}

{spec_section('5\\.2 忙碌', 3)}
"""
    return head + body + tail


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    prompt_only = "--prompt-only" in sys.argv
    if not args:
        sys.exit(__doc__)
    (ROOT / "lessons").mkdir(exist_ok=True)
    failed = []
    for lid in args:
        if lid not in L:
            sys.exit(f"{lid} 不在課綱裡")
        prompt = build_prompt(lid)
        if prompt_only:
            print(prompt)
            continue
        print(f"▶ {lid} 交給 Codex…", flush=True)
        r = subprocess.run(["codex", "exec", "--sandbox", "workspace-write", "--skip-git-repo-check", "-C", str(ROOT), prompt],
                           capture_output=True, text=True)
        (ROOT / "lessons" / f"{lid}.codex.log").write_text(r.stdout + "\n--- stderr ---\n" + r.stderr, encoding="utf-8")
        v = subprocess.run([str(PY), str(ROOT / "validate_structure.py"), str(ROOT / "lessons" / f"{lid}.json")],
                           capture_output=True, text=True)
        print(v.stdout.strip())
        if v.returncode:
            failed.append(lid)
    if failed:
        sys.exit(f"未通過：{failed}（看 lessons/<id>.codex.log）")


if __name__ == "__main__":
    main()
