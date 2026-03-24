import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta, timezone
from sqlalchemy.engine import URL
import requests
from bs4 import BeautifulSoup
@st.cache_data(ttl=60) # 财经数据建议 1 分钟更新一次
def get_aluminum_price():
    # 目标：新浪财经沪铝主力合约 (AL0)
    # 这个接口返回的是纯文本，速度极快
    url = "https://hq.sinajs.cn/list=nf_AL0" 
    headers = {
        'Referer': 'http://finance.sina.com.cn',
        'User-Agent': 'Mozilla/5.0'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        # 解析新浪的数据格式：var hq_str_nf_AL0="沪铝2605,10:48:34,19560.00,19580.00,19510.00,..."
        data_str = response.text.split('"')[1]
        data_list = data_str.split(',')
        
        # 索引 2 是当前价格，索引 3 是昨日收盘价（用于计算涨跌）
        current_price = float(data_list[2])
        last_close = float(data_list[3])
        change_val = current_price - last_close
        
        return {
            "price": f"{current_price:.0f}", 
            "change": f"{change_val:+.0f}", 
            "status": "success"
        }
    except Exception as e:
        return {"price": "接口维护", "change": "0", "status": "error"}
# --- 2. 基础配置 ---
st.set_page_config(page_title="策启金属ERP系统", layout="wide")

def get_beijing_time():
    return datetime.now(timezone(timedelta(hours=8)))

# 安全读取 Secrets 的函数
@st.cache_resource
def get_engine():
    try:
        # 1. 读取原始连接串
        raw_url = st.secrets["db_uri"]
        
        # 2. 【关键修复】剥离导致报错的额外参数 (如 supavisor_session_id)
        # 如果包含问号，只取问号之前的部分
        clean_url = raw_url.split("?")[0] if "?" in raw_url else raw_url
        
        # 3. 创建引擎，手动补回必要的 sslmode 参数
        return create_engine(
            clean_url, 
            connect_args={"sslmode": "require"},
            pool_pre_ping=True,
            pool_recycle=300
        )
    except Exception as e:
        # 这里的报错会更详细，方便调试
        st.error(f"❌ 数据库初始化失败: {e}")
        return None

# --- 执行数据库初始化 ---
engine = get_engine()

# 增加安全检查：只有 engine 成功创建才执行后续操作
if engine:
    try:
        with engine.connect() as conn:
            # 1. 结构检查与升级
            conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS is_active INTEGER DEFAULT 1"))
            conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS is_active INTEGER DEFAULT 1"))
            
            # 2. 修复旧数据
            conn.execute(text("UPDATE orders SET is_active = 1 WHERE is_active IS NULL"))
            
            # 3. 提交更改
            conn.commit()
    except Exception as e:
        # 捕获表结构修改时的警告（部分数据库不支持 IF NOT EXISTS）
        st.info(f"💡 数据库结构检查提示: {e}")
else:
    st.warning("⚠️ 数据库连接未就绪，请检查 Secrets 配置。")
    st.stop() # 停止运行，防止后续代码崩溃
# --- 3. 权限登录 (增加安全检查) ---
def check_password():
    # --- 核心修复：如果笔记本里没这个词，先给它写上 False ---
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    # ----------------------------------------------------

    if not st.session_state["password_correct"]:
        st.title("🔒 策启金属ERP系统")
        u = st.text_input("账号")
        p = st.text_input("密码", type="password")
        
        if st.button("登录系统", use_container_width=True): # 注意：Streamlit 最新版用 use_container_width 代替 width='stretch'
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
         # 获取数据
        market_data = get_aluminum_price()

        st.sidebar.markdown("---")
        st.sidebar.subheader("📈 今日市场行情")
        
        # 显示铝锭价格
        st.sidebar.metric(
            label="南海铝锭现货均价", 
            value=f"¥ {market_data['price']}", 
            delta=market_data['change']
        )

        # 核心修改：强制使用北京/新加坡时间 (UTC+8)
        # 注意：这里需要你确认顶部有 from datetime import datetime, timedelta, timezone
        SHA_TZ = timezone(timedelta(hours=8))
        beijing_now = datetime.now(SHA_TZ)
        
        st.sidebar.caption(f"📍 节点: 北京/新加坡时间")
        st.sidebar.caption(f"⏰ 更新: {beijing_now.strftime('%Y-%m-%d %H:%M:%S')}")

  # --- 模块 B: 采购入库 (多行动态版) ---
    elif menu == "📥 采购入库":
        st.header("📥 采购入库登记")
        
        # 1. 基础信息
        with st.container(border=True):
            col_sup, col_date = st.columns([2, 1])
            with col_sup:
                supplier = st.text_input("🚚 供应商名称", placeholder="填写厂家或发货方全称")
            with col_date:
                in_date = st.date_input("入库日期")

        st.write("📦 **入库明细** (点击下方 `+` 添加多种货品)")

        # 2. 核心：多行编辑器
        # 预设一行空的
        init_purchase = pd.DataFrame([
            {"货品名称": "铝锭", "规格型号": "标准", "重量(kg)": 0.0, "进货单价": 0.0}
        ])

        edited_purchase = st.data_editor(
            init_purchase,
            num_rows="dynamic",
            column_config={
                "货品名称": st.column_config.TextColumn("货品名称", required=True),
                "规格型号": st.column_config.TextColumn("规格型号"),
                "重量(kg)": st.column_config.NumberColumn("重量", min_value=0.0, format="%.2f"),
                "进货单价": st.column_config.NumberColumn("单价", min_value=0.0, format="%.2f"),
            },
            use_container_width=True,
            key="purchase_editor"
        )

        # 计算总计
        total_in_weight = edited_purchase["重量(kg)"].sum()
        total_in_amount = (edited_purchase["重量(kg)"] * edited_purchase["进货单价"]).sum()
        
        st.info(f"📊 本次入库总重：{total_in_weight:,.2f} kg | 总金额：¥ {total_in_amount:,.2f}")

        # 3. 提交逻辑
        if st.button("确认提交入库", type="primary", use_container_width=True):
            if not supplier:
                st.error("⚠️ 供应商不能为空！")
            elif total_in_weight <= 0:
                st.error("⚠️ 请填写至少一项有效的入库明细！")
            else:
                try:
                    with engine.begin() as conn:
                        for _, row in edited_purchase.iterrows():
                            p_name = row['货品名称']
                            p_spec = row['规格型号']
                            p_num = row['重量(kg)']
                            p_price = row['进货单价']
                            
                            # A. 自动创建或更新货品档案
                            conn.execute(text("""
                                INSERT INTO products (name, spec, stock) 
                                SELECT :p, :s, 0 
                                WHERE NOT EXISTS (SELECT 1 FROM products WHERE name = :p AND spec = :s)
                            """), {"p": p_name, "s": p_spec})

                            # B. 增加库存
                            conn.execute(text("""
                                UPDATE products SET stock = stock + :n 
                                WHERE name = :p AND spec = :s
                            """), {"n": p_num, "p": p_name, "s": p_spec})
                            
                            # C. 写入流水
                            conn.execute(text("""
                                INSERT INTO orders (type, customer, product, num, total_amount, payment_status, created_at)
                                VALUES ('采购入库', :supplier, :product, :num, :amount, 'paid', NOW())
                            """), {
                                "supplier": supplier,
                                "product": f"{p_name} | {p_spec}",
                                "num": p_num,
                                "amount": round(p_num * p_price, 2)
                            })
                    
                    st.success(f"✅ 已成功入库：{len(edited_purchase)} 项货品！")
                    st.balloons()
                    # 自动刷新以清空表格
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ 入库失败: {e}")
    # --- C. 销售出库 (多行动态版) ---
    elif menu == "📤 销售出库":
        st.header("📤 销售出库 (多行录入)")
        
        # 1. 基础资料准备
        df_p = pd.read_sql("SELECT name, spec, stock FROM products WHERE stock > 0", engine)
        df_c = pd.read_sql("SELECT name, phone, address, remark FROM customers", engine)
        
        if not df_p.empty:
            df_p['display'] = df_p['name'] + " | " + df_p['spec'].fillna("标准")
            
            # 客户选择
            t_c = st.selectbox("👤 选择收货单位 (客户)", ["散客"] + df_c['name'].tolist())
            pay_s = st.radio("付款状态", ["已结清", "客户欠款"], horizontal=True)
            user_remark = st.text_input("📝 总单备注", placeholder="如：整车发货、自提等")

            st.markdown("---")
            st.write("📦 **货品明细录入** (点击下方 `+` 号添加多行)")

            # 2. 核心：多行数据编辑器
            # 定义初始行
            init_df = pd.DataFrame([
                {"货品": df_p['display'].iloc[0], "数量(kg)": 0.0, "单价(元)": 0.0}
            ])

            edited_df = st.data_editor(
                init_df,
                num_rows="dynamic", # 允许动态增减行
                column_config={
                    "货品": st.column_config.SelectboxColumn("货品选择", options=df_p['display'].tolist(), required=True),
                    "数量(kg)": st.column_config.NumberColumn("重量", min_value=0.0, format="%.2f"),
                    "单价(元)": st.column_config.NumberColumn("单价", min_value=0.0, format="%.2f"),
                },
                use_container_width=True,
                key="sale_editor"
            )

            # 3. 自动汇总计算
            total_num = edited_df["数量(kg)"].sum()
            total_money = (edited_df["数量(kg)"] * edited_df["单价(元)"]).sum()
            
            col_m1, col_m2 = st.columns(2)
            col_m1.metric("本次合计重量", f"{total_num:,.2f} kg")
            col_m2.metric("应收总金额", f"¥ {total_money:,.2f}")

            if st.button("🚀 确认提交并批量生成三联单", width='stretch', type="primary"):
                if total_num <= 0:
                    st.error("❌ 错误：货品重量不能为空！")
                else:
                    try:
                        bj_time_now = datetime.now(timezone(timedelta(hours=8)))
                        bj_str = bj_time_now.strftime('%Y-%m-%d %H:%M:%S')
                        p_status = 'paid' if pay_s == "已结清" else 'unpaid'
                        
                        # 准备三联单 HTML 表格行
                        rows_html = ""
                        
                        with engine.begin() as conn:
                            for _, row in edited_df.iterrows():
                                p_n, p_s = row['货品'].split(" | ")[0], row['货品'].split(" | ")[1]
                                row_total = round(row['数量(kg)'] * row['单价(元)'], 2)
                                
                                # A. 扣减库存
                                conn.execute(text("UPDATE products SET stock = stock - :n WHERE name = :p AND spec = :s"), 
                                             {"n": row['数量(kg)'], "p": p_n, "s": p_s})
                                
                                # B. 写入流水
                                conn.execute(text("""
                                    INSERT INTO orders (type, customer, product, num, price, total_amount, payment_status, created_at) 
                                    VALUES ('销售', :c, :p, :n, :pr, :t, :ps, :dt)
                                """), {"c": t_c, "p": row['货品'], "n": row['数量(kg)'], "pr": row['单价(元)'], "t": row_total, "ps": p_status, "dt": bj_str})
                                
                                # C. 构造 HTML 行
                                rows_html += f"""
                                <tr style="height:40px;">
                                    <td style="border:1px solid #000;">{p_n}</td>
                                    <td style="border:1px solid #000;">{p_s}</td>
                                    <td style="border:1px solid #000;">{row['数量(kg)']}</td>
                                    <td style="border:1px solid #000;">{row['单价(元)']}</td>
                                    <td style="border:1px solid #000;">{row_total}</td>
                                </tr>
                                """

                        # 4. 生成完整的三联单 HTML
                        # 此处复用你之前的样式，但将 <tbody> 里的内容换成动态生成的 rows_html
                        bill_html = f"""
                        <div id="bill" style="width:185mm; padding:8mm; border:2px dashed #000; font-family:'SimSun'; background:#fff; color:#000; margin:auto;">
                            <h2 style="text-align:center;">销售出库单 (多行)</h2>
                            <table style="width:100%; margin-bottom:10px;">
                                <tr><td><strong>收货单位：</strong>{t_c}</td><td style="text-align:right;"><strong>日期：</strong>{bj_str}</td></tr>
                            </table>
                            <table style="width:100%; border-collapse:collapse; border:1px solid #000; text-align:center;">
                                <thead style="background:#f2f2f2;">
                                    <tr>
                                        <th style="border:1px solid #000;">货品</th><th style="border:1px solid #000;">规格</th>
                                        <th style="border:1px solid #000;">重量</th><th style="border:1px solid #000;">单价</th>
                                        <th style="border:1px solid #000;">金额</th>
                                    </tr>
                                </thead>
                                <tbody>{rows_html}</tbody>
                                <tfoot>
                                    <tr>
                                        <td colspan="2" style="border:1px solid #000; font-weight:bold;">合计</td>
                                        <td style="border:1px solid #000; font-weight:bold;">{total_num}</td>
                                        <td style="border:1px solid #000;">-</td>
                                        <td style="border:1px solid #000; font-weight:bold;">{total_money}</td>
                                    </tr>
                                </tfoot>
                            </table>
                            <p><strong>备注：</strong>{user_remark} | 状态：{pay_s}</p>
                            <div style="margin-top:20px; display:flex; justify-content:space-between;">
                                <span>制单：管理员</span><span>送货人签字：__________</span><span>收货人签字：__________</span>
                            </div>
                        </div>
                        <div style="text-align:center; margin-top:15px;"><button onclick="window.print()">🖨️ 打印三联单</button></div>
                        """
                        st.components.v1.html(bill_html, height=600, scrolling=True)
                        st.success("✅ 多行数据已批量入库！")
                        st.cache_data.clear()

                    except Exception as e:
                        st.error(f"❌ 批量提交失败: {e}")
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




































