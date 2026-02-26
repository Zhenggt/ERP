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
        st.header("📈 实时库存报表")
        @st.cache_data(ttl=10)
        def load_inventory():
            query = 'SELECT name as 品名, spec as 规格, stock as "库存余量(公斤)" FROM products ORDER BY name, spec ASC'
            return pd.read_sql(query, engine)
        
        try:
            df = load_inventory()
            if not df.empty:
                # --- 多维度统计卡片 ---
                total_kg = df['库存余量(公斤)'].sum()
                item_count = len(df)
                
                c1, c2, c3 = st.columns(3)
                c1.metric("📦 库存总重", f"{total_kg:,.2f} 公斤")
                c2.metric("🔢 货品种类", f"{item_count} 种")
                c3.metric("📅 更新日期", "2026-02-26") # 实时日期
                
                st.divider() # 加一条分割线
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
                        # 使用 (name, spec) 作为唯一判断标准
                        conn.execute(text("""
                            INSERT INTO products (name, spec, stock) VALUES (:n, :s, :num) 
                            ON CONFLICT (name, spec) 
                            DO UPDATE SET stock = products.stock + :num
                        """), {"n": name, "s": spec, "num": num})
                        conn.commit()
                    st.success(f"✅ {name} | {spec} 已成功入库")
                    st.cache_data.clear()
                else:
                    st.error("请输入货品名称")

    # --- C. 销售出库 ---
    elif menu == "📤 销售出库":
        st.header("📤 销售出库单 (单位：公斤)")
        try:
            df_p = pd.read_sql("SELECT name, spec, stock FROM products WHERE stock > 0", engine)
            df_c = pd.read_sql("SELECT name FROM customers", engine)
            
            if df_p.empty:
                st.warning("仓库目前无货。")
            else:
                df_p['display_name'] = df_p['name'] + " | " + df_p['spec'].fillna("无规格")
                
                col1, col2 = st.columns(2)
                with col1:
                    target_c = st.selectbox("👤 选择客户", ["散客"] + df_c['name'].tolist())
                    selected_option = st.selectbox("📦 选择货品 (品名 | 规格)", df_p['display_name'].tolist())
                
                target_p = selected_option.split(" | ")[0]
                target_s = selected_option.split(" | ")[1]
                if target_s == "无规格": target_s = ""

                with col2:
                    num = st.number_input("⚖️ 出库重量 (公斤)", min_value=0.0, step=0.01)
                    price = st.number_input("💰 销售单价 (元/公斤)", min_value=0.0, step=0.01)

                # --- 实时金额看板：高亮醒目设计 ---
                total_val = round(num * price, 2)
                
                # 创建三列，中间放金额，更有设计感
                m_col1, m_col2, m_col3 = st.columns([1, 2, 1])
                with m_col2:
                    st.markdown(f"""
                    <div style="background-color:#1e293b; padding:20px; border-radius:15px; text-align:center; border: 2px solid #3b82f6; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
                        <p style="color:#cbd5e1; font-size:14px; margin-bottom:5px; text-transform:uppercase; letter-spacing:1px;">本次出库合计金额</p>
                        <p style="color:#3b82f6; font-size:42px; font-weight:bold; margin:0;">¥ {total_val:,.2f}</p>
                    </div>
                    """, unsafe_allow_html=True)
                
                st.write("") # 间距

                if st.button("🚀 确认提交并扣减库存", use_container_width=True):
                    if num <= 0:
                        st.error("请输入出库重量")
                    else:
                        current_row = df_p[(df_p['name'] == target_p) & (df_p['spec'] == target_s)]
                        current_stock = float(current_row['stock'].values[0])
                        
                        if num > current_stock:
                            st.error(f"库存不足！当前仅剩 {current_stock} 公斤")
                        else:
                            with engine.connect() as conn:
                                # 扣减库存
                                conn.execute(text("UPDATE products SET stock = stock - :n WHERE name = :p AND spec = :s"),
                                             {"n": num, "p": target_p, "s": target_s})
                                # 记录流水（此处建议根据你数据库结构添加 INSERT orders 的逻辑）
                                conn.commit()
                            st.success(f"✅ {selected_option} 已成功出库！")
                            st.cache_data.clear()
                            
        except Exception as e:
            st.error(f"模块运行异常: {e}")

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
                st.dataframe(df_cust, width='stretch', hide_index=True)
            except:
                st.info("暂无客户资料数据")





