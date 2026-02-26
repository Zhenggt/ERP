import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta, timezone

# --- 1. 配置与北京时间获取 ---
st.set_page_config(page_title="铝业进销存系统", layout="wide")

def get_beijing_time():
    # 强制获取北京时间 UTC+8
    beijing_tz = timezone(timedelta(hours=8))
    return datetime.now(beijing_tz)

@st.cache_resource
def get_engine():
    try:
        # 强制数据库会话也使用北京时区
        return create_engine(
            st.secrets["db_uri"], 
            pool_pre_ping=True, 
            pool_recycle=3600,
            connect_args={"options": "-c timezone=Asia/Shanghai"}
        )
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
                        # 入库流水记录
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
                
                # 金额实时跳动大屏
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
        st.header("🧾 历史交易记录")
        bj_now = get_beijing_time()
        try:
            # SQL 中查询原始 ID 以便删除
            query = """
                SELECT 
                    id,
                    created_at AT TIME ZONE 'Asia/Shanghai' as raw_time,
                    TO_CHAR(created_at AT TIME ZONE 'Asia/Shanghai', 'YYYY-MM-DD HH24:MI') as 时间, 
                    type as 类型, customer as 客户, product as 货品, 
                    num as 数量, price as 单价, total_amount as 总计 
                FROM orders ORDER BY created_at DESC
            """
            df_o = pd.read_sql(query, engine)
            
            if not df_o.empty:
                df_o['raw_time'] = pd.to_datetime(df_o['raw_time']).dt.tz_localize(None)

                # --- 筛选过滤区 ---
                st.write("🔍 **数据筛选**")
                c1, c2, c3 = st.columns([2, 1, 1])
                with c1:
                    date_range = st.date_input("日期范围", value=(bj_now.date(), bj_now.date()))
                with c2:
                    filter_type = st.selectbox("记录类型", ["全部", "销售", "进货"])
                with c3:
                    search_query = st.text_input("货品搜索", "")

                f_df = df_o.copy()
                if isinstance(date_range, tuple) and len(date_range) == 2:
                    f_df = f_df[(f_df['raw_time'].dt.date >= date_range[0]) & (f_df['raw_time'].dt.date <= date_range[1])]
                if filter_type != "全部":
                    f_df = f_df[f_df['类型'] == filter_type]
                if search_query:
                    f_df = f_df[f_df['货品'].str.contains(search_query, case=False, na=False)]

                st.divider()
                st.info(f"💰 选定范围内合计金额：**¥ {f_df['总计'].sum():,.2f}**")
                
                # 展示表格（隐藏 ID 列和原始时间列）
                display_df = f_df.drop(columns=['id', 'raw_time'])
                st.dataframe(display_df, width='stretch', hide_index=True)
                
                # --- 🛠️ 记录管理（撤销功能） ---
                st.subheader("🛠️ 记录管理")
                with st.expander("点击展开管理选项（可撤销错误记录）"):
                    st.warning("注意：撤销“销售”记录会自动回补库存，撤销“进货”记录会扣减库存。")
                    # 让用户选择要撤销的记录 ID（显示品名和时间供辨认）
                    undo_options = f_df.apply(lambda x: f"ID:{x['id']} | {x['时间']} | {x['货品']} | {x['数量']}kg", axis=1).tolist()
                    target_undo = st.selectbox("选择要作废的记录", ["-- 请选择 --"] + undo_options)
                    
                    if st.button("❌ 确认作废并回滚库存"):
                        if target_undo != "-- 请选择 --":
                            # 提取选中的 ID
                            selected_id = int(target_undo.split(" | ")[0].split(":")[1])
                            record = f_df[f_df['id'] == selected_id].iloc[0]
                            
                            # 解析品名和规格（从 "品名 | 规格" 中拆分）
                            p_info = record['货品'].split(" | ")
                            p_name = p_info[0]
                            p_spec = p_info[1] if len(p_info) > 1 else ""
                            p_num = record['数量']
                            p_type = record['类型']

                            with engine.connect() as conn:
                                # 1. 回滚库存
                                if p_type == "销售":
                                    # 销售撤销 = 库存增加
                                    conn.execute(text("UPDATE products SET stock = stock + :n WHERE name = :p AND spec = :s"),
                                                 {"n": p_num, "p": p_name, "s": p_spec})
                                elif p_type == "进货":
                                    # 进货撤销 = 库存减少
                                    conn.execute(text("UPDATE products SET stock = stock - :n WHERE name = :p AND spec = :s"),
                                                 {"n": p_num, "p": p_name, "s": p_spec})
                                
                                # 2. 删除流水记录
                                conn.execute(text("DELETE FROM orders WHERE id = :id"), {"id": selected_id})
                                conn.commit()
                            
                            st.success(f"✅ 记录 {selected_id} 已作废，库存已回滚！")
                            st.cache_data.clear()
                            st.rerun() # 刷新页面看效果
                
                csv = display_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button("📥 导出当前报表", data=csv, file_name="history.csv")
            else:
                st.info("暂无交易记录")
        except Exception as e:
            st.error(f"查询流水失败: {e}")
 # --- E. 客户档案 ---
    elif menu == "👥 客户档案":
        st.header("👥 客户信息档案")
        
        # 1. 录入新客户
        with st.expander("➕ 添加新客户", expanded=True):
            with st.form("cust_form", clear_on_submit=True):
                c1, c2 = st.columns(2)
                with c1:
                    c_name = st.text_input("客户/单位名称*", placeholder="必填")
                    c_phone = st.text_input("联系电话")
                with c2:
                    c_address = st.text_input("联系地址")
                    c_note = st.text_input("备注信息")
                
                if st.form_submit_button("保存客户信息"):
                    if c_name:
                        with engine.connect() as conn:
                            # 确保数据库表支持这些字段，如果报错请看下方的 SQL 修复
                            conn.execute(text("""
                                INSERT INTO customers (name, phone, address, note) 
                                VALUES (:n, :p, :a, :nt) 
                                ON CONFLICT (name) DO UPDATE SET 
                                    phone = EXCLUDED.phone, 
                                    address = EXCLUDED.address,
                                    note = EXCLUDED.note
                            """), {"n": c_name, "p": c_phone, "a": c_address, "nt": c_note})
                            conn.commit()
                        st.success(f"✅ 客户【{c_name}】资料已保存/更新")
                        st.cache_data.clear()
                    else:
                        st.error("请输入客户名称")

        # 2. 客户列表与管理
        st.divider()
        st.subheader("📋 客户清单")
        try:
            df_cust = pd.read_sql("SELECT name as 客户名称, phone as 电话, address as 地址, note as 备注 FROM customers ORDER BY name", engine)
            if not df_cust.empty:
                # 展示表格
                st.dataframe(df_cust, width='stretch', hide_index=True)
                
                # 删除客户功能
                with st.expander("🗑️ 客户档案维护（删除）"):
                    del_target = st.selectbox("选择要移除的客户", ["-- 请选择 --"] + df_cust['客户名称'].tolist())
                    if st.button("确认移除该客户"):
                        if del_target != "-- 请选择 --":
                            with engine.connect() as conn:
                                conn.execute(text("DELETE FROM customers WHERE name = :n"), {"n": del_target})
                                conn.commit()
                            st.success(f"已移除客户：{del_target}")
                            st.cache_data.clear()
                            st.rerun()
            else:
                st.info("暂无客户信息，请通过上方表单添加。")
        except Exception as e:
            st.error(f"加载列表失败，可能需要升级数据库字段：{e}")


