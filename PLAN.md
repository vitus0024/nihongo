# 日文 N5 學習 App — 實作計畫（PLAN v0.1，待 Codex 審）

> 依據：`SPEC.md` v1.0（ChatGPT 專案匯出，2026-09-20）
> 本文件回答 SPEC §10.2「主要交付方式」——SPEC 定義**學什麼、怎麼評**；本文件定義**在哪裡看、怎麼做、進度怎麼算**。
> 狀態：草稿，尚未實作。先給 Codex 做對抗式審查，再由 Bryant 拍板。

## 0. 一句話

每天 06:00 雲端用 OpenAI API 照課綱生一課教材 JSON → 手機 PWA 當「閱讀器」一頁做完、打勾、算進度 → 口說、批改、弱點、難度調整留在 ChatGPT App（SPEC 的主控不動）。

## 1. 三層分工（核心設計決策）

| 層 | 執行者 | 負責 | 明確不負責 |
|---|---|---|---|
| 教材工廠 | GitHub Actions cron ＋ OpenAI API | 依 `curriculum.json` 生當天 `lessons/W03D2.json`，commit 回 repo | 不看使用者成績（v1 不做適應式） |
| 閱讀器 | PWA（GitHub Pages，iOS 加到主畫面） | 顯示今日課、TTS 播日文、小檢核自評、進度％、匯出週報 | 不批改、不對話 |
| 家教 | ChatGPT App（本專案＋語音模式） | 口說角色扮演、作業批改、週測、弱點清單、§7.2–7.3 的進度與難度調整 | 不當每日教材的主要閱讀介面 |

**為什麼這樣拆**：SPEC 最有價值的部分（口說、批改、弱點追蹤）是有狀態的對話，做成自動推播會消失；但每日教材本體（§4.1 九模組）是可照課綱生產的，而放在 ChatGPT 對話裡沒法播音、沒法打勾、找不到昨天的。

**進度狀態住哪（v1 決定：方案 A）**：存手機瀏覽器 localStorage；每週產一段「週報文字」貼給 ChatGPT，由 ChatGPT 做適應調整。不做 PWA→repo 回寫（方案 B，需要手機存 GitHub token）、不做後端（方案 C）。跑滿 4 週再評估要不要升級。

## 2. 資料

### 2.1 `curriculum.json`（一次生成、人工校對、之後手改）
20 週 × 6 天 ＝ 120 課。每課：
```json
{"id":"W03D2","week":3,"day":2,"stage":"基礎建立","theme":"購物：數字與價格",
 "grammar":["〜はいくらですか","数字 100–10000"],"vocab_theme":"商店、價格、數量",
 "minna_lesson":3,"reading_type":"菜單／價目表","listening_type":"店員對話",
 "speaking_task":"替換練習：問三樣東西的價格","day_type":"new"}
```
- `day_type`：`new`（Day1–5）／`review`（Day6 週測）／`stage_test`（第 4、8、12、16、20 週 Day6）
- 由 ChatGPT 依 SPEC §3 階段表＋《大家的日本語 初級Ⅰ》1–25 課對照生成，Bryant 校對一次
- 單字總數（≈1000）、文法總數（≈80）從這裡算出來，當進度分母

### 2.2 `lessons/W03D2.json`（每日生成）
對應 SPEC §4.1 九模組，schema 固定：
```
warmup[]      前課 3–5 題（v1：從前一課 vocab／grammar 抽，不看錯題）
vocab[10]     {kanji, kana, zh, pos, example_ja, example_zh, note}
grammar[1–2]  {pattern, structure, meaning, usage, forms, mistakes, compare, examples[≥3]}
patterns[5–10]{ja, kana, zh, swap_slots[]}
reading       {type, text_ja, text_kana, questions[], answers[]}   長度依週數 §4.7
listening     {script_ja, script_kana, questions[], answers[]}      15–60 秒份量
speaking      {type, task_ja, task_zh, chatgpt_prompt}             chatgpt_prompt = 貼給 ChatGPT 的完整任務
check[3–5]    {q, options[], answer, explain}
busy_mode     {vocab_review_ids[], listening:同上, speaking_short}  §5.2 20 分鐘版
```
- 生成 prompt ＝ SPEC §4 全文 ＋ 該課 curriculum 條目 ＋ 前一課的 vocab 清單（讓新詞重複出現、暖身有題可抽）＋ 情境優先序 §2.3
- 用 Structured Outputs 綁 schema，生完跑 `validate.py`：數量、必填、假名只含 kana、JSON 合法；不過就 exit 1 讓 Actions 紅燈（進修雷達同一招）

