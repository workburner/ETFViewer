import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go

# --- Helper Functions ---

@st.cache_data(show_spinner=False)
def download_data(ticker, start, end):
    """
    Download historical data from yfinance, safely get 'Adj Close', handle empty data.
    """
    df = yf.download(ticker, start=start, end=end, progress=False, threads=False)
    if df.empty or 'Adj Close' not in df.columns:
        st.warning(f"No adjusted close data found for {ticker}")
        return pd.Series(dtype=float)
    return df['Adj Close']

def align_dates_ffill(dates_to_align, valid_dates):
    """
    Align each date in dates_to_align to the previous valid date in valid_dates using ffill.
    """
    valid_dates = pd.to_datetime(valid_dates).sort_values()
    dates_to_align = pd.to_datetime(dates_to_align)

    idxer = valid_dates.get_indexer(dates_to_align, method='ffill')
    # idxer == -1 means date is before first valid date; clip to first valid date
    idxer = np.where(idxer == -1, 0, idxer)
    aligned = valid_dates[idxer]
    return aligned

def generate_dca_dates(start_date, end_date, freq, valid_dates):
    """
    Generate investment dates by frequency between start_date and end_date,
    then align each date to previous valid trading day to avoid skips.
    """
    freq_map = {
        "Daily": "B",
        "Weekly": "W-FRI",
        "Monthly": "ME",
        "Yearly": "YE",
    }
    if freq not in freq_map:
        freq_str = "B"
    else:
        freq_str = freq_map[freq]

    raw_dates = pd.date_range(start_date, end_date, freq=freq_str)
    aligned_dates = align_dates_ffill(raw_dates, valid_dates)
    # Remove duplicates, keep dates within range
    aligned_dates = pd.Series(aligned_dates).drop_duplicates()
    aligned_dates = aligned_dates[(aligned_dates >= pd.to_datetime(start_date)) & (aligned_dates <= pd.to_datetime(end_date))]
    return aligned_dates.sort_values().tolist()

def validate_and_adjust_dates(start_date, end_date, valid_dates):
    """
    Adjust user input dates to closest valid trading dates using ffill for start and bfill for end.
    """
    valid_dates = pd.to_datetime(valid_dates).sort_values()
    start_aligned = align_dates_ffill([start_date], valid_dates)[0]
    # For end date, align forward (bfill)
    idxer_end = valid_dates.get_indexer([end_date], method='bfill')[0]
    if idxer_end == -1:
        # If no valid date after end_date, use last valid date
        end_aligned = valid_dates.iloc[-1]
    else:
        end_aligned = valid_dates[idxer_end]
    return start_aligned, end_aligned

def calculate_one_time_value(initial_amount, prices):
    if prices.empty:
        return pd.Series(dtype=float)
    initial_price = prices.iloc[0]
    return initial_amount * (prices / initial_price)

def calculate_dca(prices, invest_dates, total_amount):
    if prices.empty or len(invest_dates) == 0:
        return pd.Series(dtype=float), pd.Series(dtype=float), 0.0
    n_investments = len(invest_dates)
    invest_per_date = total_amount / n_investments
    prices_on_dates = prices.reindex(invest_dates, method='ffill')
    shares_bought = invest_per_date / prices_on_dates
    shares_held = shares_bought.cumsum().reindex(prices.index, method='ffill').fillna(0)
    portfolio_value = shares_held * prices
    cumulative_invested = invest_per_date * np.arange(1, n_investments + 1)
    cumulative_invested = pd.Series(cumulative_invested, index=invest_dates)
    cumulative_invested = cumulative_invested.reindex(prices.index, method='ffill').fillna(0)
    return portfolio_value, cumulative_invested, shares_held.sum()

# --- Streamlit UI ---

st.title("ETF Dollar-Cost Averaging Investment App")

st.sidebar.header("User Inputs")

tickers_input = st.sidebar.text_input(
    "Enter up to 5 ticker symbols (comma separated)", 
    "SSO,TQQQ,QLD,SPY,DIA"
)
tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
tickers = tickers[:5]

total_investment = st.sidebar.number_input("Total Investment Amount ($)", value=10000, step=1000, min_value=1)

time_mode = st.sidebar.selectbox("Time Mode", ["Max available history", "Custom range"])

# To store earliest available date across all tickers for feedback
earliest_data_date = None

# Download data and check earliest dates before letting user pick custom dates
data_dict_prelim = {}
for ticker in tickers:
    data = download_data(ticker, "1990-01-01", datetime.today() + timedelta(days=1))
    if not data.empty:
        data_dict_prelim[ticker] = data
        ticker_earliest = data.index.min()
        if earliest_data_date is None or ticker_earliest > earliest_data_date:
            earliest_data_date = ticker_earliest

if len(data_dict_prelim) == 0:
    st.error("No valid data found for entered tickers. Please check ticker symbols.")
    st.stop()

if time_mode == "Custom range":
    st.sidebar.write(f"Note: Earliest available data across tickers starts from {earliest_data_date.date()}")
    start_date = st.sidebar.date_input("Start Date", earliest_data_date.date())
    end_date = st.sidebar.date_input("End Date", datetime.today())
    # Validate and adjust dates
    all_valid_dates = pd.Index(sorted(set().union(*[data.index for data in data_dict_prelim.values()])))
    start_date, end_date = validate_and_adjust_dates(start_date, end_date, all_valid_dates)
    if start_date > end_date:
        st.sidebar.error("Start date must be before or equal to end date.")
