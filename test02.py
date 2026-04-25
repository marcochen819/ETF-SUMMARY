import urllib.request as req
import pandas as pd
import time
import json
import random
from pathlib import Path
START_DATE = "2026-04-20"   # 開始日期
END_DATE   = "2026-04-21"   # 結束日期

# ============================================================
# 第一部分：爬蟲
# ============================================================

def get_twse_etf_data(date_str: str) -> pd.DataFrame | None:
    """
    爬取單日三大法人買賣超資料（來源：台灣證交所）
    只保留 ETF 相關欄位
    """
    url = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={date_str}&selectType=0099P"

    try:
        resp = req.urlopen(url, timeout=10)
        data = json.loads(resp.read().decode("utf-8"))

        if data.get("stat") == "OK":
            df = pd.DataFrame(data["data"], columns=data["fields"])

            # 只保留需要的欄位
            selected_cols = [
                "證券代號",
                "證券名稱",
                "外陸資買賣超股數(不含外資自營商)",
                "投信買賣超股數",
                "自營商買賣超股數",
                "三大法人買賣超股數"
            ]
            df = df[selected_cols]

            # 加入日期欄位
            df.insert(0, "日期", date_str)
            return df

    except Exception as e:
        print(f"日期 {date_str} 抓取異常: {e}")

    return None


def run_crawler(start_date: str, end_date: str) -> pd.DataFrame:
    """
    批次爬取日期區間資料
    自動跳過假日，有重試機制，隨機間隔防封鎖
    """
    # 產生工作日清單（週一～週五）
    date_list = pd.date_range(
        start=start_date, end=end_date, freq="B"
    ).strftime("%Y%m%d")

    all_dfs = []

    print(f"\n{'='*55}")
    print(f"  開始爬取：{start_date} → {end_date}")
    print(f"  共 {len(date_list)} 個工作日")
    print(f"{'='*55}\n")

    for d in date_list:
        success = False

        # 重試機制，最多嘗試 3 次
        for attempt in range(3):
            print(f"正在抓取 {d}（嘗試 {attempt + 1}）...", end=" ")
            res = get_twse_etf_data(d)

            if res is not None:
                all_dfs.append(res)
                print("成功")
                success = True
                break
            else:
                if attempt < 2:
                    print("❌ 無資料，等待重試...")
                    time.sleep(5)
                else:
                    print("❌ 確定無資料（休市或假日）")

        # 隨機停頓，避免被封鎖
        time.sleep(random.uniform(3, 7))

    # 合併所有資料
    if not all_dfs:
        print("\n⚠️  沒有抓到任何資料")
        return pd.DataFrame()

    result = pd.concat(all_dfs, ignore_index=True)

    # 儲存原始資料
    result.to_csv("ETF_Summary.csv", encoding="utf-8-sig", index=False)
    print(f"\n📁 原始資料已儲存：ETF_Summary.csv（共 {len(result)} 筆）")

    return result


# ============================================================
# 第二部分：數據清理
# ============================================================

