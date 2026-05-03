import pandas as pd
from crawler.crawler_etf import crawler_twse_etf_task  # 引用你寫好的任務函式

def run_producer():
    # 1. 設定你想抓取的時間區間
    # 這裡可以根據你的專題需求調整
    start_date = "2026-01-01"
    end_date = "2026-04-23"

    # 2. 產生日期清單
    # freq='B' 代表 Business days (週一至週五)，自動過濾週末
    date_list = pd.date_range(start=start_date, end=end_date, freq='B').strftime("%Y%m%d")

    print(f"🚀 開始派送任務：從 {start_date} 到 {end_date}")
    print(f"📊 總計派送任務數：{len(date_list)} 天")

    # 3. 循序派送任務到 RabbitMQ
    for d in date_list:
        print(f"📅 正在派送日期：{d}", end="...")
        
        # 使用 .delay() 將日期字串傳給 Worker
        # 這會把任務丟進 RabbitMQ 後立刻繼續下一個循環，不會等待抓取完成
        crawler_twse_etf_task.delay(date_str=d)
        
        print(" [已發送]")

if __name__ == "__main__":
    run_producer()
    print("\n✅ 所有任務派送完畢！請至 Worker 視窗查看執行進度。")