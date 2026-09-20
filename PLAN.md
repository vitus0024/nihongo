# nihongo — 日文學習 App（第一段：N5） — 實作計畫（PLAN v0.6 — 設計 v0.5 經 Codex 五輪 approved；v0.6 只改生成工具，2026-09-20）

> 依據：`SPEC.md` v1.0（ChatGPT 專案匯出，2026-09-20）
> 本文件回答 SPEC §10.2「主要交付方式」——SPEC 定義**學什麼、怎麼評**；本文件定義**在哪裡看、怎麼做、進度怎麼算**。
> v0.6 變更（實作階段調整，不動設計）：教材與課綱改用 **Codex CLI（`codex exec`，ChatGPT 訂閱登入）** 生成，不用 OpenAI API；內容驗收由 Claude Code 本機做，不用 Anthropic API。前置條件少掉兩把 key。課綱第 1 階段已用此法生成並通過 `build_curriculum.py`
> v0.5 變更（回應 `reviews-round4.md` 三項＋一則備註）：①輪次切換時，X 之前的階段資格**承接**到新輪次 ②總分不足時重測集合＝所有 <70% 的分項，保證非空 ③todo 完成檢查依 kind 分別驗證 ④「失衡」明訂為相對差距，並明寫接受其非單調性
> v0.4 變更（回應 `reviews-round3.md` 四項）：①三種 day_type 各自的完成條件與狀態轉移表 ②「重來」改為原子的**學習輪次**切換，todo／adjust_tasks／stage 資格全部帶輪次 ③todo 帶流程日期與結算時的 last_activity，跨日重新評估中斷長度 ④階段通過判定統一成一個函式，聽說門檻併入 remedial_parts
> v0.3 變更（回應 `reviews-round2.md` 七項）：①階段入場改為「前一階段通過」②補強完成轉 done；當日先結算待辦清單再選課 ③schema 依 day_type 分支 ④備份 v1 只做整份取代 ⑤回歸測驗只用已學項目、零資料回首課；「重來」定義 ⑥§7.3 做成可追蹤的人工任務（Bryant 決定：不修 SPEC）⑦讀音警示逐筆裁決才可發布、涵蓋所有假名欄位、先量誤報率
> v0.2 變更（回應 `reviews-round1.md` 六項發現）：①§7.2／§8.2 規則改由 PWA 本機執行，ChatGPT 決策有回填路徑 ②課次改為狀態機，不再用「完成課數」推算 ③教材改為**分階段預生成**，取消每日 cron ④完整 JSON 備份與週報分開，且為開學前置條件 ⑤課綱帶有 ID 的單字／文法清冊 ⑥內容驗收分三層（斷詞器讀音核對、跨模型答案核對、人工抽驗）

## 0. 一句話

每個階段（4 週、24 課）開學前一次生好教材 JSON、過三層驗收 → 手機 PWA 當「閱讀器＋進度機」：選課、打勾、算進度、執行 SPEC §7.2／§8.2 的補強與門檻規則 → 口說、批改、弱點分析留在 ChatGPT App，它的判斷用一段固定格式貼回 PWA。

## 1. 三層分工

| 層 | 執行者 | 負責 | 明確不負責 |
|---|---|---|---|
| 教材庫 | `codex exec`（ChatGPT 訂閱登入，不用 API key）＋ 三層驗收，每階段跑一次 | 依 `curriculum.json` 生該階段 24 課 `lessons/W03D2.json`，自跑結構驗證修到過，commit 進 repo | 不看使用者成績；不每天跑 |
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
schema 依 `day_type` 分支（`schema/lesson-new.schema.json`、`lesson-review.schema.json`、`lesson-stage_test.schema.json`，Structured Outputs 各自綁定）：

