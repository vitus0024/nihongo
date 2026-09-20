# nihongo — 日文學習 App（第一段：N5）

手機 PWA 閱讀器＋進度機；教材由 Codex CLI 依課綱生成、三層驗收；口說與批改在 ChatGPT。設計見 `PLAN.md`（經五輪對抗式審查），規格見 `SPEC.md`。

- App：https://vitus0024.github.io/nihongo/ （iOS Safari「加入主畫面」）
- 進度只存在你的手機（localStorage）；「設定 → 匯出」每週備份一次
- 教材：`lessons/*.json`，課綱：`curriculum.json`，驗證：`validate_structure.py`
