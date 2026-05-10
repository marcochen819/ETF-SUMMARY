## 學習順序建議

如果你是第一次接觸這個專案，建議依序閱讀：

1. `config.py` — 了解環境變數怎麼管理
2. `worker.py` + `tasks.py` — 認識 Celery task 最小範例
3. `producer.py` — 派送第一個任務，親手跑一次
4. `tasks_crawler_finmind.py` — 看真實的爬蟲邏輯
5. `producer_multi_queue.py` — 學習如何分流任務
6. `scheduler.py` — 最後把一切串起來，自動化執行

## Docker Compose 檔案說明

專案根目錄有很多 `.yml`，這些是 Docker Compose 設定檔，用來一鍵啟動各種服務。初看會眼花，這裡幫你分類：

### 基礎設施（要先啟動）

| 檔案 | 啟動什麼 | 說明 |
| --- | --- | --- |
| `rabbitmq.yml` | RabbitMQ + Flower | 本地開發用，使用 `dev` 網路。Flower 是 Celery 的監控 Web UI（port 5555） |
| `rabbitmq-network.yml` | RabbitMQ + Flower | 正式環境版本，使用外部 `my_network` 網路，讓多個 compose 檔能共用網路 |
| `mysql.yml` | MySQL 8.0 + phpMyAdmin | MySQL 在 3306，phpMyAdmin 在 8000（瀏覽器可視化管理 DB） |

### Worker（消費者，執行爬蟲）

| 檔案 | 說明 |
| --- | --- |
| `docker-compose-worker.yml` | 單一 worker，使用 `dev` 網路，最簡單的版本 |
| `docker-compose-worker-network.yml` | 起兩個 worker（twse、tpex），各自監聽不同 queue，使用 `my_network` |
| `docker-compose-worker-network-version.yml` | 同上，但 image 版本可用 `DOCKER_IMAGE_VERSION` 環境變數指定，方便切換版本 |

### Producer（生產者，派送任務）

| 檔案 | 說明 |
| --- | --- |
| `docker-compose-producer-network.yml` | 執行 `producer_multi_queue.py`，一次性派送任務到 twse/tpex queue |
| `docker-compose-producer-network-version.yml` | 同上，image 版本可透過環境變數指定 |
| `docker-compose-producer-duplicate-network-version.yml` | 執行去重複版本的 producer |

### Scheduler（排程器）

| 檔案 | 說明 |
| --- | --- |
| `docker-compose-scheduler-network-version.yml` | 啟動 `scheduler.py`，按照排程自動派送任務 |

### 命名規則小抄

檔名看起來很長，其實有規則：
- **`-network`**：使用外部 `my_network`（需要先 `docker network create my_network`），讓不同 compose 檔之間能互通
- **沒 `-network`**：使用 compose 檔自己建立的 `dev` 網路，獨立不互通
- **`-version`**：image 版本改用 `${DOCKER_IMAGE_VERSION}` 變數，啟動時要搭配 `DOCKER_IMAGE_VERSION=0.0.6 docker compose up -d`
- **`-duplicate`**：使用 on_duplicate_key_update 版本的 task

### 典型啟動順序

```bash
# 1. 建立共用網路（只要做一次）
docker network create my_network

# 2. 啟動基礎設施
docker compose -f rabbitmq-network.yml up -d
docker compose -f mysql.yml up -d

# 3. 啟動 workers
DOCKER_IMAGE_VERSION=0.0.6 docker compose -f docker-compose-worker-network-version.yml up -d

# 4. 啟動 scheduler（自動派送任務）
DOCKER_IMAGE_VERSION=0.0.6 docker compose -f docker-compose-scheduler-network-version.yml up -d

# 5. 打開 http://localhost:5555 看 Flower 監控 worker 狀態
# 6. 打開 http://localhost:8000 用 phpMyAdmin 看 MySQL 資料
```

## Dockerfile 說明

專案有三個 Dockerfile，長得很像，差別在於「是否在 build 時產生 `.env`」：

