import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# 页面配置
st.set_page_config(page_title="RKLB 实盘摩擦成本网格回测", layout="wide")
st.title("🚀 RKLB 网格交易量化回测 (含富途真实摩擦成本)")

# 侧边栏：参数设置
st.sidebar.header("基本参数")
symbol = st.sidebar.text_input("股票代码", value="RKLB")
initial_capital = st.sidebar.number_input("初始资金 ($)", value=30000, step=5000)

st.sidebar.subheader("网格参数")
# 结合 RKLB 目前约 $50-$60 的股价，设置更符合现状的默认区间
grid_bottom = st.sidebar.number_input("网格区间下限 ($)", value=40.0, step=2.0)
grid_top = st.sidebar.number_input("网格区间上限 ($)", value=70.0, step=2.0)
grid_count = st.sidebar.number_input("网格数量 (数量越多越密集)", value=10, min_value=2, step=1)
# 调大默认股数以稀释 2美元/笔 的固定手续费
qty_per_grid = st.sidebar.number_input("每格交易股数", value=50, step=10)

st.sidebar.subheader("交易成本参数 (基于富途实盘账单)")
# 滑点：买入价更高，卖出价更低
slippage_pct = st.sidebar.number_input("单边滑点 (%)", value=0.10, step=0.05)
# 手续费：富途固定佣金 $0.99 + 平台费 $1.00 + 交收费等 ≈ $2.00
commission_fee = st.sidebar.number_input("单笔手续费 ($)", value=2.0, step=0.5)

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
    # 确保列名是一维的 (yfinance新版本可能返回多重索引)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] if col[1] == "" else col[1] if col[0] == symbol else col[0] for col in df.columns]

    # 计算网格价格线
    grid_levels = np.linspace(grid_bottom, grid_top, grid_count)
    st.sidebar.write("网格价格线参考 ($):", np.round(grid_levels, 2))

    # 初始化回测变量
    cash = initial_capital
    position = 0
    trades = []
    
    last_grid_level = None

    # 网格回测逻辑 (含滑点与手续费)
    for index, row in df.iterrows():
        current_price = row['Close']
        date = row['Date']
        
        # 找到最接近当前价格的网格线
        closest_grid = min(grid_levels, key=lambda x: abs(x - current_price))
        
        if last_grid_level is None:
            last_grid_level = closest_grid
            continue
            
        # 卖出逻辑：价格向上突破一个网格
        if current_price >= closest_grid > last_grid_level:
            if position >= qty_per_grid:
                # 实际成交价 = 触发价扣除滑点
                exec_price = current_price * (1 - slippage_pct / 100)
                # 实际收入 = (数量 * 实际成交价) - 交易手续费
                revenue = (qty_per_grid * exec_price) - commission_fee
                
                position -= qty_per_grid
                cash += revenue
                trades.append({
                    'Date': date.strftime('%Y-%m-%d'), 'Type': 'Sell', 'Trigger_Price': round(current_price, 2), 
                    'Exec_Price': round(exec_price, 2), 'Qty': qty_per_grid, 'Fee': commission_fee, 
                    'Cash_Balance': round(cash, 2)
                })
                last_grid_level = closest_grid
                
        # 买入逻辑：价格向下跌破一个网格
        elif current_price <= closest_grid < last_grid_level:
            # 实际成交价 = 触发价加上滑点
            exec_price = current_price * (1 + slippage_pct / 100)
            # 实际支出 = (数量 * 实际成交价) + 交易手续费
            cost = (qty_per_grid * exec_price) + commission_fee
            
            if cash >= cost:
                position += qty_per_grid
                cash -= cost
                trades.append({
                    'Date': date.strftime('%Y-%m-%d'), 'Type': 'Buy', 'Trigger_Price': round(current_price, 2), 
                    'Exec_Price': round(exec_price, 2), 'Qty': qty_per_grid, 'Fee': commission_fee,
                    'Cash_Balance': round(cash, 2)
                })
                last_grid_level = closest_grid

    # 计算期末清仓净值 (假设按最后一天收盘价扣除滑点和一笔手续费清仓)
    final_price = df.iloc[-1]['Close']
    liquidate_price = final_price * (1 - slippage_pct / 100)
    final_commission = commission_fee if position > 0 else 0
    total_asset = cash + (position * liquidate_price) - final_commission
    total_return = (total_asset - initial_capital) / initial_capital * 100
    
    # 摩擦成本统计
    total_fees = sum([t['Fee'] for t in trades]) if trades else 0

    # 1. 顶部核心指标看板
    cols = st.columns(5)
    cols[0].metric("初始资金", f"${initial_capital:,.2f}")
    cols[1].metric("最终总资产", f"${total_asset:,.2f}", f"{total_return:.2f}%")
    cols[2].metric("最终持仓数量", f"{position} 股")
    cols[3].metric("总手续费消耗", f"${total_fees:,.2f}", delta_color="inverse")
    cols[4].metric("触发交易次数", f"{len(trades)} 次")

    # 2. 可视化图表绘制
    fig = go.Figure()
    # 绘制收盘价
    fig.add_trace(go.Scatter(x=df['Date'], y=df['Close'], mode='lines', name='收盘价', line=dict(color='#00a4ff')))
    
    # 绘制网格线
    for level in grid_levels:
        fig.add_hline(y=level, line_dash="dot", line_color="gray", opacity=0.4)

    # 绘制买卖点
    if trades:
        trades_df = pd.DataFrame(trades)
        buys = trades_df[trades_df['Type'] == 'Buy']
        sells = trades_df[trades_df['Type'] == 'Sell']
        
        fig.add_trace(go.Scatter(x=buys['Date'], y=buys['Exec_Price'], mode='markers', 
                                 marker=dict(symbol='triangle-up', color='#00cc96', size=12, line=dict(width=1, color='white')), name='买入'))
        fig.add_trace(go.Scatter(x=sells['Date'], y=sells['Exec_Price'], mode='markers', 
                                 marker=dict(symbol='triangle-down', color='#ef553b', size=12, line=dict(width=1, color='white')), name='卖出'))

    fig.update_layout(title=f"{symbol} 近一年价格走势与网格成交点 (实盘成本约束)", 
                      xaxis_title="日期", yaxis_title="价格 ($)", template="plotly_dark", height=600,
                      legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01))
    st.plotly_chart(fig, use_container_width=True)

    # 3. 交易明细与 CSV 导出
    st.subheader("📝 交易明细记录")
    if trades:
        trades_df = pd.DataFrame(trades)
        st.dataframe(trades_df, use_container_width=True)
        
        # 将 DataFrame 转换为 CSV 字节流
        csv_data = trades_df.to_csv(index=False).encode('utf-8')
        
        # 提供一键下载按钮
        st.download_button(
            label="⬇️ 导出交易明细为 CSV",
            data=csv_data,
            file_name=f"{symbol}_grid_trades_{pd.Timestamp.today().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )
    else:
        st.info("当前参数配置下，未触发任何网格买卖点。")
