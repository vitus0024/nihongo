/* nihongo — 閱讀器＋進度機（PLAN §3、§5、§6）。進度只存這支手機的 localStorage；教材從 lessons/*.json 讀。 */
"use strict";

// ---------- 常數與小工具 ----------
const LEVEL = { name: "N5", lessons: 120, weeks: 20 };          // 20 週 × 6 天（SPEC §3）；課綱尚未全生時分母仍用 120
const STORE = "nihongo.state.v1";
const TZ = "Asia/Taipei";
const MODULES_NEW = [["warmup", "複習暖身"], ["vocab", "單字"], ["grammar", "文法"], ["patterns", "實用句型"],
  ["reading", "閱讀"], ["listening", "聽力與跟讀"], ["speaking", "口說"], ["check", "小檢核"]];
const BUSY_MODULES = ["vocab", "listening", "speaking"];        // SPEC §5.2：單字複習、聽力跟讀、口說
const PARTS = [["vocab", "單字"], ["grammar", "文法句型"], ["reading", "閱讀"], ["listening", "聽力"], ["speaking", "口說"]];

const $ = (s, r = document) => r.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const today = () => new Intl.DateTimeFormat("sv-SE", { timeZone: TZ }).format(new Date());
const daysBetween = (a, b) => Math.round((new Date(b) - new Date(a)) / 86400000);
const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x.toISOString().slice(0, 10); };
const pct = (a, b) => (b ? Math.round((a / b) * 100) : 0);
const sample = (arr, n) => [...arr].sort(() => Math.random() - .5).slice(0, n);
// ---------- 注音（漢字上方的假名） ----------
// 把 ja 切成「漢字段／非漢字段」，非漢字段在整句假名裡逐段定位，夾在中間的假名就是前一個漢字段的讀音。
// 對不上就整句退回純文字（不會顯示錯的注音）。
const isKanji = (c) => /[一-鿿〇々〆ヶ]/.test(c);
function rubyHTML(ja, kana) {
  if (!ja) return "";
  if (!kana || ![...ja].some(isKanji) || !SHOW_RUBY) return esc(ja).replace(/\n/g, "<br>");
  if (ja.includes("\n")) {                                  // 多行：行數對得上就逐行對齊
    const a = ja.split("\n"), b = kana.split("\n");
    if (a.length === b.length) return a.map((l, i) => rubyHTML(l, b[i])).join("<br>");
    return rubyHTML(ja.replace(/\s+/g, ""), kana.replace(/\s+/g, ""));
  }
  const runs = []; let cur = "", curK = null;
  for (const c of ja) { const k = isKanji(c); if (curK === null || k === curK) { cur += c; curK = k; } else { runs.push([cur, curK]); cur = c; curK = k; } }
  if (cur) runs.push([cur, curK]);
  // 回溯對齊：非漢字段在假名裡可能出現多次（電車で行きます 的「で」也在「でんしゃ」裡），逐一嘗試直到整句對得上
  const solve = (i, pos) => {
    if (i === runs.length) return pos === kana.length ? [] : null;
    const [text, k] = runs[i];
    if (k) {                                                 // 漢字段：讀音長度 1..剩餘，交給下一段決定
      if (i + 1 === runs.length) { const r = kana.slice(pos); return r ? [[text, r]] : null; }
      const [next] = runs[i + 1]; let from = pos + 1;
      while (true) { const idx = kana.indexOf(next, from); if (idx < 0) return null; const rest = solve(i + 1, idx); if (rest) return [[text, kana.slice(pos, idx)], ...rest]; from = idx + 1; }
    }
    if (kana.startsWith(text, pos)) { const rest = solve(i + 1, pos + text.length); return rest ? [[text, null], ...rest] : null; }
    return null;
  };
  const segs = solve(0, 0);
  if (!segs) return esc(ja);
  return segs.map(([t, r]) => (r ? `<ruby>${esc(t)}<rt>${esc(r)}</rt></ruby>` : esc(t))).join("");
}
let SHOW_RUBY = true;
try { SHOW_RUBY = localStorage.getItem("nihongo.ruby") !== "off"; } catch {}

let toastTimer;
function toast(msg) { const t = $("#toast"); t.textContent = msg; t.hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => (t.hidden = true), 2200); }

// ---------- 語音（每台裝置各自設定，不進備份） ----------
const TTS_KEY = "nihongo.tts";
const RATES = { slow: 0.7, normal: 0.9, fast: 1.1 };
const RATE_LABEL = { slow: "慢", normal: "正常", fast: "快" };
let TTS = { rate: "normal", voice: null };
try { TTS = { ...TTS, ...JSON.parse(localStorage.getItem(TTS_KEY) || "{}") }; } catch {}
const saveTTS = () => { try { localStorage.setItem(TTS_KEY, JSON.stringify(TTS)); } catch {} };
let VOICES = [];                                           // iOS 的 getVoices() 有時先回空清單，voiceschanged 之後才有；兩邊都收
function refreshVoices() { const vs = speechSynthesis.getVoices(); if (vs.length) VOICES = vs; return VOICES; }
function jaVoices() { return refreshVoices().filter((v) => (v.lang || "").replace("_", "-").toLowerCase().startsWith("ja")); }
let LAST_TTS = null;                                       // 設定頁顯示上一次實際用了什麼，方便回報
function voiceScore(v) {                                   // 越高越自然：iOS／macOS 的加強版聲音名字帶 Enhanced／Premium／拡張
  const n = v.name.toLowerCase(); let s = 0;
  if (/enhanced|premium|拡張|neural|natural/.test(n)) s += 10;
  if (/siri/.test(n)) s += 8;
  if (/o-ren|hattori|otoya|kyoko/.test(n)) s += 2;
  if (!v.localService) s += 1;
  return s;
}
function pickVoice() { const vs = jaVoices(); if (!vs.length) return null; if (TTS.voice) { const v = vs.find((v) => v.name === TTS.voice); if (v) return v; } return vs.sort((a, b) => voiceScore(b) - voiceScore(a))[0]; }
let CURRENT_U = null;                                      // 留住 utterance 物件：iOS 被 GC 掉就不會唸
function speak(text, rateKey) {
  if (!("speechSynthesis" in window)) return toast("這個瀏覽器不支援語音");
  // 一律在使用者手勢裡同步呼叫 speak()：iOS 若延遲（setTimeout）會失去手勢授權而靜音；
  // 且 iOS 的 speaking／pending 旗標在 cancel 後可能卡住，不能拿來判斷
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "ja-JP"; u.rate = RATES[rateKey || TTS.rate] || RATES.normal; u.pitch = 1; u.volume = 1;
  const v = pickVoice();                                     // 每次都從最新清單挑：iOS 用到舊的 voice 物件會退回系統預設（中文）
  if (v && (v.lang || "").toLowerCase().startsWith("ja")) u.voice = v;
  LAST_TTS = { voice: u.voice ? u.voice.name : "（無，僅 lang=ja-JP）", lang: u.voice ? u.voice.lang : "ja-JP", rate: u.rate, at: new Date().toLocaleTimeString(), state: "已送出" };
  u.onstart = () => { LAST_TTS.state = "播放中"; updateTTSLine(); };
  u.onend = () => { LAST_TTS.state = "播完"; updateTTSLine(); };
  u.onerror = (e) => { LAST_TTS.state = `錯誤 ${e.error}`; updateTTSLine(); };
  CURRENT_U = u;
  speechSynthesis.speak(u);
  updateTTSLine();
}
function updateTTSLine() { const el = $("#tts-last"); if (el && LAST_TTS) el.textContent = `上次播放：${LAST_TTS.voice}（${LAST_TTS.lang}）· 速度 ${LAST_TTS.rate} · ${LAST_TTS.state} · ${LAST_TTS.at}`; }

// ---------- 狀態（PLAN §2.3） ----------
const DEFAULT = () => ({ schema: 1, curriculum_version: null, started: null, round: 1, flow: null, todo: [], lessons: {}, practice: [],
  weekly: {}, stage: {}, weak: [], diagnostic: { done: false, exempt_vocab: [], exempt_grammar: [] }, adjust_tasks: [], feedback_log: [], history: [],
  lesson_issues: [], last_activity: null, busy: false, last_export: null });
