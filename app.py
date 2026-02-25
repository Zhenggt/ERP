import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

# --- 1. 性能优化：缓存数据库连接 ---
# 使用 cache_resource 确保 engine 全局只创建一次，极大提升加载速度
@st.cache_resource
def get_engine():
    try:
        db_url = st.secrets["db_uri"]
        # pool_pre_ping=True 会自动检查连接有效性，防止断开
        return create_engine(db_url, pool_pre_ping=True, pool_recycle=3600)
    except Exception as e:
        st.error(f"数据库连接初始化失败: {e}")
        return None

engine = get_engine()

# --- 2. 安全验证模块 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.title("🏮 进销存云系统")
        st.subheader("身份验证")
        user_input = st.text_input("管理员账号")
        pass_input = st.text_input("管理员密码", type="password")
        
        if st.button("登录系统"):
            if user_input == st.secrets["auth"]["admin_user"] and \
               pass_input == st.secrets["auth"]["admin_pass"]:
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("❌ 账号或密码不正确")
        return False
    return True

# --- 3. 业务核心逻辑 ---
if check_password():
    # 侧边栏
    if st.sidebar.button("🔒 退出登录"):
        del st.session_state["password_correct"]
        st.rerun()
        
    st.sidebar.title("控制面板")
    menu = st.sidebar.radio("功能切换", ["📊 实时库存", "📥 采购入库", "📤 销售出库"])

    # A. 实时库存 (使用了 cache_data，10秒内刷新无需重复读库)
    if menu == "📊 实时库存":
        st.header("📈 实时库存报表")
        
        # 局部函数：获取数据并缓存
        @st.cache_data(ttl=10) 
        def fetch_stock():
            return pd.read_sql("SELECT name, spec, stock FROM products ORDER BY stock DESC", engine)

        try:
            df = fetch_stock()
            if not df.empty:
                # 使用 dataframe 模式，支持手机端滑动和排序
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("仓库目前没有商品，请先入库。")
        except:
            st.error("无法读取数据，请确认数据库表已建立。")

    # B. 采购入库
    elif menu == "📥 采购入库":
        st.header("增加库存")
        with st.form("in_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            name = col1.text_input("货品名称")
            spec = col2.text_input("规格")
            num = st.number_input("入库数量", min_value=1, step=1)
            
            if st.form_submit_button("确认入库"):
                with engine.connect() as conn:
                    # 更新或插入库存
                    conn.execute(
                        text("INSERT INTO products (name, spec, stock) VALUES (:n, :s, :num) "
                             "ON CONFLICT (name) DO UPDATE SET stock = products.stock + :num"),
                        {"n": name, "s": spec, "num": num}
                    )
                    # 记流水
                    conn.execute(
                        text("INSERT INTO orders (type, product, num) VALUES ('进货', :p, :n)"),
                        {"p": name, "n": num}
                    )
                    conn.commit()
                st.success(f"✅ {name} 入库成功！")
                st.cache_data.clear() # 入库后清除缓存，确保下次查询看到最新数据

    # C. 销售出库
    elif menu == "📤 销售出库":
        st.header("减少库存")
        try:
            df_p = pd.read_sql("SELECT name, stock FROM products WHERE stock > 0", engine)
            p_list = df_p['name'].tolist()
            
            if not p_list:
                st.warning("暂无库存可售。")
            else:
                with st.form("out_form", clear_on_submit=True):
                    target = st.selectbox("选择货品", p_list)
                    sale_num = st.number_input("销售数量", min_value=1, step=1)
                    
                    if st.form_submit_button("确认成交"):
                        curr_stock = df_p[df_p['name'] == target]['stock'].values[0]
                        if sale_num > curr_stock:
                            st.error(f"库存不足（余量：{curr_stock}）")
                        else:
                            with engine.connect() as conn:
                                conn.execute(text("UPDATE products SET stock = stock - :n WHERE name = :p"),
                                             {"n": sale_num, "p": target})
                                conn.execute(text("INSERT INTO orders (type, product, num) VALUES ('销售', :p, :n)"),
                                             {"p": target, "n": sale_num})
                                conn.commit()
                            st.success(f"🚀 {target} 出库成功！")
                            st.cache_data.clear() # 出库后清除缓存
        except:
            st.error("数据加载失败。")