### 2.3 手機端狀態（localStorage）
```
done:   {W03D2: {modules:{vocab:true,...}, check_score:4/5, busy:false, date:"2026-10-06"}}
weekly: {W03: {quiz:{vocab:16,grammar:18,reading:15,listening:14,speaking:12}}}   Day6 自填
weak:   ["〜は〜です 否定","を/が","数字 600"]                                      手動加或從錯題加
```

## 3. 閱讀器（PWA）頁面

| 頁 | 內容 |
|---|---|
| 首頁 | **總進度 37%（44／120 課）**；階段名＋本階段 2／4 週；本週 3／6 天；單字 440／1000；文法 31／80；每週小測五分項折線（§7.3 的 85%／70% 畫成參考線） |
| 今日 | 九模組依序展開，每個做完打勾；頂部「忙碌版」開關只留 §5.2 三項；日期對應課次由「開始日＋已完成課數」算，不是死綁日曆（§5.2 未完成移到下一個正常日） |
| 單字 | 翻卡：漢字 → 假名 → 中文 → 例句；▶ 播 TTS |
| 聽力 | 先只出題；「看逐字稿」按了才顯示；分句 ▶；照 §4.5 盲聽→答題→看稿→跟讀→不看稿重聽 |
| 口說 | 顯示任務；「複製給 ChatGPT」把 `chatgpt_prompt` 進剪貼簿 |
| 課表 | 20 × 6 格，完成變色，點格子可回看任一課 |
| 週報 | 產一段文字：本週完成課次、小測分項、弱點清單、聽力錯誤類型（SPEC §11 的欄位）→ 貼給 ChatGPT；同一段也是「匯出／匯入」的備份格式 |

- TTS：`speechSynthesis`，`lang="ja-JP"`，iOS 內建 Kyoko／Otoya；不做 MP3（SPEC §4.5 明說不保證）
- 骨架複用料理靈感工具：單檔 HTML ＋ Service Worker ＋ GitHub Pages
- 內容從 `lessons/*.json` 讀，PWA 快取最近 14 課離線可用

## 4. 教材工廠（GitHub Actions）

- cron 每天 22:00 UTC（台灣 06:00）；`workflow_dispatch` 可指定 lesson id 重生
- 生哪一課：讀 `state/next_lesson.txt`（由前一次生成 +1），**不是**照日曆——休息日、值班日不生新課
- 失敗處理：API 錯或 validate 不過 → 紅燈寄信；PWA 沒新課就顯示昨天的並標「今日教材未更新」
- 金鑰：`OPENAI_API_KEY` 進 repo secret；本機在 `~/.config/openai/api_key`（600）
- LINE：生成成功後推一則「W03D2 購物：數字與價格 → 連結」，走進修雷達同一支 push 函式
- 成本估：每課 in ≈ 6k tokens（SPEC ＋課綱＋前課）、out ≈ 4k；gpt-5-mini 等級每月 < NT$100

## 5. 明確不做（v1）

- 適應式生成（看成績調教材）——交給 ChatGPT 家教
- 口說錄音、發音評分——ChatGPT 語音模式
- 跨裝置同步——方案 B 的事
- 帳號、後端、資料庫
- N4 階段內容（先把 20 週跑完）

## 6. 建置順序

1. `curriculum.json`：ChatGPT 生 → Bryant 校對 → 進 repo
2. `generate.py` ＋ `validate.py` ＋ schema；本機用 API 生 W01D1–W01D3 三課看品質，調 prompt
3. PWA：首頁進度 ＋ 今日頁 ＋ 單字 ＋ 聽力 TTS（先做這四個就能開始學）
4. Actions cron ＋ LINE 推播
5. 課表、週報、匯出／匯入
6. 跑 4 週後檢討：要不要方案 B、哪些頁沒在用

## 7. 前置條件

- [ ] OpenAI API key（Bryant 建）
- [ ] GitHub private repo `vitus0024/japanese-n5`
- [ ] ChatGPT 專案裡先生 `curriculum.json`（prompt 我來寫）

## 8. 想請 Codex 特別挑的地方

1. 三層拆法會不會讓學習體驗斷裂——「教材在 PWA、口說在 ChatGPT」每天要切兩個 app，實際會不會很煩？
2. 方案 A 把弱點清單留在手機，ChatGPT 靠週報文字接手，§7.2「未達 70% 次日先補強」這條在 v1 等於失效，可接受嗎？
3. 課次不綁日曆而綁「已完成課數」，跟 cron 每天生一課會不會脫節（例如三天沒學，cron 已經生了三課）？
4. Structured Outputs 對日文假名／漢字混排的品質風險
5. 有沒有比 localStorage 更省事、又不用後端的進度存法漏掉了
