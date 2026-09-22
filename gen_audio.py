#!/usr/bin/env python3
"""語音檔生成（PLAN §6b 的解法：預先生成音檔，app 用 <audio> 播放）。後端：OpenAI gpt-4o-mini-tts／VOICEVOX（本地）／ElevenLabs。

  ~/.venvs/nihongo/bin/python gen_audio.py --lesson W01D1 [W01D2 ...]   # 用 venv（有 fugashi）        # 一課的單字、例句、文法、句型、閱讀、聽力 → audio/W01D1/<hash>.mp3 ＋ index.json
  python3 gen_audio.py --csv words.csv --out audio/misc  # CSV 欄位 text[,name]；依 name（沒有就用 text）命名
  python3 gen_audio.py --text "こんにちは" --out audio/misc
  python3 gen_audio.py --compare "三百円です。"          # 三個後端各出一檔到 audio/_compare/，A/B 用
  python3 gen_audio.py --preview                         # 用 6 句探針試 tts_profile.json 的設定
  python3 gen_audio.py --speakers                        # 列 VOICEVOX speaker id

設定在 tts_profile.json（後端、聲音、語速、指令、version）。檔名帶 profile version：改聲音只重生受影響的；教材重生但句子沒變不重做。
金鑰：~/.config/openai/api_key、~/.config/elevenlabs/api_key（600、每台各存）；環境變數 OPENAI_API_KEY／ELEVENLABS_API_KEY 也接受。
VOICEVOX：沒在跑就自動啟動 /Applications/VOICEVOX.app 內建引擎。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
PROFILE = ROOT / "tts_profile.json"
AUDIO = ROOT / "audio"
VV_URL = "http://127.0.0.1:50021"
VV_ENGINE = Path("/Applications/VOICEVOX.app/Contents/Resources/vv-engine/run")
PROBES = ["こんにちは。私は台湾人です。", "三百円です。", "東京へ行きます。", "切手をください。雑誌もください。",
          "このお茶はいくらですか。", "エレベーターはあそこです。午前九時から午後五時までです。"]


def key_for(service: str) -> str | None:
    env = os.environ.get({"openai": "OPENAI_API_KEY", "elevenlabs": "ELEVENLABS_API_KEY"}[service])
    if env:
        return env.strip()
    p = Path.home() / ".config" / service / "api_key"
    return p.read_text().strip() if p.exists() else None


def load_profile() -> dict:
    if not PROFILE.exists():
        sys.exit("沒有 tts_profile.json——先建一個（見 --help 或 repo 裡的範例）")
    return json.loads(PROFILE.read_text(encoding="utf-8"))


# ---------- 後端（改自 Bryant 的 tts_compare.py） ----------
def tts_openai(text: str, prof: dict) -> bytes:
    key = key_for("openai")
    if not key:
        raise RuntimeError("沒有 OpenAI key（~/.config/openai/api_key）")
    payload = {"model": prof.get("model", "gpt-4o-mini-tts"), "voice": prof.get("voice", "sage"), "input": text,
               "instructions": prof.get("instructions", ""), "response_format": "mp3"}
    if prof.get("speed"):
        payload["speed"] = prof["speed"]
    req = urllib.request.Request("https://api.openai.com/v1/audio/speech", data=json.dumps(payload).encode(),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def vv_ready(start: bool = True) -> bool:
    try:
        urllib.request.urlopen(f"{VV_URL}/version", timeout=2)
        return True
    except Exception:
        if not start or not VV_ENGINE.exists():
            return False
        subprocess.Popen([str(VV_ENGINE), "--host", "127.0.0.1", "--port", "50021"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        for _ in range(30):
            time.sleep(2)
            try:
                urllib.request.urlopen(f"{VV_URL}/version", timeout=2)
                return True
            except Exception:
                pass
        return False


def tts_voicevox(text: str, prof: dict) -> bytes:
    if not vv_ready():
        raise RuntimeError("VOICEVOX 引擎起不來")
    spk = int(prof.get("speaker", 30))
    q = urllib.request.urlopen(urllib.request.Request(f"{VV_URL}/audio_query?speaker={spk}&text={urllib.parse.quote(text)}", method="POST"), timeout=15).read()
    aq = json.loads(q)
    for k in ("speedScale", "pitchScale", "intonationScale", "volumeScale", "prePhonemeLength", "postPhonemeLength"):
        if k in prof:
            aq[k] = prof[k]
    aq.setdefault("outputSamplingRate", 24000)
    wav = urllib.request.urlopen(urllib.request.Request(f"{VV_URL}/synthesis?speaker={spk}", data=json.dumps(aq).encode(),
                                                        headers={"Content-Type": "application/json"}, method="POST"), timeout=60).read()
    return wav_to_mp3(wav)


def wav_to_mp3(wav: bytes) -> bytes:
    """VOICEVOX 出 wav（一句 400KB），用 ffmpeg 轉 mp3 給網頁用；沒 ffmpeg 就原樣回 wav。"""
    try:
        r = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", "pipe:0", "-codec:a", "libmp3lame", "-b:a", "64k", "-f", "mp3", "pipe:1"],
                           input=wav, capture_output=True, check=True)
        return r.stdout
    except (FileNotFoundError, subprocess.CalledProcessError):
        return wav


def tts_elevenlabs(text: str, prof: dict) -> bytes:
    key = key_for("elevenlabs")
    if not key:
        raise RuntimeError("沒有 ElevenLabs key（~/.config/elevenlabs/api_key）")
    voice = prof.get("voice_id", "21m00Tcm4TlvDq8ikWAM")
    payload = {"text": text, "model_id": prof.get("model", "eleven_multilingual_v2"),
               "voice_settings": prof.get("voice_settings", {"stability": 0.5, "similarity_boost": 0.75})}
    req = urllib.request.Request(f"https://api.elevenlabs.io/v1/text-to-speech/{voice}", data=json.dumps(payload).encode(),
                                 headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


BACKENDS = {"openai": tts_openai, "voicevox": tts_voicevox, "elevenlabs": tts_elevenlabs}


def readings_table() -> tuple[dict[str, str], dict[str, str]]:
    """schema/readings.txt：全部條目（人名、にほん、時刻、助數詞、日期、〇）。TTS 跟斷詞器一樣會把這些唸錯，送出前先換成假名。
    回傳 (全部, 人名)。人名另外要求後面接 さん／です 等，避免誤傷（森林）。"""
    allr, names, section = {}, {}, ""
    for ln in (ROOT / "schema" / "readings.txt").read_text(encoding="utf-8").splitlines():
        if ln.startswith("#"):
            section = ln
            continue
        if "\t" in ln:
            k, v = (x.strip() for x in ln.split("\t", 1)); allr[k] = v
            if "人名" in section:
                names[k] = v
    return allr, names


READINGS, NAMES = readings_table()
try:
    import fugashi
    _TAGGER = fugashi.Tagger()
except ImportError:                                        # 用系統 python 跑時退回逐字比對（較粗）
    _TAGGER = None


def for_tts(text: str) -> str:
    """斷詞後，連續 token 拼起來命中 readings.txt 就換成假名（林→りん、二十歳→はたち、九時→くじ、〇→れい）。
    跟 validate_content.mecab_kana 同一套最長優先匹配，所以驗收的期待讀音與送 TTS 的文字一致。"""
    if not _TAGGER:
        out = text
        for k in sorted(READINGS, key=len, reverse=True):
            out = out.replace(k, READINGS[k])
        return out
    toks = [t.surface for t in _TAGGER(text)]
    out, i = [], 0
    while i < len(toks):
        hit = 0
        for j in range(min(len(toks), i + 5), i, -1):
            if "".join(toks[i:j]) in READINGS:
                out.append(READINGS["".join(toks[i:j])]); hit = j; break
        if hit:
            i = hit; continue
        out.append(toks[i]); i += 1
    return "".join(out)


def synth(text: str, prof: dict) -> bytes:
    return BACKENDS[prof["backend"]](for_tts(text), prof)


# ---------- 輸入來源 ----------
def lesson_items(lid: str) -> list[tuple[str, str]]:
    """(key, text)：key 用來對應 app 裡的欄位。"""
    d = json.loads((ROOT / "lessons" / f"{lid}.json").read_text(encoding="utf-8"))
    out: list[tuple[str, str]] = []
    if d["meta"]["day_type"] == "new":
        for v in d["vocab"]:
            out += [(f"vocab.{v['id']}", v["kana"] if v["kanji"] == v["kana"] else v["kanji"]), (f"vocab.{v['id']}.ex", v["example_ja"])]
        for g in d["grammar"]:
            out += [(f"grammar.{g['id']}.form.{i}", f["ja"]) for i, f in enumerate(g["forms"])]
            out += [(f"grammar.{g['id']}.ex.{i}", e["ja"]) for i, e in enumerate(g["examples"])]
        out += [(f"patterns.{i}", p["ja"]) for i, p in enumerate(d["patterns"])]
        out += [("reading", d["reading"]["text_ja"]), ("listening", d["listening"]["script_ja"])]
        out += [(f"listening.line.{i}", s) for i, s in enumerate(split_lines(d["listening"]["script_ja"]))]
        if d["speaking"].get("task_ja"):
            out.append(("speaking", d["speaking"]["task_ja"]))
    else:
        q = d["quiz"]
        if "passages" in q["reading"]:
            out += [(f"reading.{i}", p["text_ja"]) for i, p in enumerate(q["reading"]["passages"])]
            out += [(f"listening.{i}", s["script_ja"]) for i, s in enumerate(q["listening"]["scripts"])]
        else:
            out += [("reading", q["reading"]["text_ja"]), ("listening", q["listening"]["script_ja"])]
        if q["speaking"].get("task_ja"):
            out.append(("speaking", q["speaking"]["task_ja"]))
    return out


def split_lines(s: str) -> list[str]:
    import re
    parts = [x.strip() for x in re.split(r"(?<=[。？！」])\s*", s)]
    return [x for x in parts if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", x)]   # 只留有假名或漢字的片段（「」單獨一段不要）


def csv_items(p: Path) -> list[tuple[str, str]]:
    rows = list(csv.DictReader(p.open(encoding="utf-8-sig")))
    if not rows or "text" not in rows[0]:
        sys.exit("CSV 要有 text 欄（name 欄可選）")
    return [((r.get("name") or r["text"]).strip(), r["text"].strip()) for r in rows if r["text"].strip()]


# ---------- 生成 ----------
def fname(text: str, prof: dict, name: str | None = None) -> str:
    h = hashlib.sha1(f"{prof['backend']}|{prof.get('voice') or prof.get('speaker')}|{prof['version']}|{for_tts(text)}".encode()).hexdigest()[:12]
    ext = "mp3" if prof["backend"] != "voicevox" or have_ffmpeg() else "wav"
    return f"{safe(name)}.{ext}" if name else f"{h}.{ext}"


def safe(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in s)[:60]


_ff: bool | None = None


def have_ffmpeg() -> bool:
    global _ff
    if _ff is None:
        _ff = subprocess.run(["which", "ffmpeg"], capture_output=True).returncode == 0
    return _ff


def generate(items: list[tuple[str, str]], out_dir: Path, prof: dict, by_name: bool = False) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    idx_path = out_dir / "index.json"
    index = json.loads(idx_path.read_text(encoding="utf-8")) if idx_path.exists() else {}
    made = skipped = failed = 0
    for key, text in items:
        f = fname(text, prof, key if by_name else None)
        if (out_dir / f).exists() and index.get(key, {}).get("file") == f:
            skipped += 1
            continue
        try:
            data = synth(text, prof)
        except Exception as e:
            print(f"  ✗ {key}: {e}")
            failed += 1
            continue
        (out_dir / f).write_bytes(data)
        index[key] = {"file": f, "text": text, "profile": prof["version"], "backend": prof["backend"]}
        made += 1
        print(f"  ✓ {key} → {f} ({len(data) // 1024} KB)")
    wanted = {k for k, _ in items}
    stale = [k for k in index if k not in wanted]                 # 教材改了、句子沒了：索引與檔案一起移除（丟垃圾桶）
    for k in stale:
        f = out_dir / index.pop(k)["file"]
        if f.exists() and not any(v["file"] == f.name for v in index.values()):
            subprocess.run(["trash", str(f)], check=False)
    idx_path.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{out_dir.name}: 新生 {made}、沿用 {skipped}、失敗 {failed}" + (f"、移除 {len(stale)}" if stale else ""))
    return index


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lesson", nargs="*", help="課次 id")
    ap.add_argument("--extra", nargs="*", help="延伸閱讀週次（extras/W02.json → audio/extras-W02/）")
    ap.add_argument("--csv", type=Path)
    ap.add_argument("--text")
    ap.add_argument("--out", type=Path, help="--csv／--text 的輸出資料夾（預設 audio/misc）")
    ap.add_argument("--compare", metavar="TEXT", help="三個後端各出一檔")
    ap.add_argument("--preview", action="store_true", help="6 句探針試 profile")
    ap.add_argument("--speakers", action="store_true", help="列 VOICEVOX speaker")
    ap.add_argument("--backend", choices=BACKENDS, help="臨時覆蓋 profile 的後端")
    ap.add_argument("--redo", nargs="*", metavar="LESSON:KEY", help="強制重生指定段（音檔驗收裁決為 TTS 錯時用），例：W03D5:vocab.v0141.ex")
    a = ap.parse_args()

    if a.speakers:
        if not vv_ready():
            sys.exit("VOICEVOX 起不來")
        for s in json.loads(urllib.request.urlopen(f"{VV_URL}/speakers").read()):
            print(f"{s['name']:16s}", " | ".join(f"{st['id']:3d} {st['name']}" for st in s["styles"]))
        return

    prof = load_profile()
    if a.backend:
        prof = {**prof, **prof.get("backends", {}).get(a.backend, {}), "backend": a.backend}
    elif "backends" in prof:
        prof = {**prof, **prof["backends"].get(prof["backend"], {})}

    if a.redo:
        for spec in a.redo:
            lid, key = spec.split(":", 1)
            d = AUDIO / lid; idx_path = d / "index.json"; index = json.loads(idx_path.read_text(encoding="utf-8"))
            if key in index:
                f = d / index.pop(key)["file"]
                if f.exists() and not any(v["file"] == f.name for v in index.values()):
                    subprocess.run(["trash", str(f)], check=False)
                idx_path.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
        for lid in sorted({x.split(":", 1)[0] for x in a.redo}):
            print(f"▶ {lid}（重生指定段）")
            generate(lesson_items(lid), AUDIO / lid, prof)
        return
    if a.compare:
        out = AUDIO / "_compare"; out.mkdir(parents=True, exist_ok=True)
        for b in BACKENDS:
            p = {**prof, **prof.get("backends", {}).get(b, {}), "backend": b}
            try:
                data = synth(a.compare, p)
                f = out / f"{b}.{'mp3' if b != 'voicevox' or have_ffmpeg() else 'wav'}"
                f.write_bytes(data); print(f"  ✓ {b} → {f.relative_to(ROOT)} ({len(data) // 1024} KB)")
            except Exception as e:
                print(f"  – {b}: {e}")
        return
    if a.preview:
        generate([(f"probe{i}", t) for i, t in enumerate(PROBES)], AUDIO / "_preview" / f"{prof['backend']}-v{prof['version']}", prof, by_name=True)
        return
    if a.extra:
        for wk in a.extra:
            d = json.loads((ROOT / "extras" / f"{wk}.json").read_text(encoding="utf-8"))
            items = [("text", d["text_ja"])] + [(f"line.{i}", t) for i, t in enumerate(split_lines(d["text_ja"]))]
            print(f"▶ 延伸閱讀 {wk}")
            generate(items, AUDIO / f"extras-{wk}", prof)
    if a.lesson:
        for lid in a.lesson:
            print(f"▶ {lid}")
            generate(lesson_items(lid), AUDIO / lid, prof)
        return
    if a.csv:
        generate(csv_items(a.csv), a.out or AUDIO / "misc", prof, by_name=True)
        return
    if a.text:
        generate([(a.text, a.text)], a.out or AUDIO / "misc", prof, by_name=True)
        return
    ap.print_help()


if __name__ == "__main__":
    main()
