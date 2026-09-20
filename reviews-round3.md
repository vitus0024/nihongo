[codex] Starting Codex task thread.
[codex] Thread ready (01a0bd42-09ac-7161-befb-e0051d57de54).
[codex] Turn started (01a0bd42-0a59-7662-ae39-ce50d09eb6c2).
[codex] Assistant message captured: 我會先核對第二輪七項的修正，再追查待辦跨日、重來後的狀態一致性，以及測驗完成與階段解鎖的規則。
[codex] Running command: /bin/zsh -lc "pwd; rg --files -g 'AGENTS.md' -g '*round*' -g 'PLAN.md' -g 'SPEC.md'"
[codex] Command completed: /bin/zsh -lc "pwd; rg --files -g 'AGENTS.md' -g '*round*' -g 'PLAN.md' -g 'SPEC.md'" (exit 0)
[codex] Running command: /bin/zsh -lc 'cat reviews-round2.md; cat reviews-round1.md; nl -ba PLAN.md; cat SPEC.md'
[codex] Command completed: /bin/zsh -lc 'cat reviews-round2.md; cat reviews-round1.md; nl -ba PLAN.md; cat SPEC.md' (exit 0)
[codex] Running command: /bin/zsh -lc "nl -ba PLAN.md | sed -n '66,156p'"
[codex] Command completed: /bin/zsh -lc "nl -ba PLAN.md | sed -n '66,156p'" (exit 0)
[codex] Assistant message captured: { "verdict": "needs-attention", "summary": "不建議依 v0.3 定案實作，仍有 high 問題。第二輪逐項：#1 原階段入場死結已解；#2 補...
[codex] Turn completed.
# Codex Adversarial Review

Target: working tree diff
Verdict: needs-attention

不建議依 v0.3 定案實作，仍有 high 問題。第二輪逐項：#1 原階段入場死結已解；#2 補強轉 done 已解，但待辦生命週期未閉合；#3 schema 的十詞矛盾已解，但週測缺少完成轉移；#4 合併風險已由整份取代消除；#5 空資料已解，重來仍會留下失效狀態；#6 人工任務方案已落實，但新增門檻與重測流程矛盾；#7 發布前裁決規則已補齊，誤報／漏報實測仍待執行。尚不能 approved。

Findings:
- [high] review 換成測驗 schema，卻沒有對應的完成條件 (PLAN.md:59-67)
  W01D6 現在只有 quiz、review_pack、busy_mode，沒有九模組或 check；§3.1 仍要求九模組全勾且小檢核有分數才能 done。§3.3 只替 stage_test 定義例外。因此依現有規則，即使第一週五分項全填完，W01D6 仍不能完成，§3.2 B 會一直選回它，無法進 W02D1。生成合法 JSON 的驗收抓不到這個進度死結。
  Recommendation: 依 day_type 定義完成與失敗轉移：明定 review 的五分項、訂正要求及低分後行為，並指定 weekly 寫入與 lesson.status 更新為同一次狀態提交。加入 W01D6 完成後能選到 W02D1 的驗收。
- [high] 重來保留舊補強待辦，可把尚未重學的課直接標成完成 (PLAN.md:104)
  可重現情境：W03D2 為 remedial，中斷十天後產生 return_test 與 remedial 待辦；回歸測驗選從 W03D1 重來，W03D2 被改成 available，但舊 remedial 待辦仍在。接著依 A 完成舊補強，§3.1 又把 W03D2 轉 done；重學完 W03D1 後就跳過 W03D2。重設也只替 stage 加 superseded，沒有撤銷 passed 或要求解鎖查詢排除 superseded；舊通過資格可能繼續生效。
  Recommendation: 把重來定義成原子狀態轉移：建立新的學習輪次，清除或失效化受影響的 todo、模組勾選、check、remedial_done、adjust_tasks 與階段資格；歷史紀錄另存。待辦完成時須確認其輪次與課次狀態仍有效，所有門檻只讀目前輪次。
- [medium] 未完成待辦永久沿用，會漏掉後續長期中斷 (PLAN.md:96-100)
  例如中斷兩天開 app，產生 short_review 後未完成就關閉，再過十天才回來。依第 100 行必須沿用同一份 todo、不重算，因此只做短複習便能進新課，漏掉本應執行的回歸測驗。狀態亦未保存當日流程識別或已結算日期，無法明確區分同日重開、跨午夜及新一輪中斷；單靠 todo 是否為空不足以表達這些情況。
  Recommendation: 保存流程日期、固定時區與結算時的 last_activity；同一流程重開須冪等。跨日恢復時保留補強義務，但重新評估中斷長度，必要時把 short_review 升級為 return_test。明定實際完成學習才更新 last_activity，並驗收同日重開、跨午夜及待辦擱置十天。
- [medium] 新增聽說門檻要求重測，卻沒有可進入的重測狀態 (PLAN.md:112-117)
  假設筆試分項均為 90%、聽力 65%、口說 75%：§3.3 判定總分與各項達標，應 passed 且不進 remedial_week；第 117 行卻要求先重測聽力才可 passed。目前唯一重測入口是 §3.3 的未通過補強週，沒有定義此情境何時可重測，也沒有欄位表示「仍欠一次重測」。依實作採用哪條規則，會直接解鎖或停在無重測入口的鎖定狀態。
  Recommendation: 統一階段通過判定函式，明定分數尺度、採用哪次測驗及規則優先序。若 60–69% 也必須重測，新增 retest_required、重測入口與等待期限，完成後再計算 passed；若不需要額外重測，移除此條新增阻擋。

Next steps:
- 補齊三種 day_type 的狀態轉移表，以及重來、待辦跨日與階段重測的有效狀態。
- 將四個發現中的失敗情境加入 §8 驗收，再進行定案審查。
