# 日文 N5 學習 App — 實作計畫（PLAN v0.2，待 Codex 第二輪審）

> 依據：`SPEC.md` v1.0（ChatGPT 專案匯出，2026-09-20）
> 本文件回答 SPEC §10.2「主要交付方式」——SPEC 定義**學什麼、怎麼評**；本文件定義**在哪裡看、怎麼做、進度怎麼算**。
> v0.2 變更（回應 `reviews-round1.md` 六項發現）：①§7.2／§8.2 規則改由 PWA 本機執行，ChatGPT 決策有回填路徑 ②課次改為狀態機，不再用「完成課數」推算 ③教材改為**分階段預生成**，取消每日 cron ④完整 JSON 備份與週報分開，且為開學前置條件 ⑤課綱帶有 ID 的單字／文法清冊 ⑥內容驗收分三層（斷詞器讀音核對、跨模型答案核對、人工抽驗）

## 0. 一句話

每個階段（4 週、24 課）開學前一次生好教材 JSON、過三層驗收 → 手機 PWA 當「閱讀器＋進度機」：選課、打勾、算進度、執行 SPEC §7.2／§8.2 的補強與門檻規則 → 口說、批改、弱點分析留在 ChatGPT App，它的判斷用一段固定格式貼回 PWA。

## 1. 三層分工

| 層 | 執行者 | 負責 | 明確不負責 |
|---|---|---|---|
| 教材庫 | `generate.py`（OpenAI API）＋ 三層驗收，每階段跑一次 | 依 `curriculum.json` 生該階段 24 課 `lessons/W03D2.json`，commit 進 repo | 不看使用者成績；不每天跑 |
| 閱讀器＋進度機 | PWA（GitHub Pages，iOS 加到主畫面） | 選下一課、九模組打勾、TTS、小檢核、**§7.2 次日補強、§7.2 中斷規則、§8.2 階段門檻**、進度％、完整備份、週報 | 不批改、不對話、不生內容 |
| 家教 | ChatGPT App（本專案＋語音模式） | 口說角色扮演與評分、作業批改、週測口說分項、弱點分析、§7.3 難度調整建議 | 不當每日教材的主要閱讀介面；不持有進度真相 |
| 提醒 | GitHub Actions cron ＋ LINE（進修雷達現成管道） | 每天 07:00 推「今天的日文 → 連結」；週六 20:00 推「週測」 | 不知道你在第幾課（連結進 PWA 由它選） |

**進度真相只有一份：PWA 的 localStorage**（方案 A）。ChatGPT 的判斷是「建議」，經由 §3.4 的貼回機制進入 PWA 才生效。

**v0.1→v0.2 最大的改變：取消每日生成。** v1 不做適應式教材，就沒有理由每天生；分階段預生讓品質問題在開學前抓到、沒有「今天教材沒生出來」的失敗模式、總成本不變。「持續生成」的含義變成：每階段開學前生下一批；ChatGPT 家教那層本來就是即時互動。

## 2. 資料

### 2.1 `curriculum.json`（每階段由 ChatGPT 生 → Bryant 校對 → 進 repo，帶 `version`）
```json
{"version":"2026-09-20.1",
 "vocab":   [{"id":"v0123","kanji":"財布","kana":"さいふ","zh":"錢包","pos":"名","minna":3}, ...],   ≈1000 筆，來源《大家的日本語 初級Ⅰ》各課單字表
 "grammar": [{"id":"g012","pattern":"〜はいくらですか","minna":3}, ...],                          ≈80 筆
 "lessons": [
  {"id":"W03D2","week":3,"day":2,"stage":2,"stage_name":"基礎建立","day_type":"new",
   "theme":"購物：數字與價格","minna_lesson":3,
   "new_vocab":["v0121","v0122",...10],"review_vocab":["v0088",...],"new_grammar":["g012"],
   "reading_type":"價目表","listening_type":"店員對話","speaking_task":"替換練習：問三樣東西的價格"},
  ...120 筆]}
```
- `day_type`：`new`（Day1–5，10 個新詞）／`review`（Day6 週測，`new_vocab` 為空）／`stage_test`（第 4、8、12、16、20 週 Day6）
- **進度分母從清冊算**：單字 ＝ `vocab` 唯一 ID 數；文法 ＝ `grammar` 唯一 ID 數；課 ＝ 120。Day6 不貢獻新詞，不會虛增
- 生成 prompt 拿到的是**指定要教的單字項目**（含漢字／假名／中文），模型不自己選詞、不會重複教

