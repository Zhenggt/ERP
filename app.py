import streamlit as st
import pandas as pd
from datetime import datetime

# --- 1. 模拟数据库 (实际使用时会保存到文件) ---
if 'products' not in st.session_state:
    st.session_state.products = pd.DataFrame([
        {"商品名称": "不锈钢管 A", "库存": 100, "单价": 50.0},
        {"商品名称": "铝合金框 B", "库存": 50, "单价": 120.0}
    ])

if 'orders' not in st.session_state:
    st.session_state.orders = pd.DataFrame(columns=["日期", "客户", "商品", "数量", "金额"])

# --- 2. 界面设计 ---
st.title("🚀 我的私有进销存系统")

# 侧边栏：导航
menu = st.sidebar.selectbox("菜单", ["销售出库", "库存查询", "统计报表"])

if menu == "销售出库":
    st.header("🛒 新增销售单")
    with st.form("order_form"):
        customer = st.text_input("客户名称")
        prod_name = st.selectbox("选择商品", st.session_state.products["商品名称"])
        quantity = st.number_input("销售数量", min_value=1, step=1)
        
        submitted = st.form_submit_button("确认出库并打印")
        if submitted:
            # 逻辑：减库存
            idx = st.session_state.products[st.session_state.products["商品名称"] == prod_name].index[0]
            if st.session_state.products.at[idx, "库存"] >= quantity:
                st.session_state.products.at[idx, "库存"] -= quantity
                
                # 逻辑：记订单
                price = st.session_state.products.at[idx, "单价"]
                new_order = {"日期": datetime.now().strftime("%Y-%m-%d"), "客户": customer, 
                             "商品": prod_name, "数量": quantity, "金额": price * quantity}
                st.session_state.orders = pd.concat([st.session_state.orders, pd.DataFrame([new_order])], ignore_index=True)
                st.success(f"出库成功！总金额：{price * quantity} 元")
            else:
                st.error("库存不足！")

elif menu == "库存查询":
    st.header("📦 当前库存状态")
    st.table(st.session_state.products)

elif menu == "统计报表":
    st.header("📊 销售数据统计")
    if not st.session_state.orders.empty:
        # 简单统计
        total_sales = st.session_state.orders["金额"].sum()
        st.metric("累计销售额", f"￥{total_sales}")
        
        # 销量排行图表
        st.bar_chart(st.session_state.orders.groupby("商品")["数量"].sum())
        
        # 明细表
        st.subheader("历史单据 (对账用)")
        st.dataframe(st.session_state.orders)
    else:
        st.info("暂无销售数据")