else:
    # Use earliest_data_date as start to avoid empty data
    start_date = earliest_data_date
    end_date = datetime.today()

return_mode = st.sidebar.selectbox("Return Mode", ["Dollar Value", "Percentage"])

dca_enabled = st.sidebar.checkbox("Enable Dollar-Cost Averaging (DCA)", value=True)

dca_frequency = None
if dca_enabled:
    dca_frequency = st.sidebar.selectbox("DCA Frequency", ["Daily", "Weekly", "Monthly", "Yearly"])

st.sidebar.markdown("---")

# Download full data for selected tickers and date range
data_dict = {}
for ticker in tickers:
    data = download_data(ticker, start_date, end_date + timedelta(days=1))
    if data.empty:
        st.warning(f"No data for {ticker} in selected date range, skipping.")
        continue
    data_dict[ticker] = data

if not data_dict:
    st.error("No data available for the selected date range and tickers.")
    st.stop()

# Align all ticker data on same date index (union)
all_dates = pd.Index(sorted(set().union(*[data.index for data in data_dict.values()])))
for ticker in data_dict:
    # Reindex with forward fill and back fill for missing days (weekends/holidays)
    data_dict[ticker] = data_dict[ticker].reindex(all_dates, method='ffill').fillna(method='bfill')

prices_df = pd.DataFrame(data_dict)
# Trim to selected date range (safe-guard)
prices_df = prices_df[(prices_df.index >= pd.to_datetime(start_date)) & (prices_df.index <= pd.to_datetime(end_date))]

st.subheader("Sample Price Data")
st.dataframe(prices_df.head())

# Investment Calculations
results = {}

for ticker in prices_df.columns:
    prices = prices_df[ticker].dropna()
    if prices.empty:
        st.warning(f"No price data for {ticker} after filtering.")
        continue

    one_time_val = calculate_one_time_value(total_investment, prices)

    if dca_enabled:
        invest_dates = generate_dca_dates(prices.index[0], prices.index[-1], dca_frequency, prices.index)
        dca_val, dca_cum_invested, total_shares = calculate_dca(prices, invest_dates, total_investment)
    else:
        dca_val = pd.Series(dtype=float)
        dca_cum_invested = pd.Series(dtype=float)
        invest_dates = []
        total_shares = 0

    results[ticker] = {
        "one_time_value": one_time_val,
        "dca_value": dca_val,
        "dca_cumulative_invested": dca_cum_invested,
        "invest_dates": invest_dates,
        "total_shares": total_shares
    }

# Plotting function
def plot_investment(ticker, data, key_suffix):
    fig = go.Figure()

    if not data["one_time_value"].empty:
        fig.add_trace(go.Scatter(
            x=data["one_time_value"].index,
            y=data["one_time_value"].values,
            mode='lines',
            name="One-time Investment Value",
            yaxis="y1"
        ))

    if dca_enabled and not data["dca_value"].empty:
        fig.add_trace(go.Scatter(
            x=data["dca_value"].index,
            y=data["dca_value"].values,
            mode='lines',
            name="DCA Portfolio Value",
            yaxis="y1"
        ))
        fig.add_trace(go.Scatter(
            x=data["dca_cumulative_invested"].index,
            y=data["dca_cumulative_invested"].values,
            mode='lines',
            name="DCA Cumulative Invested",
            yaxis="y2",
            line=dict(dash='dash')
        ))

    fig.update_layout(
        title=f"{ticker} Investment Performance",
        xaxis_title="Date",
        yaxis=dict(
            title="Dollar Value",
            side='left',
            showgrid=False,
            zeroline=False,
        ),
        yaxis2=dict(
            title="Cumulative Invested Amount",
            overlaying='y',
            side='right',
            showgrid=False,
            zeroline=False,
        ),
        legend=dict(x=0, y=1),
        hovermode="x unified",
        width=None,
        height=500
    )

    if return_mode == "Percentage":
        initial = total_investment

        def to_pct(series):
            return ((series / initial) - 1) * 100

        fig.data = []  # clear existing traces

        if not data["one_time_value"].empty:
            fig.add_trace(go.Scatter(
                x=data["one_time_value"].index,
                y=to_pct(data["one_time_value"]),
                mode='lines',
                name="One-time % Return",
                yaxis="y1"
            ))

        if dca_enabled and not data["dca_value"].empty:
            fig.add_trace(go.Scatter(
                x=data["dca_value"].index,
                y=to_pct(data["dca_value"]),
                mode='lines',
                name="DCA % Return",
                yaxis="y1"
            ))
            fig.add_trace(go.Scatter(
                x=data["dca_cumulative_invested"].index,
                y=to_pct(data["dca_cumulative_invested"]),
                mode='lines',
                name="DCA Cumulative Invested (%)",
                yaxis="y2",
                line=dict(dash='dash')
            ))

        fig.update_layout(
            yaxis=dict(title="Percentage Return (%)"),
            yaxis2=dict(title="Cumulative Invested (%)"),
        )

    st.plotly_chart(fig, width="stretch", use_container_width=True, key=f"{ticker}_chart_{key_suffix}")

st.subheader("Investment Performance Charts")

for i, ticker in enumerate(results):
    plot_investment(ticker, results[ticker], key_suffix=i)

st.markdown("---")
st.markdown("""
### Notes
- DCA investment dates are aligned to the previous valid trading day to avoid skipping intended investment periods.
- The app caches downloaded data to speed up repeat runs.
- Use the sidebar controls to customize tickers, investment amount, date range, return mode, and DCA options.
- Hover over the charts to see detailed investment values on each date.
""")