let S = DEFAULT();
function load() { try { const raw = localStorage.getItem(STORE); if (raw) S = { ...DEFAULT(), ...JSON.parse(raw) }; } catch (e) { console.warn("讀取狀態失敗", e); } }
function save() { try { localStorage.setItem(STORE, JSON.stringify(S)); } catch (e) { toast("無法儲存進度（瀏覽器儲存被擋）"); } }
function touch() { S.last_activity = today(); }        // 只在實際學習完成時呼叫

// ---------- 教材資料 ----------
let CUR = null; const V = {}, G = {}, L = {}; let ORDER = [];
const lessonCache = {};
async function loadCurriculum() {
  CUR = await (await fetch("curriculum.json", { cache: "no-cache" })).json();
  CUR.vocab.forEach((v) => (V[v.id] = v)); CUR.grammar.forEach((g) => (G[g.id] = g)); CUR.lessons.forEach((l) => (L[l.id] = l));
  ORDER = CUR.lessons.slice().sort((a, b) => a.week - b.week || a.day - b.day).map((l) => l.id);
  if (!S.curriculum_version) S.curriculum_version = CUR.version;
}
const audioIndex = {};                                    // id → {key: {file,...}}；沒有音檔的課是 {}
async function loadLesson(id) {
  if (lessonCache[id]) return lessonCache[id];
  const r = await fetch(`lessons/${id}.json`, { cache: "no-cache" });
  if (!r.ok) return null;
  try { const a = await fetch(`audio/${id}/index.json`, { cache: "no-cache" }); audioIndex[id] = a.ok ? await a.json() : {}; } catch { audioIndex[id] = {}; }
  return (lessonCache[id] = await r.json());
}
// 預生成音檔（gen_audio.py）優先，沒有才退回系統語音；三段速用 playbackRate，音高不變
const PLAYER = new Audio();
PLAYER.preservesPitch = true;
const PLAY_RATES = { slow: 0.8, normal: 1.0, fast: 1.2 };
function playKey(id, key, rateKey, fallbackText) {
  const entry = audioIndex[id]?.[key];
  if (!entry) return speak(fallbackText, rateKey);
  PLAYER.pause(); PLAYER.src = `audio/${id}/${entry.file}`; PLAYER.playbackRate = PLAY_RATES[rateKey || TTS.rate] || 1;
  LAST_TTS = { voice: `音檔 ${entry.backend}`, lang: "ja-JP", rate: PLAYER.playbackRate, at: new Date().toLocaleTimeString(), state: "播放中" };
  PLAYER.play().catch(() => speak(fallbackText, rateKey));
}
const btnPlay = (id, key, text, label = "▶", extra = "") => `<button class="btn tts small" data-act="play" data-id="${id}" data-key="${esc(key)}" data-text="${esc(text)}" ${extra}>${label}</button>`;

// ---------- 進度機（PLAN §3） ----------
const st = (id) => S.lessons[id] || { status: "available", modules: {} };
function lessonState(id) { if (!S.lessons[id]) S.lessons[id] = { status: "available", modules: {} }; return S.lessons[id]; }
const stageOf = (id) => L[id].stage;
const isFirstOfStage = (id) => L[id].day === 1 && (L[id].week - 1) % 4 === 0;
const stageRec = (s) => (S.stage[s] && S.stage[s].round === S.round ? S.stage[s] : null);

function settleTodo() {                                   // §3.2 A
  const d = today();
  if (S.flow && S.flow.date === d && S.todo.length && S.flow.round === S.round) return;
  const keep = S.todo.filter((t) => t.kind === "remedial" && t.round === S.round);
  for (const id of ORDER) { const x = st(id); if (x.status === "remedial" && !x.remedial_done && !keep.some((t) => t.lesson === id)) keep.push({ kind: "remedial", lesson: id, round: S.round }); }
  const gap = S.last_activity ? daysBetween(S.last_activity, d) : 0;
  const learnedAny = ORDER.some((id) => ["done", "remedial"].includes(st(id).status));
  if (learnedAny && gap >= 7) keep.unshift({ kind: "return_test", round: S.round });
  else if (learnedAny && gap >= 1 && S.todo.some((t) => t.kind === "short_review") || (learnedAny && gap >= 1 && gap <= 6 && S.last_activity)) {
    if (!keep.some((t) => t.kind === "return_test")) keep.push({ kind: "short_review", round: S.round });
  }
  const order = { return_test: 0, remedial: 1, short_review: 2 };
  S.todo = keep.sort((a, b) => order[a.kind] - order[b.kind]);
  S.flow = { date: d, settled_last_activity: S.last_activity, round: S.round };
  save();
}
function nextLessonId() {                                 // §3.2 B
  for (const id of ORDER) {
    const s = st(id).status;
    if (["done", "exempt", "remedial"].includes(s)) continue;
    if (isFirstOfStage(id) && stageOf(id) >= 2) { const prev = stageRec(stageOf(id) - 1); if (!prev || !prev.passed) return { id, locked: `第 ${stageOf(id) - 1} 階段測驗${prev ? "未通過" : "尚未填分數"}` }; }
    return { id };
  }
  return { id: null };
}
function passFn(parts) {                                  // §3.3；parts 各 0–20
  const p = {}; for (const [k] of PARTS) p[k] = (parts[k] ?? 0) / 20;
  const total = Object.values(parts).reduce((a, b) => a + (b ?? 0), 0);
  const written = (p.vocab + p.grammar + p.reading) / 3;
  const rem = new Set();
  for (const [k] of PARTS) if (p[k] < .6) rem.add(k);
  for (const k of ["listening", "speaking"]) if (p[k] < .7 && written - p[k] >= .2) rem.add(k);
  if (total < 70) for (const [k] of PARTS) if (p[k] < .7) rem.add(k);
  return { passed: total >= 70 && rem.size === 0, remedial_parts: [...rem], total };
}
function completeTodo(t) {
  if (t.round !== S.round) return false;
  if (t.kind === "remedial") { const x = st(t.lesson); if (x.status !== "remedial" || x.remedial_done) return false; }
  else if (!S.flow || S.flow.round !== S.round) return false;
  S.todo = S.todo.filter((u) => u !== t); touch(); save(); return true;
}
function newRound(fromId) {                               // §3.6
  const wk = L[fromId].week, sg = L[fromId].stage;
  S.round += 1;
  for (const id of ORDER) if (L[id].week > wk || (L[id].week === wk && L[id].day >= L[fromId].day)) delete S.lessons[id];
  S.todo = []; S.flow = { date: today(), settled_last_activity: S.last_activity, round: S.round };
  S.adjust_tasks.forEach((a) => { if (a.week >= wk) a.superseded = true; else a.round = S.round; });
  for (const w of Object.keys(S.weekly)) { if (+w.slice(1) >= wk) { S.history.push({ kind: "weekly", key: w, round: S.round - 1, data: S.weekly[w] }); delete S.weekly[w]; } else S.weekly[w].round = S.round; }
  for (const s of Object.keys(S.stage)) { if (+s >= sg) { S.history.push({ kind: "stage", key: s, round: S.round - 1, data: S.stage[s] }); delete S.stage[s]; } else { S.stage[s].round = S.round; S.stage[s].carried_from = S.round - 1; } }
  save();
}
function progress() {
  const done = ORDER.filter((id) => ["done", "exempt", "remedial"].includes(st(id).status));
  const vocabDone = new Set(), gramDone = new Set();
  done.forEach((id) => { L[id].new_vocab.forEach((v) => vocabDone.add(v)); L[id].new_grammar.forEach((g) => gramDone.add(g)); });
  S.diagnostic.exempt_vocab.forEach((v) => vocabDone.add(v)); S.diagnostic.exempt_grammar.forEach((g) => gramDone.add(g));
  return { done: done.length, total: Math.max(LEVEL.lessons, CUR.totals.lessons), vocab: vocabDone.size, vocabTotal: CUR.totals.vocab, gram: gramDone.size, gramTotal: CUR.totals.grammar };
}

// ---------- 畫面 ----------
let tab = "home"; let runner = {};                       // runner：今日頁的暫存（作答、翻卡位置），不進 localStorage
const view = $("#view");
function render() { document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab)); ({ home: renderHome, today: renderToday, schedule: renderSchedule, settings: renderSettings })[tab](); window.scrollTo(0, 0); }
document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => { tab = b.dataset.tab; render(); }));
view.addEventListener("click", (e) => { const a = e.target.closest("[data-act]"); if (a) ACT[a.dataset.act]?.(a, e); });

