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
            # 解决别名中括号引起的语法错误
            query = 'SELECT name as 品名, spec as 规格, stock as "库存余量(公斤)" FROM products ORDER BY stock DESC'
            return pd.read_sql(query, engine)
        
        try:
            df = load_inventory()
            if not df.empty:
                st.dataframe(df, use_container_width=True, hide_index=True)
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
                        # 更新库存
                        conn.execute(text("INSERT INTO products (name, spec, stock) VALUES (:n, :s, :num) "
                                          "ON CONFLICT (name) DO UPDATE SET stock = products.stock + :num"),
                                     {"n": name, "s": spec, "num": num})
                        # 记录流水（采购也记入流水，总额=数量*单价）
                        conn.execute(text("INSERT INTO orders (type, product, num, price, total_amount) VALUES ('进货', :p, :n, :pr, :t)"),
                                     {"p": name, "n": num, "pr": in_price, "t": num * in_price})
                        conn.commit()
                    st.success(f"✅ {name} {num}公斤 已入库")
                    st.cache_data.clear()
                else:
                    st.error("请输入货品名称")

    # --- C. 销售出库 ---
    elif menu == "📤 销售出库":
        st.header("📤 销售出库单 (单位：公斤)")
        try:
            df_p = pd.read_sql("SELECT name, stock FROM products WHERE stock > 0", engine)
            df_c = pd.read_sql("SELECT name FROM customers", engine)
            
            if df_p.empty:
                st.warning("仓库目前无货，请先办理入库。")
            else:
                with st.form("out_form", clear_on_submit=True):
                    col1, col2 = st.columns(2)
                    with col1:
                        target_c = st.selectbox("👤 选择客户", ["散客"] + df_c['name'].tolist())
                        target_p = st.selectbox("📦 选择货品", df_p['name'].tolist())
                    with col2:
                        num = st.number_input("⚖️ 出库重量 (公斤)", min_value=0.0, step=0.01, format="%.2f")
                        price = st.number_input("💰 销售单价 (元/公斤)", min_value=0.0, step=0.01, format="%.2f")
                    
                    total = num * price
                    st.info(f"💡 合计：{num} 公斤 × {price} 元/公斤 = ￥{total:,.2f}")
                    
                    if st.form_submit_button("确认出库并扣减库存"):
                        current_stock = float(df_p[df_p['name'] == target_p]['stock'].values[0])
                        if num > current_stock:
                            st.error(f"❌ 库存不足！仅剩 {current_stock} 公斤")
                        elif num <= 0:
                            st.error("❌ 出库重量必须大于 0")
                        else:
                            with engine.connect() as conn:
                                conn.execute(text("UPDATE products SET stock = stock - :n WHERE name = :p"),
                                             {"n": num, "p": target_p})
                                conn.execute(text("""INSERT INTO orders (type, customer, product, num, price, total_amount) 
                                                VALUES ('销售', :c, :p, :n, :pr, :t)"""),
                                             {"c": target_c, "p": target_p, "n": num, "pr": price, "t": total})
                                conn.commit()
                            st.success(f"🚀 出库成功！{target_p} 减少 {num} 公斤")
                            st.cache_data.clear()
        except Exception as e:
            st.error(f"出库模块运行异常: {e}")

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
                st.dataframe(df_cust, use_container_width=True, hide_index=True)
            except:
                st.info("暂无客户资料")
