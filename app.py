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
    
    # 1. 定义全部菜单，在末尾加入回收站
    all_menus = [
        "📊 库存看板", 
        "📥 采购入库", 
        "📤 销售出库", 
        "🧾 历史流水", 
        "👥 客户档案", 
        "🔔 订单审核", 
        "💰 财务对账", 
        "📈 经营看板",
        "♻️ 回收站"  # 新增
    ]
    
    # 2. 动态过滤：员工只看前三项，管理员看全部
    display_menu = all_menus[:3] if role == "staff" else all_menus
    
    st.sidebar.title(f"👤 {'管理员' if role == 'admin' else '员工'}")
    
    # 3. 渲染菜单
    menu = st.sidebar.radio("功能导航", display_menu)
    
    # 退出登录逻辑
    if st.sidebar.button("安全退出", width='stretch'):
        del st.session_state["password_correct"]
        st.session_state["user_role"] = None
        st.rerun()

    # --- 下面开始进入各个功能的具体代码 ---
    if menu == "📊 库存看板":
        pass # 原有代码...
    
    # ... 中间其他功能代码 ...
    
    # --- 最后加入回收站的入口 ---
    elif menu == "♻️ 回收站":
        # 这里放我之前发给你的“模块 G: 回收站”的完整代码
        st.header("♻️ 数据回收站")
        # (此处省略具体逻辑，请确保下面接上之前修复好的 G 模块代码)

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
        st.header("📤 销售出库")
        
        # 1. 准备数据
        df_p = pd.read_sql("SELECT name, spec, stock FROM products WHERE stock > 0", engine)
        df_c = pd.read_sql("SELECT name, phone, address, remark FROM customers", engine)
        
        if not df_p.empty:
            df_p['display'] = df_p['name'] + " | " + df_p['spec'].fillna("标准")
            col1, col2 = st.columns(2)
            with col1:
                t_c = st.selectbox("👤 选择客户", ["散客"] + df_c['name'].tolist())
                s_o = st.selectbox("📦 选择货品", df_p['display'].tolist())
            with col2:
                num = st.number_input("⚖️ 重量 (kg)", min_value=0.0)
                price = st.number_input("💰 单价 (元)", min_value=0.0)
                pay_s = st.radio("付款状态", ["已结清", "客户欠款"], horizontal=True)
            
            # 你要求的“单据备注”
            user_remark = st.text_input("📝 本单备注", placeholder="如：加急、自提、或特殊要求")
            
            total = round(num * price, 2)
            st.info(f"合计金额：¥ {total:,.2f}")
            
            if st.button("确认提交并生成单据", width='stretch'):
                # --- 关键：解决北京时间 ---
                # 无论服务器在哪，强制计算北京时间
                bj_time_now = datetime.now(timezone(timedelta(hours=8)))
                bj_str = bj_time_now.strftime('%Y-%m-%d %H:%M:%S')
                
                # --- 关键：抓取客户资料及其备注 ---
                c_phone, c_address, c_file_remark = "未登记", "无地址", ""
                if t_c != "散客":
                    cust_info = df_c[df_c['name'] == t_c].iloc[0]
                    c_phone = cust_info['phone'] if cust_info['phone'] else "未登记"
                    c_address = cust_info['address'] if cust_info['address'] else "无地址"
                    c_file_remark = cust_info['remark'] if cust_info['remark'] else ""

                # 数据库写入
                p_n, p_s = s_o.split(" | ")[0], s_o.split(" | ")[1]
                p_status = 'paid' if pay_s == "已结清" else 'unpaid'
                
                with engine.connect() as conn:
                    conn.execute(text("UPDATE products SET stock = stock - :n WHERE name = :p AND spec = :s"), {"n": num, "p": p_n, "s": p_s})
                    conn.execute(text("""
                        INSERT INTO orders (type, customer, product, num, price, total_amount, payment_status, created_at) 
                        VALUES ('销售', :c, :p, :n, :pr, :t, :ps, :dt)
                    """), {"c": t_c, "p": s_o, "n": num, "pr": price, "t": total, "ps": p_status, "dt": bj_str})
                    conn.commit()
                
                st.success(f"✅ 出库成功！记录时间：{bj_str}")

                # --- 核心：完全复刻你的经典三联单样式 ---
                bill_html = f"""
                <div id="bill" style="width:185mm; padding:8mm; border:2px dashed #000; font-family:'SimSun', 'Songti SC', serif; background:#fff; color:#000; margin:auto;">
                    <h2 style="text-align:center; font-size:26px; font-weight:bold; letter-spacing:10px; text-decoration:underline; margin-bottom:15px;">销售出库单</h2>
                    
                    <table style="width:100%; font-size:15px; margin-bottom:10px;">
                        <tr>
                            <td><strong>收货单位：</strong>{t_c}</td>
                            <td style="text-align:right;"><strong>日期：</strong>{bj_time_now.strftime('%Y-%m-%d %H:%M')}</td>
                        </tr>
                        <tr>
                            <td colspan="2"><strong>联系电话：</strong>{c_phone} &nbsp;&nbsp; <strong>收货地址：</strong>{c_address}</td>
                        </tr>
                    </table>

                    <table style="width:100%; border-collapse:collapse; border:2px solid #000; text-align:center;">
                        <thead>
                            <tr style="background:#f2f2f2;">
                                <th style="border:2px solid #000; padding:8px;">货品名称</th>
                                <th style="border:2px solid #000; padding:8px;">规格型号</th>
                                <th style="border:2px solid #000; padding:8px;">重量(kg)</th>
                                <th style="border:2px solid #000; padding:8px;">单价</th>
                                <th style="border:2px solid #000; padding:8px;">金额</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr style="height:60px;">
                                <td style="border:2px solid #000;">{p_n}</td>
                                <td style="border:2px solid #000;">{p_s}</td>
                                <td style="border:2px solid #000;">{num}</td>
                                <td style="border:2px solid #000;">{price}</td>
                                <td style="border:2px solid #000;">{total}</td>
                            </tr>
                            <tr>
                                <td style="border:2px solid #000; font-weight:bold;">单据备注</td>
                                <td colspan="4" style="border:2px solid #000; text-align:left; padding-left:15px;">
                                    {user_remark} &nbsp; {"(档案备注: "+c_file_remark+")" if c_file_remark else ""}
                                    <span style="float:right; margin-right:15px;">状态：{"【已结清】" if p_status=='paid' else "【客户欠款】"}</span>
                                </td>
                            </tr>
                        </tbody>
                    </table>

                    <div style="margin-top:30px; display:flex; justify-content:space-between; font-size:15px;">
                        <span>制单：{st.session_state['user_role']}</span>
                        <span>送货人签字：__________</span>
                        <span>收货人签字：__________</span>
                    </div>
                </div>

                <div style="text-align:center; margin-top:15px;">
                    <button onclick="window.print()" style="padding:10px 40px; background:#000; color:#fff; border:none; cursor:pointer; font-size:16px;">
                        🖨️ 点击打印单据
                    </button>
                </div>
                """
                st.components.v1.html(bill_html, height=550)
                st.cache_data.clear()
   # --- 模块 D: 历史流水 (强力修复：保证出数据版) ---
    elif menu == "🧾 历史流水":
        st.header("🧾 业务流水记录")
        
        # 1. 直接读取原始数据
        df_history = pd.read_sql("SELECT * FROM orders ORDER BY id DESC", engine)
        
        if not df_history.empty:
            # 2. 转换时间格式（先转成 Pandas 时间对象）
            df_history['created_at'] = pd.to_datetime(df_history['created_at'])
            
            # --- 关键：手动补时差 ---
            # 如果你发现时间还是慢了8小时，就把下面这行开头的 # 号删掉
            # df_history['created_at'] = df_history['created_at'] + pd.Timedelta(hours=8)
            
            # 3. 格式化为整齐的字符串显示
            df_history['交易时间'] = df_history['created_at'].dt.strftime('%m-%d %H:%M')
            
            # 4. 汉化状态图标
            status_map = {'paid': '✅ 已结', 'unpaid': '❌ 欠款', 'pending': '⏳ 待审'}
            df_history['付款状态'] = df_history['payment_status'].map(status_map).fillna(df_history['payment_status'])
            
            # 5. 定义要显示的列（严格匹配数据库字段名）
            # 确保这些字段名在你数据库里都是存在的
            display_cols = {
                'id': 'ID',
                '交易时间': '时间',
                'type': '类型',
                'customer': '客户',
                'product': '货品',
                'num': '重量',
                'total_amount': '金额',
                '付款状态': '状态'
            }
            
            # 6. 渲染表格
            st.dataframe(
                df_history[list(display_cols.keys())].rename(columns=display_cols),
                width='stretch',
                hide_index=True
            )

            # --- 7. 管理员删除功能 ---
            if role == "admin":
                st.divider()
                with st.expander("🗑️ 删除记录"):
                    del_id = st.number_input("输入要删除的记录 ID", step=1, value=0)
                    if st.button("确认删除", type="primary", width='stretch'):
                        if del_id > 0:
                            with engine.connect() as conn:
                                conn.execute(text("DELETE FROM orders WHERE id = :id"), {"id": del_id})
                                conn.commit()
                            st.success(f"ID {del_id} 已删除")
                            st.rerun()
        else:
            st.info("暂无流水数据")

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

