import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta, timezone

# --- 1. 初始化 Session State (必须放在最前面) ---
if "password_correct" not in st.session_state:
    st.session_state["password_correct"] = False
if "user_role" not in st.session_state:
    st.session_state["user_role"] = None

# --- 2. 基础配置 ---
st.set_page_config(page_title="铝业ERP系统", layout="wide")

def get_beijing_time():
    return datetime.now(timezone(timedelta(hours=8)))

# 安全读取 Secrets 的函数
@st.cache_resource
def get_engine():
    try:
        # 确保能读取到 db_uri
        db_url = st.secrets["db_uri"]
        return create_engine(db_url, pool_pre_ping=True)
    except Exception as e:
        st.error("❌ 数据库配置读取失败，请检查 Secrets 中的 db_uri")
        return None

engine = get_engine()

# --- 3. 权限登录 (增加安全检查) ---
def check_password():
    if not st.session_state["password_correct"]:
        st.title("🔒 铝业生产管理系统")
        u = st.text_input("账号")
        p = st.text_input("密码", type="password")
        if st.button("登录系统", width='stretch'):
            try:
                # 检查 Secrets 中是否存在 auth 部分
                auth = st.secrets["auth"]
                if u == auth["admin_user"] and p == auth["admin_pass"]:
                    st.session_state["password_correct"] = True
                    st.session_state["user_role"] = "admin"
                    st.rerun()
                elif u == auth["staff_user"] and p == auth["staff_pass"]:
                    st.session_state["password_correct"] = True
                    st.session_state["user_role"] = "staff"
                    st.rerun()
                else:
                    st.error("🚫 账号或密码错误")
            except KeyError:
                st.error("❌ 权限配置缺失：请在 Secrets 中添加 [auth] 相关项")
        return False
    return True