| 檔案 | 用途 | 差別 |
| --- | --- | --- |
| `Dockerfile` | 最基本版本 | 複製整個專案進去，不產生 `.env`（環境變數需執行時給） |
| `with.env.Dockerfile` | 開發/測試用 | build 時跑 `ENV=DOCKER genenv.py` 產生 `.env`（適合 docker 內跑） |
| `prod.with.env.Dockerfile` | 正式環境用 | build 時跑 `ENV=PRODUCTION genenv.py` 產生 `.env`（使用正式環境的 host、帳密） |

### Dockerfile 內部做了什麼？

以 `Dockerfile` 為例，流程大致是：

```
FROM ubuntu:22.04               ← 從乾淨的 Ubuntu 開始
→ 安裝 curl、ca-certificates    ← 下載 uv 需要的工具
→ 安裝 uv                       ← Python 套件管理工具
→ 安裝 Python 3.11              ← 指定 Python 版本
→ COPY 專案檔案進容器
→ uv sync --frozen              ← 根據 uv.lock 安裝所有套件（確保版本一致）
→ 設定 UTF-8 語系              ← 避免中文編碼問題
→ CMD bash                      ← 預設進入 bash
```

**為什麼要 `uv sync --frozen`？**
`--frozen` 會嚴格按照 `uv.lock` 的版本安裝，不會自己去解析最新版。這樣才能保證「開發機」跟「正式機」裝到的是一模一樣的套件版本，避免「我這裡跑得好好的」這種問題。

**為什麼開發和正式要分開 Dockerfile？**
因為不同環境的資料庫 host、帳密都不同。`genenv.py` 會根據 `ENV` 變數從 `local.ini` 讀對應區段，產生正確的 `.env`。

## .gitignore 說明

`.gitignore` 列出「不要被 git 追蹤的檔案/資料夾」，避免意外把敏感資料或垃圾檔案推上 GitHub。

| 項目 | 為什麼要忽略 |
| --- | --- |
| `*__pycache__/`、`*.pyc` | Python 編譯產生的暫存檔，換台電腦重新產生就好 |
| `.vscode/`、`*.vscode` | 編輯器個人設定，每個人習慣不同 |
| `*.pytest_cache/` | pytest 的快取 |
| `.env` | **最重要！** 裡面有資料庫帳密、API key，絕不能進 git |
| `*.egg-info`、`build/` | Python 打包產生的檔案 |
| `.cache` | 各種工具的暫存 |

**新手常見錯誤**：把 `.env` 推上 public repo，幾分鐘內密碼就會被掃到外洩。養成習慣：加 `.env` 進 `.gitignore` **永遠是第一步**。


# 環境設定

#### 安裝 uv

    curl -LsSf https://astral.sh/uv/install.sh | sh

#### 安裝 Python 3.11

    uv python install 3.11

#### set uv 虛擬環境

    uv venv --python 3.11

#### 安裝 repo 套件

    uv sync

#### 建立環境變數

    ENV=DEV python genenv.py
    ENV=DOCKER python genenv.py
    ENV=PRODUCTION python genenv.py

#### 排版

    black -l 80 crawler/

# Worker

#### 啟動預設執行 celery 的 queue 的工人

    uv run celery -A crawler.worker worker --loglevel=info
    uv run --env-file=.env celery -A crawler.worker worker --loglevel=info

#### 啟動執行 twse 的 queue 的工人

    uv run celery -A crawler.worker worker -Q twse,tpex --loglevel=info
    uv run --env-file=.env celery -A crawler.worker worker -Q twse,tpex --loglevel=info

# Producer

#### 發送任務

    uv run python crawler/producer.py
    uv run --env-file=.env python crawler/producer.py

#### for loop 發送多個任務

    uv run python crawler/producer_crawler_finmind.py
    uv run --env-file=.env python crawler/producer_crawler_finmind.py

#### 發送任務到不同 queue

    uv run python crawler/producer_multi_queue.py
    uv run --env-file=.env python crawler/producer_multi_queue.py


# Docker

