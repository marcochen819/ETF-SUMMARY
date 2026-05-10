
Open In Colab

# 動態追蹤期間成交量前 20 名 ETF（00 開頭）
# 並產出日期、代號、名稱、投信買賣超、自營買賣超、三大法人合計、
# 投信買賣超_5日均、投信買賣超_10日均、投信買賣超_5日方向、三大法人合計_5日均、
# 三大法人合計_10日均、三大法人合計_5日方向、三大法人_連續天數、收盤、成交量、5日均價、20日均價、日報酬率、5日累積報酬

import requests
import pandas as pd
import yfinance as yf
import time
import logging
import os
import urllib3
from datetime import datetime, timedelta
from pathlib import Path
from tabulate import tabulate

df = pd.read_csv("data/clean/etf_top20_final.csv")
df["日期"] = pd.to_datetime(df["日期"])

# 統計每檔 ETF 出現幾天
count_per_etf = df.groupby("代號").size().sort_values(ascending=False)
print(count_per_etf)

# 統計每天有幾檔 ETF
count_per_day = df.groupby("日期").size().sort_values()
print(count_per_day)

# 關閉 SSL 警告（解決 TWSE 憑證 SKI 缺失問題）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 解決 Pandas 中文對齊問題
pd.set_option('display.unicode.ambiguous_as_wide', True)
pd.set_option('display.unicode.east_asian_width', True)
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)