function renderHome() {
  settleTodo();
  const p = progress(); const nx = nextLessonId(); const curL = nx.id ? L[nx.id] : null;
  const weekDone = curL ? ORDER.filter((id) => L[id].week === curL.week && st(id).status === "done").length : 0;
  const stageWeeks = curL ? ((curL.week - 1) % 4) + 1 : 0;
  const weeks = Object.keys(S.weekly).filter((w) => S.weekly[w].quiz).sort().slice(-8);
  const chart = weeks.length ? `<div class="card"><h3>每週小測</h3>${weeks.map((w) => { const q = S.weekly[w].quiz; const t = PARTS.reduce((a, [k]) => a + (q[k] ?? 0), 0); return `<div class="row between small"><span>${w}</span><span class="grow"><div class="bar indigo"><i style="width:${t}%"></i></div></span><b>${t}</b><span class="faint">${PARTS.map(([k, n]) => `${n[0]}${q[k] ?? "–"}`).join(" ")}</span></div>`; }).join("")}<p class="faint">85 分以上兩週：加難度；單項 70 以下兩週：加練習（SPEC §7.3）</p></div>` : "";
  const tasks = S.adjust_tasks.filter((a) => !a.done && !a.superseded && a.round === S.round);
  const exportWarn = !S.last_export || daysBetween(S.last_export, today()) >= 7;
  view.innerHTML = `
    <h1>nihongo <span class="badge indigo">${LEVEL.name}</span></h1>
    <p class="muted">${S.started ? `開始於 ${S.started}` : "還沒開始——先到「今日」做入學診斷"}</p>
    <div class="card accent">
      <div class="row between"><div><div class="progress-big">${pct(p.done, p.total)}%</div><div class="muted">總進度 ${p.done}／${p.total} 課</div></div>
        <div style="text-align:right">${curL ? `<div class="badge red">${curL.stage_name}</div><p class="small" style="margin:6px 0 0">第 ${curL.week} 週 · 本階段 ${stageWeeks}／4 週<br>本週 ${weekDone}／6 天</p>` : `<div class="badge green">N5 課程完成</div>`}</div></div>
      <div class="bar"><i style="width:${pct(p.done, p.total)}%"></i></div>
      <div class="stats"><div class="stat"><b>${p.vocab}<span class="faint">／${p.vocabTotal}</span></b><span>單字</span></div><div class="stat"><b>${p.gram}<span class="faint">／${p.gramTotal}</span></b><span>文法</span></div><div class="stat"><b>${S.practice.filter((x) => x.kind === "busy").length}</b><span>忙碌版次數</span></div></div>
    </div>
    ${S.todo.length ? `<div class="notice">今天先做：${S.todo.map((t) => ({ return_test: "回歸測驗", remedial: `補強 ${t.lesson}`, short_review: "短複習" })[t.kind]).join(" → ")}</div>` : ""}
    ${nx.locked ? `<div class="notice red">${nx.id} 鎖住：${nx.locked}</div>` : ""}
    ${S.suggest && daysBetween(S.suggest.at, today()) < 7 ? `<div class="notice indigo"><b>ChatGPT 建議（${S.suggest.week}）</b>：${esc(S.suggest.text)}</div>` : ""}
    ${tasks.length ? `<div class="card"><h3>本週必做（SPEC §7.3）</h3>${tasks.map((a) => `<label class="sw"><input type="checkbox" data-act="task-done" data-id="${a.id}"> ${esc(a.task)}</label>`).join("")}</div>` : ""}
    ${exportWarn && S.started ? `<div class="notice">已超過一週沒備份進度——到「設定」匯出一次</div>` : ""}
    <button class="btn primary block" data-act="go-today">${nx.id ? `開始今天：${nx.id} ${esc(curL.theme)}` : "查看課表"}</button>
    ${chart}`;
}

function renderSchedule() {
  const nx = nextLessonId();
  const weeks = [...new Set(ORDER.map((id) => L[id].week))];
  let html = `<h1>課表 <span class="badge">${CUR.totals.lessons}／${LEVEL.lessons} 課已備</span></h1><div class="grid"><span></span>${["一", "二", "三", "四", "五", "測"].map((d) => `<span class="wk" style="text-align:center">${d}</span>`).join("")}`;
  for (const w of weeks) {
    html += `<span class="wk">W${String(w).padStart(2, "0")}</span>`;
    for (let d = 1; d <= 6; d++) { const id = `W${String(w).padStart(2, "0")}D${d}`; const x = st(id); const cls = x.status + (nx.id === id ? " next" : "") + (x.status === "available" && ORDER.indexOf(id) > ORDER.indexOf(nx.id) ? " locked" : "");
      html += `<button class="cell ${cls}" data-act="open-lesson" data-id="${id}" title="${esc(L[id].theme)}">${d === 6 ? (L[id].day_type === "stage_test" ? "階" : "測") : d}</button>`; }
  }
  html += `</div><div class="legend"><span><i style="background:var(--green)"></i>完成</span><span><i style="background:var(--green-soft);border:1px solid var(--green)"></i>進行中</span><span><i style="background:var(--amber-soft);border:1px solid var(--amber)"></i>待補強</span><span><i style="background:var(--indigo-soft)"></i>豁免</span><span><i style="border:1px dashed var(--accent)"></i>下一課</span></div>
    <h2>階段</h2>${[1, 2, 3, 4, 5].map((s) => { const r = stageRec(s); const name = CUR.stages[s]; return `<div class="card soft row between"><span>第 ${s} 階段 ${name}</span>${r ? (r.passed ? `<span class="badge green">通過 ${r.test.total}</span>` : `<span class="badge amber">補強中</span>`) : `<span class="badge">未測</span>`}</div>${r && !r.passed ? renderStageEntry(s) : ""}`; }).join("")}`;
  view.innerHTML = html;
}

function renderSettings() {
  view.innerHTML = `<h1>設定 <span class="badge">app v8</span></h1>
    <div class="card"><h3>備份（完整 JSON）</h3><p class="small muted">每週日匯出一次，存到 iCloud 備忘錄或檔案。匯入是<b>整份取代</b>，取代前會先把目前狀態複製到剪貼簿當退路。</p>
      <div class="row"><button class="btn primary" data-act="export">匯出到剪貼簿</button><button class="btn" data-act="share">分享…</button></div>
      <p class="faint">上次匯出：${S.last_export || "從未"}</p>
      <textarea id="import-box" placeholder="貼上之前匯出的 JSON"></textarea><button class="btn" data-act="import">匯入（取代目前進度）</button></div>
    <div class="card"><h3>從 ChatGPT 貼回</h3><p class="small muted">把 ChatGPT 週檢討最後的 <code>n5-feedback</code> 區塊整段貼上。</p>
      <textarea id="fb-box" placeholder='\`\`\`n5-feedback\n{"week":"W01","speaking":12,...}\n\`\`\`'></textarea><button class="btn" data-act="feedback">貼回</button></div>
    <div class="card"><h3>週報</h3><p class="small muted">給 ChatGPT 做週檢討用的摘要（不是備份）。</p><button class="btn" data-act="weekly-report">產生本週週報到剪貼簿</button></div>
    <div class="card"><h3>狀態</h3><p class="small">課綱版本 ${esc(CUR.version)}（狀態記錄 ${esc(S.curriculum_version)}）· 輪次 ${S.round} · 最後學習 ${S.last_activity || "–"}</p>
      <div class="row"><label class="sw">開始日 <input type="date" id="started" value="${S.started || ""}" data-act="set-started"></label></div>
      <p class="faint">弱點清單 ${S.weak.length} 項 · 回報教材錯誤 ${S.lesson_issues.length} 件</p></div>
    <div class="card"><h3>顯示</h3>${rubyToggleHTML()}</div>
    <div class="card"><h3>語音</h3>
      <p class="small muted">有預生成音檔的課（OpenAI TTS，NHK 播報風格）用音檔；沒有的退回 iOS 系統語音。語速兩者都吃：</p>
      <div class="row">${Object.keys(RATES).map((k) => `<button class="btn ${TTS.rate === k ? "primary" : ""}" data-act="tts-rate" data-rate="${k}">${RATE_LABEL[k]}</button>`).join("")}</div>
      <p class="small muted" style="margin-top:10px">聲音（機器感太重就換一個；名字有 Enhanced／Premium／拡張 的最自然，iOS 要先下載）</p>
      <select id="tts-voice" style="max-width:100%;font:inherit;padding:6px;border-radius:8px;border:1px solid var(--border)"><option value="">自動挑最自然的</option>${jaVoices().map((v) => `<option value="${esc(v.name)}" ${TTS.voice === v.name ? "selected" : ""}>${esc(v.name)}${voiceScore(v) >= 10 ? "（加強版）" : ""}</option>`).join("")}</select>
      <p><button class="btn tts" data-act="tts-test">▶ 試聽</button> <span class="faint">會用：${esc(pickVoice()?.name || "（找不到日文聲音）")}</span></p>
      <p class="faint" id="tts-last">上次播放：${LAST_TTS ? `${esc(LAST_TTS.voice)}（${esc(LAST_TTS.lang)}）· 速度 ${LAST_TTS.rate} · ${esc(LAST_TTS.state)} · ${LAST_TTS.at}` : "—"}</p>
      <p><button class="btn small" data-act="tts-diag">診斷</button> <span class="faint">沒聲音時按：會顯示引擎狀態，並解除卡住的暫停</span></p>
      <p class="faint">裝置日文聲音 ${jaVoices().length} 個／全部 ${refreshVoices().length} 個。若播出來是中文：先按「▶ 試聽」看上面這行用了哪個聲音，再回報。</p>
      <p class="faint">iOS 下載加強版聲音：設定 → 輔助使用 → 朗讀內容 → 聲音 → 日文 → Kyoko／Otoya／O-Ren／Hattori 旁的下載，選「加強」或「進階」</p></div>`;
  $("#tts-voice")?.addEventListener("change", (e) => ACT["tts-voice"](e.target));
  $("#started")?.addEventListener("change", (e) => { S.started = e.target.value || null; save(); toast("已更新開始日"); });
}

