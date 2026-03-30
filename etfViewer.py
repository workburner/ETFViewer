import streamlit as st
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt

st.set_page_config(layout="wide")
st.title("📊 ETF Strategy Comparison Tool")

# -------------------------
# SIDEBAR INPUTS
# -------------------------
st.sidebar.header("User Inputs")

default_tickers = ["SSO", "SPUU", "TQQQ", "QLD"]
tickers_input = st.sidebar.text_input(
    "Tickers (comma separated)",
    value=",".join(default_tickers)
)
tickers = [t.strip().upper() for t in tickers_input.split(",")][:5]

total_investment = st.sidebar.number_input(
    "Total Investment ($)",
    min_value=1000,
    max_value=10000000,
    value=10000,
    step=1000
)

time_mode = st.sidebar.selectbox(
    "Time Mode",
    ["Full History", "Custom Range"]
)

# -------------------------
# DOWNLOAD DATA
# -------------------------
@st.cache_data
def load_data(tickers):
    data = yf.download(tickers, period="max", auto_adjust=True, threads=False)
    if isinstance(data.columns, pd.MultiIndex):
        data = data["Close"]
    return data.dropna(how="all")

data = load_data(tickers)
earliest_date = data.dropna().index[0]
latest_date = data.index[-1]

st.sidebar.write(f"Earliest: {earliest_date.date()}")
st.sidebar.write(f"Latest: {latest_date.date()}")

# -------------------------
# TIME SELECTION
# -------------------------
if time_mode == "Custom Range":
    start_date = st.sidebar.date_input("Start Date", earliest_date)
    duration = st.sidebar.number_input("Duration", 1, 50, 5)
    unit = st.sidebar.selectbox("Unit", ["Years", "Months", "Days"])
    start_date = pd.to_datetime(start_date)

    if unit == "Years":
        end_date = start_date + pd.DateOffset(years=duration)
        freq = "YE"
    elif unit == "Months":
        end_date = start_date + pd.DateOffset(months=duration)
        freq = "ME"
    else:
        end_date = start_date + pd.DateOffset(days=duration)
        freq = "D"

    data = data[(data.index >= start_date) & (data.index <= end_date)]

else:
    data = data[(data.index >= earliest_date) & (data.index <= latest_date)]
    freq = "ME"  # default monthly

# -------------------------
# HELPERS
# -------------------------
def calculate_drawdown(series):
    peak = series.cummax()
    return (series - peak) / peak

def plot_chart(df, title):
    fig, ax = plt.subplots(figsize=(10,5))
    for col in df.columns:
        ax.plot(df.index, df[col], label=col)
    ax.set_title(title)
    ax.legend()
    ax.grid()
    st.pyplot(fig)

# -------------------------
# SCENARIO A: LUMP SUM
# -------------------------
lump_results = {}
for ticker in tickers:
    if ticker not in data.columns:
        continue
    prices = data[ticker].dropna()
    if len(prices) == 0:
        continue
    shares = total_investment / prices.iloc[0]
    lump_results[ticker] = shares * prices

lump_df = pd.DataFrame(lump_results)
lump_drawdown = lump_df.apply(calculate_drawdown)

# -------------------------
# SCENARIO B: RECURRING (DCA)
# -------------------------
if freq == "YE":
    investment_dates = data.resample("YE").first().index
elif freq == "ME":
    investment_dates = data.resample("ME").first().index
else:
    investment_dates = data.index

recurring_results = {}
for ticker in tickers:
    if ticker not in data.columns:
        continue
    prices = data[ticker].dropna()
    shares = 0
    values = []
    valid_dates = investment_dates[investment_dates.isin(prices.index)]
    num = len(valid_dates)
    if num == 0:
        continue
    invest_each = total_investment / num
    for date in prices.index:
        if date in valid_dates:
            shares += invest_each / prices.loc[date]
        values.append(shares * prices.loc[date])
    recurring_results[ticker] = pd.Series(values, index=prices.index)

recurring_df = pd.DataFrame(recurring_results)
recurring_drawdown = recurring_df.apply(calculate_drawdown)

# -------------------------
# DISPLAY
# -------------------------
st.header("📈 Scenario A: Lump Sum")
col1, col2 = st.columns(2)
with col1:
    plot_chart(lump_df, "Performance")
with col2:
    plot_chart(lump_drawdown, "Drawdown")

st.header("🔁 Scenario B: Recurring Investment (DCA)")
col3, col4 = st.columns(2)
with col3:
    plot_chart(recurring_df, "Performance")
with col4:
    plot_chart(recurring_drawdown, "Drawdown")

# -------------------------
# SNAPSHOT
# -------------------------
st.header("📅 Snapshot")
snapshot_date = st.date_input("Select Date", latest_date)
snapshot_date = pd.to_datetime(snapshot_date)

if snapshot_date:
    st.subheader("Lump Sum")
    st.write(lump_df.loc[:snapshot_date].tail(1).T)
    st.subheader("Recurring")
    st.write(recurring_df.loc[:snapshot_date].tail(1).T)