### 2.2 `lessons/W03D2.json`（每階段預生成）
對應 SPEC §4.1 九模組，schema 固定（`schema/lesson.schema.json`，Structured Outputs 綁定）：
```
meta          {id, curriculum_version, lesson_version, generated_at, model}
warmup[3–5]   從 review_vocab／前課 grammar 出題（v1 固定，不看錯題；補強由 PWA 用本課資料另組）
vocab[10]     {id, kanji, kana, zh, pos, example_ja, example_kana, example_zh, note}   id 必須 ∈ new_vocab
grammar[1–2]  {id, pattern, structure, meaning, usage, forms, mistakes, compare, examples[≥3]{ja,kana,zh,scene}}
patterns[5–10]{ja, kana, zh, swap_slots[]}
reading       {type, text_ja, text_kana, questions[]{q, options[], answer, evidence}}   evidence = 原文中支持答案的片段
listening     {script_ja, script_kana, questions[]{q, options[], answer, evidence}}
speaking      {type, task_ja, task_zh, chatgpt_prompt}
check[3–5]    {q, options[], answer, explain, tests: "v0123"|"g012"}   每題標記考的是哪個項目 → 錯題自動進弱點
busy_mode     {vocab_review_ids[], listening: 同上, speaking_short}
```
- 生成模型：OpenAI API（gpt-5 系列，`generate.py` 可換）；驗收另用 Claude（§4）
- 每課 in ≈ 8k（SPEC §4 ＋ 該課 curriculum 條目 ＋ 指定單字 ＋ 前一課 grammar）、out ≈ 5k；120 課總量約 1.6M tokens，一次性成本 < NT$500

### 2.3 手機端狀態（localStorage，`schema` 帶版本）
```
{"schema":1,"curriculum_version":"2026-09-20.1","started":"2026-09-27",
 "lessons":{"W03D2":{"status":"done","modules":{"vocab":true,...9 項},"check":{"score":4,"total":5,"wrong":["v0123"]},
                     "done_at":"2026-10-06","remedial_done":true}},
 "practice":[{"date":"2026-10-07","kind":"busy","lesson":"W03D2","minutes":20}],     忙碌版、休息日輕量、補強都記這裡，不動課次狀態
 "weekly":{"W03":{"quiz":{"vocab":16,"grammar":18,"reading":15,"listening":14,"speaking":12},"entered_at":"..."}},
 "stage":{"2":{"test":{"total":74,"parts":{...}},"passed":true,"remedial_week":false}},
 "weak":[{"id":"v0123","source":"check","count":2,"first":"2026-10-06"},{"id":"g012","source":"chatgpt","note":"を/が 混用"}],
 "diagnostic":{"exempt_vocab":["v0001",...],"exempt_grammar":["g001"],"skip_kana_review":true},
 "last_activity":"2026-10-07"}
```

## 3. 進度機（PWA 本機規則，取代 v0.1 的「完成課數」）

### 3.1 課次狀態
`locked` → `available` → `partial`（有模組打勾）→ `done`（九模組全勾＋小檢核有分數）；另有 `exempt`（診斷豁免，§7.1）、`remedial`（小檢核 <70%，次日要先補強）。

### 3.2 選「下一課」
1. 若上一次完成的課 `status=remedial` 且 `remedial_done=false` → 先出**補強區塊**（該課 check 錯題 ＋ 錯題對應的 vocab／grammar ＋ 5 題重出），完成才解鎖下一課（§7.2）
2. 若 `today − last_activity ≥ 7 天` → 先出**回歸測驗**（最近一個 `review` 課的 warmup ＋ 最近 20 個 done 單字抽 10），依結果建議「從 W0xD1 重來」或「續」，由使用者選（§7.2 中斷 >7 天）
3. 若 `1–3 天` → 先出 5 題短複習，不補課（§7.2 中斷 1–3 天）
4. 否則 → 課綱順序第一個非 `done/exempt` 的課；但若它屬於下一階段且該階段 `passed≠true` → 顯示「階段測驗未通過／未填分數」，鎖住（§8.2）
- **忙碌版**：任何一課都能開「忙碌版」，做完記進 `practice`，**不改課次狀態、不推進**（SPEC §5.2「未完成的新內容移到下一個正常學習日」）
- **診斷**：第 0 週在 PWA 做（假名、單字、文法、閱讀；聽力與口說在 ChatGPT），結果標 `exempt`，被豁免的單字仍算進度分母但直接計入「已學」

