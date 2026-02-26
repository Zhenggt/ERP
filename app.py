import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta, timezone

# --- 1. 配置 ---
st.set_page_config(page_title="铝业管理系统", layout="wide")

def get_beijing_time():
    return datetime.now(timezone(timedelta(hours=8)))

@st.cache_resource
def get_engine():
    try:
        return create_engine(st.secrets["db_uri"], pool_pre_ping=True, 
                             connect_args={"options": "-c timezone=Asia/Shanghai"})
    except Exception as e:
        st.error(f"连接失败: {e}")
        return None

engine = get_engine()

# --- 2. 登录 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.title("🔒 登录系统")
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

# --- 3. 业务逻辑 ---
if check_password():
    st.sidebar.title("🏮 功能导航")
    menu = st.sidebar.radio("选择操作", ["📊 库存看板", "📥 采购入库", "📤 销售出库", "🧾 历史流水", "👥 客户档案"])

    # --- A. 库存看板 ---
    if menu == "📊 库存看板":
        st.header("📈 实时库存")
        try:
            df = pd.read_sql('SELECT name as 品名, spec as 规格, stock as "库存(公斤)" FROM products ORDER BY name', engine)
            if not df.empty:
                st.metric("📦 总库存重", f"{df['库存(公斤)'].sum():,.2f} 公斤")
                st.dataframe(df, width='stretch', hide_index=True)
            else:
                st.info("库存为空")
        except Exception as e:
            st.error(f"错误: {e}")

    # --- B. 采购入库 ---
    elif menu == "📥 采购入库":
        st.header("📥 采购入库")
        with st.form("in_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                name = st.text_input("货品名称")
                spec = st.text_input("规格型号")
            with c2:
                num = st.number_input("重量(公斤)", min_value=0.0)
                price = st.number_input("采购单价", min_value=0.0)
            if st.form_submit_button("确认入库"):
                if name:
                    with engine.connect() as conn:
                        conn.execute(text("INSERT INTO products (name, spec, stock) VALUES (:n, :s, :num) ON CONFLICT (name, spec) DO UPDATE SET stock = products.stock + :num"), {"n": name, "s": spec, "num": num})
                        conn.execute(text("INSERT INTO orders (type, customer, product, num, price, total_amount) VALUES ('进货', '供应商', :p, :n, :pr, :t)"), {"p": f"{name} | {spec}", "n": num, "pr": price, "t": num*price})
                        conn.commit()
                    st.success("已入库")
                    st.cache_data.clear()

    # --- C. 销售出库 ---
    elif menu == "📤 销售出库":
        st.header("📤 销售出库单")
        try:
            df_p = pd.read_sql("SELECT name, spec, stock FROM products WHERE stock > 0", engine)
            df_c = pd.read_sql("SELECT name, phone, address FROM customers", engine)
            if not df_p.empty:
                df_p['display'] = df_p['name'] + " | " + df_p['spec'].fillna("")
                col1, col2 = st.columns(2)
                with col1:
                    t_c = st.selectbox("👤 选择客户", ["散客"] + df_c['name'].tolist())
                    if t_c != "散客":
                        c_info = df_c[df_c['name'] == t_c].iloc[0]
                        st.caption(f"📞 {c_info['phone'] or '无电话'} | 📍 {c_info['address'] or '无地址'}")
                    s_o = st.selectbox("📦 选择货品", df_p['display'].tolist())
                with col2:
                    num = st.number_input("⚖️ 出库重量", min_value=0.0)
                    price = st.number_input("💰 销售单价", min_value=0.0)
                
                total = round(num * price, 2)
                st.markdown(f'<div style="background:#1e293b;padding:20px;border-radius:10px;text-align:center;border:1px solid #3b82f6;"><p style="color:#cbd5e1;margin:0;">合计金额</p><p style="color:#3b82f6;font-size:32px;font-weight:bold;margin:0;">¥ {total:,.2f}</p></div>', unsafe_allow_html=True)
                
                if st.button("确认提交并扣减库存", use_container_width=True):
                    stock_now = float(df_p[df_p['display'] == s_o]['stock'].values[0])
                    if num > stock_now: st.error("库存不足")
                    elif num <= 0: st.error("请输入重量")
                    else:
                        p_n, p_s = s_o.split(" | ")[0], s_o.split(" | ")[1]
                        with engine.connect() as conn:
                            conn.execute(text("UPDATE products SET stock = stock - :n WHERE name = :p AND spec = :s"), {"n": num, "p": p_n, "s": p_s})
                            conn.execute(text("INSERT INTO orders (type, customer, product, num, price, total_amount) VALUES ('销售', :c, :p, :n, :pr, :t)"), {"c": t_c, "p": s_o, "n": num, "pr": price, "t": total})
                            conn.commit()
                        st.success("出库成功")
                        st.cache_data.clear()
        except Exception as e:
            st.error(f"运行异常: {e}")

    # --- D. 历史流水 ---
    elif menu == "🧾 历史流水":
        st.header("🧾 交易记录")
        try:
            query = """SELECT id, created_at AT TIME ZONE 'Asia/Shanghai' as raw_time, TO_CHAR(created_at AT TIME ZONE 'Asia/Shanghai', 'YYYY-MM-DD HH24:MI') as 时间, type as 类型, customer as 客户, product as 货品, num as 数量, price as 单价, total_amount as 总计 FROM orders ORDER BY created_at DESC"""
            df_o = pd.read_sql(query, engine)
            if not df_o.empty:
                df_o['raw_time'] = pd.to_datetime(df_o['raw_time']).dt.tz_localize(None)
                c1, c2 = st.columns(2)
                with c1: dr = st.date_input("选择日期范围", value=(get_beijing_time().date(), get_beijing_time().date()))
                with c2: st.metric("选定合计", f"¥ {df_o['总计'].sum():,.2f}")
                
                st.dataframe(df_o.drop(columns=['id', 'raw_time']), width='stretch', hide_index=True)
                
                with st.expander("🛠️ 记录管理"):
                    target = st.selectbox("选择要作废的单号", ["--请选择--"] + df_o.apply(lambda x: f"ID:{x['id']} | {x['货品']}", axis=1).tolist())
                    if st.button("确认作废"):
                        if "--请选择--" not in target:
                            sid = int(target.split(" | ")[0].split(":")[1])
                            with engine.connect() as conn:
                                conn.execute(text("DELETE FROM orders WHERE id = :id"), {"id": sid})
                                conn.commit()
                            st.rerun()
            else: st.info("暂无数据")
        except Exception as e: st.error(f"失败: {e}")

    # --- E. 客户档案 ---
    elif menu == "👥 客户档案":
        st.header("👥 客户档案")
        with st.form("c_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            name = c1.text_input("客户名称*")
            phone = c1.text_input("电话")
            addr = c2.text_input("地址")
            note = c2.text_input("备注")
            if st.form_submit_button("保存"):
                if name:
                    with engine.connect() as conn:
                        conn.execute(text("INSERT INTO customers (name, phone, address, note) VALUES (:n, :p, :a, :nt) ON CONFLICT (name) DO UPDATE SET phone=EXCLUDED.phone, address=EXCLUDED.address, note=EXCLUDED.note"), {"n": name, "p": phone, "a": addr, "nt": note})
                        conn.commit()
                    st.success("保存成功")
                    st.cache_data.clear()
        
        df_c = pd.read_sql("SELECT name as 姓名, phone as 电话, address as 地址 FROM customers", engine)
        st.dataframe(df_c, width='stretch', hide_index=True)
