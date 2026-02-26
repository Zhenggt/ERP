import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

# --- 1. 配置与性能优化 ---
st.set_page_config(page_title="南总进销存系统", layout="wide")

@st.cache_resource
def get_engine():
    """创建持久化数据库连接，提升响应速度"""
    try:
        return create_engine(st.secrets["db_uri"], pool_pre_ping=True, pool_recycle=3600)
    except Exception as e:
        st.error(f"数据库连接失败: {e}")
        return None

engine = get_engine()

# --- 2. 安全登录模块 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.title("🔒 南总云端管理系统")
        with st.container():
            u = st.text_input("账号")
            p = st.text_input("密码", type="password")
            if st.button("登录"):
                if u == st.secrets["auth"]["admin_user"] and p == st.secrets["auth"]["admin_pass"]:
                    st.session_state["password_correct"] = True
                    st.rerun()
                else:
                    st.error("账号或密码错误")
        return False
    return True

# --- 3. 核心业务逻辑 ---
if check_password():
    # 侧边栏导航
    st.sidebar.title("🏮 系统菜单")
    menu = st.sidebar.radio("请选择操作", ["📊 库存看板", "📥 采购入库", "📤 销售出库", "👥 客户档案"])
    
    if st.sidebar.button("退出登录"):
        del st.session_state["password_correct"]
        st.rerun()

    # --- A. 库存看板 ---
    if menu == "📊 库存看板":
        st.header("实时库存统计")
        @st.cache_data(ttl=10) # 缓存10秒，减少数据库压力
        def load_inventory():
            return pd.read_sql("SELECT name as 品名, spec as 规格, stock as 数量 FROM products ORDER BY stock DESC", engine)
        
        df = load_inventory()
        st.dataframe(df, use_container_width=True, hide_index=True)

    # --- B. 采购入库 ---
    elif menu == "📥 采购入库":
        st.header("商品采购入库")
        with st.form("in_form", clear_on_submit=True):
            name = st.text_input("货品名称")
            spec = st.text_input("规格型号")
            num = st.number_input("入库数量", min_value=1, step=1)
            if st.form_submit_button("确认入库"):
                with engine.connect() as conn:
                    # 更新库存：若品名存在则累加，不存在则插入
                    conn.execute(text("INSERT INTO products (name, spec, stock) VALUES (:n, :s, :num) "
                                      "ON CONFLICT (name) DO UPDATE SET stock = products.stock + :num"),
                                 {"n": name, "s": spec, "num": num})
                    conn.execute(text("INSERT INTO orders (type, product, num) VALUES ('进货', :p, :n)"),
                                 {"p": name, "n": num})
                    conn.commit()
                st.success(f"✅ {name} 已入库")
                st.cache_data.clear() # 清除缓存强制刷新数据

    # --- C. 销售出库 ---
    elif menu == "📤 销售出库":
        st.header("销售出库单")
        try:
            # 联动读取库存和客户
            df_p = pd.read_sql("SELECT name, stock FROM products WHERE stock > 0", engine)
            df_c = pd.read_sql("SELECT name FROM customers", engine)
            
            if df_p.empty:
                st.warning("仓库没货，请先去进货")
            else:
                with st.form("out_form", clear_on_submit=True):
                    cust_name = st.selectbox("选择客户", ["散客"] + df_c['name'].tolist())
                    prod_name = st.selectbox("选择货品", df_p['name'].tolist())
                    out_num = st.number_input("出库数量", min_value=1, step=1)
                    
                   if st.form_submit_button("确认出库"):
                        current_stock = df_p[df_p['name'] == prod_name]['stock'].values[0]
                        if out_num > current_stock:
                            st.error(f"库存不足！剩余 {current_stock}")
                        else:
                            with engine.connect() as conn:
                                # 1. 更新产品库存
                                conn.execute(
                                    text("UPDATE products SET stock = stock - :n WHERE name = :p"),
                                    {"n": out_num, "p": prod_name}
                                ) # <-- 确保这里有右括号闭合
                                
                                # 2. 插入销售流水记录
                                conn.execute(
                                    text("INSERT INTO orders (type, customer, product, num) VALUES ('销售', :c, :p, :n)"),
                                    {"c": cust_name, "p": prod_name, "n": out_num}
                                ) # <-- 确保这里有右括号闭合
                                
                                conn.commit()
                            st.success(f"🚀 {prod_name} 出库成功")
                            st.cache_data.clear()

