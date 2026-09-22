#!/usr/bin/env python3
"""音檔驗收（PLAN §4.2 第四層）：把每段音檔送 whisper-1 轉成假名，跟教材期待的讀音比對。

  ~/.venvs/nihongo/bin/python validate_audio.py --lesson W01D1 [W01D2 ...]     # → verdicts/<id>.audio.json，列出可疑段
  ~/.venvs/nihongo/bin/python validate_audio.py --lesson W01D1 --all           # 連通過的也列

期待讀音 ＝ validate_content.mecab_kana（課綱讀音＋readings.txt 為權威，跟文字層同一套）。
辨識本身也會錯（人名、短句），所以只標「可疑」交裁決，不自動判死；相似度 < 0.85 或人名讀音對不上才標。
費用：whisper-1 每分鐘 US$0.006，一課約 3 分鐘。
"""
from __future__ import annotations

import argparse
import difflib
import json
import mimetypes
import sys
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from validate_content import mecab_kana, norm, KNOWN  # noqa: E402
from gen_audio import key_for, NAMES  # noqa: E402

ROOT = Path(__file__).parent
OUT = ROOT / "verdicts"
PROMPT = "ひらがなだけで書き起こす。例：わたしはがくせいです。りんさんはたいわんじんですか。さんびゃくえんです。"
THRESHOLD = 0.85
SHORT = 6                                  # 6 個假名以下的單字，辨識本身不可靠（いしゃ→にしゃ），門檻放到 0.5
WRONG_NAME_READINGS = {"林": ["はやし", "こばやし"], "陳": ["ちぇん"], "王": ["わん"]}   # TTS 可能唸成的日本／中國讀法


DIGIT = {"0": "れい", "1": "いち", "2": "に", "3": "さん", "4": "よん", "5": "ご", "6": "ろく", "7": "なな", "8": "はち", "9": "きゅう"}


import re

NUM = {1: "いち", 2: "に", 3: "さん", 4: "よん", 5: "ご", 6: "ろく", 7: "なな", 8: "はち", 9: "きゅう", 10: "じゅう"}
MONTH = {1: "いちがつ", 2: "にがつ", 3: "さんがつ", 4: "しがつ", 5: "ごがつ", 6: "ろくがつ", 7: "しちがつ", 8: "はちがつ", 9: "くがつ", 10: "じゅうがつ", 11: "じゅういちがつ", 12: "じゅうにがつ"}
DAY = {1: "ついたち", 2: "ふつか", 3: "みっか", 4: "よっか", 5: "いつか", 6: "むいか", 7: "なのか", 8: "ようか", 9: "ここのか", 10: "とおか", 14: "じゅうよっか", 20: "はつか", 24: "にじゅうよっか"}
HOUR = {4: "よじ", 7: "しちじ", 9: "くじ"}


def _num(n: int) -> str:
    if n <= 10: return NUM[n]
    if n < 20: return "じゅう" + NUM[n - 10]
    return NUM[n // 10] + "じゅう" + (NUM[n % 10] if n % 10 else "")


def digits_to_kana(s: str) -> str:
    """辨識常把日期時刻寫成 4月1日、9時：先照日文讀法換（しがつ、ついたち、くじ），剩下的數字串逐位換（電話號碼）。"""
    s = re.sub(r"(\d{1,2})月", lambda m: MONTH.get(int(m.group(1)), _num(int(m.group(1))) + "がつ"), s)
    s = re.sub(r"(\d{1,2})日", lambda m: DAY.get(int(m.group(1)), _num(int(m.group(1))) + "にち"), s)
    s = re.sub(r"(\d{1,2})時", lambda m: HOUR.get(int(m.group(1)), _num(int(m.group(1))) + "じ"), s)
    s = re.sub(r"(\d{1,2})分", lambda m: _num(int(m.group(1))) + "ふん", s)
    return "".join(DIGIT.get(c, c) for c in s)


def transcribe(path: Path) -> str:
    key = key_for("openai")
    if not key:
        sys.exit("沒有 OpenAI key")
    boundary = uuid.uuid4().hex
    fields = {"model": "whisper-1", "language": "ja", "response_format": "json", "prompt": PROMPT, "temperature": "0"}
    body = b""
    for k, v in fields.items():
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{path.name}\"\r\n"
             f"Content-Type: {mimetypes.guess_type(path.name)[0] or 'audio/mpeg'}\r\n\r\n").encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request("https://api.openai.com/v1/audio/transcriptions", data=body,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
    for attempt in range(3):                                  # 網路偶爾 timeout，重試兩次
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())["text"]
        except Exception as e:
            if attempt == 2:
                return f"[辨識失敗 {e}]"


def check_lesson(lid: str, show_all: bool) -> dict:
    d = ROOT / "audio" / lid
    idx = json.loads((d / "index.json").read_text(encoding="utf-8"))
    rows, flagged = [], 0
    for key, e in idx.items():
        expected = mecab_kana(e["text"])
        heard = mecab_kana(digits_to_kana(transcribe(d / e["file"])))   # 辨識有時無視提示吐漢字／阿拉伯數字，同樣轉假名再比
        sim = difflib.SequenceMatcher(None, expected, heard).ratio()
        # 人名：辨識對人名不準（たなか→かなた），只抓「聽到已知的錯讀法」（林→はやし）
        name_miss = [f"{k}→{w}" for k, ws in WRONG_NAME_READINGS.items() if k in e["text"] for w in ws if w in heard]
        flag = (len(expected) > 3 and sim < (0.5 if len(expected) <= SHORT else THRESHOLD)) or bool(name_miss)   # 1–3 個假名的單字辨識太不穩，不用相似度判
        flagged += flag
        rows.append({"key": key, "file": e["file"], "text": e["text"], "expected": expected, "heard": heard, "sim": round(sim, 3), "name_miss": name_miss, "flag": flag})
        if flag or show_all:
            print(f"  {'⚠' if flag else '✓'} {key} sim={sim:.2f}{' 人名:' + ','.join(name_miss) if name_miss else ''}\n     期待 {expected}\n     聽到 {heard}")
    OUT.mkdir(exist_ok=True)
    (OUT / f"{lid}.audio.json").write_text(json.dumps({"lesson": lid, "clips": len(rows), "flagged": flagged, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{lid}：{len(rows)} 段，可疑 {flagged} → verdicts/{lid}.audio.json")
    return {"clips": len(rows), "flagged": flagged}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lesson", nargs="+", required=True)
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    for lid in a.lesson:
        print(f"▶ {lid}")
        check_lesson(lid, a.all)


if __name__ == "__main__":
    main()
