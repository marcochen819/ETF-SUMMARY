#第一階段：Linux 基礎與環境切換
在開始之前，確保你的身份是一般使用者而非 root，以降低誤刪系統文件的風險。  

1. 切換一般使用者 (Windows PowerShell 執行)
若 VSCode 終端機顯示為 root，請開啟 Windows PowerShell 輸入：

設定預設用戶：ubuntu2204.exe config --default-user 你的用戶名
查詢目前身份：ubuntu2204.exe run whoami

2. Linux 常用指令 (VSCode 終端機執行)
切換目錄：cd 資料夾名稱
回上一層：cd ..
新增資料夾：mkdir 資料夾名稱
列出檔案：ls
用 VSCode 打開當前目錄：code .

  
#第二階段：Docker 部署與管理
Docker 解決了「在我的電腦可以跑，別人的不行」的環境一致性問題。  

1. 基礎概念
Image (映像檔)：如同安裝光碟，包含執行程式所需的所有環境（如 MySQL, Python）。  
Container (容器)：根據 Image 建立出的獨立執行環境。  
Volume (資料卷)：將容器內部空間與主機硬碟連結，確保資料永久保存。  

2. Docker 實戰指令
查看執行中的容器：docker ps
查看所有容器 (含已停止)：docker ps -a
查看容器 Log (除錯用)：docker logs 容器名稱
一鍵啟動服務：docker compose -f 檔案名稱.yml up -d
關閉並移除服務：docker compose -f 檔案名稱.yml down
建立虛擬內網：docker network create my_network


#第三階段：Python 環境管理 (使用 uv)
uv 是由 Rust 編寫的現代化工具，比傳統 pip 快 10–100 倍，能一站式管理環境與套件。  

1. uv 安裝與初始化
安裝 uv：curl -LsSf [https://astral.sh/uv/install.sh](https://astral.sh/uv/install.sh) | sh
安裝指定版本 Python：uv python install 3.11
初始化專案：uv init
此指令會生成 pyproject.toml（記錄套件）、.python-version（記錄版本）與 README.md 等核心檔案。  

2. 套件安裝與同步
建立虛擬環境：uv venv --python=3.11
新增套件 (如 Flask)：uv add flask==3.1.0
一鍵同步團隊環境：uv sync
當你 git clone 別人的專案後，只需輸入 uv sync 即可自動安裝所有符合版本的套件。  

🚀 第四階段：分散式爬蟲架構 (Celery + RabbitMQ)
當爬蟲資料量大（如 2000 支股票）時，單機順序執行太慢，需使用分散式架構提升效率。  

1. 角色分配
Producer (主管)：發送任務到訊息中心。  
RabbitMQ (訊息中心/Broker)：暫存任務的候位區。  
Worker (工人)：從訊息中心領取並執行任務。  
Flower (監控)：網頁介面監控所有工人狀態。  

2. 執行指令
發送任務：uv run python crawler/producer.py
啟動工人：uv run celery -A crawler.worker worker --loglevel=info
啟動多個工人 (提速)：開啟多個終端機並指定名稱 -n worker1, -n worker2。
