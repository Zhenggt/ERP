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
    # --- C. 销售出库 ---
    elif menu == "📤 销售出库":
        st.header("📤 销售出库单")
        try:
            # 获取库存和客户数据
            df_p = pd.read_sql("SELECT name, spec, stock FROM products WHERE stock > 0", engine)
            df_c = pd.read_sql("SELECT name, phone, address FROM customers", engine)
            
            if df_p.empty:
                st.warning("仓库目前无货。")
            else:
                # 格式化货品显示名称
                df_p['display'] = df_p['name'] + " | " + df_p['spec'].fillna("标准")
                
                col1, col2 = st.columns(2)
                with col1:
                    # 客户选择与详情显示
                    t_c = st.selectbox("👤 选择客户", ["散客"] + df_c['name'].tolist())
                    c_info = {"phone": "未登记", "address": "自提/无地址"} # 默认值
                    if t_c != "散客":
                        res = df_c[df_c['name'] == t_c].iloc[0]
                        c_info['phone'] = res['phone'] if res['phone'] else "未登记"
                        c_info['address'] = res['address'] if res['address'] else "无地址"
                        st.caption(f"📞 {c_info['phone']} | 📍 {c_info['address']}")
                    
                    s_o = st.selectbox("📦 选择货品", df_p['display'].tolist())
                
                # 拆分品名和规格
                p_n = s_o.split(" | ")[0]
                p_s = s_o.split(" | ")[1]

                with col2:
                    num = st.number_input("⚖️ 出库重量 (kg)", min_value=0.0, step=0.01)
                    price = st.number_input("💰 销售单价 (元)", min_value=0.0, step=0.01)

                total = round(num * price, 2)
                
                # 金额汇总显示
                st.markdown(f"""
                <div style="background:#1e293b;padding:15px;border-radius:10px;text-align:center;border:1px solid #3b82f6;margin:10px 0;">
                    <p style="color:#cbd5e1;margin:0;font-size:14px;">合计金额</p>
                    <p style="color:#3b82f6;font-size:32px;font-weight:bold;margin:0;">¥ {total:,.2f}</p>
                </div>
                """, unsafe_allow_html=True)

                if st.button("🚀 确认提交并生成三联单", use_container_width=True):
                    # 检查库存
                    stock_now = float(df_p[df_p['display'] == s_o]['stock'].values[0])
                    if num > stock_now:
                        st.error(f"库存不足！当前余量：{stock_now} kg")
                    elif num <= 0:
                        st.error("请输入有效重量")
                    else:
                        # 数据库操作
                        with engine.connect() as conn:
                            conn.execute(text("UPDATE products SET stock = stock - :n WHERE name = :p AND spec = :s"), 
                                         {"n": num, "p": p_n, "s": p_s})
                            conn.execute(text("""
                                INSERT INTO orders (type, customer, product, num, price, total_amount) 
                                VALUES ('销售', :c, :p, :n, :pr, :t)
                            """), {"c": t_c, "p": s_o, "n": num, "pr": price, "t": total})
                            conn.commit()
                        
                        st.success("✅ 出库成功！单据生成如下：")
                        st.cache_data.clear()

                        # --- 三联单 HTML 打印模板 ---
                        bill_html = f"""
                        <style>
                            .bill-box {{
                                width: 185mm; 
                                padding: 10mm; 
                                border: 1px dashed #666;
                                font-family: 'SimSun', 'STSong', serif;
                                color: #000;
                                background: #fff;
                            }}
                            .title {{ text-align: center; font-size: 22px; font-weight: bold; letter-spacing: 4px; margin-bottom: 10px; }}
                            .info-table {{ width: 100%; font-size: 13px; margin-bottom: 5px; }}
                            .data-table {{ width: 100%; border-collapse: collapse; border: 1.5px solid #000; }}
                            .data-table th, .data-table td {{ border: 1px solid #000; padding: 6px; text-align: center; font-size: 13px; }}
                            .footer {{ width: 100%; margin-top: 15px; font-size: 13px; display: flex; justify-content: space-between; }}
                            @media print {{
                                .no-print {{ display: none !important; }}
                                @page {{ size: 241mm 140mm; margin: 0; }}
                            }}
                        </style>

                        <div class="bill-box" id="bill">
                            <div class="title">销售出库单</div>
                            <table class="info-table">
                                <tr>
                                    <td><strong>收货单位:</strong> {t_c}</td>
                                    <td style="text-align:right;"><strong>日期:</strong> {get_beijing_time().strftime('%Y-%m-%d %H:%M')}</td>
                                </tr>
                                <tr>
                                    <td colspan="2"><strong>联系信息:</strong> {c_info['phone']} | {c_info['address']}</td>
                                </tr>
                            </table>
                            <table class="data-table">
                                <thead>
                                    <tr>
                                        <th>货品名称</th><th>规格型号</th><th>数量(kg)</th><th>单价(元)</th><th>金额(元)</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    <tr style="height:40px;">
                                        <td>{p_n}</td><td>{p_s}</td><td>{num}</td><td>{price}</td><td>{total}</td>
                                    </tr>
                                    <tr style="height:30px;">
                                        <td>备注</td><td colspan="4"></td>
                                    </tr>
                                </tbody>
                            </table>
                            <div class="footer">
                                <span>制单人: 管理员</span>
                                <span>送货人签字: _________</span>
                                <span>收货人签字: _________________</span>
                            </div>
                        </div>

                        <button class="no-print" onclick="printBill()" style="margin-top:15px; padding:10px 25px; background:#2563eb; color:white; border:none; border-radius:5px; cursor:pointer;">
                            🖨️ 打印三联单
                        </button>

                        <script>
                        function printBill() {{
                            var content = document.getElementById('bill').innerHTML;
                            var style = document.getElementsByTagName('style')[0].innerHTML;
                            var win = window.open('', '', 'height=600,width=800');
                            win.document.write('<html><head><style>' + style + '</style></head><body>');
                            win.document.write(content);
                            win.document.write('</body></html>');
                            win.document.close();
                            setTimeout(function(){{ win.print(); win.close(); }}, 250);
                        }}
                        </script>
                        """
                        import streamlit.components.v1 as components
                        components.html(bill_html, height=450)
                        
        except Exception as e:
            st.error(f"出库模块错误: {e}")
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
        st.header("👥 客户档案管理")
        
        # 1. 获取现有客户数据
        try:
            df_cust = pd.read_sql("SELECT name, phone, address, note FROM customers ORDER BY name", engine)
            
            tabs = st.tabs(["➕ 新增/修改客户", "📋 客户列表"])
            
            with tabs[0]:
                st.subheader("编辑客户信息")
                # 模式选择：新增还是修改
                edit_mode = st.radio("操作类型", ["修改现有客户", "添加新客户"], horizontal=True)
                
                with st.form("c_form", clear_on_submit=True):
                    if edit_mode == "修改现有客户" and not df_cust.empty:
                        # 如果是修改模式，先选人，自动填入原信息
                        target_name = st.selectbox("选择要修改的客户", df_cust['name'].tolist())
                        # 获取该客户的原有信息作为默认值
                        old_info = df_cust[df_cust['name'] == target_name].iloc[0]
                        
                        c1, c2 = st.columns(2)
                        new_name = c1.text_input("客户名称*", value=old_info['name'], disabled=True) # 名称通常不改
                        new_phone = c1.text_input("新电话", value=old_info['phone'] or "")
                        new_addr = c2.text_input("新地址", value=old_info['address'] or "")
                        new_note = c2.text_input("新备注", value=old_info['note'] or "")
                    else:
                        # 如果是新增模式，显示空表单
                        target_name = None
                        c1, c2 = st.columns(2)
                        new_name = c1.text_input("客户名称* (新)")
                        new_phone = c1.text_input("电话")
                        new_addr = c2.text_input("地址")
                        new_note = c2.text_input("备注")
                    
                    if st.form_submit_button("💾 保存/更新资料"):
                        final_name = target_name if edit_mode == "修改现有客户" else new_name
                        if final_name:
                            with engine.connect() as conn:
                                conn.execute(text("""
                                    INSERT INTO customers (name, phone, address, note) 
                                    VALUES (:n, :p, :a, :nt) 
                                    ON CONFLICT (name) DO UPDATE SET 
                                        phone=EXCLUDED.phone, 
                                        address=EXCLUDED.address, 
                                        note=EXCLUDED.note
                                """), {"n": final_name, "p": new_phone, "a": new_addr, "nt": new_note})
                                conn.commit()
                            st.success(f"✅ {final_name} 的资料已更新")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error("请输入客户名称")

            with tabs[1]:
                st.subheader("所有客户清单")
                if not df_cust.empty:
                    st.dataframe(df_cust.rename(columns={
                        'name': '姓名', 'phone': '电话', 'address': '地址', 'note': '备注'
                    }), width='stretch', hide_index=True)
                    
                    # 快速删除功能
                    with st.expander("🗑️ 危险操作：删除客户"):
                        del_name = st.selectbox("选择要彻底删除的客户", ["--选择--"] + df_cust['name'].tolist())
                        if st.button("确认删除记录"):
                            if del_name != "--选择--":
                                with engine.connect() as conn:
                                    conn.execute(text("DELETE FROM customers WHERE name = :n"), {"n": del_name})
                                    conn.commit()
                                st.warning(f"已删除客户：{del_name}")
                                st.cache_data.clear()
                                st.rerun()
                else:
                    st.info("暂无数据")
                    
        except Exception as e:
            st.error(f"客户模块加载异常: {e}")

