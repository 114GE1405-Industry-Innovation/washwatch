# washwatch

簡易宿舍洗衣機看板

| 資料夾 | 是什麼 |
|---|---|
| `v0-toy/` | 只有畫面 + 假資料 |
| `v1-direct/` | 瀏覽器直接去抓真的資料 |
| `v2-api/` | query 我們自己的 API server |
| `server/app.py` | 我們的 API server（FastAPI） |
| `server/wipepay.py` | 助教給的程式，負責抓洗衣機狀態。當黑盒子用就好 |

## 課前準備（Setup）

需要：**Python 3.10 以上**、**Chrome**（會用 DevTools）、VS Code。

### 1. 下載

GitHub 頁面右上角綠色 **Code** → **Download ZIP** → 解壓縮，用 VS Code 打開這個資料夾。

### 2. 建立虛擬環境

在 VS Code 開 Terminal（終端機），確認位置在 `washwatch` 資料夾裡：

```bash
# Windows
python -m venv venv
.\venv\Scripts\activate.bat

# macOS
python3 -m venv venv
source ./venv/bin/activate
```

成功的話，命令列最前面會出現 `(venv)`。

> Important: 每次重新打開 Terminal 都要再 activate 一次。

### 3. 安裝套件

```bash
pip install -r requirements.txt
```

### 4. 確認能跑

```bash
cd server
python app.py
```

看到 `Uvicorn running on http://127.0.0.1:3000` 就成功了。用瀏覽器打開 <http://localhost:3000/docs>，看看是否能跑出畫面。

按 `Ctrl + C` 可以停止 server。

## 怎麼用

| 想看 | 怎麼做 |
|---|---|
| v0、v1 | 直接用 Chrome 打開 `v0-toy/index.html`、`v1-direct/index.html` |
| v2 | **先**跑起 `server/app.py`，再用 Chrome 打開 `v2-api/index.html` |
| API 文件 | server 跑起來後打開 <http://localhost:3000/docs> |

## 常見問題

- **`python` 找不到** → macOS 請用 `python3`；Windows 安裝 Python 時要勾 *Add python.exe to PATH*。
- **`address already in use`** → 3000 port 被別的程式佔走了，先關掉另一個還在跑的 `app.py`。
- **v2 顯示 `Can't reach http://localhost:3000`** → server 沒開，回到第 4 步。