### 3.3 階段門檻（§8.2）
`stage_test` 課完成 ＝ 填入五分項分數（口說分數來自 ChatGPT）。總分 ≥70 且各項 ≥60 → `passed`；否則 `remedial_week=true`：該階段所有課保持可開，PWA 顯示「補強週：弱項 ＝ 聽力、口說」，一週後可重填弱項分數重測（只填弱項，§8.2）。N4 判定（§8.3）同法，六條件做成 checklist。

### 3.4 ChatGPT → PWA 回填契約
ChatGPT 專案的固定指令（寫進它的 project instructions）：每次週測批改或弱點分析結尾，輸出一段：
```
```n5-feedback
{"week":"W03","speaking":12,"weak_add":[{"id":"g012","note":"を/が 混用"},{"text":"数字 600 的讀音","note":"ろっぴゃく"}],"weak_remove":["v0088"],"suggest":"下週聽力加一次針對性練習"}
```
```
PWA「從 ChatGPT 貼回」貼上整段 → 驗證 → 合併：`speaking` 填進 weekly、`weak_add` 依 id 合併（無 id 的以 text 存）、`suggest` 顯示在首頁一週。**PWA 不自動執行 §7.3 難度調整**（那是教材層的事，v1 不做），只顯示建議。

### 3.5 PWA → ChatGPT 週報
週報頁產生純文字（SPEC §11 欄位）：本週完成課次與日期、新增／複習單字範圍、文法、小測五分項、弱點清單、聽力錯誤類型、上週 `suggest` 有無執行。貼給 ChatGPT 做週檢討。**週報不是備份**（見 §5）。

## 4. 教材庫：生成與三層驗收

### 4.1 流程（每階段一次，本機跑）
`generate.py --stage 2` → 24 課 → `validate_structure.py` → `validate_content.py` → 人工抽驗 → commit。任何一層失敗的課標 `needs_fix`，不進 PWA。

### 4.2 三層驗收
| 層 | 工具 | 檢查 | 不過怎麼辦 |
|---|---|---|---|
| 結構 | JSON schema | 數量、必填、`vocab.id ⊆ new_vocab`、`check.tests` 都是合法 ID、假名欄只含 ひらがな／カタカナ／ー／標點空白 | 自動重生該課（最多 2 次） |
| 內容-機械 | `fugashi`＋`unidic-lite` | 每個 vocab 的 kana 與斷詞器讀音一致；例句 `example_kana` 與 `example_ja` 逐詞讀音比對，不一致率 >10% 標記 | 列出不一致清單給下一層 |
| 內容-跨模型 | Claude（`validate_content.py` 呼叫 Claude API） | 每題 `answer` 是否被 `evidence` 支持、`evidence` 是否真的在原文、文法 `forms` 變化是否正確、`mistakes` 是否成立、情境是否符合 §2.3 | 回報 fail 項目；自動把回報餵回 `generate.py --fix W03D2` 重生一次；仍 fail → `needs_fix` 人工看 |
| 人工 | Bryant | 每階段抽 3 課（各 day_type 一課）通讀 | 改 prompt 後重生整階段 |

### 4.3 錯誤教材的處置
PWA 每課有「回報錯誤」按鈕 → 存進 `weak` 旁的 `lesson_issues[]`，進週報；修正後 `lesson_version+1`，PWA 依 `meta.lesson_version` 提示「本課已更新」。

## 5. 備份與還原（開學前置條件）

- **完整匯出**：整份 §2.3 狀態 JSON（含 schema、curriculum_version、started）→ 複製到剪貼簿／iOS 分享表 → 存 iCloud 備忘錄或檔案。首頁提醒：每週日匯出一次；連續 7 天未匯出顯示黃色提示
- **匯入**：檢查 `schema` 與 `curriculum_version`；版本不同→提示可能對不上；二選一：**取代**（整份覆蓋）或 **合併**（每課取 `done_at` 較晚者、practice 聯集、weak 依 id 聯集、weekly 取有值者）
- **驗收條件**：Day 1 前做一次「匯出 → 清站台資料 → 匯入 → 進度一致」的測試，通過才算可用
- 週報只作溝通摘要，不承擔還原

## 6. 閱讀器頁面

