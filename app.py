import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime

# --- 1. 配置与性能优化 ---
st.set_page_config(page_title="铝业进销存系统 2026", layout="wide")

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
    menu = st.sidebar.radio("请选择操作", ["📊 库存看板", "📥 采购入库", "📤 销售出库", "🧾 历史流水", "👥 客户档案"])
    
    if st.sidebar.button("退出登录"):
        del st.session_state["password_correct"]
        st.rerun()

    # --- A. 库存看板 ---
    if menu == "📊 库存看板":
        st.header("📈 实时库存报表")
        @st.cache_data(ttl=5)
        def load_inventory():
            query = 'SELECT name as 品名, spec as 规格, stock as "库存余量(公斤)" FROM products ORDER BY name, spec ASC'
            return pd.read_sql(query, engine)
        
        try:
            df = load_inventory()
            if not df.empty:
                c1, c2 = st.columns(2)
                c1.metric("📦 库存总重", f"{df['库存余量(公斤)'].sum():,.2f} 公斤")
                c2.metric("🔢 货品种类", f"{len(df)} 种")
                st.divider()
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
                num = st.number_input("入库重量 (公斤)", min_value=0.0, step=0.1)
                in_price = st.number_input("采购单价 (元/公斤)", min_value=0.0, step=0.01)
            
            if st.form_submit_button("确认入库"):
                if name:
                    with engine.connect() as conn:
                        conn.execute(text("""
                            INSERT INTO products (name, spec, stock) VALUES (:n, :s, :num) 
                            ON CONFLICT (name, spec) DO UPDATE SET stock = products.stock + :num
                        """), {"n": name, "s": spec, "num": num})
                        # 入库也记一笔流水
                        conn.execute(text("""
                            INSERT INTO orders (type, customer, product, num, price, total_amount) 
                            VALUES ('进货', '供应商', :p, :n, :pr, :t)
                        """), {"p": f"{name} | {spec}", "n": num, "pr": in_price, "t": num * in_price})
                        conn.commit()
                    st.success(f"✅ {name} | {spec} 已成功入库")
                    st.cache_data.clear()

    # --- C. 销售出库 ---
    elif menu == "📤 销售出库":
        st.header("📤 销售出库单")
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
                    selected_option = st.selectbox("📦 选择货品", df_p['display_name'].tolist())
                
                target_p = selected_option.split(" | ")[0]
                target_s = selected_option.split(" | ")[1]
                if target_s == "无规格": target_s = ""

                with col2:
                    num = st.number_input("⚖️ 出库重量", min_value=0.0, step=0.01)
                    price = st.number_input("💰 销售单价", min_value=0.0, step=0.01)

                total_val = round(num * price, 2)
                
                # 金额大屏显示
                st.markdown(f"""
                <div style="background-color:#1e293b; padding:20px; border-radius:15px; text-align:center; border: 2px solid #3b82f6; margin: 15px 0;">
                    <p style="color:#cbd5e1; font-size:14px; margin:0;">本次合计金额</p>
                    <p style="color:#3b82f6; font-size:42px; font-weight:bold; margin:0;">¥ {total_val:,.2f}</p>
                </div>
                """, unsafe_allow_html=True)

                if st.button("🚀 确认提交并扣减库存", use_container_width=True):
                    current_stock = float(df_p[df_p['display_name'] == selected_option]['stock'].values[0])
                    if num > current_stock:
                        st.error(f"库存不足！当前仅剩 {current_stock} 公斤")
                    elif num <= 0:
                        st.error("请输入重量")
                    else:
                        with engine.connect() as conn:
                            conn.execute(text("UPDATE products SET stock = stock - :n WHERE name = :p AND spec = :s"),
                                         {"n": num, "p": target_p, "s": target_s})
                            conn.execute(text("""
                                INSERT INTO orders (type, customer, product, num, price, total_amount) 
                                VALUES ('销售', :c, :p, :n, :pr, :t)
                            """), {"c": target_c, "p": selected_option, "n": num, "pr": price, "t": total_val})
                            conn.commit()
                        st.success(f"✅ {selected_option} 出库成功！")
                        st.cache_data.clear()
        except Exception as e:
            st.error(f"运行异常: {e}")

    # --- D. 历史流水 ---
    elif menu == "🧾 历史流水":
        st.header("🧾 进销存历史记录")
        try:
            # 1. 查询数据：AT TIME ZONE 将 UTC 转为北京时间
            query = """
                SELECT 
                    TO_CHAR(created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Shanghai', 'YYYY-MM-DD HH24:MI') as 时间, 
                    type as 类型, 
                    customer as 客户, 
                    product as 货品, 
                    num as 数量, 
                    price as 单价, 
                    total_amount as 总计 
                FROM orders 
                ORDER BY created_at DESC
            """
            df_o = pd.read_sql(query, engine)
            
            if not df_o.empty:
                # --- 2. 筛选功能栏 ---
                col1, col2 = st.columns(2)
                with col1:
                    # 按货品搜索
                    search_query = st.text_input("🔍 按货品或规格搜索", "")
                with col2:
                    # 按类型筛选 (全部/销售/进货)
                    filter_type = st.selectbox("📅 记录类型", ["全部", "销售", "进货"])

                # --- 3. 执行过滤逻辑 ---
                filtered_df = df_o.copy()
                if search_query:
                    filtered_df = filtered_df[filtered_df['货品'].str.contains(search_query, case=False, na=False)]
                
                if filter_type != "全部":
                    filtered_df = filtered_df[filtered_df['类型'] == filter_type]

                # --- 4. 展示筛选后的结果 ---
                st.write(f"共找到 {len(filtered_df)} 条记录")
                st.dataframe(filtered_df, width='stretch', hide_index=True)
                
                # 可选：导出按钮
                csv = filtered_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button("📥 下载当前报表 (Excel可开)", data=csv, file_name=f"流水_{datetime.now().strftime('%Y%m%d')}.csv")
            else:
                st.info("暂无交易记录")
        except Exception as e:
            st.error(f"查询失败: {e}")

    # --- E. 客户档案 ---
    elif menu == "👥 客户档案":
        st.header("👥 客户信息档案")
        c_name = st.text_input("新增客户名")
        if st.button("保存客户"):
            if c_name:
                with engine.connect() as conn:
                    conn.execute(text("INSERT INTO customers (name) VALUES (:n) ON CONFLICT DO NOTHING"), {"n": c_name})
                    conn.commit()
                st.success("客户已保存")
                st.cache_data.clear()