**`new`（Day1–5）**——SPEC §4.1 九模組：
```
meta          {id, day_type, curriculum_version, lesson_version, generated_at, model}
warmup[3–5]   從 review_vocab／前課 grammar 出題（v1 固定，不看錯題；補強由 PWA 用本課資料另組）
vocab[10]     {id, kanji, kana, zh, pos, example_ja, example_kana, example_zh, note}   id 集合必須 ＝ new_vocab（不多不少、不重複）
grammar[1–2]  {id, pattern, structure, meaning, usage, forms, mistakes, compare, examples[≥3]{ja,kana,zh,scene}}
patterns[5–10]{ja, kana, zh, swap_slots[]}
reading       {type, text_ja, text_kana, questions[]{q, options[], answer, evidence}}   evidence = 原文中支持答案的片段
listening     {script_ja, script_kana, questions[]{q, options[], answer, evidence}}
speaking      {type, task_ja, task_zh, chatgpt_prompt}
check[3–5]    {q, options[], answer, explain, tests: "v0123"|"g012"}   每題標記考的是哪個項目 → 錯題自動進弱點
busy_mode     {vocab_review_ids[], listening: 同上, speaking_short}
```
**`review`（Day6 週測，SPEC §8.1）**——沒有新詞、沒有新文法：
```
meta, quiz{vocab[10]{q,options,answer,tests}, grammar[10]{…}, reading{text_ja,text_kana,questions[5]}, listening{script_ja,script_kana,questions[5]},
      speaking{task_ja, task_zh, chatgpt_prompt, rubric: 五面向各 4 分}}   tests 只能引用本週 new_vocab／new_grammar
review_pack   {vocab_ids: 本週 50 詞, grammar_ids}                          給 PWA 做錯題訂正頁
busy_mode     同 new
```
**`stage_test`（第 4／8／12／16／20 週 Day6，SPEC §8.2）**——同 review 結構，但 `tests` 可引用整個階段的項目，題數 vocab 20／grammar 20／reading 2 篇／listening 2 段，另附 `n5_mock: true`（第 20 週）。
- 結構驗證以 W01D6、W04D6 各生一課確認有合法輸出，才算 schema 完成
- 生成：`codex exec --sandbox workspace-write`，prompt ＝ `prompts/lesson.md`（含 SPEC §4 摘要、該課 curriculum 條目展開成實際單字／文法、前一課的 grammar、schema 路徑）；Codex 寫檔後自跑 `validate_structure.py`，不過就自己修（課綱那步已驗證此流程可行）
- 沒有 Structured Outputs 綁定，靠 schema 驗證＋自修；一課一個 `codex exec`，可平行
- 成本：ChatGPT 訂閱額度，不另計費；課綱兩段共用了 ≈ 55k tokens

### 2.3 手機端狀態（localStorage，`schema` 帶版本）
```
{"schema":1,"curriculum_version":"2026-09-20.1","started":"2026-09-27",
 "lessons":{"W03D2":{"status":"done","modules":{"vocab":true,...9 項},"check":{"score":4,"total":5,"wrong":["v0123"]},
                     "done_at":"2026-10-06","remedial_done":true}},
 "practice":[{"date":"2026-10-07","kind":"busy","lesson":"W03D2","minutes":20}],     忙碌版、休息日輕量、補強都記這裡，不動課次狀態
 "weekly":{"W03":{"quiz":{"vocab":16,"grammar":18,"reading":15,"listening":14,"speaking":12},"entered_at":"..."}},
 "stage":{"2":{"round":1,"test":{"total":74,"parts":{...},"taken":"2026-10-25"},"passed":true,"remedial_parts":[],"retest_after":null}},   只讀目前 round 的紀錄
 "weak":[{"id":"v0123","source":"check","count":2,"first":"2026-10-06"},{"id":"g012","source":"chatgpt","note":"を/が 混用"}],
 "diagnostic":{"exempt_vocab":["v0001",...],"exempt_grammar":["g001"],"skip_kana_review":true},
 "round":1,                                                                          學習輪次；「重來」+1（§3.6）
 "flow":{"date":"2026-10-07","settled_last_activity":"2026-10-04","round":1},         本次待辦結算的日期（Asia/Taipei，固定）與依據
 "todo":[{"kind":"remedial","lesson":"W03D2","round":1},{"kind":"return_test","round":1}],   做完才刪；完成時檢查 round 與課次狀態仍有效
 "adjust_tasks":[{"id":"a03","rule":"7.3-low","part":"listening","week":"W05","round":1,"task":"本週加一次針對性聽力練習（NHK Easy 一篇＋跟讀）","done":false}],
 "feedback_log":[{"week":"W03","received":"2026-10-11","hash":"…"}],   §3.4 重貼防重
 "last_activity":"2026-10-07"}
```

