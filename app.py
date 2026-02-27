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
           # --- 1. 在界面上增加备注输入框 ---
            with col1:
                t_c = st.selectbox("👤 客户", ["散客"] + df_c['name'].tolist())
                s_o = st.selectbox("📦 货品", df_p['display'].tolist())
            with col2:
                num = st.number_input("⚖️ 重量 (kg)", min_value=0.0)
                price = st.number_input("💰 单价 (元)", min_value=0.0)
                pay_s = st.radio("付款状态", ["已结清", "客户欠款"], horizontal=True)
            
            # 这里新增一行：备注输入框
            user_remark = st.text_input("📝 单据备注", placeholder="如：自提、规格特殊要求等")
            
            total = round(num * price, 2)
            st.info(f"合计金额：¥ {total:,.2f}")
            
            if st.button("确认提交并生成单据", width='stretch'):
                # ... (中间的库存检查逻辑保持不变) ...
                
                # --- 2. 数据库写入逻辑（把备注存进数据库） ---
                # 注意：这里如果你的数据库没有备注字段，我会把备注拼在 product 后面或者存入对应的字段
                p_status = 'paid' if pay_s == "已结清" else 'unpaid'
                
                # 抓取客户档案
                c_phone, c_address = "未登记", "无地址"
                if t_c != "散客":
                    with engine.connect() as conn:
                        res = conn.execute(text("SELECT phone, address FROM customers WHERE name = :n"), {"n": t_c}).fetchone()
                        if res:
                            c_phone = res[0] if res[0] else "未登记"
                            c_address = res[1] if res[1] else "无地址"

                # 写入数据库
                with engine.connect() as conn:
                    # 建议将备注信息拼接到订单记录中
                    conn.execute(text("""
                        INSERT INTO orders (type, customer, product, num, price, total_amount, payment_status) 
                        VALUES ('销售', :c, :p, :n, :pr, :t, :ps)
                    """), {"c": t_c, "p": f"{s_o} (备注:{user_remark})", "n": num, "pr": price, "t": total, "ps": p_status})
                    conn.commit()
                
                st.success("✅ 出库成功！")

                # --- 3. 修改三联单 HTML 模板，显示备注 ---
                bill_html = f"""
                <style>
                    /* ... 之前的 CSS 样式保持不变 ... */
                    .bill-container {{ width: 185mm; padding: 10mm; border: 2px dashed #000; font-family: 'SimSun'; color: #000; background: #fff; margin: 10px auto; }}
                    .data-table {{ width: 100%; border-collapse: collapse; border: 2px solid #000; }}
                    .data-table th, .data-table td {{ border: 2px solid #000; padding: 10px; text-align: center; }}
                </style>
                <div id="print_area">
                    <div class="bill-container">
                        <div style="text-align:center; font-size:26px; font-weight:bold; margin-bottom:15px;">销售出库单</div>
                        <div style="display:flex; justify-content:space-between; margin-bottom:10px;">
                            <span>收货单位：{t_c}</span>
                            <span>日期：{get_beijing_time().strftime('%Y-%m-%d %H:%M')}</span>
                        </div>
                        <div style="margin-bottom:10px;">联系电话：{c_phone} | 地址：{c_address}</div>
                        
                        <table class="data-table">
                            <thead>
                                <tr>
                                    <th>货品名称</th><th>规格</th><th>重量(kg)</th><th>单价</th><th>金额</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr style="height:60px;">
                                    <td>{s_o.split(" | ")[0]}</td><td>{s_o.split(" | ")[1]}</td><td>{num}</td><td>{price}</td><td>{total}</td>
                                </tr>
                                <tr>
                                    <td><strong>备注信息</strong></td>
                                    <td colspan="4" style="text-align:left; padding-left:15px;">
                                        {user_remark} | 状态：{"已结清" if p_status=='paid' else "欠款"}
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                        <div style="margin-top:20px; display:flex; justify-content:space-between;">
                            <span>制单：{role}</span>
                            <span>送货签字：__________</span>
                            <span>收货人签字：__________</span>
                        </div>
                    </div>
                </div>
                <div style="text-align:center;"><button onclick="window.print()">🖨️ 打印单据</button></div>
                """
                st.components.v1.html(bill_html, height=550)
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

    # --- E. 客户档案 (带备注功能) ---
    elif menu == "👥 客户档案":
        st.header("👥 客户信息管理")
        
        # 自动检查并添加备注字段（防止报错）
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS remark TEXT"))
            conn.commit()

        # 1. 新增客户表单
        with st.form("add_cust", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                c_n = st.text_input("客户名称 (必填)")
                c_p = st.text_input("联系电话")
            with col2:
                c_a = st.text_input("收货地址")
                c_r = st.text_input("客户备注 (如：优惠级别、特殊要求)")
            
            if st.form_submit_button("➕ 添加新客户", width='stretch'):
                if c_n:
                    with engine.connect() as conn:
                        conn.execute(text("""
                            INSERT INTO customers (name, phone, address, remark) 
                            VALUES (:n, :p, :a, :r)
                        """), {"n": c_n, "p": c_p, "a": c_a, "r": c_r})
                        conn.commit()
                    st.success(f"✅ 客户 {c_n} 已录入档案")
                    st.cache_data.clear()
                else:
                    st.error("请输入客户名称")

        st.divider()

        # 2. 客户列表显示
        st.subheader("📋 客户名录")
        df_cust = pd.read_sql("SELECT name as 客户名称, phone as 电话, address as 地址, remark as 备注 FROM customers", engine)
        
        if not df_cust.empty:
            # 使用 width='stretch' 适配 2026 最新版本
            st.dataframe(df_cust, width='stretch', hide_index=True)
            
            # 3. 删除功能 (仅管理员可见)
            if role == "admin":
                with st.expander("🗑️ 删除客户资料"):
                    del_name = st.selectbox("选择要删除的客户", df_cust['客户名称'].tolist())
                    if st.button(f"确认删除 {del_name}", type="primary"):
                        with engine.connect() as conn:
                            conn.execute(text("DELETE FROM customers WHERE name = :n"), {"n": del_name})
                            conn.commit()
                        st.success("删除成功")
                        st.rerun()
        else:
            st.info("目前还没有录入任何客户。")

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

# --- H. 经营看板 (管理员专享) ---
    elif menu == "📈 经营看板":
        st.header("📈 经营数据分析")
        
        # 1. 从数据库读取所有销售记录
        df_sales = pd.read_sql("""
            SELECT created_at, total_amount, payment_status 
            FROM orders 
            WHERE type = '销售'
        """, engine)

        if df_sales.empty:
            st.warning("目前还没有销售数据，请先去『销售出库』录入单据。")
        else:
            # 数据预处理
            df_sales['created_at'] = pd.to_datetime(df_sales['created_at'])
            df_sales['date'] = df_sales['created_at'].dt.date
            
            # 2. 核心指标卡片
            total_rev = df_sales['total_amount'].sum()
            paid_rev = df_sales[df_sales['payment_status'] == 'paid']['total_amount'].sum()
            unpaid_rev = df_sales[df_sales['payment_status'] == 'unpaid']['total_amount'].sum()

            col1, col2, col3 = st.columns(3)
            col1.metric("总销售额", f"¥ {total_rev:,.2f}")
            col2.metric("已收金额", f"¥ {paid_rev:,.2f}", delta=f"{paid_rev/total_rev*100:.1f}%" if total_rev > 0 else "0%")
            col3.metric("待收欠款", f"¥ {unpaid_rev:,.2f}", delta=f"-{unpaid_rev/total_rev*100:.1f}%", delta_color="inverse")

            st.divider()

            # 3. 销售趋势图
            st.subheader("🗓️ 每日销售走势")
            trend_data = df_sales.groupby('date')['total_amount'].sum().reset_index()
            st.line_chart(trend_data.set_index('date'), width='stretch')

            # 4. 欠款分布（按客户）
            st.subheader("👤 客户欠款排名")
            df_debt = pd.read_sql("""
                SELECT customer as 客户, SUM(total_amount) as 欠款金额 
                FROM orders 
                WHERE type = '销售' AND payment_status = 'unpaid'
                GROUP BY customer
                ORDER BY 欠款金额 DESC
            """, engine)
            
            if not df_debt.empty:
                st.bar_chart(df_debt.set_index('客户'), width='stretch')
                st.dataframe(df_debt, width='stretch', hide_index=True)
            else:
                st.success("🎉 太棒了！目前没有任何客户欠款。")





