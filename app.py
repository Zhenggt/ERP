import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

# --- 1. 配置与性能优化 ---
st.set_page_config(page_title="进销存系统", layout="wide")

@st.cache_resource
def get_engine():
    try:
        return create_engine(st.secrets["db_uri"], pool_pre_ping=True, pool_recycle=3600)
    except Exception as e:
        st.error(f"数据库连接失败: {e}")
        return None

engine = get_engine()

# --- 2. 安全登录模块 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.title("🔒 云端管理系统")
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
    st.sidebar.title("🏮 系统菜单")
    menu = st.sidebar.radio("请选择操作", ["📊 库存看板", "📥 采购入库", "📤 销售出库", "👥 客户档案"])
    
    if st.sidebar.button("退出登录"):
        del st.session_state["password_correct"]
        st.rerun()

    # --- A. 库存看板 ---
    if menu == "📊 库存看板":
        st.header("📈 实时库存报表 (单位：公斤)")
        @st.cache_data(ttl=10)
        def load_inventory():
            # 修改后的看板查询
            query = 'SELECT name as 品名, spec as 规格, stock as "库存余量(公斤)" FROM products ORDER BY name, spec ASC'
            return pd.read_sql(query, engine)
        
        try:
            df = load_inventory()
            if not df.empty:
                # 适配 2026 年新语法：width='stretch'
                st.dataframe(df, width='stretch', hide_index=True)
            else:
                st.info("目前库存为空，请先录入采购信息。")
        except Exception as e:
            st.error(f"查询失败: {e}")

    # --- B. 采购入库 ---
    elif menu == "📥 采购入库":
        st.header("📥 增加库存 (公斤)")
        with st.form("in_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("货品名称")
                spec = st.text_input("规格型号")
            with col2:
                num = st.number_input("入库重量 (公斤)", min_value=0.0, step=0.1, format="%.2f")
                in_price = st.number_input("采购单价 (元/公斤)", min_value=0.0, step=0.01)
            
           if st.form_submit_button("确认入库"):
                if name:
                    with engine.connect() as conn:
                        # 注意：下面这两行必须比 with 语句多出 4 个空格
                        conn.execute(text(""" 
                            INSERT INTO products (name, spec, stock) VALUES (:n, :s, :num) 
                            ON CONFLICT (name, spec) 
                            DO UPDATE SET stock = products.stock + :num
                        """), {"n": name, "s": spec, "num": num})
                        
                        conn.execute(text("""
                            INSERT INTO orders (type, product, num, price, total_amount) 
                            VALUES ('进货', :p, :n, :pr, :t)
                        """), {"p": name, "n": num, "pr": in_price, "t": num * in_price})
                        
                        conn.commit()
                    st.success(f"✅ {name} | {spec} 已入库")
                    st.cache_data.clear()
                else:
                    st.error("请输入货品名称")

    # --- C. 销售出库 ---
   elif menu == "📤 销售出库":
        st.header("📤 销售出库单 (单位：公斤)")
        try:
            # 修改点：同时读取品名和规格
            df_p = pd.read_sql("SELECT name, spec, stock FROM products WHERE stock > 0", engine)
            df_c = pd.read_sql("SELECT name FROM customers", engine)
            
            if df_p.empty:
                st.warning("仓库目前无货。")
            else:
                # 关键：将品名和规格合并为一个可选项
                df_p['display_name'] = df_p['name'] + " | " + df_p['spec'].fillna("无规格")
                
                with st.form("out_form", clear_on_submit=True):
                    col1, col2 = st.columns(2)
                    with col1:
                        target_c = st.selectbox("👤 选择客户", ["散客"] + df_c['name'].tolist())
                        # 用户现在选的是“铝棒 | 5051”
                        selected_option = st.selectbox("📦 选择货品 (品名 | 规格)", df_p['display_name'].tolist())
                    
                    # 根据选择的内容，反向拆分出品名和规格
                    target_p = selected_option.split(" | ")[0]
                    target_s = selected_option.split(" | ")[1]
                    if target_s == "无规格": target_s = ""

                    with col2:
                        num = st.number_input("⚖️ 出库重量 (公斤)", min_value=0.0, step=0.01)
                        price = st.number_input("💰 销售单价", min_value=0.0, step=0.01)

                    if st.form_submit_button("确认出库"):
                        # 查找对应的库存数值（匹配品名和规格）
                        current_row = df_p[(df_p['name'] == target_p) & (df_p['spec'] == target_s)]
                        current_stock = float(current_row['stock'].values[0])
                        
                        if num > current_stock:
                            st.error(f"库存不足！当前仅剩 {current_stock} 公斤")
                        else:
                            with engine.connect() as conn:
                                # 减库存时，必须同时匹配 name 和 spec
                                conn.execute(text("UPDATE products SET stock = stock - :n WHERE name = :p AND spec = :s"),
                                             {"n": num, "p": target_p, "s": target_s})
                                # 记流水
                                conn.execute(text("INSERT INTO orders (type, customer, product, num, price, total_amount) VALUES ('销售', :c, :p, :n, :pr, :t)"),
                                             {"c": target_c, "p": selected_option, "n": num, "pr": price, "t": num * price})
                                conn.commit()
                            st.success(f"🚀 {selected_option} 出库成功！")
                            st.cache_data.clear()
        except Exception as e:
            st.error(f"出错: {e}")

    # --- D. 客户档案 ---
    elif menu == "👥 客户档案":
        st.header("👥 客户信息档案")
        tab1, tab2 = st.tabs(["➕ 新增客户", "📋 客户名册"])
        with tab1:
            with st.form("customer_form", clear_on_submit=True):
                c_name = st.text_input("客户姓名/公司名 (必填)")
                c_phone = st.text_input("联系电话")
                c_address = st.text_area("收货地址")
                if st.form_submit_button("💾 点击保存到云端"):
                    if c_name:
                        try:
                            with engine.connect() as conn:
                                conn.execute(text("INSERT INTO customers (name, phone, address) VALUES (:n, :p, :a) "
                                                  "ON CONFLICT (name) DO UPDATE SET phone = :p, address = :a"),
                                             {"n": c_name, "p": c_phone, "a": c_address})
                                conn.commit()
                            st.success(f"✅ 客户【{c_name}】资料已同步")
                            st.cache_data.clear()
                        except Exception as e:
                            st.error(f"保存失败: {e}")
                    else:
                        st.error("❌ 名称不能为空")
        with tab2:
            try:
                df_cust = pd.read_sql("SELECT name as 客户名称, phone as 联系电话, address as 地址 FROM customers ORDER BY id DESC", engine)
                # 适配 2026 年新语法：width='stretch'
                st.dataframe(df_cust, width='stretch', hide_index=True)
            except:
                st.info("暂无客户资料数据")