# ============================================================
# 全域設定
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("etf_pipeline.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# 資料夾建立
Path("data/raw").mkdir(parents=True, exist_ok=True)
Path("data/clean").mkdir(parents=True, exist_ok=True)

# 動態填入：執行 find_top20_etfs() 後填入
TAIWAN_ETFS = {}
ETF_CODES = []


# ============================================================
# 第一部分：爬蟲
# ============================================================

def fetch_institutional_investors(date: str) -> pd.DataFrame | None:
    """爬取單日三大法人買賣超資料（來源：台灣證交所）"""
    url = "https://www.twse.com.tw/rwd/zh/fund/T86"
    params = {"response": "json", "date": date, "selectType": "ALLBUT0999"}

    try:
        res = requests.get(url, params=params, headers=HEADERS,
                           timeout=10, verify=False)
        res.raise_for_status()

        if not res.text or not res.text.strip():
            logger.warning(f"⚠️  {date}：回傳空內容（可能為休市日）")
            return None

        try:
            data = res.json()
        except ValueError:
            logger.warning(f"⚠️  {date}：非 JSON 回應（可能為休市日）")
            return None

        if data.get("stat") != "OK":
            logger.warning(f"查無資料（可能為假日或休市）：{date}，stat={data.get('stat')}")
            return None

        if not data.get("data"):
            logger.warning(f"⚠️  {date}：data 欄位為空")
            return None

        df = pd.DataFrame(data["data"], columns=data["fields"])
        df["日期原始"] = date
        logger.info(f"✅ 三大法人 {date}：共 {len(df)} 筆")
        return df

    except requests.exceptions.Timeout:
        logger.error(f"❌ 連線逾時：{date}")
        return None
    except requests.exceptions.ConnectionError as e:
        logger.error(f"❌ 網路連線失敗：{date}，詳細：{e}")
        return None
    except Exception as e:
        logger.error(f"❌ 未知錯誤 {date}：{type(e).__name__} - {e}")
        return None


def fetch_institutional_range(start_date: str, end_date: str, delay: float = 3.5) -> pd.DataFrame:
    """批次爬取日期區間的三大法人買賣超資料"""
    start = datetime.strptime(start_date, "%Y%m%d")
    end = datetime.strptime(end_date, "%Y%m%d")
    all_data = []
    current = start
    fetched = 0

    logger.info(f"開始爬取三大法人資料：{start_date} → {end_date}")

    while current <= end:
        if current.weekday() < 5:
            date_str = current.strftime("%Y%m%d")
            df = fetch_institutional_investors(date_str)
            if df is not None:
                all_data.append(df)
                fetched += 1
            time.sleep(delay)
        current += timedelta(days=1)

    if not all_data:
        logger.warning("⚠️  無任何法人資料被爬取")
        return pd.DataFrame()

    result = pd.concat(all_data, ignore_index=True)

    save_path = f"data/raw/institutional_{start_date}_{end_date}.csv"
    result.to_csv(save_path, index=False, encoding="utf-8-sig")
    logger.info(f"📁 三大法人原始資料已儲存：{save_path}（共 {fetched} 個交易日）")

    return result


# ============================================================
# 🆕 第一部分增強：動態挑選成交量前 20 名 ETF
# ============================================================

def find_top20_etfs(institutional_df: pd.DataFrame,
                    start_date: str,
                    end_date: str) -> dict:
    """
    從三大法人資料中找出所有 ETF（00 開頭），
    再用 yfinance 抓成交量，取期間總成交量前 20 名

    參數：
        institutional_df: 已爬取的三大法人資料
        start_date: 'YYYYMMDD'
        end_date:   'YYYYMMDD'
    回傳：
        dict: {代號: 名稱}，例如 {"0050": "元大台灣50", ...}
    """
    if institutional_df.empty:
        logger.error("❌ 三大法人資料為空，無法挑選 ETF")
        return {}

    # 1️⃣ 從三大法人資料抓出所有 00 開頭的代號（即 ETF）
    code_col = "證券代號" if "證券代號" in institutional_df.columns else "代號"
    name_col = "證券名稱" if "證券名稱" in institutional_df.columns else "名稱"

    if code_col not in institutional_df.columns:
        logger.error(f"❌ 找不到證券代號欄位")
        return {}

    # 篩選 00 開頭、且代號為 4-6 位數字的 ETF
    df = institutional_df[[code_col, name_col]].drop_duplicates()
    etf_df = df[df[code_col].astype(str).str.match(r"^00\d{2,4}[A-Z]?$")]

    # 排除權證、ETN 等（通常是 5-6 位數+B/L/U 結尾，但也有純數字 ETF）
    # ETF 通常代號 4-6 位數，B 結尾常為債券 ETF（也算 ETF）
    etf_df = etf_df[etf_df[code_col].str.len() <= 6]

    candidate_etfs = dict(zip(etf_df[code_col], etf_df[name_col]))
    logger.info(f"🔍 候選 ETF 數量：{len(candidate_etfs)} 檔（00 開頭）")

    if not candidate_etfs:
        logger.error("❌ 找不到任何 00 開頭的 ETF")
        return {}

    # 2️⃣ 用 yfinance 抓成交量
    price_start = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
    price_end = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"

    logger.info(f"📡 開始抓取 {len(candidate_etfs)} 檔 ETF 成交量資料...")

    volume_data = []
    failed_count = 0
    for i, (code, name) in enumerate(candidate_etfs.items(), 1):
        try:
            ticker = f"{code}.TW"
            stock = yf.Ticker(ticker)
            df = stock.history(start=price_start, end=price_end)

            if df.empty or "Volume" not in df.columns:
                failed_count += 1
                continue

            total_vol = df["Volume"].sum()
            avg_vol = df["Volume"].mean()
            # 👇 新增：用每日(成交量 × 收盤價)的總和當成交金額
            total_amount = (df["Volume"] * df["Close"]).sum()
            avg_amount = (df["Volume"] * df["Close"]).mean()

            volume_data.append({
                "代號": code,
                "名稱": name,
                "總成交量(股)": int(total_vol),
                "總成交張數": int(total_vol / 1000),  # 換算成張
                "總成交金額(元)": int(total_amount),  # 元
                "總成交金額(億)": round(total_amount / 1e8, 2),  # 億元
                "平均日成交量(股)": int(avg_vol),
                "平均日成交額(元)": int(avg_amount),
                "資料天數": len(df)
            })

            if i % 20 == 0:
                logger.info(f"  進度：{i}/{len(candidate_etfs)}")

        except Exception as e:
            failed_count += 1
            logger.debug(f"  ⚠️ {code} 抓取失敗：{e}")

    logger.info(f"✅ 成功抓取 {len(volume_data)} 檔，失敗 {failed_count} 檔")

    if not volume_data:
        logger.error("❌ 無法取得任何成交量資料")
        return {}

    # 3️⃣ 排序並取前 20
    rank_df = pd.DataFrame(volume_data).sort_values("總成交金額(元)", ascending=False)
    top20_df = rank_df.head(20)

    # 4️⃣ 顯示排名
    logger.info(f"\n{'=' * 70}")
    logger.info(f"  📊 期間 ETF 成交量前 20 名（{start_date} → {end_date}）")
    logger.info(f"{'=' * 70}")
    logger.info(f"\n{tabulate(top20_df, headers='keys', tablefmt='pretty', showindex=False)}\n")

    # 5️⃣ 儲存排名結果
    save_path = f"data/clean/top20_etfs_{start_date}_{end_date}.csv"
    top20_df.to_csv(save_path, index=False, encoding="utf-8-sig")
    logger.info(f"📁 前 20 名清單已儲存：{save_path}\n")

    # 6️⃣ 回傳成 dict
    return dict(zip(top20_df["代號"], top20_df["名稱"]))


def fetch_etf_prices(start_date: str, end_date: str) -> pd.DataFrame:
    """使用 yfinance 批次下載所有 ETF 歷史股價"""
    all_price = []
    logger.info(f"📡 開始下載 ETF 股價：{start_date} → {end_date}")

    for code, name in TAIWAN_ETFS.items():
        ticker = f"{code}.TW"
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(start=start_date, end=end_date)

            if df.empty:
                logger.warning(f"⚠️  {name}（{ticker}）無資料")
                continue

            df = df.reset_index()

            df.rename(columns={
                "Date": "日期", "Open": "開盤", "High": "最高",
                "Low": "最低", "Close": "收盤", "Volume": "成交量"
            }, inplace=True)

            # 去除時區，避免 merge 時報錯
            df["日期"] = pd.to_datetime(df["日期"]).dt.tz_localize(None).dt.normalize()

            df["代號"] = code
            df["ETF名稱"] = name

            df["5日均價"] = df["收盤"].rolling(5, min_periods=1).mean().round(2)
            df["20日均價"] = df["收盤"].rolling(20, min_periods=1).mean().round(2)
            df["日報酬率"] = df["收盤"].pct_change().round(4)
            df["5日累積報酬"] = df["收盤"].pct_change(5).round(4)

            df = df[["日期", "代號", "ETF名稱", "開盤", "最高", "最低",
                     "收盤", "成交量", "5日均價", "20日均價", "日報酬率", "5日累積報酬"]]

            all_price.append(df)
            logger.info(f"✅ {name}（{ticker}）：{len(df)} 筆")

        except Exception as e:
            logger.error(f"❌ {ticker} 下載失敗：{e}")

    if not all_price:
        logger.warning("⚠️  無任何 ETF 股價資料")
        return pd.DataFrame()

    result = pd.concat(all_price, ignore_index=True)
    save_path = f"data/raw/etf_prices_{start_date}_{end_date}.csv"
    result.to_csv(save_path, index=False, encoding="utf-8-sig")
    logger.info(f"📁 ETF 股價已儲存：{save_path}")
    return result


# ============================================================
# 第二部分：資料清洗（不變）
# ============================================================

def clean_institutional(df: pd.DataFrame) -> pd.DataFrame:
    """清洗三大法人原始資料"""
    if df.empty:
        return df

    df = df.copy()

    rename_map = {
        "證券代號": "代號", "證券名稱": "名稱",
        "外陸資買進股數": "外資買進", "外陸資賣出股數": "外資賣出",
        "外陸資買賣超股數": "外資買賣超",
        "投信買進股數": "投信買進", "投信賣出股數": "投信賣出",
        "投信買賣超股數": "投信買賣超", "自營商買賣超股數": "自營買賣超",
        "三大法人買賣超股數": "三大法人合計", "日期原始": "日期",
    }
    df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)

    numeric_cols = ["外資買進", "外資賣出", "外資買賣超",
                    "投信買進", "投信賣出", "投信買賣超",
                    "自營買賣超", "三大法人合計"]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = (df[col].astype(str)
                       .str.replace(",", "", regex=False)
                       .str.replace(" ", "", regex=False)
                       .str.strip())
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "日期" in df.columns:
        def parse_date(d):
            d = str(d).strip()
            if "/" in d and len(d.split("/")[0]) <= 3:
                parts = d.split("/")
                year = int(parts[0]) + 1911
                return pd.Timestamp(f"{year}-{parts[1]}-{parts[2]}")
            try:
                return pd.to_datetime(d, format="%Y%m%d")
            except Exception:
                return pd.NaT
        df["日期"] = df["日期"].apply(parse_date)

    if "三大法人合計" not in df.columns:
        df["三大法人合計"] = (
                df.get("外資買賣超", 0).fillna(0) +
                df.get("投信買賣超", 0).fillna(0) +
                df.get("自營買賣超", 0).fillna(0)
        )

    for col in numeric_cols:
        if col in df.columns:
            df[col] = df[col].fillna(0)

    col = "三大法人合計"
    if col in df.columns and len(df) > 10:
        mean, std = df[col].mean(), df[col].std()
        before = len(df)
        df = df[abs(df[col] - mean) <= 4 * std].copy()
        removed = before - len(df)
        if removed > 0:
            logger.info(f"🔧 異常值過濾：移除 {removed} 筆（超過 4σ）")

    keep = ["日期", "代號", "名稱", "外資買賣超", "投信買賣超", "自營買賣超", "三大法人合計"]
    df = df[[c for c in keep if c in df.columns]]

    logger.info(f"✅ 三大法人清洗完成：{len(df)} 筆")
    return df