## 3. 進度機（PWA 本機規則，取代 v0.1 的「完成課數」）

### 3.1 課次狀態與轉移（依 day_type，回應第三輪 #1）
共同狀態：`locked` → `available` → `partial` → `done`；另有 `exempt`（診斷豁免）、`remedial`（欠一次補強）。

| day_type | `partial` | `done` 條件 | 失敗轉移 |
|---|---|---|---|
| `new` | 任一模組打勾 | 九模組全勾 ＋ 小檢核有分數 | 小檢核 <70% → `remedial`（課算學過，欠補強）；補強完成 → `done`、`remedial_done=true` |
| `review` | 任一 quiz 分項作答 | quiz 四個自動分項（單字／文法／閱讀／聽力）作答完 ＋ **錯題訂正頁**做完；`weekly[W].quiz` 四項在**同一次提交**寫入 | 沒有 remedial（SPEC §8.1 週測不擋進度）；口說分數可後補：`weekly[W].quiz.speaking=null` 時首頁提示「口說分數待填」，3 天後標黃，不鎖課 |
| `stage_test` | 同 review | 同 review ＋ `stage[S].test` 在同一次提交寫入；口說分數**必填**（§8.2 五分項都要） | 由 §3.3 通過函式決定 `passed`／`remedial_parts`；不通過不改課次狀態，只鎖下一階段 |

**同一次狀態提交**：`lesson.status`、`weekly`、`stage`、`todo` 的變更在一個函式內一起寫回 localStorage，不分兩步，避免寫到一半關 app。

### 3.2 選「下一課」——兩段式：先結算待辦，再選課

**A. 開啟流程時結算 `todo`**（回應第三輪 #3，冪等且跨日會重評）。「今天」＝ Asia/Taipei 固定時區的日曆日（不隨手機時區變）：
- `flow.date == today` 且 `todo` 非空 → **同日重開：沿用**，不重算
- 否則（首次、或 `flow.date < today`）→ 重新結算：
  - 保留既有 `todo{remedial}`（義務不消失）；補加目前所有 `status=remedial && !remedial_done` 的課
  - 用 **`last_activity`**（只在實際學習完成時更新：模組打勾、quiz 提交、練習記錄、補強完成；開 app、看課表不算）算 gap：`≥7` → `return_test`；`1–6` → `short_review`；若舊 todo 有 `short_review` 而 gap 已 ≥7 → **升級**為 `return_test`（擱置十天的情境）
  - 寫入 `flow{date: today, settled_last_activity, round}`
- 順序：**先回歸測驗、再補強、再短複習**；全部完成才進 B
- todo 完成時的有效性檢查**依 kind**（回應第四輪 #3）：全部檢查 `todo.round == state.round`；`remedial` 另檢查目標課仍是 `remedial && !remedial_done`；`return_test`／`short_review` 另檢查 `flow.round == state.round`。不符 → 丟棄該 todo，並重新結算（不進 B）。結果處理、todo 移除、`last_activity` 更新在同一次提交

**B. 選課**：課綱順序第一個 `status ∉ {done, exempt, remedial}` 的課。若它是階段 S 的第一課（S ≥ 2）且 `stage[S−1].passed ≠ true` → 鎖住並顯示「第 S−1 階段測驗未通過／未填分數」（§8.2；回應第二輪 #1：**入場條件是前一階段**）。第 1 階段入場條件 ＝ 診斷完成（或明確跳過診斷）。

