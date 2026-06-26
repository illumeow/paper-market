# paper-market — 技術規格

**專案：** 營隊賭場銀行模擬系統（Camp Casino Bank Simulation）
**活動時長：** 120 分鐘
**版本：** v1.0（對應實作）

---

## 1. 系統概觀

`paper-market` 是一套為營隊賭場活動打造的假錢銀行與股票交易模擬系統。學員用 play currency 存款、貸款，並在模擬市場裡買賣股票。

系統有三個 surface：

- **Teller Panel** — 行員操作，處理現金面的交易（存款、提款、貸款、定存、紓困、代客下單、發布新聞、匯出）。
- **Member Web App** — 學員端，處理股票交易與帳戶檢視，讓會員不必為了每一筆下單都排隊到櫃檯。
- **Public Stock Dashboard** — 共用螢幕上的唯讀顯示，呈現所有學員可見的即時報價與新聞。

**技術棧：** 單一 FastAPI process（uvicorn）搭配 SQLite（WAL mode）狀態，所有 mutating 操作以一個全域 async lock 包住以確保 atomicity。純運算的 domain 數學（利息、price engine、淨值）獨立出來並做 unit test；薄薄一層 API 包在外面。即時更新透過 SSE 推播，並有一個 5 秒的背景 ticker 推進價格、觸發排程事件。前端是原生 JS。整套以 Docker Compose 部署（app + Caddy），由 Caddy 終止 TLS 並提供 auto-HTTPS。

---

## 2. 認證（Authentication）

### 2.1 會員登入

- 會員只用 **PIN** 登入，不需輸入 member_id。PIN 為 **4 位數、全域唯一**。
- PIN 以 **sha256** hex 儲存（不存明碼），login 設定一組 signed-cookie session（itsdangerous）。
- Login 有 rate limit（每 IP 每分鐘上限），正式環境走 HTTPS。
- PIN 在活動前就**預先指派**並凍結於 `config/pins.csv`（由 `scripts/gen_pins.py` 一次性產生，排除明顯的數字樣式），以便事先印製、公告給會員。provision（`scripts/setup_db.py`，見 §3.1）時把這些 PIN 雜湊成 sha256 寫進 DB —— **執行期不會重新產生**。

### 2.2 行員登入

- 只有一位行員，因此一組共用 password 就夠（來自環境變數 `STAFF_PASSWORD`），同樣以 signed-cookie 做 role gate。
- 會員 session **無法存取** `/api/teller/*` 與 `/api/export`；嘗試存取會被擋下（403）。

> `config/pins.csv` 是 master credential list，列入 gitignore，絕不進版控，需另行私下複製到 VM。

---

## 3. 資料模型（Data Model）

狀態存在 SQLite（WAL mode）。利息採 **lazy accrual** —— 不跑 cron，而是在每次存取帳戶時，依 timestamp 即時把利息算進去。**event clock（活動起始時間 `event_start_at`）不在 provision 時設定，而是由行員開跑時的明確動作設定**（見 §3.1），存於 `meta` table，process 重啟後仍存活。

每位學員有單一帳戶，欄位如下：

| 欄位 | 型別 | 說明 |
|---|---|---|
| `member_id` | string | 格式 `{group}-{index}`，例如 `3-7`。group 為 0–9，index 為 1–12，共 120 位會員。 |
| `pin` | string | 該會員 4 位數 PIN 的 sha256 hex（全域唯一）。 |
| `balance` | integer | 目前現金餘額（play currency），對外一律為整數。 |
| `balance_accrued_at` | timestamp | 上次把活存利息結算進 `balance` 的時間，供 lazy accrual 使用。 |
| `debt` | integer | 未清償的貸款本金。 |
| `loan_taken_at` | timestamp | 動用貸款的時間；全部還清後設回 null。 |
| `relief_claimed` | boolean | 是否已領取一次性紓困。 |
| `last_teller_visit_at` | timestamp | 最近一次 teller 查詢（visit）的時間，供 5 分鐘 cooldown 使用。 |
| `holdings` | map\<stock_id, integer\> | 每檔股票的持股數。 |
| `fixed_deposits` | list\<FixedDeposit\> | 進行中的定存紀錄（見 §4）。 |

> 內部利息運算一律以 `Decimal` 進行，落到使用者／DB 的金額才四捨五入（round half-up）為整數。持股為整數，無碎股。

### 3.1 DB 設定、開機與活動開跑（lifecycle）