// ---------- 今日 ----------
async function renderToday() {
  settleTodo();
  if (!S.diagnostic.done) return renderDiagnostic();
  const t = S.todo[0];
  if (t) return t.kind === "return_test" ? renderReturnTest(t) : t.kind === "remedial" ? renderRemedial(t) : renderShortReview(t);
  const nx = nextLessonId();
  if (!nx.id) { view.innerHTML = `<h1>今日</h1><div class="card"><p>目前課綱的課都完成了。</p></div>`; return; }
  if (nx.locked) { view.innerHTML = `<h1>今日</h1><div class="notice red">${nx.id} 鎖住：${nx.locked}</div><p class="muted">到課表的階段區填分數，或重測弱項。</p>${renderStageEntry(stageOf(nx.id) - 1)}`; return; }
  await renderLesson(nx.id);
}

function renderDiagnostic() {
  view.innerHTML = `<h1>第 0 週：入學診斷</h1><div class="card"><p>SPEC §7.1：正式上課前先做 20–25 分鐘診斷。v1 的診斷在 ChatGPT 做（假名、單字、文法、閱讀、聽力、口說），結果回來這裡登記：</p>
    <label class="sw"><input type="checkbox" id="kana-ok"> 假名（平假名＋片假名）已熟練</label>
    <p class="small muted">已熟練的單字／文法之後可在課表長按標「豁免」；現在先開始。</p>
    <div class="row"><label class="sw">開始日 <input type="date" id="started" value="${today()}"></label></div>
    <button class="btn primary block" data-act="diag-done">完成診斷，開始 Day 1</button></div>
    <div class="card soft"><p class="small muted">給 ChatGPT 的診斷指令：</p><pre class="prompt">請依我們的日文學習計畫規格書 §7.1 幫我做 N5 入學診斷，約 20–25 分鐘：假名辨讀 10 題、單字 10 題、文法 10 題、一段閱讀＋3 題、一段聽力（你唸）＋3 題、簡短口說 1 分鐘。做完給我各項百分比，以及「可以跳過的內容」清單。</pre><button class="btn small" data-act="copy" data-text="請依我們的日文學習計畫規格書 §7.1 幫我做 N5 入學診斷，約 20–25 分鐘：假名辨讀 10 題、單字 10 題、文法 10 題、一段閱讀＋3 題、一段聽力（你唸）＋3 題、簡短口說 1 分鐘。做完給我各項百分比，以及「可以跳過的內容」清單。">複製</button></div>`;
}

function rubyToggleHTML() { return `<label class="sw small"><input type="checkbox" data-act="ruby-toggle" ${SHOW_RUBY ? "checked" : ""}> 顯示注音（熟了就關掉，SPEC §4.4）</label>`; }
function quizHTML(qs, key, opts = {}) {                    // 一組題目；runner.answers[key] 記作答
  const ans = (runner.answers ??= {})[key] ??= {};
  const graded = runner.graded?.[key];
  return qs.map((q, i) => `<div class="q"><p><b>${i + 1}.</b> ${esc(q.q)}</p>${q.options.map((o, j) => { let cls = "opt"; if (graded) { if (j === q.answer) cls += " ok"; else if (ans[i] === j) cls += " bad"; } else if (ans[i] === j) cls += " sel"; return `<button class="${cls}" data-act="pick" data-key="${key}" data-q="${i}" data-o="${j}" ${graded ? "disabled" : ""}>${esc(o)}</button>`; }).join("")}
    ${graded && (q.explain || q.evidence) ? `<div class="explain">${esc(q.explain || `依據：「${q.evidence}」`)}</div>` : ""}</div>`).join("") +
    (graded ? `<p class="small"><b>${graded.score}／${qs.length}</b> 答對</p>` : `<button class="btn primary small" data-act="grade" data-key="${key}" ${opts.label ? `data-label="${opts.label}"` : ""}>送出作答</button>`);
}
function gradeQuiz(qs, key) { const ans = runner.answers?.[key] || {}; let score = 0; const wrong = []; qs.forEach((q, i) => { if (ans[i] === q.answer) score++; else wrong.push(q.tests || q.q); }); (runner.graded ??= {})[key] = { score, wrong }; return { score, wrong }; }

