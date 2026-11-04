"""Plotly figures for the Streamlit stock movement dashboard."""
import plotly.graph_objects as go

COLORS = {
    'AAPL': '#1f77b4', 'ADBE': '#ff7f0e', 'AMZN': '#2ca02c', 'GOOGL': '#d62728',
    'META': '#9467bd', 'MSFT': '#8c564b', 'NVDA': '#e377c2', 'TSLA': '#7f7f7f',
}


def relative_price_figure(indexed):
    fig = go.Figure()
    for symbol, rows in indexed.groupby('symbol', sort=False):
        fig.add_trace(go.Scatter(
            x=rows['date'], y=rows['indexed_price'], mode='lines', name=symbol,
            line={'color': COLORS[symbol]},
            customdata=rows[['period_change']],
            hovertemplate=(f'<b>{symbol}</b><br>%{{x|%Y-%m-%d}}<br>'
                           'Indexed price: %{y:.2f}<br>Change since first observation: %{customdata[0]:.2%}<extra></extra>'),
        ))
    fig.add_hline(y=100, line_dash='dash', line_color='#777')
    fig.update_layout(title='Relative price performance — first available trading day = 100',
                      xaxis_title='Date', yaxis_title='Indexed adjusted close', hovermode='x unified',
                      legend_title='Ticker', margin={'t': 70, 'l': 20, 'r': 20, 'b': 20})
    return fig


def stock_price_figure(series, symbol):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=series['date'], y=series['close'], mode='lines', name=f'{symbol} close',
        line={'color': COLORS[symbol]},
        customdata=series[['high', 'low', 'daily_range_pct', 'is_flagged', 'co_flag_count']],
        hovertemplate=(f'<b>{symbol}</b><br>%{{x|%Y-%m-%d}}<br>Close: $%{{y:.2f}}'
                       '<br>High: $%{customdata[0]:.2f}<br>Low: $%{customdata[1]:.2f}'
                       '<br>Normalized range: %{customdata[2]:.2%}'
                       '<br>Flagged: %{customdata[3]}<br>Co-flags: %{customdata[4]}<extra></extra>'),
    ))
    flagged = series.loc[series['is_flagged']]
    if not flagged.empty:
        fig.add_trace(go.Scatter(x=flagged['date'], y=flagged['close'], mode='markers',
                                 name='Flagged day', marker={'color': '#d62728', 'size': 10, 'symbol': 'diamond'}))
    fig.update_layout(title=f'{symbol} closing price and flagged days', xaxis_title='Date',
                      yaxis_title='Close (USD)', hovermode='closest', margin={'t': 60, 'l': 20, 'r': 20, 'b': 20})
    return fig
