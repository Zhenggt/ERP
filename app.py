import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

# --- 1. 安全读取云端配置 ---
# 这里不需要手动填 URI，它会自动去 Streamlit 的 Secrets 里找
try:
    DB_URL = st.secrets["db_uri"]
except:
    st.error("请在 Streamlit Cloud 的 Secrets 中配置 db_uri")
    st.stop()

engine = create_engine(DB_URL)

# --- 2. 界面设计 ---
st.set_page_config(page_title="云端进销存系统", layout="wide")
st.title("🛡️ 真正属于你的云端管理系统")

menu = st.sidebar.radio("菜单", ["库存报表", "出入库操作", "历史明细"])

# --- 3. 业务功能 ---
if menu == "库存报表":
    st.subheader("实时库存盘点")
    try:
        df = pd.read_sql("SELECT name, spec, stock, sell_price FROM products", engine)
        st.dataframe(df, use_container_width=True)
    except Exception as e:
        st.warning("数据库中尚无数据表，请先进行一次入库操作。")

elif menu == "出入库操作":
    st.subheader("单据录入")
    with st.form("jxc_form"):
        col1, col2 = st.columns(2)
        p_name = col1.text_input("商品品名")
        p_type = col2.selectbox("操作类型", ["进货入库", "销售出库"])
        p_num = col1.number_input("数量", min_value=1)
        p_customer = col2.text_input("往来单位/客户")
        
        if st.form_submit_button("立即同步到云端"):
            with engine.connect() as conn:
                # 简单的入库逻辑：这里仅做流水记录，实际可扩展库存自动计算
                query = text("INSERT INTO orders (type, customer, product, num) VALUES (:t, :c, :p, :n)")
                conn.execute(query, {"t": p_type, "c": p_customer, "p": p_name, "n": p_num})
                conn.commit()
            st.success(f"云端同步成功！已记录一笔{p_type}单据。")
            st.balloons()