async function renderLesson(id) {
  const d = await loadLesson(id);
  const cl = L[id];
  if (!d) { view.innerHTML = `<h1>${id}</h1><div class="notice red">這課的教材還沒生成（${esc(cl.theme)}）。</div>`; return; }
  if (runner.id !== id) runner = { id, answers: {}, graded: {}, card: 0, cards: {}, reveal: false };
  const x = lessonState(id);
  if (cl.day_type !== "new") return renderQuizLesson(id, d, x);
  const busy = S.busy;
  const mods = busy ? MODULES_NEW.filter(([k]) => BUSY_MODULES.includes(k)) : MODULES_NEW;
  if (!runner.openMod || !mods.some(([k]) => k === runner.openMod)) runner.openMod = (mods.find(([k]) => !x.modules[k]) || mods[0])[0];
  const doneCount = MODULES_NEW.filter(([k]) => x.modules[k]).length;
  const grammarIds = d.grammar.map((g) => g.id);
  view.innerHTML = `<div class="row between"><h1>${id} <span class="badge">${esc(cl.stage_name)} · 第 ${cl.week} 週</span></h1></div>
    <p class="muted">${esc(cl.theme)}</p>
    <div class="row between"><label class="sw"><input type="checkbox" data-act="busy-toggle" ${busy ? "checked" : ""}> 忙碌／值班版（20 分鐘）</label><span class="faint">${doneCount}／${MODULES_NEW.length} 模組</span></div>
    ${busy ? `<div class="notice">忙碌版只做單字複習、聽力跟讀、口說；不算完成這一課（SPEC §5.2）。</div>` : ""}
    ${mods.map(([k, name], i) => `<details class="module ${x.modules[k] ? "done" : ""}" data-mod="${k}" ${k === runner.openMod ? "open" : ""}><summary><span class="num">${x.modules[k] ? "✓" : i + 1}</span>${name}</summary><div class="body">${moduleHTML(k, d, cl, x)}</div></details>`).join("")}
    ${busy ? `<button class="btn primary block" data-act="busy-done">記錄一次忙碌版練習</button>` : ""}`;
  view.querySelectorAll("details.module").forEach((el) => el.addEventListener("toggle", () => { if (el.open) runner.openMod = el.dataset.mod; else if (runner.openMod === el.dataset.mod) runner.openMod = null; }));
}
function moduleHTML(k, d, cl, x) {
  const doneBtn = (label = "完成這個模組") => `<button class="btn small" data-act="mod-done" data-mod="${k}" ${x.modules[k] ? "disabled" : ""}>${x.modules[k] ? "已完成" : label}</button>`;
  switch (k) {
    case "warmup": return quizHTML(d.warmup, "warmup") + `<p>${doneBtn()}</p>`;
    case "vocab": {
      const list = S.busy ? d.busy_mode.vocab_review_ids.map((i) => V[i]).filter(Boolean).map((v) => ({ ...v, example_ja: "", example_kana: "", example_zh: "" })) : d.vocab;
      const i = Math.min(runner.card, list.length - 1); const v = list[i]; const flip = runner.cards[i] || 0;
      return `<div class="dots">${list.map((_, j) => `<i class="${j === i ? "on" : runner.know?.[j] === true ? "know" : runner.know?.[j] === false ? "dunno" : ""}"></i>`).join("")}</div>
        <div class="flash" data-act="flip"><div class="kanji ja">${esc(v.kanji)}</div>${(flip >= 1 || SHOW_RUBY) && v.kanji !== v.kana ? `<div class="kana ja">${esc(v.kana)}</div>` : ""}${flip >= 2 ? `<div>${esc(v.zh)} <span class="pos">${esc(v.pos)}</span></div>${v.example_ja ? `<div class="ex ja">${rubyHTML(v.example_ja, v.example_kana)}<br><span class="muted small">${esc(v.example_zh)}</span></div>` : ""}${v.note ? `<p class="faint">${esc(v.note)}</p>` : ""}` : `<p class="faint">${SHOW_RUBY ? "點一下看意思" : "讀音？點一下"}</p>`}</div>
        <div class="row" style="margin-top:8px"><button class="btn tts" data-act="play" data-id="${runner.id}" data-key="vocab.${v.id}" data-text="${esc(v.kana)}">▶ 讀音</button>${v.example_ja ? `<button class="btn tts" data-act="play" data-id="${runner.id}" data-key="vocab.${v.id}.ex" data-text="${esc(v.example_ja)}">▶ 例句</button>` : ""}<span class="grow"></span><button class="btn small" data-act="card-mark" data-v="0">不會</button><button class="btn small primary" data-act="card-mark" data-v="1">會了 ✓</button></div>
        <div class="row between" style="margin-top:8px"><button class="btn ghost small" data-act="card-prev">‹ 上一個</button><span class="faint">${i + 1}／${list.length}</span><button class="btn ghost small" data-act="card-next">下一個 ›</button></div><p>${doneBtn()}</p>`;
    }
    case "grammar": return d.grammar.map((g) => `<div class="gram"><h3 class="ja">${esc(g.pattern)}</h3><dl><dt>接續</dt><dd>${esc(g.structure)}</dd><dt>意思</dt><dd>${esc(g.meaning)}</dd><dt>用法</dt><dd>${esc(g.usage)}</dd>
      <dt>變化</dt><dd>${g.forms.map((f, fi) => `<div class="line">${btnPlay(runner.id, `grammar.${g.id}.form.${fi}`, f.ja)}<div><span class="faint">${esc(f.label)}</span><br><span class="ja">${rubyHTML(f.ja, f.kana)}</span><br><span class="small muted">${esc(f.zh)}</span></div></div>`).join("")}</dd>
      <dt>例句</dt><dd>${g.examples.map((e, ei) => `<div class="line">${btnPlay(runner.id, `grammar.${g.id}.ex.${ei}`, e.ja)}<div><span class="ja">${rubyHTML(e.ja, e.kana)}</span><br><span class="small muted">${esc(e.zh)}</span> <span class="badge">${esc(e.scene)}</span></div></div>`).join("")}</dd>
      <dt>常見錯誤</dt><dd><ul>${g.mistakes.map((m) => `<li>${esc(m)}</li>`).join("")}</ul></dd>${g.compare ? `<dt>比較</dt><dd>${esc(g.compare)}</dd>` : ""}</dl></div>`).join("<hr>") + `<p>${doneBtn()}</p>`;
    case "patterns": return d.patterns.map((p, pi) => `<div class="line">${btnPlay(runner.id, `patterns.${pi}`, p.ja)}<div><span class="ja">${rubyHTML(p.ja, p.kana)}</span><br><span class="small muted">${esc(p.zh)}</span> <span class="faint">可換：${p.swap_slots.map(esc).join("、")}</span></div></div>`).join("") + `<p class="faint">照 SPEC §4.4：每句用自己的資訊換一次。</p><p>${doneBtn()}</p>`;
    case "reading": return `<span class="badge">${esc(d.reading.type)}</span><div class="script ja">${rubyHTML(d.reading.text_ja, d.reading.text_kana)}</div>${rubyToggleHTML()}
      ${btnPlay(runner.id, "reading", d.reading.text_ja, "▶ 朗讀")}${quizHTML(d.reading.questions, "reading")}<p>${doneBtn()}</p>`;
    case "listening": {
      const src = S.busy ? d.busy_mode : d;  // 忙碌版聽力同上
      return `<p class="small muted">SPEC §4.5 流程：盲聽 1–2 次 → 作答 → 看逐字稿 → 分句跟讀 → 不看稿重聽</p>
        <div class="row">${Object.keys(RATES).map((k) => `<button class="btn tts" data-act="play" data-id="${runner.id}" data-key="listening" data-text="${esc(d.listening.script_ja)}" data-rate="${k}">▶ ${RATE_LABEL[k]}</button>`).join("")}</div>
        ${quizHTML(d.listening.questions, "listening")}
        ${runner.reveal ? `<h3>逐字稿（分句跟讀）</h3><div class="script ja">${rubyHTML(d.listening.script_ja, d.listening.script_kana)}</div>${rubyToggleHTML()}${d.listening.script_ja.split(/(?<=[。？！」])\s*/).filter((s) => s.trim()).map((s, si) => `<div class="line">${btnPlay(runner.id, `listening.line.${si}`, s)}<span class="ja">${esc(s)}</span></div>`).join("")}` : `<button class="btn small" data-act="reveal">作答後看逐字稿</button>`}
        <p>${doneBtn()}</p>`;
    }
    case "speaking": { const sp = S.busy ? { task_zh: d.busy_mode.speaking_short, chatgpt_prompt: d.speaking.chatgpt_prompt, type: "忙碌版" } : d.speaking;
      return `<span class="badge indigo">${esc(sp.type)}</span><p>${esc(sp.task_zh)}</p>${sp.task_ja ? `<p class="ja">${esc(sp.task_ja)} ${btnPlay(runner.id, "speaking", sp.task_ja)}</p>` : ""}
        <button class="btn primary" data-act="copy" data-text="${esc(sp.chatgpt_prompt)}">複製給 ChatGPT</button><details><summary class="faint small">看指令內容</summary><pre class="prompt">${esc(sp.chatgpt_prompt)}</pre></details><p>${doneBtn("練完了")}</p>`; }
    case "check": return quizHTML(d.check, "check") + (runner.graded?.check ? `<p><button class="btn primary" data-act="finish-lesson">完成這一課</button></p>` : `<p class="faint">送出作答後才能完成這一課。</p>`);
  }
}