#### build docker image

    docker build -f Dockerfile -t linsamtw/tibame_crawler:0.0.1 .
    docker build -f Dockerfile -t linsamtw/tibame_crawler:0.0.2 .
    docker build -f with.env.Dockerfile -t linsamtw/tibame_crawler:0.0.3 .
    docker build -f with.env.Dockerfile -t linsamtw/tibame_crawler:0.0.4 .
    docker build -f with.env.Dockerfile -t linsamtw/tibame_crawler:0.0.5 .
    docker build -f with.env.Dockerfile -t linsamtw/tibame_crawler:0.0.6 .
    docker buildx build -f with.env.Dockerfile --platform linux/arm64 -t linsamtw/tibame_crawler:0.0.6.arm64 .
    docker build -f with.env.Dockerfile -t linsamtw/tibame_crawler:0.0.7 .
    docker build -f prod.with.env.Dockerfile -t linsamtw/tibame_crawler:0.0.8.composer .
    docker build -f with.env.Dockerfile -t linsamtw/tibame_crawler:0.0.9 .

#### push docker image

    docker push linsamtw/tibame_crawler:0.0.1
    docker push linsamtw/tibame_crawler:0.0.2
    docker push linsamtw/tibame_crawler:0.0.3
    docker push linsamtw/tibame_crawler:0.0.4
    docker push linsamtw/tibame_crawler:0.0.5
    docker push linsamtw/tibame_crawler:0.0.6
    docker push linsamtw/tibame_crawler:0.0.6.arm64
    docker push linsamtw/tibame_crawler:0.0.7
    docker push linsamtw/tibame_crawler:0.0.8.composer
    docker push linsamtw/tibame_crawler:0.0.9

#### 建立 network

    docker network create my_network

#### 啟動 rabbitmq

    docker compose -f rabbitmq-network.yml up -d

#### 關閉 rabbitmq

    docker compose -f rabbitmq-network.yml down

#### 啟動 mysql

    docker compose -f mysql.yml up -d

#### 關閉 mysql

    docker compose -f mysql.yml down

#### 啟動 worker

    docker compose -f docker-compose-worker-network.yml up -d
    DOCKER_IMAGE_VERSION=0.0.3 docker compose -f docker-compose-worker-network-version.yml up -d
    DOCKER_IMAGE_VERSION=0.0.5 docker compose -f docker-compose-worker-network-version.yml up -d
    DOCKER_IMAGE_VERSION=0.0.6 docker compose -f docker-compose-worker-network-version.yml up -d

#### 關閉 worker

    docker compose -f docker-compose-worker-network.yml down
    DOCKER_IMAGE_VERSION=0.0.3 docker compose -f docker-compose-worker-network-version.yml down
    DOCKER_IMAGE_VERSION=0.0.5 docker compose -f docker-compose-worker-network-version.yml down
    DOCKER_IMAGE_VERSION=0.0.6 docker compose -f docker-compose-worker-network-version.yml down

#### producer 發送任務

    docker compose -f docker-compose-producer-network.yml up -d
    DOCKER_IMAGE_VERSION=0.0.3 docker compose -f docker-compose-producer-network-version.yml up -d
    DOCKER_IMAGE_VERSION=0.0.5 docker compose -f docker-compose-producer-network-version.yml up -d
    DOCKER_IMAGE_VERSION=0.0.6 docker compose -f docker-compose-producer-duplicate-network-version.yml up -d

#### 查看 docker container 狀況

    docker ps -a

#### 查看 log

    docker logs container_name

#### 啟動 scheduler

    DOCKER_IMAGE_VERSION=0.0.4 docker compose -f docker-compose-scheduler-network-version.yml up -d

#### 關閉 scheduler

    DOCKER_IMAGE_VERSION=0.0.4 docker compose -f docker-compose-scheduler-network-version.yml down

#### 下載 taiwan_stock_price.csv

    wget https://github.com/FinMind/FinMindBook/releases/download/data/taiwan_stock_price.csv

#### 上傳 taiwan_stock_price.csv

    uv run python crawler/upload_taiwan_stock_price_to_mysql.py

#### login
    gcloud auth application-default login

#### set GCP project
    gcloud config set project high-transit-465916-a6

#### 上傳台股股價到 BigQuery
    uv run --env-file=.env python crawler/upload_taiwan_stock_price_to_bigquery.py

#### 輸入 Secret Manager
    uv run --env-file=.env python crawler/print_secret_manager.py