def filter_etf_only(df: pd.DataFrame) -> pd.DataFrame:
    """從三大法人資料中篩選出指定 ETF 標的"""
    if "代號" not in df.columns or df.empty:
        return df
    etf_df = df[df["代號"].isin(ETF_CODES)].copy()
    logger.info(f"📌 ETF 篩選結果：{len(etf_df)} 筆（共 {etf_df['代號'].nunique()} 檔 ETF）")
    return etf_df


def add_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    """新增滾動統計特徵"""
    if df.empty:
        return df

    df = df.sort_values(["代號", "日期"]).copy()

    for col in ["外資買賣超", "投信買賣超", "三大法人合計"]:
        if col not in df.columns:
            continue
        df[f"{col}_5日均"] = (df.groupby("代號")[col]
                              .transform(lambda x: x.rolling(5, min_periods=1).mean()).round(0))
        df[f"{col}_10日均"] = (df.groupby("代號")[col]
                               .transform(lambda x: x.rolling(10, min_periods=1).mean()).round(0))
        df[f"{col}_5日方向"] = (df.groupby("代號")[col]
                                .transform(lambda x: x.rolling(5, min_periods=1)
                                           .apply(lambda s: int((s > 0).sum()) - int((s < 0).sum()))))

    def streak(series):
        result, count = [], 0
        for val in series:
            if val > 0:
                count = count + 1 if count > 0 else 1
            elif val < 0:
                count = count - 1 if count < 0 else -1
            else:
                count = 0
            result.append(count)
        return result

    if "三大法人合計" in df.columns:
        df["三大法人_連續天數"] = (df.groupby("代號")["三大法人合計"].transform(streak))

    logger.info("✅ 滾動特徵新增完成")
    return df


