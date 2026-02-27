import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta, timezone

# --- 1. 基础配置 ---
st.set_page_config(page_title="铝业管理ERP系统", layout="wide")

def get_beijing_time():
    return datetime.now(timezone(timedelta(hours=8)))

@st.cache_resource
def get_engine():
    # 目前依然连接 Supabase，后续迁移国内服务器时只需改这一行
    return create_engine(st.secrets["db_uri"], pool_pre_ping=True)

engine = get_engine()

# --- 2. 权限登录系统 ---
def check_password():
    # 1. 确保 user_role 始终存在（初始化）
    if "user_role" not in st.session_state:
        st.session_state["user_role"] = None
    if "password_correct" not in st.session_state:
        st.title("🚀 铝业生产管理系统")
        with st.container():
            u = st.text_input("账号")
            p = st.text_input("密码", type="password")
            if st.button("进入系统", use_container_width=True):
                # 校验老板账号
                if u == st.secrets["auth"]["admin_user"] and p == st.secrets["auth"]["admin_pass"]:
                    st.session_state["password_correct"] = True
                    st.session_state["user_role"] = "admin"
                    st.rerun()
                # 校验员工账号
                elif u == st.secrets["auth"]["staff_user"] and p == st.secrets["auth"]["staff_pass"]:
                    st.session_state["password_correct"] = True
                    st.session_state["user_role"] = "staff"
                    st.rerun()
                else:
                    st.error("🚫 账号或密码无效")
        return False
    return True

