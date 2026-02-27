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
with engine.connect() as conn:
    conn.execute(text("UPDATE orders SET is_active = 1 WHERE is_active IS NULL"))
    conn.commit()
if engine:
    with engine.connect() as conn:
        try:
            # 1. 给 orders 表增加 is_active 字段 (1为正常, 0为回收站)
            conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS is_active INTEGER DEFAULT 1"))
            
            # 2. 给 customers 表增加 is_active 字段
            conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS is_active INTEGER DEFAULT 1"))
            
            # 提交更改
            conn.commit()
        except Exception as e:
            # 如果报错可能是因为权限问题，或者字段已存在但数据库不支持 IF NOT EXISTS
            st.warning(f"数据库结构自动检查中... (若已手动升级请忽略: {e})")
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
    

    

    # --- A. 库存看板 ---
    if menu == "📊 库存看板":
        st.header("📊 当前库存")
        df = pd.read_sql('SELECT name as 品名, spec as 规格, stock as "库存(kg)" FROM products WHERE stock > 0', engine)
        st.dataframe(df, width='stretch', hide_index=True)

  # --- 模块 B: 采购入库 (优化排版版) ---
    # --- 模块 B: 采购入库 ---
    elif menu == "📥 采购入库":
        st.header("📥 采购入库登记")
        
        # 1. 输入表单区块
        with st.form("purchase_form_clean", clear_on_submit=True):
            # 供应商信息
            supplier = st.text_input("🚚 供应商名称", placeholder="填写厂家或发货方全称")
            
            st.write("") # 增加微量间距
            
            # 货品信息并行排列
            col_p, col_s = st.columns(2)
            with col_p:
                p_name = st.text_input("货品名称", placeholder="如：铝板")
            with col_s:
                p_spec = st.text_input("规格型号", placeholder="如：6061 / 标准")
            
            # 数量金额并行排列
            col_n, col_pr = st.columns(2)
            with col_n:
                in_num = st.number_input("入库重量 (公斤)", min_value=0.0, step=0.01, format="%.2f")
            with col_pr:
                in_price = st.number_input("进货单价 (元/公斤)", min_value=0.0, step=0.01, format="%.2f")

            # 提交按钮（适配 2026 最新 width 规范）
            submit_btn = st.form_submit_button("确认提交入库", type="primary", width='stretch')

            # 2. 提交处理逻辑
            if submit_btn:
                if not supplier or not p_name:
                    st.error("⚠️ 错误：供应商和货品名称不能为空！")
                elif in_num <= 0:
                    st.error("⚠️ 错误：入库数量必须大于 0！")
                else:
                    try:
                        # 使用 begin() 开启事务：确保库存更新与流水写入【同时成功】
                        with engine.begin() as conn:
                            # A. 自动创建货品（若不存在）
                            conn.execute(text("""
                                INSERT INTO products (name, spec, stock) 
                                SELECT :p, :s, 0 
                                WHERE NOT EXISTS (
                                    SELECT 1 FROM products WHERE name = :p AND spec = :s
                                )
                            """), {"p": p_name, "s": p_spec})

                            # B. 增加库存
                            conn.execute(text("""
                                UPDATE products SET stock = stock + :n 
                                WHERE name = :p AND spec = :s
                            """), {"n": in_num, "p": p_name, "s": p_spec})
                            
                            # C. 写入历史流水 (使用 NOW() 记录数据库当前北京时间)
                            conn.execute(text("""
                                INSERT INTO orders (type, customer, product, num, total_amount, payment_status, is_active, created_at)
                                VALUES ('采购入库', :supplier, :product, :num, :amount, 'paid', 1, NOW())
                            """), {
                                "supplier": supplier,
                                "product": f"{p_name} | {p_spec}",
                                "num": in_num,
                                "amount": round(in_num * in_price, 2)
                            })
                        
                        # 3. 简洁反馈
                        st.success(f"✅ 入库成功：{supplier} | {p_name} | {in_num}公斤")
                        
                        # 停留 1.5 秒后自动刷新清空表单
                        import time
                        time.sleep(1.5)
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ 系统执行失败: {e}")
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
# --- 模块 D: 历史流水 (交互编辑版-修复版) ---
    elif "流水" in menu:
        st.header("🧾 业务流水记录")
        st.info("💡 提示：双击“状态”列下拉修改，选中行后按 Delete 键删除，完成后点击【保存修改】。")

        try:
            # 1. 获取数据 (直接读取并做初步汉化转换)
            query = "SELECT id, created_at, type, customer, product, num, total_amount, payment_status FROM orders WHERE (is_active != 0 OR is_active IS NULL) ORDER BY id DESC"
            df_history = pd.read_sql(query, engine)
            
            if not df_history.empty:
                # 时间修正
                df_history['created_at'] = pd.to_datetime(df_history['created_at']) + pd.Timedelta(hours=8)
                df_history['时间'] = df_history['created_at'].dt.strftime('%m-%d %H:%M')
                
                # 状态映射转换 (从数据库英文转为显示中文)
                status_map = {"paid": "✅ 已结", "unpaid": "❌ 欠款", "pending": "⏳ 待审"}
                df_history['payment_status'] = df_history['payment_status'].map(status_map).fillna(df_history['payment_status'])

                # 2. 使用 st.data_editor 进行交互
                edited_df = st.data_editor(
                    df_history[['id', '时间', 'type', 'customer', 'product', 'num', 'total_amount', 'payment_status']],
                    column_config={
                        "id": st.column_config.NumberColumn("ID", disabled=True), 
                        "时间": st.column_config.TextColumn("时间", disabled=True),
                        "type": st.column_config.TextColumn("类型", disabled=True),
                        "customer": st.column_config.TextColumn("客户/供应商"),
                        "product": st.column_config.TextColumn("货品"),
                        "num": st.column_config.NumberColumn("数量"),
                        "total_amount": st.column_config.NumberColumn("金额"),
                        "payment_status": st.column_config.SelectboxColumn(
                            "状态",
                            options=["✅ 已结", "❌ 欠款", "⏳ 待审"], # 直接使用显示名
                            required=True
                        )
                    },
                    width='stretch',
                    hide_index=True,
                    num_rows="dynamic" 
                )

                # 3. 保存逻辑
                if st.button("💾 保存表格中的所有修改", type="primary", width='stretch'):
                    # 识别被删除的 ID
                    current_ids = edited_df['id'].tolist()
                    original_ids = df_history['id'].tolist()
                    deleted_ids = list(set(original_ids) - set(current_ids))

                    # 状态反向映射 (存回数据库前转为英文)
                    reverse_map = {"✅ 已结": "paid", "❌ 欠款": "unpaid", "⏳ 待审": "pending"}

                    try:
                        with engine.begin() as conn:
                            # 处理删除
                            if deleted_ids:
                                conn.execute(text("UPDATE orders SET is_active = 0 WHERE id IN :ids"), {"ids": tuple(deleted_ids)})
                            
                            # 处理修改
                            for _, row in edited_df.iterrows():
                                # 将中文状态转回英文存入数据库
                                db_status = reverse_map.get(row['payment_status'], row['payment_status'])
                                conn.execute(text("""
                                    UPDATE orders SET 
                                    customer = :c, product = :p, num = :n, 
                                    total_amount = :a, payment_status = :s 
                                    WHERE id = :id
                                """), {
                                    "c": row['customer'], "p": row['product'], 
                                    "n": row['num'], "a": row['total_amount'], 
                                    "s": db_status, "id": row['id']
                                })
                        st.success("🎉 数据保存成功！")
                        import time
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ 保存失败: {e}")

            else:
                st.info("💡 暂无业务流水记录。")

        except Exception as e:
            st.error(f"❌ 数据库读取异常: {e}")
        # 4. 管理员功能区
        if role == "admin":
            st.markdown("---")
            with st.expander("🗑️ 管理员：移入回收站"):
                st.warning("提示：删除记录后库存将自动返还。")
                
                col_id, col_btn = st.columns([2, 1])
                with col_id:
                    del_id = st.number_input("请输入 ID", step=1, value=0, key="admin_del_id")
                with col_btn:
                    st.write("##") # 占位对齐
                    # 按钮也适配了新的 width='stretch'
                    if st.button("确认移入", type="primary", width='stretch'):
                        if del_id > 0:
                            with engine.connect() as conn:
                                conn.execute(text("UPDATE orders SET is_active = 0 WHERE id = :id"), {"id": del_id})
                                conn.commit()
                            st.success(f"✅ ID {del_id} 已成功移入回收站")
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