function renderQuizLesson(id, d, x) {                    // review／stage_test：四項自動計分＋口說手填
  const cl = L[id]; const isStage = cl.day_type === "stage_test"; const q = d.quiz;
  const readingQs = isStage ? q.reading.passages.flatMap((p) => p.questions) : q.reading.questions;
  const listeningQs = isStage ? q.listening.scripts.flatMap((s) => s.questions) : q.listening.questions;
  const readingHTML = (isStage ? q.reading.passages.map((p, i) => `<h3>閱讀 ${i + 1}</h3><div class="script ja">${rubyHTML(p.text_ja, p.text_kana)}</div>`).join("") : `<div class="script ja">${rubyHTML(q.reading.text_ja, q.reading.text_kana)}</div>`) + rubyToggleHTML();
  const listenHTML = isStage ? q.listening.scripts.map((s, i) => `<div class="row">${Object.keys(RATES).map((k) => btnPlay(id, `listening.${i}`, s.script_ja, `▶ 聽力 ${i + 1} ${RATE_LABEL[k]}`, `data-rate="${k}"`)).join("")}</div>`).join("") : `<div class="row">${Object.keys(RATES).map((k) => btnPlay(id, "listening", q.listening.script_ja, `▶ ${RATE_LABEL[k]}`, `data-rate="${k}"`)).join("")}</div>`;
  const allGraded = ["qv", "qg", "qr", "ql"].every((k) => runner.graded?.[k]);
  const scores = allGraded ? { vocab: Math.round(runner.graded.qv.score / q.vocab.length * 20), grammar: Math.round(runner.graded.qg.score / q.grammar.length * 20), reading: Math.round(runner.graded.qr.score / readingQs.length * 20), listening: Math.round(runner.graded.ql.score / listeningQs.length * 20) } : null;
  const wrongIds = allGraded ? [...runner.graded.qv.wrong, ...runner.graded.qg.wrong].filter((t) => V[t] || G[t]) : [];
  view.innerHTML = `<h1>${id} <span class="badge ${isStage ? "red" : "indigo"}">${isStage ? "階段測驗" : "週測"}</span></h1><p class="muted">${esc(cl.theme)}</p>
    <details class="module" open><summary><span class="num">1</span>單字 ${q.vocab.length} 題</summary><div class="body">${quizHTML(q.vocab, "qv")}</div></details>
    <details class="module"><summary><span class="num">2</span>文法句型 ${q.grammar.length} 題</summary><div class="body">${quizHTML(q.grammar, "qg")}</div></details>
    <details class="module"><summary><span class="num">3</span>閱讀</summary><div class="body">${readingHTML}${quizHTML(readingQs, "qr")}</div></details>
    <details class="module"><summary><span class="num">4</span>聽力</summary><div class="body">${listenHTML}${quizHTML(listeningQs, "ql")}${runner.graded?.ql ? (isStage ? q.listening.scripts.map((s) => `<div class="script ja">${rubyHTML(s.script_ja, s.script_kana)}</div>`).join("") : `<div class="script ja">${rubyHTML(q.listening.script_ja, q.listening.script_kana)}</div>`) : ""}</div></details>
    <details class="module"><summary><span class="num">5</span>口說（ChatGPT 評分）</summary><div class="body"><p>${esc(q.speaking.task_zh)}</p><ul class="small">${q.speaking.rubric.map((r) => `<li><b>${esc(r.name)}</b>：${esc(r.criteria)}</li>`).join("")}</ul>
      <button class="btn primary" data-act="copy" data-text="${esc(q.speaking.chatgpt_prompt)}">複製給 ChatGPT</button><p class="row">口說分數（0–20）<input type="number" id="sp-score" min="0" max="20" value="${runner.sp ?? ""}"> <span class="faint">${isStage ? "階段測驗必填" : "可之後在設定貼回"}</span></p></div></details>
    ${allGraded ? `<div class="card"><h3>成績</h3>${PARTS.map(([k, n]) => `<div class="score-row"><span>${n}</span><b>${k === "speaking" ? (runner.sp ?? "–") : scores[k]}／20</b></div>`).join("")}
      ${wrongIds.length ? `<h3 style="margin-top:12px">錯題訂正</h3>${wrongIds.map((t) => V[t] ? `<div class="line"><button class="btn tts small" data-act="say" data-text="${esc(V[t].kana)}">▶</button><span class="ja">${rubyHTML(V[t].kanji, V[t].kana)}</span> ${esc(V[t].zh)}</div>` : `<div class="line"><span class="ja">${esc(G[t].pattern)}</span> <span class="muted small">${esc(G[t].meaning_zh)}</span></div>`).join("")}<label class="sw" style="margin-top:8px"><input type="checkbox" id="corrected"> 錯題都看過訂正了</label>` : `<p class="green">全對，不用訂正。</p>`}
      <button class="btn primary block" data-act="finish-quiz" style="margin-top:10px">提交${isStage ? "階段測驗" : "週測"}</button></div>` : `<p class="faint">四項都送出作答後出現成績與提交。</p>`}`;
  $("#sp-score")?.addEventListener("change", (e) => { runner.sp = e.target.value === "" ? null : Math.max(0, Math.min(20, +e.target.value)); });
}
function renderStageEntry(s) {
  const r = stageRec(s);
  if (!r) return `<div class="card"><p>第 ${s} 階段的階段測驗還沒提交。到課表點 W${String(s * 4).padStart(2, "0")}D6。</p></div>`;
  const canRetest = r.retest_after && today() >= r.retest_after;
  return `<div class="card"><h3>第 ${s} 階段：補強週</h3><p>弱項：${r.remedial_parts.map((k) => PARTS.find(([x]) => x === k)[1]).join("、")}。${canRetest ? "可以重測了，只填弱項分數：" : `${r.retest_after} 之後可重測。`}</p>
    ${canRetest ? r.remedial_parts.map((k) => `<div class="score-row"><span>${PARTS.find(([x]) => x === k)[1]}</span><input type="number" min="0" max="20" data-part="${k}" value="${r.test.parts[k]}"></div>`).join("") + `<button class="btn primary" data-act="retest" data-stage="${s}">重測提交</button>` : ""}</div>`;
}

async function renderReturnTest(t) {                     // §3.2 回歸測驗：只從已學項目抽
  const learned = ORDER.filter((id) => ["done", "remedial"].includes(st(id).status));
  const vocab = sample(learned.flatMap((id) => L[id].new_vocab), 10), gram = sample(learned.flatMap((id) => L[id].new_grammar), 3);
  if (!learned.length) { completeTodo(t); return renderToday(); }
  runner.rt ??= { items: [...vocab.map((v) => ({ kind: "v", id: v })), ...gram.map((g) => ({ kind: "g", id: g }))], i: 0, know: [] };
  const r = runner.rt; const gap = daysBetween(S.flow.settled_last_activity, today());
  if (r.i >= r.items.length) { const ok = r.know.filter(Boolean).length, ratio = ok / r.items.length;
    view.innerHTML = `<h1>回歸測驗</h1><div class="card"><p>中斷 ${gap} 天。${ok}／${r.items.length} 還記得（${Math.round(ratio * 100)}%）。</p>${ratio < .5 ? `<div class="notice">建議從較早的課重來。選一個課次，該課之後的進度會重設（紀錄保留在 history）：</div><div class="row">${learned.map((id) => `<button class="btn small" data-act="restart-from" data-id="${id}">${id}</button>`).join("")}</div><p></p>` : ""}<button class="btn primary block" data-act="rt-continue">${ratio < .5 ? "不重來，繼續" : "繼續原進度"}</button></div>`; return; }
  const it = r.items[r.i]; const flip = r.flip;
  view.innerHTML = `<h1>回歸測驗 <span class="badge amber">中斷 ${gap} 天</span></h1><p class="muted">先看看還記得多少，再決定從哪裡接。</p><div class="dots">${r.items.map((_, j) => `<i class="${j === r.i ? "on" : r.know[j] === true ? "know" : r.know[j] === false ? "dunno" : ""}"></i>`).join("")}</div>
    <div class="flash" data-act="rt-flip">${it.kind === "v" ? `<div class="kanji ja">${esc(V[it.id].kanji)}</div>${flip ? `<div class="kana ja">${esc(V[it.id].kana)}</div><div>${esc(V[it.id].zh)}</div>` : `<p class="faint">讀音和意思？點一下看答案</p>`}` : `<div class="ja-big ja">${esc(G[it.id].pattern)}</div>${flip ? `<div>${esc(G[it.id].meaning_zh)}</div>` : `<p class="faint">意思和用法？點一下看答案</p>`}`}</div>
    <div class="row" style="margin-top:10px"><button class="btn grow" data-act="rt-mark" data-v="0">忘了</button><button class="btn primary grow" data-act="rt-mark" data-v="1">記得</button></div>`;
}
async function renderShortReview(t) {
  const last = [...ORDER].reverse().find((id) => ["done", "remedial"].includes(st(id).status));
  const d = last && await loadLesson(last);
  if (!d || !d.warmup) { completeTodo(t); return renderToday(); }
  runner.sr ??= {};
  view.innerHTML = `<h1>短複習 <span class="badge amber">中斷 ${daysBetween(S.flow.settled_last_activity, today())} 天</span></h1><p class="muted">SPEC §7.2：中斷 1–3 天先做短複習，不補課。用 ${last} 的暖身題：</p><div class="card">${quizHTML(d.warmup, "sr")}${runner.graded?.sr ? `<button class="btn primary block" data-act="sr-done">完成，進今天的課</button>` : ""}</div>`;
}
async function renderRemedial(t) {
  const d = await loadLesson(t.lesson); const x = st(t.lesson);
  if (!d) { view.innerHTML = `<div class="notice red">找不到 ${t.lesson} 的教材</div>`; return; }
  const wrong = x.check?.wrong || [];
  view.innerHTML = `<h1>補強 ${t.lesson} <span class="badge amber">小檢核 ${x.check?.score}／${x.check?.total}</span></h1><p class="muted">SPEC §7.2：未達 70%，先補強 5–10 分鐘再開新課。</p>
    <div class="card"><h3>上次錯的</h3>${wrong.length ? wrong.map((w) => V[w] ? `<div class="line"><button class="btn tts small" data-act="say" data-text="${esc(V[w].kana)}">▶</button><span class="ja">${rubyHTML(V[w].kanji, V[w].kana)}</span> ${esc(V[w].zh)}</div>` : G[w] ? `<div class="line"><span class="ja">${esc(G[w].pattern)}</span> <span class="muted small">${esc(G[w].meaning_zh)}</span></div>` : "").join("") : "<p class='muted'>（沒有記錄到錯題項目）</p>"}</div>
    <div class="card"><h3>重做小檢核</h3>${quizHTML(d.check, "rem")}${runner.graded?.rem ? `<button class="btn primary block" data-act="rem-done">補強完成</button>` : ""}</div>`;
}

