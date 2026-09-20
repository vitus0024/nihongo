[codex] Starting Codex task thread.
[codex] Thread ready (01a0bd3b-9a98-7f80-80a3-bbb5440556de).
[codex] Turn started (01a0bd3b-9b6e-7e90-a1cb-7b44088377de).
[codex] Assistant message captured: 我會先讀取實際 diff、SPEC 與第一輪發現，逐項檢查修正是否閉合，再針對 §11 的假設找出可重現的失敗情境。
[codex] Running command: /bin/zsh -lc 'git diff -- PLAN.md'
[codex] Command completed: /bin/zsh -lc 'git diff -- PLAN.md' (exit 0)
[codex] Running command: /bin/zsh -lc 'rg --files -g AGENTS.md -g SPEC.md -g PLAN.md -g reviews-round1.md; nl -ba PLAN...
[codex] Command completed: /bin/zsh -lc 'rg --files -g AGENTS.md -g SPEC.md -g PLAN.md -g reviews-round1.md; nl -ba PLAN... (exit 0)
[codex] Assistant message captured: 預生成已解決第一輪的排課來源衝突，但狀態機仍有兩個阻塞：補強完成後沒有回到 done 的轉移，下一階段又要求自身先通過測驗才能進入。另有第一週就會遇到的 schema 矛盾：複習課的新詞...
[codex] Assistant message captured: { "verdict": "needs-attention", "summary": "不建議依 v0.2 開工。第一輪逐項結論：①交接部分解決，難度調整仍違反 SPEC；②課次識別改善...
[codex] Turn completed.
# Codex Adversarial Review

Target: working tree diff
Verdict: needs-attention

不建議依 v0.2 開工。第一輪逐項結論：①交接部分解決，難度調整仍違反 SPEC；②課次識別改善，但補強與階段解鎖仍會卡住；③預生成已解決排課來源衝突；④完整備份已補，合併仍不安全；⑤清冊已補，但複習課 schema 無法成立；⑥品質檢查已增加，讀音問題仍沒有明確結案門檻。§11 六點中，格式寬鬆與斷詞器誤報率目前沒有實測證據，不能據此宣稱可靠。

Findings:
- [high] 下一階段要求自身先通過，形成解鎖死結 (PLAN.md:81-86)
  §3.2 要求下一課所屬的「該階段」passed=true，但 §3.3 只能在完成該階段末尾的 stage_test 後設定 passed。依文字實作，完成第一階段後仍進不了第二階段，也無法到達第二階段測驗。
  Recommendation: 明定階段 S 的入場條件是前一階段通過；第一階段另設診斷完成條件。加入第一階段通過後開啟第二階段首課的驗收。
- [high] 補強完成後仍會再次選到原本的 remedial 課 (PLAN.md:75-81)
  補強只寫 practice，且明訂不動課次狀態。即使 remedial_done 改成 true，選課第 4 步仍會挑第一個非 done/exempt 的課，因此再次選中原本的 remedial 課。另在補強與長期中斷同時成立時，若補強更新 last_activity，後續回歸測驗條件會消失；目前沒有保留待辦義務的狀態。
  Recommendation: 明訂 remedial 完成後轉 done，或把補強義務與課次完成分開保存。開啟當日流程時先記錄補強與回歸測驗待辦，完成兩者才選新課，不以更新後的 last_activity 重新推算。
- [high] 複習課不可能通過固定十詞的結構驗證 (PLAN.md:43-48)
  §2.1 明訂 review 的 new_vocab 為空，但教材要求 vocab[10]，每個 ID 必須屬於 new_vocab，§4.2 又驗證此條件。W01D6 因而不存在合法輸出；自動重生也無法修復，整階段開學前驗收會卡住。這表示第一輪要求的不同 day_type 數量規則尚未完成。
  Recommendation: 以 day_type 分支定義 schema：new 必須完整且不重複地涵蓋指定新詞；review／stage_test 改用複習清單與測驗結構，不要求十個新詞。以 W01D6、W04D6 驗證可生成合法教材。
- [high] done_at 無法判定備份中哪份補強與重測狀態較新 (PLAN.md:118-120)
  同一課補強前後可有相同 done_at，partial 又沒有完成時間；較晚完成時間無法判定 remedial_done、模組或修正分數的新舊。weekly「取有值者」無法處理兩份都有分數，stage 則完全沒有合併規則。依實作選邊方式，舊備份可能復活已完成的補強，或保留過期的通過狀態。不同 schema／課綱版本也只提示後繼續匯入，沒有轉換契約。
  Recommendation: v1 先僅支援驗證後整份取代，匯入前保留原狀態；不相容版本拒絕匯入或經明確遷移。若保留合併，加入更新版本、衝突處理與 stage 等全部欄位規則，測試補強前後及重測前後備份交叉匯入。
- [medium] 第一週中斷後的回歸測驗沒有可用資料保證 (PLAN.md:79-81)
  只學一課甚至尚未完成一課就中斷一週，是正常情境；此時不存在已學過的 review 課，也可能不足十個 done 單字。若取未學的 W01D6，測驗又會包含尚未教過的內容。計畫沒有空資料替代路徑，且使用者選「重來」後未定義如何改寫 done 與階段狀態，原選課規則仍會跳過那些課。
  Recommendation: 回歸測驗只取已學項目，不足時縮減題數，零資料時回到診斷或首課；定義重來是另建複習路徑或重設哪些狀態。加入第一課前、第一課後中斷的驗收。
- [medium] SPEC 的強制調整被降為可忽略建議，未完成需求修訂 (PLAN.md:95)
  SPEC §7.3 要求連續兩週高分後增加難度、單項連續低分後增加針對性練習。v0.2 只顯示一週建議，§7 又讓使用者決定是否改課綱，沒有保證任何調整會執行。預生成不會自動使既定規則失效；尤其連續弱項可能一直沿用原教材。第一輪的控制流程缺口因此僅部分解決。
  Recommendation: 明確修訂 SPEC，列出 v1 延後的調整規則與驗收影響；或把高低分條件轉成可追蹤的人工任務，記錄教材調整或追加練習確實完成。
- [medium] 讀音不一致只有轉交，沒有發布前必須結案的規則 (PLAN.md:109-111)
  機械層將讀音不一致清單交給下一層，但跨模型層列出的驗收項目沒有要求裁決這份清單。未被抽中的課，即使已有讀音疑點，仍沒有明確的發布阻擋條件；patterns、閱讀與聽力的 kana 也不在逐詞核對範圍。不能以沒有實測的誤報率推論工具好壞，但現有流程確實未說明如何區分誤報與真正錯誤。
  Recommendation: 要求每筆讀音警示有裁決與理由，未結案不得發布；涵蓋所有提供給學習者的 kana 欄位。先用人工標註的外來語、數字與例句測試集衡量誤報及漏報，再決定正規化與門檻。

Next steps:
- 先修正階段入場條件、補強轉移與依 day_type 區分的 schema。
- 以補強加長期中斷、第一週資料不足、重測後匯入舊備份驗收狀態流程。
- 明寫 SPEC 的 v1 取捨，並將讀音警示結案列為發布條件；回填格式先維持嚴格驗證，另補分數範圍、重貼與舊回饋衝突規則。