# --- 3. 业务核心逻辑 ---
if check_password():
    role = st.session_state["user_role"]
    
    # 动态菜单：管理员看到全部，员工仅限前三项
    all_menus = ["📊 库存看板", "📥 采购入库", "📤 销售出库", "🧾 历史流水", "👥 客户档案", "🔔 订单审核", "💰 财务对账", "📈 经营看板"]
    display_menu = all_menus[:3] if role == "staff" else all_menus
    
    st.sidebar.title(f"👤 {'管理员' if role == 'admin' else '员工'}")
    menu = st.sidebar.radio("功能导航", display_menu)
    
    if st.sidebar.button("安全退出", width='stretch'):
        del st.session_state["password_correct"]
        st.session_state["user_role"] = None
        st.rerun()

    # --- A. 库存看板 ---
    if menu == "📊 库存看板":
        st.header("📊 当前库存")
        df = pd.read_sql('SELECT name as 品名, spec as 规格, stock as "库存(kg)" FROM products WHERE stock > 0', engine)
        st.dataframe(df, width='stretch', hide_index=True)

    # --- B. 采购入库 ---
    elif menu == "📥 采购入库":
        st.header("📥 采购入库")
        with st.form("in_form", clear_on_submit=True):
            name = st.text_input("铝材品名")
            spec = st.text_input("规格型号")
            num = st.number_input("入库重量 (kg)", min_value=0.0)
            cost = st.number_input("采购单价 (元/kg)", min_value=0.0)
            if st.form_submit_button("确认入库", width='stretch'):
                if name and num > 0:
                    with engine.connect() as conn:
                        conn.execute(text("INSERT INTO products (name, spec, stock) VALUES (:n, :s, :num) ON CONFLICT (name, spec) DO UPDATE SET stock = products.stock + :num"), {"n": name, "s": spec, "num": num})
                        conn.execute(text("INSERT INTO orders (type, customer, product, num, price, total_amount, payment_status) VALUES ('进货', '供应商', :p, :n, :pr, :t, 'paid')"), {"p": f"{name} | {spec}", "n": num, "pr": cost, "t": num*cost})
                        conn.commit()
                    st.success("进货入库成功！")
                    st.cache_data.clear()

    # --- C. 销售出库 ---
    elif menu == "📤 销售出库":
        st.header("📤 销售出库单")
        df_p = pd.read_sql("SELECT name, spec, stock FROM products WHERE stock > 0", engine)
        df_c = pd.read_sql("SELECT name FROM customers", engine)
        if not df_p.empty:
            df_p['display'] = df_p['name'] + " | " + df_p['spec'].fillna("标准")
            col1, col2 = st.columns(2)
            with col1:
                t_c = st.selectbox("👤 客户", ["散客"] + df_c['name'].tolist())
                s_o = st.selectbox("📦 货品", df_p['display'].tolist())
            with col2:
                num = st.number_input("⚖️ 重量 (kg)", min_value=0.0)
                price = st.number_input("💰 单价 (元)", min_value=0.0)
                pay_s = st.radio("付款状态", ["已结清", "客户欠款"], horizontal=True)
            
            total = round(num * price, 2)
            if st.button("确认提交并生成单据", width='stretch'):
                stock_now = float(df_p[df_p['display'] == s_o]['stock'].values[0])
                if num > stock_now: 
                    st.error(f"库存不足！当前余量：{stock_now} kg")
                elif num <= 0: 
                    st.error("请输入有效重量")
                else:
                    p_n, p_s = s_o.split(" | ")[0], s_o.split(" | ")[1]
                    p_status = 'paid' if pay_s == "已结清" else 'unpaid'
                    
                    # 1. 强行抓取客户详细档案（解决你说的读取不到信息问题）
                    c_phone, c_address = "未登记", "无地址"
                    if t_c != "散客":
                        with engine.connect() as conn:
                            res = conn.execute(text("SELECT phone, address FROM customers WHERE name = :n"), {"n": t_c}).fetchone()
                            if res:
                                c_phone = res[0] if res[0] else "未登记"
                                c_address = res[1] if res[1] else "无地址"

                    # 2. 数据库写入
                    with engine.connect() as conn:
                        conn.execute(text("UPDATE products SET stock = stock - :n WHERE name = :p AND spec = :s"), {"n": num, "p": p_n, "s": p_s})
                        conn.execute(text("""
                            INSERT INTO orders (type, customer, product, num, price, total_amount, payment_status) 
                            VALUES ('销售', :c, :p, :n, :pr, :t, :ps)
                        """), {"c": t_c, "p": s_o, "n": num, "pr": price, "t": total, "ps": p_status})
                        conn.commit()
                    
                    st.success("✅ 出库成功！")
                    st.cache_data.clear()

                    # --- 3. 核心：恢复旧版三联单 HTML 模板 ---
                    # 这个版本包含你要求的：虚线边框、宋体、针式打印尺寸、双窗口打印逻辑
                    bill_html = f"""
                    <style>
                        .bill-container {{
                            width: 185mm; 
                            padding: 10mm; 
                            border: 2px dashed #000;
                            font-family: 'SimSun', 'STSong', serif;
                            color: #000;
                            background: #fff;
                            margin: 10px auto;
                        }}
                        .bill-title {{ text-align: center; font-size: 26px; font-weight: bold; letter-spacing: 8px; margin-bottom: 15px; }}
                        .info-row {{ width: 100%; font-size: 15px; margin-bottom: 8px; display: flex; justify-content: space-between; }}
                        .data-table {{ width: 100%; border-collapse: collapse; border: 2px solid #000; margin: 10px 0; }}
                        .data-table th, .data-table td {{ border: 2px solid #000; padding: 10px; text-align: center; font-size: 15px; }}
                        .footer-row {{ width: 100%; margin-top: 30px; font-size: 15px; display: flex; justify-content: space-between; }}
                        @media print {{
                            @page {{ size: 241mm 140mm; margin: 0; }}
                            .no-print {{ display: none !important; }}
                        }}
                    </style>

                    <div id="print_area">
                        <div class="bill-container">
                            <div class="bill-title">销售出库单</div>
                            <div class="info-row">
                                <span><strong>收货单位：</strong>{t_c}</span>
                                <span><strong>日期：</strong>{get_beijing_time().strftime('%Y-%m-%d %H:%M')}</span>
                            </div>
                            <div class="info-row">
                                <span><strong>联系方式：</strong>{c_phone}</span>
                                <span><strong>收货地址：</strong>{c_address}</span>
                            </div>
                            <table class="data-table">
                                <thead>
                                    <tr>
                                        <th>货品名称</th><th>规格型号</th><th>数量(kg)</th><th>单价(元)</th><th>金额(元)</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    <tr style="height:60px;">
                                        <td>{p_n}</td><td>{p_s}</td><td>{num}</td><td>{price}</td><td>{total}</td>
                                    </tr>
                                    <tr>
                                        <td><strong>合计(大写)</strong></td>
                                        <td colspan="4" style="text-align:left; padding-left:20px;">
                                            收款状态：{"【已结清】" if p_status=='paid' else "【客户欠款】"}
                                        </td>
                                    </tr>
                                </tbody>
                            </table>
                            <div class="footer-row">
                                <span>制单：{role}</span>
                                <span>送货签字：__________</span>
                                <span>收货人签字：__________</span>
                            </div>
                        </div>
                    </div>

                    <div style="text-align:center;">
                        <button class="no-print" onclick="doPrint()" style="padding:15px 40px; background:#000; color:#fff; border:none; cursor:pointer; font-size:18px; font-weight:bold;">
                            🖨️ 打印单据 (针式打印机)
                        </button>
                    </div>

                    <script>
                    function doPrint() {{
                        var head = document.getElementsByTagName('head')[0].innerHTML;
                        var content = document.getElementById('print_area').innerHTML;
                        var win = window.open('', '', 'height=600,width=900');
                        win.document.write('<html><head>' + head + '</head><body>' + content + '</body></html>');
                        win.document.close();
                        setTimeout(function(){{ win.print(); win.close(); }}, 500);
                    }}
                    </script>
                    """
                    import streamlit.components.v1 as components
                    components.html(bill_html, height=600, scrolling=True)
    # --- D. 历史流水 (管理员) ---
    elif menu == "🧾 历史流水":
        st.header("🧾 业务流水记录")
        df_history = pd.read_sql("SELECT id, created_at, type, customer, product, num, total_amount, payment_status FROM orders ORDER BY created_at DESC", engine)
        st.dataframe(df_history, width='stretch', hide_index=True)
        if role == "admin":
            with st.expander("🗑️ 删除错误记录"):
                del_id = st.number_input("输入要删除的ID", step=1)
                if st.button("执行删除", type="primary"):
                    with engine.connect() as conn:
                        conn.execute(text("DELETE FROM orders WHERE id = :id"), {"id": del_id})
                        conn.commit()
                    st.rerun()

    # --- E. 客户档案 ---
    elif menu == "👥 客户档案":
        st.header("👥 客户信息管理")
        with st.form("add_cust"):
            c_n = st.text_input("客户名称")
            c_p = st.text_input("联系电话")
            c_a = st.text_input("地址")
            if st.form_submit_button("添加客户", width='stretch'):
                with engine.connect() as conn:
                    conn.execute(text("INSERT INTO customers (name, phone, address) VALUES (:n, :p, :a)"), {"n": c_n, "p": c_p, "a": c_a})
                    conn.commit()
                st.success("添加成功")
        df_cust = pd.read_sql("SELECT * FROM customers", engine)
        st.dataframe(df_cust, width='stretch', hide_index=True)

    # --- F. 订单审核 ---
    elif menu == "🔔 订单审核":
        st.header("🔔 待处理客户订单")
        df_pending = pd.read_sql("SELECT * FROM orders WHERE payment_status = 'pending'", engine)
        if df_pending.empty:
            st.info("暂无待审核订单")
        else:
            st.dataframe(df_pending, width='stretch')
            # 审核逻辑可在下方继续扩展

    # --- G. 财务对账 (管理员) ---
    elif menu == "💰 财务对账":
        st.header("💰 欠款对账")
        df_unpaid = pd.read_sql("SELECT id, customer, total_amount FROM orders WHERE payment_status = 'unpaid'", engine)
        st.dataframe(df_unpaid, width='stretch', hide_index=True)




