import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

# 1. 数据库连接设置
try:
    DB_URL = st.secrets["db_uri"]
    engine = create_engine(DB_URL)
except:
    st.error("⚠️ 数据库连接配置错误，请检查 Secrets")
    st.stop()

# 2. 登录验证函数
def check_password():
    """如果返回 True，则显示主程序；否则显示登录界面"""
    if "password_correct" not in st.session_state:
        st.title("🔒 南总云端进销存系统")
        user_input = st.text_input("请输入管理员账号")
        pass_input = st.text_input("请输入管理员密码", type="password")
        
        if st.button("进入系统"):
            if user_input == st.secrets["auth"]["admin_user"] and \
               pass_input == st.secrets["auth"]["admin_pass"]:
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("❌ 账号或密码错误")
        return False
    return True

# 3. 主程序逻辑
if check_password():
    # 侧边栏：退出按钮和导航
    if st.sidebar.button("登出退出"):
        del st.session_state["password_correct"]
        st.rerun()

    st.sidebar.title("🏮 功能菜单")
    menu = st.sidebar.radio("请选择", ["📦 库存清单", "📥 进货登记", "📤 销售出库"])

    # --- 模块 A：库存清单 ---
    if menu == "📦 库存清单":
        st.header("📊 当前库存实时统计")
        try:
            df = pd.read_sql("SELECT name as 品名, spec as 规格, stock as 数量 FROM products", engine)
            st.table(df) # 用 table 格式更适合手机查看
        except:
            st.info("目前库房是空的，请先录入数据。")

    # --- 模块 B：进货登记 ---
    elif menu == "📥 进货登记":
        st.header("🛒 新货入库录入")
        with st.form("add_stock", clear_on_submit=True):
            name = st.text_input("商品品名")
            spec = st.text_input("规格型号")
            num = st.number_input("入库数量", min_value=1, step=1)
            
            if st.form_submit_button("确认提交"):
                with engine.connect() as conn:
                    # 更新库存逻辑
                    conn.execute(
                        text("INSERT INTO products (name, spec, stock) VALUES (:n, :s, :num)"),
                        {"n": name, "s": spec, "num": num}
                    )
                    # 记录流水
                    conn.execute(
                        text("INSERT INTO orders (type, product, num) VALUES ('进货', :p, :n)"),
                        {"p": name, "n": num}
                    )
                    conn.commit()
                st.success(f"✅ {name} 入库成功！")
                st.balloons()

    # --- 模块 C：销售出库 ---
    elif menu == "📤 销售出库":
        st.header("🧾 销售出库单")
        st.write("此处可以根据实际业务需求，增加减库存的逻辑。")