# --- G. 财务对账 ---
    elif menu == "💰 财务对账":
        st.header("💰 欠款对账与核销")
        
        try:
            # 1. 读取所有未结清账目
            query = "SELECT id, created_at, customer, product, num, total_amount FROM orders WHERE payment_status = 'unpaid' AND (is_active != 0 OR is_active IS NULL) ORDER BY id DESC"
            df_unpaid = pd.read_sql(query, engine)

            if not df_unpaid.empty:
                # 时间修正与汉化
                df_unpaid['created_at'] = pd.to_datetime(df_unpaid['created_at']) + pd.Timedelta(hours=8)
                df_unpaid['日期'] = df_unpaid['created_at'].dt.strftime('%m-%d')
                
                # --- A. 顶部汇总指标 ---
                total_debt = df_unpaid['total_amount'].sum()
                customer_count = df_unpaid['customer'].nunique()
                
                c1, c2 = st.columns(2)
                c1.metric("🚩 待收/应付总欠款", f"¥ {total_debt:,.2f}")
                c2.metric("👥 欠款单位总数", f"{customer_count} 家")
                
                st.divider()

                # --- B. 欠款分布图 (直观看出大客户) ---
                st.subheader("📊 欠款单位分布")
                debt_summary = df_unpaid.groupby('customer')['total_amount'].sum().reset_index()
                debt_summary.columns = ['客户/供应商', '欠款总额']
                st.bar_chart(debt_summary.set_index('客户/供应商'), width='stretch')

                # --- C. 交互式核销表 (使用 2026 data_editor) ---
                st.subheader("📝 欠款明细与一键结算")
                st.info("💡 提示：如需结算，请将“状态”双击改为“✅ 已结”，然后点击下方保存。")
                
                # 为编辑准备数据，增加一列状态
                df_edit = df_unpaid[['id', '日期', 'customer', 'product', 'num', 'total_amount']].copy()
                df_edit['状态'] = "❌ 未结" # 初始化显示名

                edited_df = st.data_editor(
                    df_edit,
                    column_config={
                        "id": st.column_config.NumberColumn("ID", disabled=True),
                        "日期": st.column_config.TextColumn("日期", disabled=True),
                        "customer": st.column_config.TextColumn("客户/供应商", disabled=True),
                        "total_amount": st.column_config.NumberColumn("金额", format="¥%.2f", disabled=True),
                        "状态": st.column_config.SelectboxColumn(
                            "操作结算",
                            options=["❌ 未结", "✅ 已结清"],
                            required=True
                        )
                    },
                    width='stretch',
                    hide_index=True,
                    key="debt_editor"
                )

                # --- D. 保存核销逻辑 ---
                if st.button("💾 确认提交结算修改", type="primary", width='stretch'):
                    # 找出被修改为“已结清”的 ID
                    settled_ids = edited_df[edited_df['状态'] == "✅ 已结清"]['id'].tolist()
                    
                    if settled_ids:
                        try:
                            with engine.begin() as conn:
                                conn.execute(
                                    text("UPDATE orders SET payment_status = 'paid' WHERE id IN :ids"),
                                    {"ids": tuple(settled_ids)}
                                )
                            st.success(f"🎉 成功核销 {len(settled_ids)} 笔账目！")
                            import time
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            st.error(f"核销失败: {e}")
                    else:
                        st.warning("未检测到状态变更，请先修改表格中的状态。")

            else:
                st.success("🎉 目前没有任何欠款记录，账目全清！")

        except Exception as e:
            st.error(f"❌ 对账模块异常: {e}")

