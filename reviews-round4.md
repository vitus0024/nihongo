[codex] Starting Codex task thread.
[codex] Thread ready (01a0bd44-aebf-7fa2-9bbe-048b97bd4487).
[codex] Turn started (01a0bd44-af69-7bf1-a580-4135f8c24de4).
[codex] Assistant message captured: 我會先核對第三輪四項與 SPEC，再追查 v0.4 的輪次切換、待辦流程及重測是否仍有死結。
[codex] Running command: /bin/zsh -lc "pwd; rg --files -g 'AGENTS.md' -g '*round*.md' -g 'PLAN.md' -g 'SPEC.md'"
[codex] Command completed: /bin/zsh -lc "pwd; rg --files -g 'AGENTS.md' -g '*round*.md' -g 'PLAN.md' -g 'SPEC.md'" (exit 0)
[codex] Running command: /bin/zsh -lc 'cat reviews-round3.md reviews-round2.md reviews-round1.md; nl -ba PLAN.md; cat ...
[codex] Command completed: /bin/zsh -lc 'cat reviews-round3.md reviews-round2.md reviews-round1.md; nl -ba PLAN.md; cat ... (exit 0)
[codex] Running command: /bin/zsh -lc "nl -ba PLAN.md | sed -n '87,170p'; git diff --stat"
[codex] Command completed: /bin/zsh -lc "nl -ba PLAN.md | sed -n '87,170p'; git diff --stat" (exit 0)
[codex] Assistant message captured: { "verdict": "needs-attention", "summary": "尚不能 approved：仍有兩個 high 死結。第三輪逐項：#1 review 完成轉移已解；...
[codex] Turn completed.
# Codex Adversarial Review

Target: working tree diff
Verdict: needs-attention

尚不能 approved：仍有兩個 high 死結。第三輪逐項：#1 review 完成轉移已解；#2 舊補強跳課已解，但輪次切換誤廢前階段資格；#3 跨日升級已解，但新增待辦檢查誤套所有種類；#4 原聽說重測入口已解，但總分不及格仍可能無項目可重測。

Findings:
- [high] 局部重來會撤銷仍必要的前階段通過資格 (PLAN.md:120-126)
  第一階段已通過，使用者選 W05D1 重來：round 變成 2，但 stage[1] 不在搬移範圍，仍是 round=1。所有門檻只讀目前輪次，因此 §3.2 B 會鎖住 W05D1；第一階段課次卻全部保留 done，正常選課流程不會帶使用者重考。局部重來因而失去原本有效的入場資格。
  Recommendation: 切換輪次時，明確承接 X 之前未受影響的階段資格與必要任務至新輪次，保留來源紀錄；只撤銷受重來範圍影響的資格。加入從 W05D1 重來仍可入場的驗收。
- [high] 總分未達 70、各項皆達 60 時沒有合法重測項目 (PLAN.md:134-138)
  五項各 13/20 時，總分 65、written=65%，remedial_parts 為空，passed=false。七天後規則只允許重填 remedial_parts，其餘沿用，因此沒有任何分數能改，重跑函式仍不通過，下一階段永久鎖住。這是合法且常見的成績組合。
  Recommendation: 為總分不足明訂非空的重測集合，例如所有低於 70% 的分項；重測後由五項最新有效分數重新加總。驗收五項各 13 分，補強重測後能解鎖。
- [medium] 所有待辦都要求目標課為 remedial，會誤判回歸與短複習 (PLAN.md:112)
  新增檢查套用「每個 todo」，但 return_test 與 short_review 沒有 remedial 目標課。依文字實作，正常短複習或回歸測驗完成時必定被當成失效待辦丟棄，無法可靠提交有效結果；若失效分支直接進選課，還會略過回歸結果的重定位流程。第一週中斷後就能碰到。
  Recommendation: 依 kind 分別驗證：全部檢查輪次；只有 remedial 檢查目標課狀態；return_test／short_review 檢查流程識別與待辦有效性。結果處理、待辦移除與 last_activity 更新須同次提交。

Next steps:
- 將上述三個失敗情境加入 §8，修正後再定案。
- §11 第三點：三個等配分筆試分項取平均合理；SPEC 未明訂筆試 85% 這個切點，因此不能直接認定聽說 60–69% 必須一律阻擋。但現規則有反向誘因：筆試各 80%、聽力 65%、口說 75% 可通過，筆試提升至各 85% 卻不通過。應明訂「落後／失衡」的判準，確認這種非單調結果是否符合需求。
