import streamlit as st
import yfinance as yf
import pandas as pd
import gspread
from datetime import date
import os

# ----------------- 網頁基礎設定 -----------------
st.set_page_config(page_title="專屬存股追蹤器", page_icon="📱", layout="wide")

# ----------------- 密碼鎖防護系統 -----------------
try:
    APP_PASSWORD = st.secrets.get("APP_PASSWORD", "123456")
    HAS_SECRETS = True
except Exception:
    APP_PASSWORD = "123456"
    HAS_SECRETS = False

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        st.title("🔒 專屬存股追蹤器 (請先登入)")
        pwd = st.text_input("請輸入登入密碼：", type="password")
        if st.button("登入"):
            if pwd == APP_PASSWORD:
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("密碼錯誤，請重新輸入。")
        return False
    return True

if not check_password():
    st.stop()

# ----------------- 登入成功後的主畫面 -----------------
st.title("📱 專屬存股績效追蹤器 (買賣進階版)")
if st.sidebar.button("登出"):
    st.session_state["password_correct"] = False
    st.rerun()

# ----------------- 智慧連線至 Google Sheets -----------------
@st.cache_resource 
def get_google_sheet():
    try:
        if HAS_SECRETS and "gcp_service_account" in st.secrets:
            gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        else:
            gc = gspread.service_account(filename="google_key.json")
        
        # 使用你設定的檔案名稱直接連線！
        sh = gc.open("存股")
        return sh.sheet1
    except Exception as e:
        st.error(f"連線失敗，錯誤訊息：{e}")
        st.stop()

worksheet = get_google_sheet()

def load_data():
    records = worksheet.get_all_records()
    if not records:
        return pd.DataFrame(columns=["交易日期", "交易類別", "股票代碼", "成交單價", "成交股數"])
    df = pd.DataFrame(records)
    df['交易日期'] = pd.to_datetime(df['交易日期'], format='%Y-%m-%d', errors='coerce').dt.date
    return df

if 'ledger' not in st.session_state:
    st.session_state['ledger'] = load_data()

days = st.sidebar.slider("選擇走勢圖查看過去幾個「交易日」：", 10, 120, 60, 10)

tab1, tab2, tab3 = st.tabs(["📊 庫存總覽與走勢", "📝 手機專用記帳", "⚙️ 修改歷史紀錄"])

# ==========================================
# 分頁 2：手機專用記帳 (大按鈕表單)
# ==========================================
with tab2:
    st.subheader("📝 新增一筆存股紀錄")
    st.write("這是專為手機設計的輸入介面，輸入完按下送出即可！")
    
    with st.form("mobile_input_form", clear_on_submit=True):
        input_type = st.radio("交易類別", ["買進", "賣出"], horizontal=True)
        
        col1, col2 = st.columns(2)
        with col1:
            input_date = st.date_input("交易日期", date.today())
            input_code = st.text_input("股票代碼 (免加.TW)", placeholder="例如: 2330")
        with col2:
            input_price = st.number_input("成交單價", min_value=0.0, step=0.1)
            input_shares = st.number_input("成交股數", min_value=1, step=1)
            
        submitted = st.form_submit_button("🚀 確認送出並寫入雲端", type="primary", use_container_width=True)
        
        if submitted:
            if not input_code:
                st.error("請輸入股票代碼！")
            else:
                new_row = pd.DataFrame([{
                    "交易日期": input_date,
                    "交易類別": input_type,
                    "股票代碼": input_code.strip(),
                    "成交單價": input_price,
                    "成交股數": input_shares
                }])
                st.session_state['ledger'] = pd.concat([st.session_state['ledger'], new_row], ignore_index=True)
                
                upload_df = st.session_state['ledger'].copy()
                upload_df['交易日期'] = upload_df['交易日期'].astype(str)
                # 👉 安全鎖 1：把所有 NaN 替換為空白字串，避免 InvalidJSONError
                upload_df = upload_df.fillna("") 
                
                worksheet.clear()
                worksheet.update([upload_df.columns.values.tolist()] + upload_df.values.tolist())
                st.success(f"✅ 成功寫入雲端：{input_code} {input_type} {input_shares} 股！")

# ==========================================
# 分頁 3：修改歷史紀錄
# ==========================================
with tab3:
    st.info("如果你發現以前的紀錄打錯了，可以在這邊直接像 Excel 一樣修改，修改完記得按儲存。")
    edited_ledger = st.data_editor(
        st.session_state['ledger'], 
        num_rows="dynamic", 
        use_container_width=True,
        column_config={
            "交易類別": st.column_config.SelectboxColumn("交易類別", options=["買進", "賣出"], required=True)
        }
    )
    if st.button("💾 儲存修改至雲端資料庫"):
        st.session_state['ledger'] = edited_ledger
        
        upload_df = edited_ledger.copy()
        upload_df['交易日期'] = upload_df['交易日期'].astype(str)
        # 👉 安全鎖 2：把所有 NaN 替換為空白字串，避免 InvalidJSONError
        upload_df = upload_df.fillna("")
        
        worksheet.clear()
        worksheet.update([upload_df.columns.values.tolist()] + upload_df.values.tolist())
        st.success("✅ 歷史紀錄修改已同步至雲端！")