**設定（provision）與執行期（runtime）分離** —— DB 的初始化是一個明確、刻意的動作，不混在 app 開機裡：

- **provision**：`python scripts/setup_db.py` 建立 schema 並寫入 members（PIN→sha256）／stocks／events，資料來源是當下的 `config.toml` + `config/pins.csv`。它**不設定 event clock**。`--reset`（搭配 `--force` 於非互動環境）會清空整個 DB 重建 —— 用於賽前準備或重測。
  - 注意：events 是 provision 時一次性寫入的；之後改 `config.toml` 的 `[[events]]` **不會**影響既有 DB，需 `--reset` 重建。
- **開機（resume only）**：app 啟動時**只連線、不 seed**。若 DB 尚未 provision（沒有 members），會在啟動（lifespan startup）時明確報錯，要你先跑 `setup_db.py`。因此活動中不慎 Ctrl-C／crash 後重啟，會**接續既有狀態**而非重置 —— 這正是用 on-disk DB 的目的。
- **開跑（kickoff）**：活動正式開始時，行員在 Teller Panel 按 **Start event**（`POST /api/teller/start`，staff-only），此時才把 `event_start_at` 設為 now。此動作**idempotent**：重複按不會重設時鐘（避免活動中誤觸歸零）。`at_min`／elapsed 全部以這個開跑時刻為基準。
- **開跑前的狀態**：時鐘未設前，**價格凍結**（ticker 不推進價格）、**禁止買賣**（trade route 回 409 `event not started`）。但**銀行業務（存提／貸款／定存／紓困）開跑前仍可操作**，方便賽前先幫會員開戶／佈置。
- Public Dashboard 會顯示 `started` 與 `elapsed_min`（開跑前顯示「尚未開始」）。

---

## 4. 銀行服務（Banking）

Teller Panel 支援以下交易。股票交易刻意排除在行員職責之外（除了代客下單），主要由 Member Web App 處理（見 §7.2）。

### 4.1 存款與提款

- **Deposit** — 加進 `balance`。
- **Withdraw** — 從 `balance` 扣除；若會使餘額變負則擋下（拋 `ValueError`）。
- 兩者都會**先**做活存 accrual 再變動餘額。

### 4.2 活存（Demand Deposit）

- `balance` 以 **每分鐘 0.5%** 複利持續成長：

  ```
  balance = principal × (1 + 0.005) ^ elapsed_minutes
  ```

- 無鎖定期，資金隨時可動用。
- 此 accrual 是**連續**的（lazy，從 timestamp 計算）—— 會員可在 Web App 即時看到餘額成長。

### 4.3 定存（Fixed Deposit）

**開立截止（opening cutoff）** —— 若一筆新定存會延伸到活動結束（T = 120 分）之後，系統擋下開立。通則：`opened_at + term_minutes ≤ 120`。Teller Panel 與 Member Web App 都強制此規則，過了截止點該動作即停用。這保證匯出時每筆未平倉定存都已到期。

`FixedDeposit` 紀錄：

| 欄位 | 型別 | 說明 |
|---|---|---|
| `fd_id` | string | 唯一識別碼。 |
| `principal` | integer | 鎖定金額。 |
| `term_minutes` | integer | `30` 或 `60`。 |
| `rate_per_min` | float | 30 分期為 `0.01`，60 分期為 `0.02`。 |
| `created_at` | timestamp | 定存起始時間。 |
| `matured` | boolean | 是否已完成期限。 |
| `closed` | boolean | 是否已平倉。 |

**到期（maturity）** —— payout 以契約利率對整個 term 複利：

```
payout = principal × (1 + rate_per_min) ^ term_minutes
```

**提前解約（early exit，未滿期）** —— payout 改用 **penalty rate `0.8 × demand_rate` 每分鐘**，對實際經過分鐘數複利，而非契約利率：

```
early_exit_rate = 0.8 × demand_rate        # 例如 0.8 × 0.005 = 0.004
payout = principal × (1 + early_exit_rate) ^ elapsed_minutes
```

`early_exit_rate` 由 `demand_rate` 推導，不寫死；config 改了會自動跟著變。

> **定存與活存是兩個獨立的 pot。** 開立時 principal 從活存 `balance` 扣除；在定存進行期間，**剩餘的活存現金仍持續以 demand rate 累息**。因此 `fd_close` 時，系統會**先把剩餘活存餘額累息到當下**，再把 FD payout 加上去。FD 本身的報酬不受影響（到期用契約利率、提前用 penalty 利率）。