# --- 模块 G: 回收站 (逻辑删除管理) ---
    elif menu == "♻️ 回收站":
        st.header("♻️ 数据回收站")
        st.markdown("---")
        
        # 使用标签页区分 订单 和 客户
        tab_order, tab_cust = st.tabs(["📄 订单回收站", "👥 客户回收站"])

        with tab_order:
            # 读取 is_active = 0 的订单 (即被移入回收站的)
            df_trash_o = pd.read_sql("SELECT id, created_at, type, customer, product, num, total_amount FROM orders WHERE is_active = 0 ORDER BY id DESC", engine)
            
            if not df_trash_o.empty:
                st.warning("以下订单已从正常流水中隐藏。还原订单将重新扣除/增加相应库存。")
                st.dataframe(df_trash_o, width='stretch', hide_index=True)
                
                c1, c2 = st.columns(2)
                with c1:
                    res_o_id = st.number_input("输入要【还原】的订单 ID", step=1, value=0, key="res_order")
                    if st.button("⏪ 撤销删除（还原数据）", width='stretch'):
                        if res_o_id > 0:
                            with engine.connect() as conn:
                                # 1. 还原前先查出货品和数量，准备重新扣减库存
                                order = conn.execute(text("SELECT product, num FROM orders WHERE id = :id"), {"id": res_o_id}).fetchone()
                                if order:
                                    p_display, n_val = order[0], order[1]
                                    # 拆分品名和规格
                                    p_parts = p_display.split(" | ")
                                    p_n = p_parts[0]
                                    p_s = p_parts[1] if len(p_parts) > 1 else "标准"
                                    
                                    # 2. 重新扣库存 (假设还原的是销售单)
                                    conn.execute(text("UPDATE products SET stock = stock - :n WHERE name = :p AND spec = :s"), {"n": n_val, "p": p_n, "s": p_s})
                                    # 3. 将状态改回 1
                                    conn.execute(text("UPDATE orders SET is_active = 1 WHERE id = :id"), {"id": res_o_id})
                                    conn.commit()
                                    st.success(f"✅ ID {res_o_id} 已还原，库存已同步更新")
                                    st.rerun()
                with c2:
                    del_o_id = st.number_input("输入要【粉碎】的订单 ID", step=1, value=0, key="kill_order")
                    if st.button("🔥 彻底粉碎（不可恢复）", type="primary", width='stretch'):
                        if del_o_id > 0:
                            with engine.connect() as conn:
                                conn.execute(text("DELETE FROM orders WHERE id = :id"), {"id": del_o_id})
                                conn.commit()
                            st.error(f"💀 ID {del_o_id} 已永久删除")
                            st.rerun()
            else:
                st.info("订单回收站目前是空的。")

        with tab_cust:
            # 读取 is_active = 0 的客户
            df_trash_c = pd.read_sql("SELECT name, phone, address, remark FROM customers WHERE is_active = 0", engine)
            
            if not df_trash_c.empty:
                st.dataframe(df_trash_c, width='stretch', hide_index=True)
                res_c_name = st.selectbox("选择要还原的客户", df_trash_c['name'].tolist())
                if st.button("⏪ 还原该客户资料"):
                    with engine.connect() as conn:
                        # 给订单表增加 is_active 字段 (默认值 1 代表正常数据)
                        conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS is_active INTEGER DEFAULT 1"))
                        # 给客户表增加 is_active 字段 (默认值 1 代表正常数据)
                        conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS is_active INTEGER DEFAULT 1"))
                        conn.commit()
                    st.success(f"✅ 客户 {res_c_name} 已重新回到档案库")
                    st.rerun()
            else:
                st.write("客户回收站没有记录。")