// ---------- 動作 ----------
const ACT = {
  "go-today": () => { tab = "today"; render(); },
  "open-lesson": async (a) => { const id = a.dataset.id; tab = "today"; document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === "today")); runner = {}; await renderLesson(id); },
  say: (a) => speak(a.dataset.text, a.dataset.rate),
  play: (a) => playKey(a.dataset.id, a.dataset.key, a.dataset.rate, a.dataset.text),
  "tts-test": () => speak("こんにちは。私は台湾人です。日本語を勉強しています。"),
  "tts-diag": () => { const ss = speechSynthesis; toast(`speaking=${ss.speaking} pending=${ss.pending} paused=${ss.paused} 日文聲音=${jaVoices().length}／${refreshVoices().length}`); if (ss.paused) ss.resume(); },
  "tts-rate": (a) => { TTS.rate = a.dataset.rate; saveTTS(); renderSettings(); speak("こんにちは。私は台湾人です。"); },
  "tts-voice": (a) => { TTS.voice = a.value || null; saveTTS(); speak("こんにちは。私は台湾人です。"); },
  copy: async (a) => { try { await navigator.clipboard.writeText(a.dataset.text); toast("已複製，去 ChatGPT 貼上"); } catch { prompt("手動複製：", a.dataset.text); } },
  flip: () => { runner.cards[runner.card] = ((runner.cards[runner.card] || 0) + 1) % 3; renderLesson(runner.id); },
  "card-prev": () => { runner.card = Math.max(0, runner.card - 1); renderLesson(runner.id); },
  "card-next": () => { runner.card += 1; renderLesson(runner.id); },
  "card-mark": (a) => { (runner.know ??= {})[runner.card] = a.dataset.v === "1"; if (a.dataset.v === "0") { const d = lessonCache[runner.id]; const list = S.busy ? d.busy_mode.vocab_review_ids : d.vocab.map((v) => v.id); addWeak(list[runner.card], "card"); } runner.card += 1; runner.cards[runner.card] = 0; renderLesson(runner.id); },
  pick: (a) => { runner.answers[a.dataset.key][a.dataset.q] = +a.dataset.o; tab === "today" && (runner.id ? renderLesson(runner.id) : renderToday()); },
  grade: (a) => { const key = a.dataset.key; const qs = quizByKey(key); const g = gradeQuiz(qs, key); if (key === "check") { g.wrong.forEach((w) => addWeak(w, "check")); } if (key === "sr" || key === "rem") return renderToday(); renderLesson(runner.id); },
  reveal: () => { runner.reveal = true; renderLesson(runner.id); },
  "ruby-toggle": (a) => { SHOW_RUBY = a.checked; try { localStorage.setItem("nihongo.ruby", SHOW_RUBY ? "on" : "off"); } catch {} runner.id ? renderLesson(runner.id) : render(); },
  "mod-done": (a) => { const x = lessonState(runner.id); x.modules[a.dataset.mod] = true; if (x.status === "available") x.status = "partial"; runner.openMod = null; touch(); save(); renderLesson(runner.id); },
  "busy-toggle": (a) => { S.busy = a.checked; save(); renderLesson(runner.id); },
  "busy-done": () => { S.practice.push({ date: today(), kind: "busy", lesson: runner.id, minutes: 20 }); S.busy = false; touch(); save(); toast("已記錄忙碌版練習，課次不推進"); tab = "home"; render(); },
  "finish-lesson": () => {                               // §3.1 new 課完成
    const d = lessonCache[runner.id]; const x = lessonState(runner.id); const g = runner.graded.check;
    MODULES_NEW.forEach(([k]) => (x.modules[k] = true));
    x.check = { score: g.score, total: d.check.length, wrong: g.wrong };
    const ok = g.score / d.check.length >= .7;
    x.status = ok ? "done" : "remedial"; x.remedial_done = ok ? undefined : false; x.done_at = today();
    if (!S.started) S.started = today();
    touch(); save(); runner = {}; toast(ok ? "完成！" : "小檢核未達 70%，下次先補強"); tab = "home"; render();
  },
  "finish-quiz": () => {                                  // §3.1 review／stage_test 完成（同一次提交寫 weekly／stage）
    const id = runner.id; const cl = L[id]; const d = lessonCache[id]; const x = lessonState(id); const isStage = cl.day_type === "stage_test";
    const wrongIds = [...runner.graded.qv.wrong, ...runner.graded.qg.wrong].filter((t) => V[t] || G[t]);
    if (wrongIds.length && !$("#corrected")?.checked) return toast("先勾「錯題都看過訂正了」");
    if (isStage && runner.sp == null) return toast("階段測驗需要口說分數");
    const readingN = isStage ? d.quiz.reading.passages.reduce((a, p) => a + p.questions.length, 0) : d.quiz.reading.questions.length;
    const listenN = isStage ? d.quiz.listening.scripts.reduce((a, s) => a + s.questions.length, 0) : d.quiz.listening.questions.length;
    const parts = { vocab: Math.round(runner.graded.qv.score / d.quiz.vocab.length * 20), grammar: Math.round(runner.graded.qg.score / d.quiz.grammar.length * 20), reading: Math.round(runner.graded.qr.score / readingN * 20), listening: Math.round(runner.graded.ql.score / listenN * 20), speaking: runner.sp ?? null };
    wrongIds.forEach((w) => addWeak(w, isStage ? "stage" : "weekly"));
    const wk = `W${String(cl.week).padStart(2, "0")}`;
    S.weekly[wk] = { quiz: parts, entered_at: today(), round: S.round };
    if (isStage) { const r = passFn(parts); S.stage[cl.stage] = { round: S.round, test: { total: r.total, parts, taken: today() }, passed: r.passed, remedial_parts: r.remedial_parts, retest_after: r.passed ? null : addDays(today(), 7) }; }
    evalAdjustTasks(cl.week);
    x.status = "done"; x.done_at = today(); x.modules = { quiz: true };
    touch(); save(); runner = {}; toast(isStage ? (S.stage[cl.stage].passed ? "階段通過！" : "未通過，進入補強週") : "週測已記錄"); tab = "home"; render();
  },
  retest: (a) => { const s = +a.dataset.stage; const r = stageRec(s); document.querySelectorAll("[data-part]").forEach((i) => (r.test.parts[i.dataset.part] = Math.max(0, Math.min(20, +i.value)))); const p = passFn(r.test.parts); Object.assign(r, { test: { ...r.test, total: p.total, taken: today() }, passed: p.passed, remedial_parts: p.remedial_parts, retest_after: p.passed ? null : addDays(today(), 7) }); touch(); save(); toast(p.passed ? "通過！下一階段解鎖" : "仍未通過，再補強一週"); render(); },
  "rt-flip": () => { runner.rt.flip = true; renderToday(); },
  "rt-mark": (a) => { runner.rt.know[runner.rt.i] = a.dataset.v === "1"; if (a.dataset.v === "0") addWeak(runner.rt.items[runner.rt.i].id, "return_test"); runner.rt.i++; runner.rt.flip = false; renderToday(); },
  "rt-continue": () => { const t = S.todo.find((t) => t.kind === "return_test"); if (t) completeTodo(t); runner = {}; renderToday(); },
  "restart-from": (a) => { if (!confirm(`從 ${a.dataset.id} 重來？該課之後的進度會重設。`)) return; newRound(a.dataset.id); runner = {}; toast(`第 ${S.round} 輪，從 ${a.dataset.id} 開始`); renderToday(); },
  "sr-done": () => { const t = S.todo.find((t) => t.kind === "short_review"); if (t) completeTodo(t); runner = {}; renderToday(); },
  "rem-done": () => { const t = S.todo.find((t) => t.kind === "remedial"); if (!completeTodo(t)) { S.todo = S.todo.filter((u) => u !== t); save(); return renderToday(); }   // 先驗有效再轉狀態（§3.2）
    const x = lessonState(t.lesson); x.remedial_done = true; x.status = "done"; save(); runner = {}; toast("補強完成"); renderToday(); },
  "diag-done": () => { S.diagnostic.done = true; S.diagnostic.kana_ok = $("#kana-ok").checked; S.started = $("#started").value || today(); save(); renderToday(); },
  "task-done": (a) => { const t = S.adjust_tasks.find((x) => x.id === a.dataset.id); if (t) { t.done = true; t.done_at = today(); save(); toast("已完成"); } },
  export: async () => { const s = exportText(); try { await navigator.clipboard.writeText(s); S.last_export = today(); save(); toast("已複製完整備份"); renderSettings(); } catch { prompt("手動複製：", s); } },
  share: async () => { const s = exportText(); if (navigator.share) { try { await navigator.share({ title: `nihongo 備份 ${today()}`, text: s }); S.last_export = today(); save(); renderSettings(); } catch {} } else toast("這個瀏覽器不支援分享"); },
  import: async () => {
    let d; try { d = JSON.parse($("#import-box").value); } catch { return toast("不是合法 JSON"); }
    if (d.schema !== 1) return toast(`schema 不符（${d.schema}）`);
    if (d.curriculum_version !== CUR.version) return toast(`課綱版本不同（備份 ${d.curriculum_version}，目前 ${CUR.version}），拒絕匯入`);
    const n = Object.values(d.lessons || {}).filter((x) => x.status === "done").length, m = Object.values(S.lessons).filter((x) => x.status === "done").length;
    if (!confirm(`將以備份（${n} 課完成）取代目前狀態（${m} 課完成）？目前狀態會先複製到剪貼簿。`)) return;
    try { await navigator.clipboard.writeText(exportText()); } catch {}
    S = { ...DEFAULT(), ...d }; save(); toast("已匯入"); render();
  },
  feedback: () => {
    const raw = $("#fb-box").value; const m = raw.match(/```n5-feedback\s*([\s\S]*?)```/) || [null, raw];
    let d; try { d = JSON.parse(m[1].trim()); } catch { return toast("格式不對：找不到合法的 n5-feedback JSON"); }
    if (!/^W\d{2}$/.test(d.week || "")) return toast("week 欄位要像 W03");
    if (d.speaking != null && !(Number.isInteger(d.speaking) && d.speaking >= 0 && d.speaking <= 20)) return toast("speaking 要是 0–20 的整數");
    for (const w of d.weak_add || []) if (w.id && !V[w.id] && !G[w.id]) return toast(`weak_add 的 id ${w.id} 不在課綱`);
    const hash = [...m[1]].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7).toString(16);
    if (S.feedback_log.some((f) => f.hash === hash)) return toast("這段已經貼過了");
    if (d.speaking != null) { S.weekly[d.week] ??= { quiz: {}, round: S.round }; if (S.weekly[d.week].quiz.speaking != null && !confirm(`${d.week} 已有口說分數 ${S.weekly[d.week].quiz.speaking}，覆蓋？`)) return; S.weekly[d.week].quiz.speaking = d.speaking; }
    (d.weak_add || []).forEach((w) => addWeak(w.id || w.text, "chatgpt", w.note)); (d.weak_remove || []).forEach((id) => (S.weak = S.weak.filter((w) => w.id !== id)));
    if (d.suggest) S.suggest = { text: d.suggest, week: d.week, at: today() };
    S.feedback_log.push({ week: d.week, received: today(), hash }); save(); toast("已貼回"); renderSettings();
  },
  "weekly-report": async () => { const s = weeklyReport(); try { await navigator.clipboard.writeText(s); toast("週報已複製"); } catch { prompt("手動複製：", s); } },
};
function quizByKey(key) { const d = lessonCache[runner.id]; const isStage = runner.id && L[runner.id].day_type === "stage_test";
  if (key === "sr") { const last = [...ORDER].reverse().find((id) => ["done", "remedial"].includes(st(id).status)); return lessonCache[last].warmup; }
  if (key === "rem") { const t = S.todo.find((t) => t.kind === "remedial"); return lessonCache[t.lesson].check; }
  return { warmup: d?.warmup, reading: d?.reading?.questions, listening: d?.listening?.questions, check: d?.check, qv: d?.quiz?.vocab, qg: d?.quiz?.grammar,
    qr: isStage ? d?.quiz?.reading.passages.flatMap((p) => p.questions) : d?.quiz?.reading.questions, ql: isStage ? d?.quiz?.listening.scripts.flatMap((s) => s.questions) : d?.quiz?.listening.questions }[key]; }