**回歸測驗的內容**（回應第二輪 #5）：只從 `status ∈ {done, remedial}` 的課取——單字抽 min(10, 已學數)，文法抽 min(3, 已學數)，加最近一個已完成 `review` 課的 5 題（若無則略）。零已學 → 不出測驗，直接回首課。結果 <50% → 建議「重來」（§3.6）；選「續」則什麼都不改。

### 3.6 「重來」＝ 原子的學習輪次切換（回應第三輪 #2）
使用者選一個課次 X 後，**一次提交**做完以下全部：
1. `round += 1`
2. X 起（含）所有課：`status=available`，清空 `modules`、`check`、`remedial_done`、`done_at`
3. `todo` 清空（正在做的 return_test 視為已完成）；`flow` 重寫為今天＋新 round
4. `adjust_tasks` 中 `week ≥ week(X)` 者標 `superseded`
5. `weekly` 中 `week ≥ week(X)`、`stage` 中 `stage ≥ stage(X)` 的紀錄搬進 `history[]`（保留可看），目前欄位清空 → 該階段 `passed` 隨之失效，下一階段重新鎖住
5b. **承接**（回應第四輪 #1）：`stage` 中 `stage < stage(X)` 的紀錄與 `weekly` 中 `week < week(X)` 的紀錄，`round` 改寫為新輪次並加 `carried_from: 舊 round`；X 之前的課次狀態不動。因此從 W05D1 重來時 `stage[1].passed` 仍有效，W05D1 可入場
5c. `adjust_tasks` 中 `week < week(X)` 且未完成者同樣承接（義務不因重來消失）
6. `weak`、`practice`、`diagnostic`、`lesson_issues` 不動
所有門檻（§3.2 B、§3.3）只讀 `round == state.round` 的紀錄；舊 round 的 todo／任務／資格一律無效。
- **忙碌版**：任何一課都能開「忙碌版」，做完記進 `practice`，**不改課次狀態、不推進**（SPEC §5.2「未完成的新內容移到下一個正常學習日」）
- **診斷**：第 0 週在 PWA 做（假名、單字、文法、閱讀；聽力與口說在 ChatGPT），結果標 `exempt`，被豁免的單字仍算進度分母但直接計入「已學」

### 3.3 階段門檻（§8.2）
**統一的通過判定函式**（回應第三輪 #4），輸入五分項各 0–20、總分 0–100，輸出 `passed` 與 `remedial_parts`：
```
pct(p)   = 分項分數 / 20
written  = avg(pct(vocab), pct(grammar), pct(reading))
remedial_parts = { p | pct(p) < 60% }                                                  ← §8.2 各項下限
               ∪ { p ∈ {listening, speaking} | pct(p) < 70% and written − pct(p) ≥ 20 點 }   ← §8.2「無明顯失衡」＋§7.3「聽說落後不加速」
               ∪ ( total < 70% ? { p | pct(p) < 70% } : ∅ )                            ← 總分不足時保證重測集合非空（回應第四輪 #2）
passed = total ≥ 70% and remedial_parts 為空
```
- 「失衡」＝ 聽力或口說 <70% **且**落後筆試平均 ≥20 點。這是相對判準，所以筆試變好可能讓原本能過的組合變成不過（第四輪備註的非單調）——**接受**，因為 SPEC §8.2「無明顯失衡」本來就是相對概念，且沒有人會為了通過而故意考差筆試
- 總分 <70% 時至少有一個分項 <70%（平均性質），所以重測集合必非空
- 不通過 → `stage[S] = {passed:false, remedial_parts, retest_after: taken + 7 天}`；該階段所有課保持可開，首頁顯示「補強週：弱項 ＝ 聽力」；`retest_after` 之後可**只重填 remedial_parts 的分數**，其餘沿用，**五項最新有效分數重新加總**再跑同一個函式（§8.2 只重測弱項）
- 通過 → `passed:true`，下一階段第一課解鎖
- 判定只讀 `stage[S].round == state.round` 的紀錄
- N4 判定（§8.3）：六條件 checklist，兩次模擬測驗各自跑上述函式