# --- 3. 业务核心逻辑 ---
if check_password():
    role = st.session_state["user_role"]
    
    # 动态菜单分配
    admin_menu = ["📊 库存看板", "📥 采购入库", "📤 销售出库", "🧾 历史流水", "👥 客户档案", "🛒 客户下单", "🔔 订单审核", "💰 财务对账", "📈 经营看板"]
    staff_menu = ["📊 库存看板", "📥 采购入库", "📤 销售出库"] # 员工只能看到这三个
    
    st.sidebar.title(f"👤 {'管理员' if role == 'admin' else '员工操作员'}")
    menu = st.sidebar.radio("功能导航", admin_menu if role == "admin" else staff_menu)
    
    if st.sidebar.button("安全退出"):
        del st.session_state["password_correct"]
        st.rerun()

    # --- A. 库存看板 (全员可见) ---
    if menu == "📊 库存看板":
        st.header("📈 当前库存概览")
        df = pd.read_sql('SELECT name as 品名, spec as 规格, stock as "库存(kg)" FROM products WHERE stock > 0', engine)
        if not df.empty:
            st.metric("📦 库内总重", f"{df['库存(kg)'].sum():,.2f} kg")
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("仓库暂无库存")

    # --- B. 采购入库 (全员可见) ---
    elif menu == "📥 采购入库":
        st.header("📥 采购货物入库")
        with st.form("in_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            name = c1.text_input("铝材品名 (如: 6063铝棒)")
            spec = c1.text_input("规格型号")
            num = c2.number_input("入库重量 (kg)", min_value=0.0)
            cost = c2.number_input("采购单价 (元/kg)", min_value=0.0)
            if st.form_submit_button("确认入库并记账"):
                if name and num > 0:
                    with engine.connect() as conn:
                        conn.execute(text("INSERT INTO products (name, spec, stock) VALUES (:n, :s, :num) ON CONFLICT (name, spec) DO UPDATE SET stock = products.stock + :num"), {"n": name, "s": spec, "num": num})
                        conn.execute(text("INSERT INTO orders (type, customer, product, num, price, total_amount, payment_status) VALUES ('进货', '供应商', :p, :n, :pr, :t, 'paid')"), {"p": f"{name} | {spec}", "n": num, "pr": cost, "t": num*cost})
                        conn.commit()
                    st.success("入库成功！")
                    st.cache_data.clear()

# --- C. 销售出库 (修正缩进与参数版) ---
    elif menu == "📤 销售出库":
        st.header("📤 销售出库单")
        df_p = pd.read_sql("SELECT name, spec, stock FROM products WHERE stock > 0", engine)
        df_c = pd.read_sql("SELECT name, phone, address FROM customers", engine)
        
        if not df_p.empty:
            df_p['display'] = df_p['name'] + " | " + df_p['spec'].fillna("标准")
            col1, col2 = st.columns(2)
            with col1:
                t_c = st.selectbox("👤 选择客户", ["散客"] + df_c['name'].tolist())
                s_o = st.selectbox("📦 选择货品", df_p['display'].tolist())
            with col2:
                num = st.number_input("⚖️ 出库重量 (kg)", min_value=0.0)
                price = st.number_input("💰 销售单价 (元)", min_value=0.0)
                pay_s = st.radio("付款状态", ["已结清", "客户欠款"], horizontal=True)
            
            total = round(num * price, 2)
            st.info(f"合计金额：¥ {total:,.2f}")
            
            # 使用最新的 width='stretch' 参数替代 use_container_width
            if st.button("确认提交并生成单据", width='stretch'):
                # 检查库存
                stock_now = float(df_p[df_p['display'] == s_o]['stock'].values[0])
                if num > stock_now: 
                    st.error(f"库存不足！当前余量：{stock_now} kg")
                elif num <= 0: 
                    st.error("请输入有效重量")
                else:
                    p_n, p_s = s_o.split(" | ")[0], s_o.split(" | ")[1]
                    p_status = 'paid' if pay_s == "已结清" else 'unpaid'
                    
                    with engine.connect() as conn:
                        # 更新库存
                        conn.execute(text("UPDATE products SET stock = stock - :n WHERE name = :p AND spec = :s"), 
                                     {"n": num, "p": p_n, "s": p_s})
                        # 插入订单
                        conn.execute(text("""
                            INSERT INTO orders (type, customer, product, num, price, total_amount, payment_status) 
                            VALUES ('销售', :c, :p, :n, :pr, :t, :ps)
                        """), {"c": t_c, "p": s_o, "n": num, "pr": price, "t": total, "ps": p_status})
                        conn.commit()
                    
                    st.success("✅ 出库成功！")
                    st.cache_data.clear()
                    # 此处可继续添加之前的高质量三联单 HTML 代码

                    # --- 2. 恢复原来那个高质量三联单 HTML 模板 ---
                    c_info = {"phone": "未登记", "address": "无地址"}
                    if t_c != "散客":
                        res = df_c[df_c['name'] == t_c].iloc[0]
                        c_info['phone'] = res['phone'] if res['phone'] else "未登记"
                        c_info['address'] = res['address'] if res['address'] else "无地址"

                    bill_html = f"""
                    <style>
                        .bill-box {{
                            width: 185mm; 
                            padding: 10mm; 
                            border: 1.5px dashed #000;
                            font-family: 'SimSun', 'STSong', serif;
                            color: #000;
                            background: #fff;
                            margin: 10px auto;
                        }}
                        .title {{ text-align: center; font-size: 24px; font-weight: bold; letter-spacing: 5px; margin-bottom: 10px; }}
                        .info-table {{ width: 100%; font-size: 14px; margin-bottom: 5px; }}
                        .data-table {{ width: 100%; border-collapse: collapse; border: 1.5px solid #000; }}
                        .data-table th, .data-table td {{ border: 1.5px solid #000; padding: 8px; text-align: center; font-size: 14px; }}
                        .footer {{ width: 100%; margin-top: 20px; font-size: 14px; display: flex; justify-content: space-between; }}
                        @media print {{
                            .no-print {{ display: none !important; }}
                            @page {{ size: 241mm 140mm; margin: 0; }}
                        }}
                    </style>

                    <div class="bill-box" id="bill_content">
                        <div class="title">销售出库单</div>
                        <table class="info-table">
                            <tr>
                                <td><strong>收货单位:</strong> {t_c}</td>
                                <td style="text-align:right;"><strong>日期:</strong> {get_beijing_time().strftime('%Y-%m-%d %H:%M')}</td>
                            </tr>
                            <tr>
                                <td colspan="2"><strong>联系方式:</strong> {c_info['phone']} | <strong>地址:</strong> {c_info['address']}</td>
                            </tr>
                        </table>
                        <table class="data-table">
                            <thead>
                                <tr>
                                    <th>货品名称</th><th>规格型号</th><th>数量(kg)</th><th>单价(元)</th><th>金额(元)</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr style="height:50px;">
                                    <td>{p_n}</td><td>{p_s}</td><td>{num}</td><td>{price}</td><td>{total}</td>
                                </tr>
                                <tr style="height:35px;">
                                    <td>备注</td><td colspan="4">付款状态：{"已结清" if p_status=='paid' else "未付款(欠款)"}</td>
                                </tr>
                            </tbody>
                        </table>
                        <div class="footer">
                            <span>制单: {role}</span>
                            <span>送货人签字: _________</span>
                            <span>收货人签字: _________________</span>
                        </div>
                    </div>

                    <div style="text-align:center;">
                        <button class="no-print" onclick="printBill()" style="margin-top:15px; padding:12px 30px; background:#2563eb; color:white; border:none; border-radius:5px; cursor:pointer; font-size:16px; font-weight:bold;">
                            🖨️ 立即打印三联单
                        </button>
                    </div>

                    <script>
                    function printBill() {{
                        var content = document.getElementById('bill_content').innerHTML;
                        var style = document.getElementsByTagName('style')[0].innerHTML;
                        var win = window.open('', '', 'height=600,width=900');
                        win.document.write('<html><head><title>打印销售单</title><style>' + style + '</style></head><body>');
                        win.document.write(content);
                        win.document.write('</body></html>');
                        win.document.close();
                        setTimeout(function(){{ win.print(); win.close(); }}, 300);
                    }}
                    </script>
                    """
                    import streamlit.components.v1 as components
                    components.html(bill_html, height=500, scrolling=True)

    # --- D. 财务对账 (管理员可见) ---
    elif menu == "💰 财务对账" and role == "admin":
        st.header("💰 欠款对账管理")
        df_unpaid = pd.read_sql("SELECT id, customer, product, num, total_amount, TO_CHAR(created_at, 'YYYY-MM-DD') as date FROM orders WHERE payment_status = 'unpaid'", engine)
        if not df_unpaid.empty:
            st.warning(f"当前共有 {len(df_unpaid)} 笔欠款未收回")
            st.dataframe(df_unpaid.drop(columns=['id']), use_container_width=True)
            with st.expander("💳 确认收款"):
                target = st.selectbox("选择销账单号", df_unpaid.apply(lambda x: f"ID:{x['id']} | {x['customer']} | {x['total_amount']}元", axis=1))
                if st.button("标记为已收款"):
                    sid = int(target.split("|")[0].split(":")[1])
                    with engine.connect() as conn:
                        conn.execute(text("UPDATE orders SET payment_status = 'paid' WHERE id = :id"), {"id": sid})
                        conn.commit()
                    st.rerun()
        else:
            st.success("账目清晰，暂无欠款")

    # --- E. 经营看板 (管理员可见) ---
    elif menu == "📈 经营看板" and role == "admin":
        st.header("📈 经营数据看板")
        # 汇总本月销售
        df_stats = pd.read_sql("SELECT SUM(total_amount) as total FROM orders WHERE type='销售' AND created_at >= date_trunc('month', current_date)", engine)
        st.metric("本月累计销售额", f"¥ {df_stats['total'].iloc[0] or 0:,.2f}")
        # 这里可以加入 line_chart 绘制趋势图





