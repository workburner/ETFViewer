import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go

# -------------------------
# Page Setup
# -------------------------
st.set_page_config(layout="wide", page_title="ETF Strategy Comparison")
st.title("📊 ETF Strategy Comparison Tool")

# -------------------------
# Sidebar Inputs
# -------------------------
st.sidebar.header("User Inputs")

default_tickers = ["SSO", "SPUU", "TQQQ", "QLD"]
tickers_input = st.sidebar.text_input(
    "Tickers (comma separated, up to 5)", value=",".join(default_tickers)
)
tickers = [t.strip().upper() for t in tickers_input.split(",")][:5]

total_investment = st.sidebar.number_input(
    "Total Investment ($)", min_value=1000, max_value=10000000, value=10000, step=1000
)

return_type = st.sidebar.selectbox("Return Type", ["Dollar Value", "Percentage"])
dca_frequency = st.sidebar.selectbox("DCA Frequency", ["Daily", "Weekly", "Monthly", "Yearly"])
time_mode = st.sidebar.selectbox("Time Mode", ["Full History", "Custom Range"])

# -------------------------
# Download Data
# -------------------------
@st.cache_data
def load_data(tickers):
    data = yf.download(tickers, period="max", auto_adjust=True, threads=False)
    if isinstance(data.columns, pd.MultiIndex):
        data = data["Close"]
    return data.dropna(how="all")

with st.spinner("Loading data..."):
    data = load_data(tickers)

earliest_date = data.dropna().index[0]
latest_date = data.index[-1]

st.sidebar.write(f"Earliest available: {earliest_date.date()}")
st.sidebar.write(f"Latest available: {latest_date.date()}")

# -------------------------
# Time Selection
# -------------------------
if time_mode == "Custom Range":
    start_date = st.sidebar.date_input("Start Date", earliest_date)
    duration = st.sidebar.number_input("Duration", 1, 50, 5)
    unit = st.sidebar.selectbox("Unit", ["Years", "Months", "Days"])
    start_date = pd.to_datetime(start_date)

    if unit == "Years":
        end_date = start_date + pd.DateOffset(years=duration)
    elif unit == "Months":
        end_date = start_date + pd.DateOffset(months=duration)
    else:
        end_date = start_date + pd.DateOffset(days=duration)

    data = data[(data.index >= start_date) & (data.index <= end_date)]
else:
    data = data[(data.index >= earliest_date) & (data.index <= latest_date)]

# -------------------------
# Helper Functions
# -------------------------
def calculate_drawdown(series):
    peak = series.cummax()
    return (series - peak) / peak * 100  # always in %

def plot_chart(df, title, yaxis_title):
    fig = go.Figure()
    for col in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index,
            y=df[col],
            mode='lines',
            name=col,
            hovertemplate='%{y:.2f}<br>%{x|%Y-%m-%d}'
        ))
    fig.update_layout(
        title=title,
        xaxis_title='Date',
        yaxis_title=yaxis_title,
        hovermode="x unified",
        template="plotly_white"
    )
    st.plotly_chart(fig, width="stretch", key=f"{title}-{id(df)}")

def get_dca_dates(data, freq):
    if freq == "Daily":
        return data.index
    elif freq == "Weekly":
        return data.resample("W-FRI").first().index
    elif freq == "Monthly":
        return data.resample("ME").first().index
    elif freq == "Yearly":
        return data.resample("YE").first().index
    return data.index

# -------------------------
# Scenario A: Lump Sum
# -------------------------
lump_results = {}
for ticker in tickers:
    if ticker not in data.columns:
        continue
    prices = data[ticker].dropna()
    first_price_date = prices.index[0]
    if return_type == "Dollar Value":
        shares = total_investment / prices.loc[first_price_date]
        lump_results[ticker] = shares * prices
    else:
        lump_results[ticker] = (prices / prices.loc[first_price_date] - 1) * 100

lump_df = pd.DataFrame(lump_results)
lump_drawdown = lump_df.apply(calculate_drawdown)

# -------------------------
# Scenario B: Recurring Investment (DCA)
# -------------------------
dca_dates = get_dca_dates(data, dca_frequency)

recurring_results = {}
for ticker in tickers:
    if ticker not in data.columns:
        continue
    prices = data[ticker].dropna()
    shares = 0
    values = []
    cumulative_invested = 0
    valid_dates = dca_dates[dca_dates.isin(prices.index)]
    num = len(valid_dates)
    if num == 0:
        continue
    invest_each = total_investment / num
    for date in prices.index:
        if date in valid_dates:
            shares += invest_each / prices.loc[date]
            cumulative_invested += invest_each
        portfolio_value = shares * prices.loc[date]
        if return_type == "Dollar Value":
            values.append(portfolio_value)
        else:
            pct_return = (portfolio_value / cumulative_invested - 1) * 100 if cumulative_invested > 0 else 0
            values.append(pct_return)
    recurring_results[ticker] = pd.Series(values, index=prices.index)

recurring_df = pd.DataFrame(recurring_results)
recurring_drawdown = recurring_df.apply(calculate_drawdown)

# -------------------------
# Display Charts
# -------------------------
st.header("📈 Scenario A: Lump Sum")
col1, col2 = st.columns(2)
with col1:
    yaxis = "% Return" if return_type == "Percentage" else "Portfolio Value ($)"
    plot_chart(lump_df, "Performance", yaxis)
with col2:
    plot_chart(lump_drawdown, "Drawdown (%)", "Drawdown (%)")

st.header("🔁 Scenario B: Recurring Investment (DCA)")
col3, col4 = st.columns(2)
with col3:
    yaxis = "% Return" if return_type == "Percentage" else "Portfolio Value ($)"
    plot_chart(recurring_df, "Performance", yaxis)
with col4:
    plot_chart(recurring_drawdown, "Drawdown (%)", "Drawdown (%)")

# -------------------------
# Snapshot Table
# -------------------------
st.header("📅 Snapshot")
snapshot_date = st.date_input("Select Date", latest_date)
snapshot_date = pd.to_datetime(snapshot_date)

# Safely get closest previous trading day
if snapshot_date not in data.index:
    idx = data.index.get_indexer([snapshot_date], method="ffill")[0]
    snapshot_date = data.index[idx]

st.subheader("Lump Sum")
st.write(lump_df.loc[:snapshot_date].tail(1).T)
st.subheader("Recurring")
st.write(recurring_df.loc[:snapshot_date].tail(1).T)