def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    清洗三大法人原始資料
    步驟：
        1. 移除千分位逗號，轉為數值
        2. 統一日期格式
        3. 移除重複資料
        4. 填補空值為 0
        5. 過濾異常值（超過 4 個標準差）
        6. 新增計算欄位
    """
    if df.empty:
        print("⚠️  輸入資料為空，跳過清洗")
        return df

    df = df.copy()

    print(f"\n{'='*55}")
    print(f"  開始清洗資料（原始：{len(df)} 筆）")
    print(f"{'='*55}")

    # ── 1. 移除千分位逗號，轉為數值 ─────────────────────
    numeric_cols = [
        "外陸資買賣超股數(不含外資自營商)",
        "投信買賣超股數",
        "自營商買賣超股數",
        "三大法人買賣超股數"
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = (
                df[col].astype(str)
                       .str.replace(",", "", regex=False)
                       .str.replace(" ", "", regex=False)
                       .str.strip()
            )
            df[col] = pd.to_numeric(df[col], errors="coerce")

    print("✅ 步驟1：千分位逗號移除，轉為數值完成")

    # ── 2. 統一日期格式 ──────────────────────────────────
    df["日期"] = pd.to_datetime(df["日期"], format="%Y%m%d", errors="coerce")
    print("✅ 步驟2：日期格式統一完成")

    # ── 3. 移除重複資料 ──────────────────────────────────
    before = len(df)
    df = df.drop_duplicates(subset=["日期", "證券代號"])
    removed = before - len(df)
    if removed > 0:
        print(f"✅ 步驟3：移除重複資料 {removed} 筆")
    else:
        print("✅ 步驟3：無重複資料")

    # ── 4. 填補空值為 0 ──────────────────────────────────
    null_count = df[numeric_cols].isnull().sum().sum()
    df[numeric_cols] = df[numeric_cols].fillna(0)
    print(f"✅ 步驟4：填補空值 {null_count} 筆（補 0）")

    # ── 5. 過濾異常值（超過 4 個標準差）─────────────────
    col = "三大法人買賣超股數"
    if col in df.columns and len(df) > 10:
        mean = df[col].mean()
        std  = df[col].std()
        before = len(df)
        df = df[abs(df[col] - mean) <= 4 * std].copy()
        removed = before - len(df)
        print(f"✅ 步驟5：過濾異常值 {removed} 筆（超過 4σ）")
    else:
        print("✅ 步驟5：資料量不足，跳過異常值過濾")

    # ── 6. 新增計算欄位 ──────────────────────────────────
    df = df.sort_values(["證券代號", "日期"]).reset_index(drop=True)

    # 各法人 5 日移動平均
    for col in numeric_cols:
        if col in df.columns:
            df[f"{col}_5日均"] = (
                df.groupby("證券代號")[col]
                  .transform(lambda x: x.rolling(5, min_periods=1).mean())
                  .round(0)
            )

    # 三大法人連續買超/賣超天數
    def calc_streak(series):
        result = []
        count = 0
        for val in series:
            if val > 0:
                count = count + 1 if count > 0 else 1
            elif val < 0:
                count = count - 1 if count < 0 else -1
            else:
                count = 0
            result.append(count)
        return result

    df["連續買賣超天數"] = (
        df.groupby("證券代號")["三大法人買賣超股數"]
          .transform(calc_streak)
    )

    print("✅ 步驟6：新增 5日均、連續買賣超天數欄位")
    print(f"\n🎉 清洗完成！最終資料：{len(df)} 筆")

    return df


# ============================================================
# 第三部分：資料驗證
# ============================================================

def validate_data(df: pd.DataFrame) -> str:
    """
    驗證清洗後資料品質
    檢查：空值、日期缺口、重複資料、數值合理性、ETF 覆蓋率
    回傳：驗證報告字串
    """
    report_lines = []
    report_lines.append("=" * 55)
    report_lines.append("  資料驗證報告")
    report_lines.append(f"  總筆數：{len(df)}")
    report_lines.append("=" * 55)

    issues = []

    # 1. 空值檢查
    null_counts = df.isnull().sum()
    null_cols   = null_counts[null_counts > 0]
    if null_cols.empty:
        report_lines.append("✅ 空值檢查：無空值")
    else:
        for col, cnt in null_cols.items():
            pct = cnt / len(df) * 100
            msg = f"⚠️  [{col}] 有 {cnt} 筆空值（{pct:.1f}%）"
            report_lines.append(msg)
            issues.append(msg)

    # 2. 日期缺口檢查（超過 7 天視為異常缺口）
    if "日期" in df.columns:
        dates = pd.to_datetime(df["日期"]).drop_duplicates().sort_values()
        gaps  = dates.diff().dropna()
        large_gaps = gaps[gaps > pd.Timedelta(days=7)]
        if large_gaps.empty:
            report_lines.append("✅ 日期檢查：無異常缺口")
        else:
            for i in large_gaps.index:
                pos = dates.tolist().index(dates[i])
                d1  = dates.iloc[pos - 1].date()
                d2  = dates.iloc[pos].date()
                msg = f"⚠️  日期缺口：{d1} → {d2}（可能為連假）"
                report_lines.append(msg)
                issues.append(msg)

    # 3. 重複資料檢查
    if "日期" in df.columns and "證券代號" in df.columns:
        dup = df.duplicated(subset=["日期", "證券代號"]).sum()
        if dup == 0:
            report_lines.append("✅ 重複檢查：無重複資料")
        else:
            msg = f"❌ 發現 {dup} 筆重複資料（同日期同代號）"
            report_lines.append(msg)
            issues.append(msg)

    # 4. 數值合理性
    col = "三大法人買賣超股數"
    if col in df.columns:
        max_val = df[col].abs().max()
        if max_val > 5e8:
            msg = f"⚠️  [{col}] 最大值 {max_val:,.0f}，請確認是否異常"
            report_lines.append(msg)
            issues.append(msg)
        else:
            report_lines.append(f"✅ 數值合理性：最大值 {max_val:,.0f}（正常範圍）")

    # 5. ETF 覆蓋率
    if "證券代號" in df.columns:
        etf_count = df["證券代號"].nunique()
        date_count = df["日期"].nunique() if "日期" in df.columns else "?"
        report_lines.append(f"✅ 覆蓋率：共 {etf_count} 檔 ETF，{date_count} 個交易日")

    # 結論
    report_lines.append("-" * 55)
    if not issues:
        report_lines.append("🎉 結論：資料品質良好，可交給模型組使用")
    else:
        report_lines.append(f"⚠️  結論：發現 {len(issues)} 個問題，請確認後再使用")
    report_lines.append("=" * 55)

    report = "\n".join(report_lines)
    print(f"\n{report}")

    # 儲存驗證報告
    with open("ETF_Validation.txt", "w", encoding="utf-8") as f:
        f.write(report)
    print("\n📁 驗證報告已儲存：ETF_Validation.txt")

    return report