### 3.3b §7.3 難度調整 → 可追蹤的人工任務（Bryant 決定：不修 SPEC，做成 B 方案）
每週填完 `weekly` 分數時自動評估，符合就產生 `adjust_tasks`，出現在首頁「本週必做」，要打勾才消失；連續未完成會在週報標紅：
| 觸發（SPEC §7.3） | 產生的任務 |
|---|---|
| 連續兩週總分 ≥85 | 「本週閱讀改讀 NHK Easy 一篇完整文章＋口說任務改自由敘述 3 分鐘」（加自然度，不加背誦量） |
| 任一分項連續兩週 <70 | 「本週該分項加一次針對性練習」，內容依分項：聽力＝NHK Easy 一篇盲聽→跟讀；口說＝ChatGPT 角色扮演一次；閱讀＝重讀本週兩篇＋問題；單字／文法＝錯題訂正頁重做 |
| 聽力或口說落後而筆試高分 | 不另設任務——已併入 §3.3 通過函式的 `remedial_parts`，走補強週＋只重測該項 |
教材本身不改（v1 不做適應式生成）；任務完成紀錄進週報，ChatGPT 據此再給下週建議。

### 3.4 ChatGPT → PWA 回填契約
ChatGPT 專案的固定指令（寫進它的 project instructions）：每次週測批改或弱點分析結尾，輸出一段：
```
```n5-feedback
{"week":"W03","speaking":12,"weak_add":[{"id":"g012","note":"を/が 混用"},{"text":"数字 600 的讀音","note":"ろっぴゃく"}],"weak_remove":["v0088"],"suggest":"下週聽力加一次針對性練習"}
```
```
PWA「從 ChatGPT 貼回」貼上整段 → **嚴格驗證**（回應第二輪：格式不放寬）：必須是 ```n5-feedback 圍欄內的合法 JSON；`week` 必須是已存在或本週的週次；`speaking` 0–20 整數；`weak_add[].id` 若有必須存在於課綱；不合法就整段拒絕並指出第幾個欄位。通過後：`speaking` 填進 weekly（已有值則問「覆蓋？」）、`weak_add` 依 id 合併（無 id 的以 text 存）、`suggest` 顯示在首頁一週。**重貼防重**：整段內容 hash 記進 `feedback_log`，同 hash 第二次貼直接忽略；同週不同內容視為修正，以新的為準並提示。
若 ChatGPT 沒輸出這段：PWA 提供「產生索取指令」按鈕，複製一句「請以 n5-feedback 格式輸出本週回饋」貼回 ChatGPT。§7.3 的調整不靠這段，由 PWA 自己依分數產生（§3.3b）。

### 3.5 PWA → ChatGPT 週報
週報頁產生純文字（SPEC §11 欄位）：本週完成課次與日期、新增／複習單字範圍、文法、小測五分項、弱點清單、聽力錯誤類型、上週 `suggest` 有無執行。貼給 ChatGPT 做週檢討。**週報不是備份**（見 §5）。

## 4. 教材庫：生成與三層驗收

### 4.1 流程（每階段一次，本機跑）
`gen_stage.sh 2`（對 24 課各跑一次 `codex exec`）→ 每課 `validate_structure.py`（Codex 自修到過）→ `validate_content.py`（機械層）→ Claude 裁決 → 人工抽驗 → commit。任何一層失敗的課標 `needs_fix`，不進 PWA。

### 4.2 三層驗收
| 層 | 工具 | 檢查 | 不過怎麼辦 |
|---|---|---|---|
| 結構 | JSON schema | 數量、必填、`vocab.id ⊆ new_vocab`、`check.tests` 都是合法 ID、假名欄只含 ひらがな／カタカナ／ー／標點空白 | 自動重生該課（最多 2 次） |
| 內容-機械 | `fugashi`＋`unidic-lite` | **所有給學習者看的假名欄位**（vocab.kana、example_kana、grammar.examples[].kana、patterns[].kana、reading.text_kana、listening.script_kana）逐詞與斷詞器讀音比對；數字、助數詞、外來語先經正規化表（ろっぴゃく／さんびゃく等連濁與促音、長音「ー」、片假名）再比 | 每筆不一致產生一則 `reading_warning{field, ja, kana_llm, kana_mecab}` |
| 內容-跨模型 | Claude Code 本機（`validate_content.py` 產生待裁決清單，由 Claude 在 session 內逐筆裁決並寫回 `verdicts/W03D2.json`） | (a) **裁決每一筆 `reading_warning`**：LLM 對／斷詞器對／兩者皆錯，附理由；(b) 每題 `answer` 是否被 `evidence` 支持、`evidence` 是否真的在原文；(c) 文法 `forms` 變化正確、`mistakes` 成立、情境符合 §2.3 | 任何一筆 warning 未裁決、或裁決為「LLM 錯」但未修正 → **不得發布**（回應第二輪 #7）；fail 項目餵回 `generate.py --fix` 重生一次；仍 fail → `needs_fix` 人工看 |
| 人工 | Bryant | 每階段抽 3 課（各 day_type 一課）通讀 | 改 prompt 後重生整階段 |

**誤報率先量再定門檻**（回應第二輪 #7，不用猜的）：建 `tests/readings.jsonl` 人工標註 100 筆（30 外來語、30 數字／助數詞、40 例句），跑機械層算誤報／漏報；誤報 >20% 就加正規化規則，仍高就改用 `pykakasi` 或雙工具交叉，門檻依實測結果寫進 `validate_content.py` 註解。

### 4.3 錯誤教材的處置
PWA 每課有「回報錯誤」按鈕 → 存進 `weak` 旁的 `lesson_issues[]`，進週報；修正後 `lesson_version+1`，PWA 依 `meta.lesson_version` 提示「本課已更新」。

## 5. 備份與還原（開學前置條件）

- **完整匯出**：整份 §2.3 狀態 JSON（含 schema、curriculum_version、started）→ 複製到剪貼簿／iOS 分享表 → 存 iCloud 備忘錄或檔案。首頁提醒：每週日匯出一次；連續 7 天未匯出顯示黃色提示
- **匯入（v1 只做整份取代，回應第二輪 #4）**：驗證 `schema` 相同、`curriculum_version` 相同（不同 → 拒絕，提示「請先更新課綱或用對應版本」）、JSON 結構合法；通過後顯示「將以 X 月 X 日的備份（N 課完成）取代目前狀態（M 課完成），確定？」→ 取代前先把目前狀態自動匯出一份到剪貼簿當退路。**不做合併**；備份之後那幾天的學習用 `practice` 手動補記或重做。
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
| 第一階段做完 | W04D6 填分 ≥70／各項 ≥60 → `stage[1].passed` → W05D1 解鎖（第二輪 #1 的死結不再發生） |
| 補強＋中斷 >7 天同時發生 | `todo` 同時有 return_test 與 remedial，先回歸測驗再補強，兩者都完成才選新課；途中關 app 不重算 |
| 只學一課就中斷 10 天 | 回歸測驗只抽該課 10 詞＋1 文法（無 review 課可抽）；一課都沒完成 → 不測，回 W01D1 |
| 補強做完再匯入補強前的備份 | 整份取代 → 該課回到 `remedial`、`remedial_done=false`，下次開啟重做補強（行為正確，因為使用者明確選擇取代，且取代前已自動匯出退路） |
| 連續兩週聽力 <70 | 產生 `adjust_tasks{7.3-low, listening}`，首頁「本週必做」，未打勾週報標紅 |
| 貼回同一段 feedback 兩次 | 第二次 hash 相同直接忽略；改過內容再貼 → 覆蓋並提示 |
| W01D6 週測做完 | quiz 四項作答＋訂正 → `done`、`weekly.W01` 同次寫入；口說分數空 → 首頁提示待填但 W02D1 照常解鎖 |
| remedial 的 W03D2，中斷十天，回歸測驗選從 W03D1 重來 | round=2，W03D1–W03D2 回 available 且清空，舊 remedial todo 被清；重學 W03D1 → 正常選到 W03D2，不會被跳過 |
| 中斷 2 天開 app 產生 short_review 沒做就關，再過 10 天 | 跨日重評：gap 以 last_activity 算 ≥7 → short_review 升級為 return_test |
| 同一天開三次 app | `flow.date == today` → 沿用同一份 todo，做到一半的進度保留 |
| 筆試各 90%、聽力 65%、口說 75% | written ≥85 且 listening <70 → `remedial_parts=[listening]`、`passed=false`；7 天後只重填聽力，≥70 → passed |
| 補強週後只重填弱項 | 其餘分項沿用原分數，函式重跑；重填的分數覆蓋 `stage[S].test.parts[p]`，`taken` 更新 |
| 第一階段已過，從 W05D1 重來 | round=2，`stage[1]` 承接（carried_from=1）→ W05D1 可入場；W05 起的紀錄進 history |
| 五項各 13/20（總分 65） | 各項 65% ≥60、written 65 無失衡、但 total <70 → `remedial_parts` ＝ 全部五項；7 天後重填，例如四項 15、一項 14 → 總分 74 → passed |
| 筆試各 80%、聽力 65%、口說 75% | written 80、聽力落後 15 點 <20 → 無失衡、各項 ≥60、總分 ≥70 → passed；筆試各 85% 同聽力 → 落後 20 點 → remedial_parts=[listening]（接受的非單調） |
| 短複習做完 | kind=short_review 只檢查 round 與 flow → 有效 → 移除 todo、更新 last_activity、進 B（不會被誤丟） |

## 9. 建置順序

1. `curriculum.json`：ChatGPT 生第 1 階段（清冊＋24 課）→ Bryant 校對 → repo
2. 三種 schema＋`validate_structure.py`＋`prompts/lesson.md`；Codex 生 W01D1–D3 ＋ **W01D6、W04D6** 看品質、確認每種 day_type 都有合法輸出、調 prompt
2b. `tests/readings.jsonl` 100 筆 → 量機械層誤報率 → 定門檻
3. `validate_content.py`（fugashi ＋ Claude 核對）；生完整第 1 階段，人工抽 3 課
4. PWA：**首頁進度 ＋ 今日（含 §3.2 選課規則）＋ 單字 ＋ 聽力 TTS ＋ 匯出／匯入**（開學最小集合）
5. 備份還原驗收（§5）→ 第 0 週診斷 → Day 1
6. 課表、週報、貼回、回報錯誤、LINE 提醒
7. 第 2 階段開學前兩週：生第 2 階段；跑滿 4 週檢討方案 B 與沒在用的頁

## 10. 前置條件

- [x] ~~OpenAI／Anthropic API key~~ → 改用 Codex CLI（已登入）＋ Claude Code 本機，不需要
- [ ] GitHub private repo `vitus0024/nihongo`（Pages 用；私有 repo 的 Pages 需 Pro 或改公開——**待確認**）
- [ ] ChatGPT 專案 instructions 加入 §3.4 的回填格式
- [x] `curriculum.json` 第 1 階段（2026-09-20，24 課／200 字／36 文法）

## 11. 請 Codex 第五輪特別挑的地方

1. 逐項確認第四輪三項是否真的解決
2. §3.6 承接規則會不會反過來讓「應該失效」的東西活下來（例如 X 所在階段的 adjust_tasks）
3. 通過函式的三個集合聯集後，有沒有「重測後永遠過不了」的分數組合
4. 還有什麼是「開學第一週就會撞到」而這裡沒寫的
若已無 high，請給 approved 或 approved-with-notes，notes 留給實作階段處理。