### 4.4 貸款（Loan）

- 會員最多可借 **5,000** play currency。
- 利息以未清本金 **每分鐘 3%** 複利。
- **單一未清貸款**：已有 `debt > 0` 時不得再借。
- **允許部分還款（partial repay）**：還款時先把 debt 累算到當下應償金額（`loan_owed`），再扣掉還款額（下限為 0）；還款從 `balance` 支付，餘額不足則擋下。全部還清後 `loan_taken_at` 設回 null。

### 4.5 紓困（Relief）

- 在櫃檯由行員發放，金額固定（500），**每位會員限領一次**；重複領取拋 `ValueError`。

### 4.6 訪問冷卻（Visit Cooldown）

採 **lookup-gated** 設計：行員對某會員做一次 lookup = 該會員的一次 visit，**該次 visit 內可做任意多筆操作**（存提、貸款、定存等），不會互相卡住。若距上次 lookup 同一會員未滿 **5 分鐘**，再次 lookup 會被鎖定，回傳 locked 狀態與剩餘秒數倒數，行員需等冷卻結束才能再次查詢該會員。

---

## 5. 股票市場（Stock Market）

### 5.1 概觀

共 **5 檔**上市公司，於 config 設定。價格在每筆交易時即時更新，並由背景 ticker 持續推進。一律整股，無碎股。

| stock_id | 名稱 | init_price | floor | ceiling | nominal_supply | s0 |
|---|---|---|---|---|---|---|
| TECH | TechCo | 100 | 30 | 300 | 10000 | 3000 |
| BANK | BankCorp | 80 | 24 | 240 | 10000 | 3000 |
| ENGY | EnergyX | 120 | 36 | 360 | 10000 | 3000 |
| FOOD | FoodInc | 50 | 15 | 150 | 10000 | 3000 |
| MEDIA | MediaPlus | 150 | 45 | 450 | 10000 | 3000 |

### 5.2 價格模型（market-maker random walk）

每檔股票的價格由一個 **market-maker random walk** 推動。每次 `next_price` 計算如下：

```
trade_impact    = β × signed_shares / depth
momentum        = μ × net_flow
supply_pressure = −γ × (total_supply_held − s0) / nominal_supply
event_drift     = Σ 進行中 events 的每 tick 分量
noise           = U(−σ, +σ)

p_new = p_old × (1 + trade_impact + momentum + supply_pressure + event_drift + noise)
```

各分量意義：

- **`signed_shares`** —— 買為 +n、賣為 −n、純 tick 為 0。
- **`net_flow`** —— **衰減型 momentum**：每次計算先以 `net_flow_decay` 衰減，再累加當下的 `signed_shares`。代表近期買賣的方向慣性。
- **`total_supply_held`** —— 全體會員此檔的總持股（絕對量），用於**抗通膨的均值回歸**：持股偏離 `s0` 越多，`supply_pressure` 把價格往回拉得越多，藉此平衡整體流通的錢量。
- **`noise`** —— 由呼叫端預先抽樣注入（`next_price` 內部不呼叫 random），方便測試以 `noise=0` 做 deterministic 驗證。

### 5.3 Clamp 次序與季度 band

夾擠（clamp）的**次序很重要**：

1. **organic move** 先夾在當季的 **±30% band**：`[quarter_open × (1 + band_floor_pct), quarter_open × (1 + band_ceiling_pct)]`。
2. **event_drift** 在 band clamp **之後**才套用（`final = organic × (1 + event_drift)`）—— 因此**事件可突破 band**。
3. **band ratchet**：若突破上界，`band_ceiling_pct = 突破後價格百分比 + 事件百分比`；突破下界同理。例如季度開盤 100、事件把價格推到 135（+35%）、事件規模 +10% → 新上界 +45%，band 變 `[70, 145]`。
4. **絕對 floor/ceiling** 最後**永遠**夾一次（無論如何價格不得離開 `[floor, ceiling]`）。

季度 band 每 **30 分鐘** reset 回 ±30%（以當下價格為新的 `quarter_open`）。reset 只在跨季時發生，第 0 季沿用 seed 時的 init price 為錨。

### 5.4 Tuning 參數

per-event 的調校參數（config `[tuning]`，執行期不經 UI 編輯）：

