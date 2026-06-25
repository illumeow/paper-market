# Glossary

paper-market 文件中保留為英文的技術詞彙（zhen 風格）。一行一詞：`EN — 中文說明`。

play currency — 活動中使用的假錢
surface — 系統對外的介面（Teller Panel／Member Web App／Public Stock Dashboard）
Teller Panel — 行員操作的後台介面
Member Web App — 學員端的網頁 app
Public Stock Dashboard — 共用螢幕上的唯讀行情看板
FastAPI — 後端 web framework
uvicorn — ASGI server
SQLite — 內嵌式資料庫
WAL — SQLite 的 write-ahead logging mode
SSE — Server-Sent Events，伺服器即時推播
ticker — 背景定時迴圈（每 tick_seconds 推進價格）
Docker Compose — 多容器編排
Caddy — 反向代理 + auto-HTTPS 的 web server
auto-HTTPS — Caddy 自動申請與更新 TLS 憑證
PIN — 會員 4 位數登入碼
member_id — 會員識別碼，格式 {group}-{index}
sha256 — PIN 的雜湊演算法
signed-cookie — 簽章的 session cookie
session — 登入狀態
itsdangerous — 產生／驗證 signed token 的函式庫
rate limit — 登入頻率限制
role gate — 角色權限閘
seed — 初始化資料（會員、股票、事件）
lazy accrual — 在存取時才依 timestamp 結算利息
Decimal — 高精度金額運算型別
balance — 活存現金餘額
deposit — 存款
withdraw — 提款
demand deposit — 活存
fixed deposit — 定存
maturity — 定存到期
payout — 定存／交易結算金額
early exit — 定存提前解約
penalty rate — 提前解約的懲罰利率
pot — 一筆獨立的資金（活存 vs 定存）
loan — 貸款
debt — 未清本金
partial repay — 部分還款
relief — 一次性紓困
lookup-gated — 以行員查詢為單位的冷卻機制
visit — 一次行員 lookup 所構成的訪問
cooldown — 冷卻時間
market-maker — 造市者價格模型
random walk — 隨機漫步
next_price — 計算下一個價格的函式
trade_impact — 交易對價格的衝擊分量
momentum — 動能分量（衰減型 net_flow）
supply_pressure — 供給壓力（抗通膨均值回歸）
event_drift — 事件造成的每 tick 漂移
noise — 隨機雜訊分量
signed_shares — 帶正負號的成交股數（買 +、賣 −）
net_flow — 衰減型的買賣淨流向
net_flow_decay — net_flow 的每 tick 衰減率
total_supply_held — 全體會員的總持股
s0 — 供給壓力的均衡持股基準
quarter_open — 每季開盤價，band 的錨點
band — 季度漲跌幅區間（±30%）
ratchet — 事件突破 band 後把界線推開
floor / ceiling — 絕對價格上下限
clamp — 夾擠到界線內
tuning — price model 的調校參數
MUTATION_LOCK — 包住所有 mutating 操作的全域 async lock
Portfolio — 會員的持倉與帳戶總覽
Chart.js — 前端繪圖函式庫
EventSource — 瀏覽器端接收 SSE 的 API
News banner — 看板上的新聞欄
volume — 累計成交量
net worth — 淨值
amount — 匯出時每位會員的淨值
loan_owed — 計算貸款當前應償金額的函式
CSV — 逗號分隔值匯出格式
LF — line feed 換行（非 CRLF）
reverse proxy — 反向代理
flush_interval — Caddy 對 SSE 不緩衝的設定（-1）
config-driven — 以 config.toml 驅動 stocks／events／tuning
DOMAIN / STAFF_PASSWORD / SECRET_KEY — 部署所需環境變數
DB_PATH — SQLite 檔路徑
provision — 賽前一次性建立 DB 資料（members/stocks/events），不設時鐘
setup_db.py — provision/reset 的 CLI 腳本
runtime — 執行期（app 開機後的常態運作）
resume — 重啟後接續既有狀態（不重置）
lifespan — FastAPI 的啟動／關閉生命週期 hook
kickoff — 活動正式開跑（設定 event clock 的時刻）
Start event — Teller Panel 上觸發開跑的按鈕
event_start_at — 活動起始時間（meta 中的鍵）
started — dashboard 回傳的「是否已開跑」旗標
elapsed_min — 自開跑起經過的分鐘數
fired — 事件是否已觸發過的持久化旗標