# --- 模块 H: 经营看板 ---
    elif menu == "📈 经营看板":
        st.header("📈 经营数据深度分析")
        
        try:
            # 1. 宽泛读取所有流水记录
            query = "SELECT * FROM orders WHERE (is_active != 0 OR is_active IS NULL)"
            df_all = pd.read_sql(query, engine)

            if df_all.empty:
                st.warning("⚠️ 数据库中暂无流水记录。")
            else:
                # --- A. 数据清洗与北京时间对齐 ---
                df_all['type'] = df_all['type'].str.strip()
                df_all['product'] = df_all['product'].str.strip()
                # 修正北京时间 (+8小时)
                df_all['created_at'] = pd.to_datetime(df_all['created_at']) + pd.Timedelta(hours=8)
                df_all['日期'] = df_all['created_at'].dt.date

                # --- B. 成本核算：修复 Pandas GroupBy 警告 ---
                df_purchase = df_all[df_all['type'].str.contains('入|采购', na=False)]
                cost_dict = {}
                if not df_purchase.empty:
                    # 适配新版 Pandas：先选取需要的列再进行聚合，避免 apply 警告
                    cost_summary = df_purchase.groupby('product')[['total_amount', 'num']].sum()
                    cost_dict = (cost_summary['total_amount'] / cost_summary['num']).to_dict()

                # --- C. 销售数据提取 ---
                df_sales = df_all[df_all['type'].str.contains('出|销售', na=False)].copy()

                if df_sales.empty:
                    st.error("❌ 未找到销售记录。请检查流水类型。")
                else:
                    # 计算每笔利润
                    df_sales['单价'] = df_sales['total_amount'] / df_sales['num']
                    df_sales['成本单价'] = df_sales['product'].map(cost_dict).fillna(df_sales['单价'] * 0.8)
                    df_sales['纯利润'] = df_sales['total_amount'] - (df_sales['成本单价'] * df_sales['num'])

                    # --- 2. 核心指标卡 ---
                    total_rev = df_sales['total_amount'].sum()
                    total_profit = df_sales['纯利润'].sum()
                    unpaid_rev = df_sales[df_sales['payment_status'] == 'unpaid']['total_amount'].sum()

                    c1, c2, c3 = st.columns(3)
                    c1.metric("💰 累计销售总额", f"¥ {total_rev:,.2f}")
                    c2.metric("🧧 累计净利润", f"¥ {total_profit:,.2f}")
                    c3.metric("⚠️ 待收总欠款", f"¥ {unpaid_rev:,.2f}", delta_color="inverse")

                    st.divider()

                    # --- 3. 每日销售走势 (适配 2026 width='stretch') ---
                    st.subheader("📈 每日营业额走势")
                    daily_data = df_sales.groupby('日期')['total_amount'].sum().reset_index()
                    daily_data.columns = ['日期', '当日销售额']
                    
                    # 核心更新：使用 width='stretch' 替代过时的 use_container_width
                    st.line_chart(daily_data.set_index('日期'), width='stretch')

                    # --- 4. 盈利贡献详情表 ---
                    st.subheader("📋 货品盈利排行榜")
                    rank_df = df_sales.groupby('product').agg({
                        'num': 'sum', 
                        'total_amount': 'sum', 
                        '纯利润': 'sum'
                    }).reset_index().rename(columns={
                        'product': '货品', 'num': '销量', 
                        'total_amount': '销售额', '纯利润': '利润'
                    })
                    
                    st.dataframe(
                        rank_df.sort_values('利润', ascending=False),
                        column_config={
                            "销售额": st.column_config.NumberColumn("销售额", format="¥%.2f"),
                            "利润": st.column_config.NumberColumn("利润", format="¥%.2f"),
                        },
                        width='stretch', # 核心更新：适配 2026 规范
                        hide_index=True
                    )

        except Exception as e:
            st.error(f"❌ 看板加载失败: {e}")