def merge_with_price(institutional_df: pd.DataFrame, price_df: pd.DataFrame) -> pd.DataFrame:
    """合併法人買賣超資料與 ETF 股價資料"""
    if institutional_df.empty or price_df.empty:
        logger.warning("⚠️  其中一個 DataFrame 為空，無法合併")
        return institutional_df

    institutional_df["日期"] = pd.to_datetime(institutional_df["日期"]).dt.tz_localize(None).dt.normalize()
    price_df["日期"] = pd.to_datetime(price_df["日期"]).dt.tz_localize(None).dt.normalize()

    price_cols = ["日期", "代號", "收盤", "成交量", "5日均價", "20日均價", "日報酬率", "5日累積報酬"]
    price_sub = price_df[[c for c in price_cols if c in price_df.columns]]

    merged = pd.merge(institutional_df, price_sub, on=["日期", "代號"], how="left")
    logger.info(f"✅ 合併完成：{len(merged)} 筆，股價覆蓋率 {merged['收盤'].notna().mean() * 100:.1f}%")
    return merged


# ============================================================
# 第三部分：資料驗證（不變）
# ============================================================

def validate(df: pd.DataFrame, label: str = "資料") -> dict:
    """執行資料品質驗證"""
    report = {"label": label, "total_rows": len(df), "issues": []}
    if df.empty:
        report["issues"].append("❌ DataFrame 完全為空")
        return report

    null_counts = df.isnull().sum()
    for col, cnt in null_counts[null_counts > 0].items():
        pct = cnt / len(df) * 100
        report["issues"].append(f"⚠️  [{col}] 有 {cnt} 筆空值（{pct:.1f}%）")

    if "日期" in df.columns:
        dates = pd.to_datetime(df["日期"]).drop_duplicates().sort_values()
        gaps = dates.diff().dropna()
        for i, gap in enumerate(gaps):
            if gap > pd.Timedelta(days=7):
                d1, d2 = dates.iloc[i], dates.iloc[i + 1]
                report["issues"].append(f"⚠️  日期缺口：{d1.date()} → {d2.date()}（{gap.days} 天）")

    if "日期" in df.columns and "代號" in df.columns:
        dup = df.duplicated(subset=["日期", "代號"]).sum()
        if dup > 0:
            report["issues"].append(f"❌ 重複資料：{dup} 筆")

    status = "✅ 全部通過" if not report["issues"] else f"發現 {len(report['issues'])} 個問題"
    logger.info(f"\n{'=' * 55}")
    logger.info(f"  驗證報告：{label}")
    logger.info(f"  資料筆數：{len(df)}　{status}")
    for issue in report["issues"]:
        logger.info(f"  {issue}")
    logger.info(f"{'=' * 55}\n")
    return report


