# ChatGPT 的原始輸出放這裡

- `grammar-stage1.json`：第一段（文法清冊）
- `lessons-stage1.json`（或 `lessons-stage1-a.json`、`-b.json` 分段）：第二段

然後：`python3 build_curriculum.py --stage 1 prompts/out/grammar-stage1.json prompts/out/lessons-stage1*.json`