# --- 模块 I: 回收站 (修正版) ---
    elif menu == "♻️ 回收站":
        st.header("♻️ 数据回收站")
        st.info("提示：回收站中的数据不会计入经营统计。")
        
        tab_order, tab_cust = st.tabs(["📄 订单回收站", "👥 客户回收站"])

        with tab_order:
            # 1. 从数据库读取原始数据
            df_trash_o = pd.read_sql("""
                SELECT id, created_at, type, customer, product, num, total_amount 
                FROM orders 
                WHERE is_active = 0 
                ORDER BY id DESC
            """, engine)
            
            if not df_trash_o.empty:
                # 2. 时间修正（转为北京时间并格式化）
                df_trash_o['created_at'] = pd.to_datetime(df_trash_o['created_at']) + pd.Timedelta(hours=8)
                df_trash_o['删除时间'] = df_trash_o['created_at'].dt.strftime('%Y-%m-%d %H:%M')
                
                # 3. 定义汉化映射字典
                # 把数据库字段名 (Key) 映射为你想显示的中文名 (Value)
                column_mapping = {
                    'id': '记录ID',
                    '删除时间': '删除时间',
                    'type': '类型',
                    'customer': '客户名称',
                    'product': '货品规格',
                    'num': '数量/重量',
                    'total_amount': '金额'
                }
                
                # 4. 筛选并重命名列
                # 只取映射字典里有的列，并重命名
                df_display = df_trash_o[list(column_mapping.keys())].rename(columns=column_mapping)
                
                # 5. 渲染表格 (适配 2026 版 width='stretch')
                st.dataframe(df_display, width='stretch', hide_index=True)
                
                # --- 下接还原/粉碎按钮逻辑 ---
                
                c1, c2 = st.columns(2)
                with c1:
                    res_o_id = st.number_input("输入要【还原】的订单 ID", step=1, value=0, key="res_o_val")
                    if st.button("⏪ 撤销删除（还原数据）", width='stretch'):
                        if res_o_id > 0:
                            with engine.connect() as conn:
                                order = conn.execute(text("SELECT type, product, num FROM orders WHERE id = :id"), {"id": res_o_id}).fetchone()
                                if order:
                                    o_type, p_display, n_val = order[0], order[1], order[2]
                                    p_parts = p_display.split(" | ")
                                    p_n = p_parts[0]
                                    p_s = p_parts[1] if len(p_parts) > 1 else "标准"
                                    
                                    # 判断是入库还是出库，反向操作库存
                                    if "入库" in o_type or "采购" in o_type:
                                        conn.execute(text("UPDATE products SET stock = stock + :n WHERE name = :p AND spec = :s"), {"n": n_val, "p": p_n, "s": p_s})
                                    else:
                                        conn.execute(text("UPDATE products SET stock = stock - :n WHERE name = :p AND spec = :s"), {"n": n_val, "p": p_n, "s": p_s})
                                    
                                    conn.execute(text("UPDATE orders SET is_active = 1 WHERE id = :id"), {"id": res_o_id})
                                    conn.commit()
                                    st.success(f"✅ ID {res_o_id} 已还原")
                                    st.rerun()
                with c2:
                    del_o_id = st.number_input("输入要【粉碎】的订单 ID", step=1, value=0, key="kill_o_val")
                    if st.button("🔥 彻底粉碎（不可恢复）", type="primary", width='stretch'):
                        if del_o_id > 0:
                            with engine.connect() as conn:
                                conn.execute(text("DELETE FROM orders WHERE id = :id"), {"id": del_o_id})
                                conn.commit()
                            st.error(f"💀 ID {del_o_id} 已永久删除")
                            st.rerun()
            else:
                st.write("订单回收站目前是空的。")

        with tab_cust:
            df_trash_c = pd.read_sql("SELECT name, phone, address, remark FROM customers WHERE is_active = 0", engine)
            if not df_trash_c.empty:
                st.dataframe(df_trash_c, width='stretch', hide_index=True)
                res_c_name = st.selectbox("选择要还原的客户", df_trash_c['name'].tolist())
                if st.button("⏪ 还原该客户资料", width='stretch'):
                    with engine.connect() as conn:
                        conn.execute(text("UPDATE customers SET is_active = 1 WHERE name = :n"), {"n": res_c_name})
                        conn.commit()
                    st.success(f"✅ 客户 {res_c_name} 已还原")
                    st.rerun()
            else:
                st.write("客户回收站没有记录。")




