| 參數 | 值 | 說明 |
|---|---|---|
| `beta` | 0.5 | trade_impact 係數 |
| `depth` | 500 | 市場深度（越大則單筆衝擊越小） |
| `mu` | 0.02 | momentum 係數 |
| `net_flow_decay` | 0.95 | net_flow 每 tick 衰減率 |
| `gamma` | 0.02 | supply_pressure 係數 |
| `sigma` | 0.005 | noise 振幅 |
| `tick_seconds` | 5 | 背景 ticker 間隔 |

### 5.5 更新時機

沒有批次結算。每筆 buy/sell 立即依模型重算並更新價格（買賣成本以**成交前價格**計算）。此外有一個 **5 秒 ticker**，每次推進所有股票價格、套用進行中的事件 drift、處理季度 reset。新價格透過 SSE 即時推給 Public Dashboard 與所有開啟的 Member Web App session。

> **開跑前市場凍結**：活動未開跑（`event_start_at` 未設）時，ticker **跳過**價格推進、買賣 route 回 409，價格維持在初始值不動（見 §3.1）。開跑後才開始上述演進。

> 已**移除**原規格的 `max_holding_ratio`（anti-whale 防巨鯨）限制 —— 不再對單一會員持股比例設限。

---

## 6. 事件引擎（Event Engine）

> 此節**取代**舊規格「news 僅供顯示、price 效果預先烘進參數、不在執行期動態連動」的設計。

- 在 config 硬編碼一份 event 清單，每筆含 `at_min`、`stock_id`、`pct`、`duration_min`、`headline`。
- 到時觸發：在 `duration_min` 期間以 **ramped** 方式套用價格效果 —— 每 tick 的 drift 設計成讓整段複利後 ≈ `pct`（`per_tick = (1 + pct) ^ (tick_min / duration_min) − 1`）。可選擇自動發布 `headline` 為一則 news。
- 事件的 drift 會 **bypass 季度 band 並 ratchet 之**（見 §5.3）。
- **手動 news 仍為 display-only**：行員可隨時發布一則文字新聞，只顯示在看板上，**不影響價格**。

事件以**開跑時刻**（§3.1）為基準計時：`at_min` 是相對開跑後的分鐘數，elapsed 達到 `at_min` 時觸發一次（`fired` 旗標持久化，每個 DB 只觸發一次）。開跑前 elapsed 視為 0，不會有事件觸發。

範例事件：`at_min=35`，ENGY，`pct=0.10`，`duration_min=5`，headline「Energy demand spikes — EnergyX surges」。

---

## 7. 介面（Surfaces）

### 7.1 Teller Panel（行員）

櫃檯行員使用。能力：

- 以 ID 查詢會員（觸發一次 visit，含 cooldown gate；被鎖定時顯示倒數）。
- 檢視餘額、debt、進行中的定存、持股、紓困狀態。
- 處理：deposit、withdraw、開立／平倉定存、loan 撥款、loan 還款、relief。
- **代客下單** —— 為沒有手機的會員買賣股票（開跑後才可用）。
- 發布手動 news 到 Public Dashboard。
- **Start event** 按鈕 —— 活動開跑，設定 event clock（見 §3.1）；按鈕僅在尚未開跑時出現，開跑後顯示「running／elapsed」。
- **Export** 按鈕（見 §8）。

所有會變動狀態的操作都在全域 `MUTATION_LOCK` 下執行。

### 7.2 Member Web App（學員）

可在學員自己手機或共用裝置開啟的 web app。會員只輸入 **PIN** 登入。能力：

- **Portfolio** —— 餘額、各檔持股、進行中定存、debt。
- **股票交易** —— 買賣 5 檔任一；買單需現金足夠、賣單需持股足夠，否則擋下。無持股比例上限。**活動開跑前無法交易**（route 回 409）。
- **即時行情** —— 與 Public Dashboard 同源的即時價格與圖表；透過 SSE 推播，斷線自動重連。

> 透過 Member Web App 的交易會即時更新所有狀態（餘額、持股、價格），不需經過行員。

### 7.3 Public Stock Dashboard（共用螢幕）

唯讀、無需登入、自動更新。內容：

- 5 檔股票的即時價格折線圖（Chart.js）。
- 每檔 summary：現價、自開盤以來的 % change、累計成交量（volume）。
- **News banner** —— 顯示事件自動發布與行員手動發布的新聞。
- **活動狀態列** —— 開跑前顯示「尚未開始」，開跑後顯示「Live · elapsed N min」（讀 `/api/dashboard` 的 `started`／`elapsed_min`）。因開跑前無 SSE 價格推播，看板另以約 15 秒輪詢 `/api/dashboard` 來反映開跑的狀態切換。
- 透過 SSE 接收即時價格與新聞，`EventSource` 斷線自動重連。