# ==========================================
# 分頁 1：庫存總覽與走勢 (輸出端 - 包含平倉邏輯)
# ==========================================
with tab1:
    ledger_df = st.session_state['ledger'].dropna(subset=["股票代碼", "成交單價", "成交股數"])
    if ledger_df.empty:
        st.warning("目前雲端資料庫是空的。請新增紀錄！")
    else:
        ledger_df['成交單價'] = ledger_df['成交單價'].astype(float)
        ledger_df['成交股數'] = ledger_df['成交股數'].astype(int)
        
        # 買賣相抵庫存邏輯
        ledger_df['買進股數'] = ledger_df.apply(lambda x: x['成交股數'] if x['交易類別'] == '買進' else 0, axis=1)
        ledger_df['賣出股數'] = ledger_df.apply(lambda x: x['成交股數'] if x['交易類別'] == '賣出' else 0, axis=1)
        ledger_df['買進總額'] = ledger_df['買進股數'] * ledger_df['成交單價']
        
        summary_df = ledger_df.groupby('股票代碼').agg(
            總買進股數=('買進股數', 'sum'),
            總賣出股數=('賣出股數', 'sum'),
            總買進成本=('買進總額', 'sum')
        ).reset_index()
        
        summary_df['持有總股數'] = summary_df['總買進股數'] - summary_df['總賣出股數']
        summary_df = summary_df[summary_df['持有總股數'] > 0] # 過濾掉已賣光的股票
        
        summary_df['平均成本價'] = summary_df.apply(
            lambda x: x['總買進成本'] / x['總買進股數'] if x['總買進股數'] > 0 else 0, axis=1
        )
        
        st.subheader("💰 我的存股庫存總覽")
        if summary_df.empty:
             st.info("目前沒有持股庫存 (可能都已賣出平倉)。")
        elif st.button("🔄 抓取最新股價並計算庫存損益"):
            with st.spinner("正在抓取即時股價，請稍候..."):
                results = []
                total_cost = 0
                total_value = 0
                portfolio_codes = summary_df['股票代碼'].tolist()
                
                for index, row in summary_df.iterrows():
                    code = str(row['股票代碼']).strip()
                    shares = int(row['持有總股數'])
                    avg_price = float(row['平均成本價'])
                    current_cost = shares * avg_price
                    
                    ticker = f"{code}.TW"
                    stock_info = yf.download(ticker, period="5d", progress=False)
                    if not stock_info.empty:
                        current_price = float(stock_info['Close'].squeeze().iloc[-1])
                        stock_value = current_price * shares
                        profit_loss = stock_value - current_cost
                        roi = (profit_loss / current_cost) * 100 if current_cost > 0 else 0
                        
                        total_cost += current_cost
                        total_value += stock_value
                        results.append({
                            "股票代碼": code, "庫存股數": shares, "平均買價": round(avg_price, 2),
                            "最新股價": round(current_price, 2), "剩餘總成本": round(current_cost, 0),
                            "目前總市值": round(stock_value, 0), "未實現損益": round(profit_loss, 0),
                            "報酬率 (%)": round(roi, 2)
                        })
                if results:
                    st.dataframe(pd.DataFrame(results), use_container_width=True)
                    st.success(f"### 🎯 總投資成本：{total_cost:,.0f} 元 ｜ 📈 目前總市值：{total_value:,.0f} 元")
                    total_pl = total_value - total_cost
                    total_roi = (total_pl / total_cost) * 100 if total_cost > 0 else 0
                    if total_pl >= 0:
                        st.info(f"### 💸 總未實現損益：+{total_pl:,.0f} 元 (+{total_roi:.2f}%)")
                    else:
                        st.error(f"### 💸 總未實現損益：{total_pl:,.0f} 元 ({total_roi:.2f}%)")
                    
                    st.divider()
                    st.subheader(f"📊 庫存持股過去 {days} 個交易日走勢比較")
                    all_roi_data = pd.DataFrame()
                    for code in portfolio_codes:
                        ticker = f"{code}.TW" 
                        data = yf.download(ticker, period=f"{days+20}d", progress=False)
                        if not data.empty:
                            close_prices = data['Close'].squeeze().tail(days)
                            base_price = float(close_prices.iloc[0])
                            roi_series = ((close_prices - base_price) / base_price) * 100
                            all_roi_data[code] = roi_series
                    if not all_roi_data.empty:
                        st.line_chart(all_roi_data)
