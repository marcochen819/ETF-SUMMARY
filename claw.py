import urllib.request as req
import pandas as pd
import time
import json
import random

def get_twse_etf_data(date_str):
    # 設定目標 URL，抓取證交所「三大法人買賣超日報 (ETF)」的 JSON 資料
    url = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={date_str}&selectType=0099P"
    try:
        resp = req.urlopen(url)
        data = json.loads(resp.read().decode('utf-8'))

        # 判斷證交所回傳狀態，若為 "OK" 代表該日期有交易資料
        if data.get("stat") == "OK":
            # 將原始資料轉換為 Pandas 表格，並指定欄位名稱
            df = pd.DataFrame(data["data"], columns=data["fields"])

            # 僅篩選出重點欄位：代號、名稱及各法人買賣股數
            selected_cols = ["證券代號", "證券名稱", "外陸資買賣超股數(不含外資自營商)",
                             "投信買賣超股數", "自營商買賣超股數", "三大法人買賣超股數"]
            df = df[selected_cols]

            # 在最左側插入「日期」欄位，方便後續合併後的區分
            df.insert(0, '日期', date_str)
            return df
    except Exception as e:
        print(f"日期 {date_str} 抓取異常: {e}")
    return None

# 設定抓取的時間區間 (freq='B' 代表僅包含周一至周五的工作日)
start_date = "2026-01-01"
end_date = "2026-04-23"
date_list = pd.date_range(start=start_date, end=end_date, freq='B').strftime("%Y%m%d")

all_dfs = []

# 開始逐日循環抓取
for d in date_list:
    success = False
    # 建立重試機制：若遇網路不穩或 API 暫時沒反應，最多嘗試 3 次
    for attempt in range(3):
        print(f"正在抓取 {d} (嘗試 {attempt + 1})...", end=" ")
        res = get_twse_etf_data(d)

        if res is not None:
            all_dfs.append(res)
            print("✅ 成功")
            success = True
            break # 成功抓取則跳出重試迴圈，進入下一個日期
        else:
            if attempt < 2:
                print("❌ 無資料或超時，等待重試...")
                time.sleep(5) # 失敗時固定停 5 秒再試
            else:
                print("❌ 確定無資料 (休市或達上限)")

    # 隨機休止機制：避免抓取頻率過快導致 IP 被封鎖
    time.sleep(random.uniform(3, 7))

# 資料彙整與輸出
if all_dfs:
    # 將所有日期的 DataFrame 合併成一張大表
    final_result = pd.concat(all_dfs, ignore_index=True)
    # 儲存為 CSV
    final_result.to_csv("ETF_Summary.csv", encoding="utf-8-sig", index=False)
    print("\n任務完成！檔案已儲存。")
else:
    print("\n沒有抓到任何資料。")