function addWeak(id, source, note) { if (!id) return; const w = S.weak.find((w) => w.id === id); if (w) { w.count = (w.count || 1) + 1; if (note) w.note = note; } else S.weak.push({ id, source, count: 1, first: today(), note }); }
function evalAdjustTasks(week) {                          // §3.3b：連續兩週規則
  const wk = (n) => S.weekly[`W${String(n).padStart(2, "0")}`]?.quiz; const a = wk(week), b = wk(week - 1); if (!a || !b) return;
  const tot = (q) => PARTS.reduce((s, [k]) => s + (q[k] ?? 0), 0);
  const mk = (rule, part, task) => { if (!S.adjust_tasks.some((t) => t.week === week + 1 && t.rule === rule && t.part === part)) S.adjust_tasks.push({ id: `a${Date.now().toString(36)}${part || ""}`, rule, part, week: week + 1, round: S.round, task, done: false }); };
  if (tot(a) >= 85 && tot(b) >= 85) mk("7.3-high", null, "本週閱讀改讀 NHK Easy 一篇完整文章＋口說任務改自由敘述 3 分鐘（連續兩週 ≥85）");
  const tasks = { listening: "本週加一次針對性聽力：NHK Easy 一篇盲聽→跟讀", speaking: "本週加一次 ChatGPT 角色扮演", reading: "本週重讀兩篇閱讀＋重做題目", vocab: "本週重做錯題訂正頁（單字）", grammar: "本週重做錯題訂正頁（文法）" };
  for (const [k] of PARTS) if ((a[k] ?? 20) < 14 && (b[k] ?? 20) < 14) mk("7.3-low", k, tasks[k] + "（連續兩週 <70）");
}
function exportText() { return JSON.stringify({ ...S, exported_at: today() }); }
function weeklyReport() {
  const nx = nextLessonId(); const cl = nx.id ? L[nx.id] : null; const week = cl ? cl.week : LEVEL.weeks; const wk = `W${String(week).padStart(2, "0")}`;
  const done = ORDER.filter((id) => L[id].week === week && st(id).status === "done").map((id) => `${id}（${st(id).done_at}）`);
  const vocab = ORDER.filter((id) => L[id].week === week && st(id).status === "done").flatMap((id) => L[id].new_vocab.map((v) => V[v].kanji));
  const q = S.weekly[wk]?.quiz;
  return [`【nihongo 週報 ${wk}】${today()}`, `完成課次：${done.join("、") || "無"}`, `本週新字：${vocab.join("、") || "無"}`, `小測：${q ? PARTS.map(([k, n]) => `${n} ${q[k] ?? "未填"}`).join("／") : "未測"}`,
    `弱點清單：${S.weak.slice(-15).map((w) => (V[w.id]?.kanji || G[w.id]?.pattern || w.id) + (w.note ? `（${w.note}）` : "") + `×${w.count}`).join("、") || "無"}`,
    `忙碌版：${S.practice.filter((p) => p.kind === "busy" && p.date >= addDays(today(), -7)).length} 次`, `上週建議是否執行：${S.adjust_tasks.filter((a) => a.week === week).map((a) => `${a.task}→${a.done ? "完成" : "未完成"}`).join("；") || "無"}`,
    `請依 SPEC §7.3、§11 做週檢討，最後用 n5-feedback 格式輸出回饋。`].join("\n");
}

// ---------- 啟動 ----------
(async () => {
  load();
  try { await loadCurriculum(); } catch (e) { view.innerHTML = `<div class="notice red">讀不到 curriculum.json：${esc(e.message)}</div>`; return; }
  render();
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
  refreshVoices();
  speechSynthesis?.addEventListener?.("voiceschanged", () => { refreshVoices(); if (tab === "settings") renderSettings(); });
})();