| 頁 | 內容 |
|---|---|
| 首頁 | **總進度 37%（44／120 課）**；階段名＋本階段 2／4 週；本週 3／6；單字 440／1000（唯一 ID）；文法 31／80；小測五分項折線，85%／70% 參考線；本週 ChatGPT `suggest`；備份提醒 |
| 今日 | §3.2 選出的課（或補強／回歸測驗／短複習）；九模組依序展開打勾；「忙碌版」開關 |
| 單字 | 翻卡：漢字→假名→中文→例句；▶ TTS；「不會」按鈕直接進 weak |
| 聽力 | 先只出題；「看逐字稿」按了才顯示；分句 ▶；§4.5 順序 |
| 口說 | 顯示任務；「複製給 ChatGPT」 |
| 課表 | 20×6 格，狀態上色（done／partial／remedial／exempt／locked），點格子回看 |
| 週報／貼回 | 產週報文字；「從 ChatGPT 貼回」輸入框 |
| 設定 | 匯出／匯入；開始日；診斷結果；回報錯誤清單 |

- TTS：`speechSynthesis` `ja-JP`（iOS Kyoko／Otoya）；不做 MP3（SPEC §4.5）
- 骨架複用料理靈感工具：單檔 HTML ＋ Service Worker ＋ GitHub Pages；`lessons/*.json` 全部靜態，SW 快取當前階段 24 課

## 7. 明確不做（v1）

- 適應式教材生成（看成績改教材）——§7.3 的調整由 ChatGPT 給建議、Bryant 決定要不要改課綱重生
- 口說錄音、發音評分——ChatGPT 語音模式
- 跨裝置自動同步——匯出／匯入手動；方案 B 留待 4 週後評估
- 帳號、後端、資料庫
- N4 階段內容

## 8. 驗收情境（Codex 第一輪要求的五個 ＋ 一個）

| 情境 | 預期行為 |
|---|---|
| 忙碌兩天後恢復 | 兩天各記一筆 `practice(busy)`，課次不動；第三天 `last_activity` 差 1–3 天 → 5 題短複習 → 續原課 |
| 診斷跳課 | 診斷標 `exempt_vocab`；含這些詞的課照上，但那些詞在單字頁標「已會」，進度直接計入 |
| 階段測驗未過 | `remedial_week=true`，下階段鎖住，首頁顯示弱項；一週後重填弱項分數 → 過則解鎖 |
| 手機資料清空 | 匯入上週日的完整 JSON → 進度回到那時；中間幾天用 `practice` 補記 |
| 教材答案錯誤 | 「回報錯誤」→ 週報；修正重生 → `lesson_version+1` → PWA 提示更新 |
| 三週沒學 | ≥7 天 → 回歸測驗 → 使用者選重來點；`practice` 空白期不影響狀態 |

## 9. 建置順序

1. `curriculum.json`：ChatGPT 生第 1 階段（清冊＋24 課）→ Bryant 校對 → repo
2. `generate.py`＋schema＋`validate_structure.py`；本機生 W01D1–D3 看品質、調 prompt
3. `validate_content.py`（fugashi ＋ Claude 核對）；生完整第 1 階段，人工抽 3 課
4. PWA：**首頁進度 ＋ 今日（含 §3.2 選課規則）＋ 單字 ＋ 聽力 TTS ＋ 匯出／匯入**（開學最小集合）
5. 備份還原驗收（§5）→ 第 0 週診斷 → Day 1
6. 課表、週報、貼回、回報錯誤、LINE 提醒
7. 第 2 階段開學前兩週：生第 2 階段；跑滿 4 週檢討方案 B 與沒在用的頁

## 10. 前置條件

- [ ] OpenAI API key（生成）＋ Anthropic API key（驗收；或改用本機 Claude Code 跑驗收，免 key）
- [ ] GitHub private repo `vitus0024/japanese-n5`（Pages 用；私有 repo 的 Pages 需 Pro 或改公開——**待確認**）
- [ ] ChatGPT 專案 instructions 加入 §3.4 的回填格式
- [ ] `curriculum.json` 第 1 階段

## 11. 請 Codex 第二輪特別挑的地方

1. §3.2 選課規則的優先順序有沒有互相打架的情況（例如既 remedial 又中斷 >7 天）
2. §3.4 回填契約：ChatGPT 會不會不穩定地輸出這段？格式要不要更寬鬆？
3. 分階段預生成後，§7.3「連續兩週 85% 以上加難度」在 v1 只剩建議——這樣的取捨 SPEC 能不能接受，還是要明寫修訂 SPEC
4. 三層驗收裡 fugashi 讀音核對對片假名外來語、數字讀音（ろっぴゃく）的誤報率
5. §5 合併規則會不會造成 remedial 狀態被較舊備份蓋掉
6. 還有什麼是「開學第一週就會撞到」而這裡沒寫的