def generate_summary(df: pd.DataFrame) -> pd.DataFrame:
    """產生各 ETF 統計摘要"""
    if "代號" not in df.columns or df.empty:
        return pd.DataFrame()

    agg_dict = {"日期": ["count", "min", "max"]}
    for col in ["外資買賣超", "投信買賣超", "三大法人合計"]:
        if col in df.columns:
            agg_dict[col] = ["mean", "std", "sum"]

    summary = df.groupby("代號").agg(agg_dict)
    summary.columns = ["_".join(c).strip() for c in summary.columns]
    summary = summary.round(0)

    logger.info(f"\n{'=' * 55}")
    logger.info("  各 ETF 資料摘要")
    logger.info(f"\n{summary.to_string()}")
    logger.info(f"{'=' * 55}\n")
    return summary


# ============================================================
# 第四部分：主流程（新增 Step 0：動態挑選）
# ============================================================

def run_pipeline(
        start_date: str = "20240101",
        end_date: str = None,
        request_delay: float = 3.5,
        skip_crawl: bool = False
) -> pd.DataFrame:
    """
    執行完整流程：動態挑前20 → 爬蟲 → 清洗 → 特徵工程 → 驗證 → 輸出
    """
    global TAIWAN_ETFS, ETF_CODES

    if end_date is None:
        end_date = datetime.today().strftime("%Y%m%d")

    price_start = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
    price_end = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"

    logger.info(f"\n{'=' * 55}")
    logger.info(f"  🚀 啟動資料流程（動態 Top 20 ETF 模式）")
    logger.info(f"  期間：{start_date} → {end_date}")
    logger.info(f"{'=' * 55}\n")

    # ── Step 1：先爬全市場三大法人（之後篩 ETF 也能用） ────
    if skip_crawl:
        logger.info("⏭️  跳過爬蟲，讀取現有原始資料...")
        inst_path = f"data/raw/institutional_{start_date}_{end_date}.csv"
        if not Path(inst_path).exists():
            logger.error(f"❌ 找不到原始資料：{inst_path}")
            return pd.DataFrame()
        raw_inst = pd.read_csv(inst_path, dtype=str)
    else:
        logger.info("📡 Step 1：爬取全市場三大法人買賣超...")
        raw_inst = fetch_institutional_range(start_date, end_date, request_delay)

    if raw_inst.empty:
        logger.error("❌ 無法繼續：三大法人資料為空")
        return pd.DataFrame()

    # ── Step 2：🆕 動態挑選成交量前 20 名 ETF ──────────────
    logger.info("🎯 Step 2：動態挑選成交量前 20 名 ETF...")
    top20 = find_top20_etfs(raw_inst, start_date, end_date)

    if not top20:
        logger.error("❌ 無法挑選 ETF，流程結束")
        return pd.DataFrame()

    TAIWAN_ETFS = top20
    ETF_CODES = list(TAIWAN_ETFS.keys())
    logger.info(f"✅ 已鎖定追蹤清單：{len(ETF_CODES)} 檔 ETF")

    # ── Step 3：下載這 20 檔的歷史股價 ──────────────────
    if skip_crawl:
        price_path = f"data/raw/etf_prices_{price_start}_{price_end}.csv"
        raw_price = pd.read_csv(price_path, dtype={"代號": str}) if Path(price_path).exists() else pd.DataFrame()
    else:
        logger.info("📡 Step 3：下載前 20 名 ETF 歷史股價...")
        raw_price = fetch_etf_prices(price_start, price_end)

    # ── Step 4：清洗 ─────────────────────────────────────
    logger.info("🧹 Step 4：清洗三大法人資料...")
    clean_inst = clean_institutional(raw_inst)

    logger.info("🔍 Step 4b：篩選前 20 名 ETF...")
    etf_inst = filter_etf_only(clean_inst)

    # ── Step 5：特徵工程 ──────────────────────────────────
    logger.info("⚙️  Step 5：新增滾動特徵...")
    etf_inst = add_rolling_features(etf_inst)

    # ── Step 6：合併股價 ──────────────────────────────────
    if not raw_price.empty:
        logger.info("🔗 Step 6：合併 ETF 股價資料...")
        final_df = merge_with_price(etf_inst, raw_price)
    else:
        logger.warning("⚠️  無股價資料，跳過合併步驟")
        final_df = etf_inst

    # ── Step 7：驗證 ─────────────────────────────────────
    logger.info("✔️  Step 7：執行資料驗證...")
    validate(final_df, "ETF 三大法人最終資料")
    generate_summary(final_df)

    # ── Step 8：儲存 ─────────────────────────────────────
    save_path = "data/clean/etf_top20_final.csv"
    final_df.to_csv(save_path, index=False, encoding="utf-8-sig")
    logger.info(f"💾 最終資料已儲存：{save_path}（{len(final_df)} 筆）")

    logger.info("\n✅ 全部流程完成！\n")
    return final_df


# ============================================================
# 入口點
# ============================================================

if __name__ == "__main__":
    # ────────────────────────────────────────────
    # ✏️  在這裡修改你要爬取的日期區間
    START_DATE = "20260101"
    END_DATE = "20260426"
    DELAY = 3.5
    SKIP_CRAWL = False
    # ────────────────────────────────────────────

    df = run_pipeline(
        start_date=START_DATE,
        end_date=END_DATE,
        request_delay=DELAY,
        skip_crawl=SKIP_CRAWL
    )

    if not df.empty:
        print("最終資料預覽（前 10 筆）：")
        print(df.head(10).to_string(index=False))
        print(f"\n欄位清單：{list(df.columns)}")
        print(f"資料筆數：{len(df)}")
        print(f"追蹤 ETF：{df['代號'].unique().tolist() if '代號' in df.columns else 'N/A'}")
     