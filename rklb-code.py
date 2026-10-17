import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# 页面配置
st.set_page_config(page_title="RKLB 网格交易回测", layout="wide")
st.title("🚀 RKLB 过去一年网格交易回测模型")

# 侧边栏：参数设置
st.sidebar.header("参数设置")
symbol = st.sidebar.text_input("股票代码", value="RKLB")
initial_capital = st.sidebar.number_input("初始资金 ($)", value=10000, step=1000)

st.sidebar.subheader("网格参数")
# 默认设置一个涵盖 RKLB 过去一年大致波动的区间
grid_bottom = st.sidebar.number_input("网格区间下限 ($)", value=3.0, step=0.5)
grid_top = st.sidebar.number_input("网格区间上限 ($)", value=8.0, step=0.5)
grid_count = st.sidebar.number_input("网格数量 (数量越多越密集)", value=10, min_value=2, step=1)
qty_per_grid = st.sidebar.number_input("每格交易股数", value=100, step=10)

# 数据获取函数 (添加缓存避免重复请求)
@st.cache_data
def load_data(ticker):
    data = yf.download(ticker, period="1y", interval="1d")
    data.reset_index(inplace=True)
    return data

# 获取数据
with st.spinner(f"正在加载 {symbol} 历史数据..."):
    df = load_data(symbol)

if df.empty:
    st.error("数据加载失败，请检查股票代码或网络连接。")
else:
    # 计算网格价格线
    grid_levels = np.linspace(grid_bottom, grid_top, grid_count)
    st.sidebar.write("网格价格线参考:", np.round(grid_levels, 2))

    # 初始化回测变量
    cash = initial_capital
    position = 0
    trades = []
    
    # 为了简化演示，这里记录最近一次触发的网格线，防止在同一条线上反复刷单
    last_grid_level = None

    # 简易网格回测逻辑
    for index, row in df.iterrows():
        current_price = row['Close']
        date = row['Date']
        
        # 找到当前价格所在的网格区间
        # 注意：实际生产环境需使用更严谨的挂单撮合逻辑（如考虑High/Low），此处仅用Close演示
        closest_grid = min(grid_levels, key=lambda x: abs(x - current_price))
        
        if last_grid_level is None:
            last_grid_level = closest_grid
            continue
            
        # 价格向上突破一个网格 -> 卖出
        if current_price >= closest_grid > last_grid_level:
            if position >= qty_per_grid:
                position -= qty_per_grid
                cash += qty_per_grid * current_price
                trades.append({'Date': date, 'Type': 'Sell', 'Price': current_price, 'Qty': qty_per_grid})
                last_grid_level = closest_grid
                
        # 价格向下跌破一个网格 -> 买入
        elif current_price <= closest_grid < last_grid_level:
            cost = qty_per_grid * current_price
            if cash >= cost:
                position += qty_per_grid
                cash -= cost
                trades.append({'Date': date, 'Type': 'Buy', 'Price': current_price, 'Qty': qty_per_grid})
                last_grid_level = closest_grid

    # 计算最终净值
    final_price = df.iloc[-1]['Close']
    total_asset = cash + (position * final_price)
    total_return = (total_asset - initial_capital) / initial_capital * 100

    # UI 展示：核心指标
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("初始资金", f"${initial_capital:,.2f}")
    col2.metric("最终总资产", f"${total_asset:,.2f}", f"{total_return:.2f}%")
    col3.metric("最终持仓数量", f"{position} 股")
    col4.metric("剩余现金", f"${cash:,.2f}")

    # 可视化：使用 Plotly 绘制 K 线与买卖点
    fig = go.Figure()
    
    # 1. 绘制收盘价折线
    fig.add_trace(go.Scatter(x=df['Date'], y=df['Close'], mode='lines', name='收盘价', line=dict(color='white')))
    
    # 2. 画出网格线
    for level in grid_levels:
        fig.add_hline(y=level, line_dash="dot", line_color="gray", opacity=0.3)

    # 3. 标记买卖点
    if trades:
        trades_df = pd.DataFrame(trades)
        buys = trades_df[trades_df['Type'] == 'Buy']
        sells = trades_df[trades_df['Type'] == 'Sell']
        
        fig.add_trace(go.Scatter(x=buys['Date'], y=buys['Price'], mode='markers', 
                                 marker=dict(symbol='triangle-up', color='green', size=10), name='买入'))
        fig.add_trace(go.Scatter(x=sells['Date'], y=sells['Price'], mode='markers', 
                                 marker=dict(symbol='triangle-down', color='red', size=10), name='卖出'))

    fig.update_layout(title=f"{symbol} 过去一年走势及网格交易触发点", xaxis_title="日期", yaxis_title="价格 ($)", template="plotly_dark", height=600)
    st.plotly_chart(fig, use_container_width=True)

    # 展示交易记录明细
    with st.expander("查看详细交易记录"):
        if trades:
            st.dataframe(trades_df.style.format({'Price': '{:.2f}'}), use_container_width=True)
        else:
            st.write("在当前参数下未触发任何交易。")