---

## 8. 匯出（Export）

Teller Panel 提供 **Export** 按鈕，活動期間或結束後皆可使用，產生一份 CSV，並排比較每組所有會員的總金額。

### 8.1 「amount」定義

某會員匯出的 `amount` 為匯出當下的**淨值（net worth）**，四捨五入為整數：

```
amount = balance
       + Σ 所有定存以契約利率計的到期 payout（匯出時全部已到期，見 §4.3）
       + 所有持股市值（shares × current price）
       − loan_owed(debt, 自貸款起的 elapsed_minutes)
```

### 8.2 CSV 版面

group **橫向跨欄**（每組一對 `member, amount`，10 組 = 20 欄）；member **縱向跨列**（index 1–12），底部加一列 `sum`。

```csv
member,amount,member,amount,...,member,amount
0-1,123,1-1,456,...,9-1,789
0-2,111,1-2,222,...,9-2,333
...
0-12,123,1-12,456,...,9-12,789
sum,1234,sum,5678,...,sum,9012
```

- **欄** —— 共 20 欄：group 0 到 9 依序各一對 `member`、`amount`。
- **列** —— 12 筆資料列（member index 1–12）後接一列 `sum`。
- `sum` 列為該組 12 位會員 `amount` 的總和。
- header 為字面的 `member`、`amount`（重複），組別由位置隱含。
- 所有 `amount` 為整數（round-to-nearest）。
- 編碼 UTF-8，line ending 為 LF。

### 8.3 觸發與存取

- 只在 Teller Panel 可用（Member Web App 不行）。
- 直接下載 `.csv`，無需預覽。
- 可多次觸發，每次反映當下的即時狀態。

---

## 9. 部署（Deployment）

- **Docker Compose** 兩個 service：`app`（FastAPI / uvicorn）與 `caddy`（auto-HTTPS、reverse proxy、static 前端）。
- Caddy 對 `/api/*` reverse_proxy 到 `app:8000`；對 `/api/stream`（SSE）設 `flush_interval -1` 避免緩衝；其餘走 static file server 提供 `frontend/`。
- 自架 VM，DNS A record 指向該機；Caddy 依 `$DOMAIN` 自動申請憑證。
- **config-driven**：stocks／events／tuning 全在 `config/config.toml`；PIN 預先產生於 `config/pins.csv`（gitignored，機密，需另行複製到 VM）。
- 環境變數：`DOMAIN`、`STAFF_PASSWORD`、`SECRET_KEY`；DB 路徑 `DB_PATH`（預設 `/data/paper.db`，以 volume 持久化）。
- **provision 是獨立一步**（app 開機不再 seed，見 §3.1）：build 後、`up` 前先跑一次性指令把 `/data` volume 的 DB 建好：`docker compose run --rm app python scripts/setup_db.py --reset --force`。之後 `docker compose up -d`；活動開跑時於 Teller Panel 按 **Start event**。

---

## 10. 業務規則彙總

| 規則 | 值 |
|---|---|
| 活存利率 | 0.5% / min，複利 `(1.005)^t` |
| 定存利率（30 min） | 1% / min，複利 `(1.01)^t` |
| 定存利率（60 min） | 2% / min，複利 `(1.02)^t` |
| 定存提前解約利率 | `0.8 × demand_rate` / min（目前 0.4%），複利 |
| 貸款利率 | 3% / min，複利 `(1.03)^t` |
| 貸款上限 | 5,000（play currency），單一未清、可部分還款 |
| 紓困 | 每會員一次性，500 |
| 訪問冷卻 | 5 分鐘（lookup-gated） |
| 股價 organic 季度 band | ±30% / 季（約 30 min），事件可突破並 ratchet |
| 股數單位 | 整數，無碎股 |
| 上市公司數 | 5 |
| 起始餘額 | 1,000 |

---

## 11. 不在範圍內（Out of Scope）

- 真實金流或金流處理。
- 活動 120 分鐘以外的長期資料保存（不過 event clock 存於 SQLite，process 重啟可續跑）。
- 原生 mobile app（web 已足夠涵蓋所有 surface）。
- 偽鈔／作弊自動偵測。

> 原規格列為 out of scope 的「執行期 news 動態連動價格」現已由 §6 的 event engine 實作；唯**手動 news 不影響價格**這點仍維持。
