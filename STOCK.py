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
st.title("📱 專屬存股績效追蹤器 (自動命名版)")
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
        
        sh = gc.open("存股")
        return sh.sheet1
    except Exception as e:
        st.error(f"連線失敗，錯誤訊息：{e}")
        st.stop()

worksheet = get_google_sheet()

def load_data():
    records = worksheet.get_all_records()
    if not records:
        return pd.DataFrame(columns=["交易日期", "交易類別", "股票代碼", "股票名稱", "成交單價", "成交股數"])
    df = pd.DataFrame(records)
    df['交易日期'] = pd.to_datetime(df['交易日期'], format='%Y-%m-%d', errors='coerce').dt.date
    return df

if 'ledger' not in st.session_state:
    st.session_state['ledger'] = load_data()

days = st.sidebar.slider("選擇走勢圖查看過去幾個「交易日」：", 10, 120, 60, 10)

# ----------------- 新增：自動抓取股票名稱函式 -----------------
def get_stock_name(code):
    """
    根據股票代碼，透過 yfinance 自動抓取公司名稱。
    會自動嘗試上市 (.TW) 與上櫃 (.TWO)。
    """
    try:
        # 先嘗試上市 (TW)
        ticker_tw = yf.Ticker(f"{code}.TW")
        name_tw = ticker_tw.info.get('shortName')
        if name_tw:
            return name_tw
            
        # 再嘗試上櫃 (TWO)
        ticker_two = yf.Ticker(f"{code}.TWO")
        name_two = ticker_two.info.get('shortName')
        if name_two:
            return name_two
            
    except Exception:
        pass
        
    return "" # 若抓不到，回傳空字串，讓使用者可以後續在表格手動修改

tab1, tab2, tab3 = st.tabs(["📊 庫存總覽與走勢", "📝 手機專用記帳", "⚙️ 修改歷史紀錄"])

# ==========================================
# 分頁 2：手機專用記帳 (極速版：移除手動名稱輸入)
# ==========================================
with tab2:
    st.subheader("📝 新增一筆存股紀錄")
    st.write("💡 輸入代碼後，系統會自動聯網幫你找股票名稱喔！")
    
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
                code_clean = input_code.strip()
                # 送出時，呼叫函式自動抓取名稱
                with st.spinner(f"正在查詢 {code_clean} 的股票名稱..."):
                    fetched_name = get_stock_name(code_clean)
                    
                new_row = pd.DataFrame([{
                    "交易日期": input_date,
                    "交易類別": input_type,
                    "股票代碼": code_clean,
                    "股票名稱": fetched_name, # 將自動抓到的名稱寫入
                    "成交單價": input_price,
                    "成交股數": input_shares
                }])
                st.session_state['ledger'] = pd.concat([st.session_state['ledger'], new_row], ignore_index=True)
                
                upload_df = st.session_state['ledger'].copy()
                upload_df['交易日期'] = upload_df['交易日期'].astype(str)
                upload_df = upload_df.fillna("") 
                
                worksheet.clear()
                worksheet.update([upload_df.columns.values.tolist()] + upload_df.values.tolist())
                
                if fetched_name:
                    st.success(f"✅ 成功寫入雲端：{fetched_name} ({code_clean}) {input_type} {input_shares} 股！")
                else:
                    st.warning(f"✅ 成功寫入雲端：代碼 {code_clean} {input_type} {input_shares} 股！(自動抓取名稱失敗，可至歷史紀錄補齊)")

# ==========================================
# 分頁 3：修改歷史紀錄
# ==========================================
with tab3:
    st.info("💡 提示：可以在這裡直接修改歷史紀錄或補上股票名稱，改完後點擊下方按鈕存檔！")
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
        upload_df = upload_df.fillna("")
        
        worksheet.clear()
        worksheet.update([upload_df.columns.values.tolist()] + upload_df.values.tolist())
        st.success("✅ 歷史紀錄修改已同步至雲端！")

# ==========================================
# 分頁 1：庫存總覽與走勢 
# ==========================================
with tab1:
    ledger_df = st.session_state['ledger'].dropna(subset=["股票代碼", "成交單價", "成交股數"]).copy()
    
    if ledger_df.empty:
        st.warning("目前雲端資料庫是空的。請新增紀錄！")
    else:
        if '股票名稱' not in ledger_df.columns:
            ledger_df['股票名稱'] = ""
        ledger_df['股票名稱'] = ledger_df['股票名稱'].fillna("").astype(str)
        
        ledger_df['成交單價'] = ledger_df['成交單價'].astype(float)
        ledger_df['成交股數'] = ledger_df['成交股數'].astype(int)
        
        ledger_df['買進股數'] = ledger_df.apply(lambda x: x['成交股數'] if x['交易類別'] == '買進' else 0, axis=1)
        ledger_df['賣出股數'] = ledger_df.apply(lambda x: x['成交股數'] if x['交易類別'] == '賣出' else 0, axis=1)
        ledger_df['買進總額'] = ledger_df['買進股數'] * ledger_df['成交單價']
        
        summary_df = ledger_df.groupby('股票代碼').agg(
            股票名稱=('股票名稱', 'max'),
            總買進股數=('買進股數', 'sum'),
            總賣出股數=('賣出股數', 'sum'),
            總買進成本=('買進總額', 'sum')
        ).reset_index()
        
        summary_df['股票名稱'] = summary_df['股票名稱'].replace("", "未命名")
        summary_df['持有總股數'] = summary_df['總買進股數'] - summary_df['總賣出股數']
        summary_df = summary_df[summary_df['持有總股數'] > 0]
        
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
                    name = str(row['股票名稱'])
                    shares = int(row['持有總股數'])
                    avg_price = float(row['平均成本價'])
                    current_cost = shares * avg_price
                    
                    current_price = 0.0
                    stock_info = yf.download(f"{code}.TW", period="5d", progress=False)
                    if stock_info.empty:
                        stock_info = yf.download(f"{code}.TWO", period="5d", progress=False)
                    
                    if not stock_info.empty:
                        current_price = float(stock_info['Close'].squeeze().iloc[-1])
                    else:
                        current_price = avg_price
                    
                    stock_value = current_price * shares
                    profit_loss = stock_value - current_cost
                    roi = (profit_loss / current_cost) * 100 if current_cost > 0 else 0
                    
                    total_cost += current_cost
                    total_value += stock_value
                    results.append({
                        "股票名稱": name,
                        "股票代碼": code, 
                        "庫存股數": shares, 
                        "平均買價": round(avg_price, 2),
                        "最新股價": round(current_price, 2), 
                        "剩餘總成本": round(current_cost, 0),
                        "目前總市值": round(stock_value, 0), 
                        "未實現損益": round(profit_loss, 0),
                        "報酬率 (%)": round(roi, 2)
                    })
                if results:
                    display_df = pd.DataFrame(results)
                    st.dataframe(display_df, use_container_width=True)
                    
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
                    for idx, row in summary_df.iterrows():
                        code = str(row['股票代碼']).strip()
                        name = str(row['股票名稱']).strip()
                        label = f"{code} ({name})"
                        
                        data = yf.download(f"{code}.TW", period=f"{days+20}d", progress=False)
                        if data.empty:
                            data = yf.download(f"{code}.TWO", period=f"{days+20}d", progress=False)
                            
                        if not data.empty:
                            close_prices = data['Close'].squeeze().tail(days)
                            base_price = float(close_prices.iloc[0])
                            roi_series = ((close_prices - base_price) / base_price) * 100
                            all_roi_data[label] = roi_series
                    if not all_roi_data.empty:
                        st.line_chart(all_roi_data)
