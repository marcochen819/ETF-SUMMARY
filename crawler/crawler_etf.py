import urllib.request as req
import pandas as pd
import json
import time
import random
from sqlalchemy import create_engine

# 這裡的引用路徑必須包含 crawler 資料夾名稱
from crawler.config import MYSQL_ACCOUNT, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT
from crawler.worker import app

def upload_etf_to_mysql(df: pd.DataFrame):
    """將清理後的資料寫入 MySQL"""
    try:
        # 這裡手動加上資料庫名稱 tibame (請確認你的 MySQL 中有這個 database)
        address = f"mysql+pymysql://{MYSQL_ACCOUNT}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/tibame"
        engine = create_engine(address)
        
        # 寫入資料表，若表不存在會自動建立
        df.to_sql(
            "etf_institutional_investors", 
            con=engine, 
            if_exists="append", 
            index=False
        )
    except Exception as e:
        print(f"資料庫寫入失敗: {e}")

@app.task(bind=True, max_retries=3)
def crawler_twse_etf_task(self, date_str):
    """
    Celery Task: 抓取指定日期的 ETF 三大法人買賣超
    """
    # 證交所 API URL
    url = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={date_str}&selectType=0099P"
    
    try:
        # 模擬瀏覽器請求
        headers = {'User-Agent': 'Mozilla/5.0'}
        request = req.Request(url, headers=headers)
        
        with req.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))

        if data.get("stat") == "OK":
            df = pd.DataFrame(data["data"], columns=data["fields"])

            # 篩選專題所需的欄位
            selected_cols = ["證券代號", "證券名稱", "外陸資買賣超股數(不含外資自營商)",
                             "投信買賣超股數", "自營商買賣超股數", "三大法人買賣超股數"]
            df = df[selected_cols]
            
            # 插入日期欄位以便識別
            df.insert(0, '日期', date_str)
            
            # 資料清理：將含逗號的字串轉為數字
            for col in selected_cols[2:]:
                df[col] = df[col].astype(str).str.replace(',', '').astype(int)

            # 執行入庫
            upload_etf_to_mysql(df)
            
            # 隨機休眠 3-7 秒，保護 IP 不被封鎖
            time.sleep(random.uniform(3, 7))
            return f"{date_str} 抓取成功並已入庫"
        
        else:
            return f"{date_str} 證交所回傳無資料 (可能為休市日)"

    except Exception as exc:
        # 如果發生網路超時或 API 報錯，10 秒後自動重試，最多 3 次
        print(f"日期 {date_str} 抓取異常，準備重試: {exc}")
        raise self.retry(exc=exc, countdown=10)