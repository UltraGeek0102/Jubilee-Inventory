# jubilee_streamlit/app.py — Full Web App with PCS Matching Total Logic, PWA, Calculator, Dashboard, Image Upload, Mobile
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from PIL import Image
import os
import json
from datetime import datetime
import base64
import io
import altair as alt

# ---------- SETUP ----------
st.set_page_config(page_title="Jubilee Inventory (Enhanced)", layout="wide")

# ---------- PWA META TAGS ----------
st.markdown("""
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="theme-color" content="#121212">
    <meta name="application-name" content="Jubilee Inventory">
    <link rel="apple-touch-icon" href="https://raw.githubusercontent.com/ultrageek0102/Jubilee-Inventory/main/logo.png">
""", unsafe_allow_html=True)

# ---------- LOGO + FAVICON ----------
st.markdown("""
    <style>
        .logo-container {
            display: flex;
            justify-content: center;
            margin-bottom: 0.5rem;
        }
    </style>
    <link rel="icon" href="https://raw.githubusercontent.com/ultrageek0102/Jubilee-Inventory/main/favicon.ico" type="image/x-icon">
    <div class="logo-container">
        <img src="https://raw.githubusercontent.com/ultrageek0102/Jubilee-Inventory/main/logo.png" width="150">
    </div>
""", unsafe_allow_html=True)

st.title("🧵 Jubilee Textile Inventory - Cloud Version")

# ---------- GOOGLE SHEETS AUTH via st.secrets ----------
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

try:
    creds_dict = json.loads(st.secrets["GCP_CREDENTIALS"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
    client = gspread.authorize(creds)
    spreadsheet = client.open("jubilee-inventory")
    sheet = spreadsheet.sheet1
except gspread.exceptions.SpreadsheetNotFound:
    st.error("❌ Google Sheet 'jubilee_inventory' not found. Please check the name or share it with your service account.")
    st.stop()
except Exception as e:
    st.error(f"❌ Unknown error connecting to Google Sheets: {type(e).__name__}: {e}")
    st.stop()

# ---------- IMAGE UPLOAD ----------
def save_image(uploaded_file):
    if uploaded_file is None:
        return ""
    file_path = os.path.join(UPLOAD_DIR, uploaded_file.name)
    image = Image.open(uploaded_file)
    image.thumbnail((800, 800))
    image.save(file_path)
    return file_path

# ---------- EXPORT ----------
def get_csv_excel_download_links(df):
    csv = df.to_csv(index=False).encode('utf-8')
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Inventory')
    excel_data = excel_buffer.getvalue()

    b64_csv = base64.b64encode(csv).decode()
    b64_excel = base64.b64encode(excel_data).decode()

    csv_link = f'<a href="data:file/csv;base64,{b64_csv}" download="inventory_export.csv">📥 Download CSV</a>'
    excel_link = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64_excel}" download="inventory_export.xlsx">📥 Download Excel</a>'

    return csv_link + " | " + excel_link

# ---------- FILTER ----------
def filter_dataframe(df):
    search_text = st.text_input("🔍 Global Search")
    if search_text:
        df = df[df.apply(lambda row: search_text.lower() in str(row).lower(), axis=1)]
    filter_company = st.multiselect("🏷 Filter by Company", options=df["Company"].unique())
    if filter_company:
        df = df[df["Company"].isin(filter_company)]
    if st.checkbox("📦 Show only Pending Deliveries"):
        df = df[df["PCS"] > df["Delivery_PCS"]]
    return df

# ---------- DASHBOARD ----------
def show_dashboard(df):
    st.subheader("📊 Inventory Summary")
    total_pcs = df["PCS"].sum()
    pending_total = (df["PCS"] - df["Delivery_PCS"]).sum()
    st.metric("Total PCS", total_pcs)
    st.metric("Pending Total", pending_total)

    chart_data = df.groupby("Company")["PCS"].sum().reset_index()
    chart = alt.Chart(chart_data).mark_bar().encode(
        x=alt.X("Company", sort="-y"),
        y="PCS",
        tooltip=["Company", "PCS"]
    ).properties(height=300)
    st.altair_chart(chart, use_container_width=True)

# ---------- IMPORT ----------
def show_import_form():
    st.subheader("📤 Import from Excel or CSV")
    uploaded = st.file_uploader("Choose file", type=["csv", "xlsx"], key="import")
    if uploaded:
        if uploaded.name.endswith(".csv"):
            df = pd.read_csv(uploaded)
        else:
            df = pd.read_excel(uploaded)
        st.dataframe(df)
        if st.button("⬆️ Upload to Google Sheet"):
            for _, row in df.iterrows():
                row_list = row.tolist()
                row_list.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                row_list += [""] * (13 - len(row_list))
                try:
                    sheet.append_row(row_list)
                except Exception as e:
                    st.error(f"Error inserting row: {e}")
            st.success("✅ File data uploaded!")
            st.experimental_rerun()

# ---------- ADD ----------
def show_add_form():
    st.subheader("➕ Add New Product")
    with st.form("add_form"):
        col1, col2, col3 = st.columns(3)
        company = col1.text_input("Company")
        dno = col2.text_input("D.NO")
        diamond = col3.text_input("Diamond")

        matching = st.text_area("Matching (format: Red:3, Blue:2)")
        pcs = 0
        try:
            if matching:
                pcs = sum(int(item.split(":")[1]) for item in matching.split(",") if ":" in item)
        except:
            pcs = 0

        delivery_pcs = st.number_input("Delivery PCS", min_value=0, format="%d")

        col4, col5, col6 = st.columns(3)
        assignee = col4.text_input("Assignee")
        ptype = col5.selectbox("Type", ["WITH LACE", "WITHOUT LACE", "With Lace", "Without Lace"])
        rate = col6.number_input("Rate", min_value=0.0, step=0.01, format="%.2f")

        st.write(f"🧮 Total: ₹{pcs * rate:.2f}")

        image = st.file_uploader("Upload Image", type=["png", "jpg", "jpeg"])
        submitted = st.form_submit_button("Add Product")
        if submitted:
            total = pcs * rate
            image_path = save_image(image)
            image_url = f"https://raw.githubusercontent.com/ultrageek0102/Jubilee-Inventory/main/{image_path}" if image else ""
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            row = [company, dno, matching, diamond, pcs, delivery_pcs, assignee, ptype, rate, total, image_url, timestamp]
            try:
                sheet.append_row(row)
                st.success("✅ Added!")
                st.experimental_rerun()
            except Exception as e:
                st.error(f"❌ Failed: {e}")

# ---------- MAIN ----------
def show_inventory():
    st.subheader("📦 Inventory Table")
    try:
        df = pd.DataFrame(sheet.get_all_records())
        if "Timestamp" not in df.columns:
            df["Timestamp"] = ""
        df["PCS"] = pd.to_numeric(df["PCS"], errors="coerce").fillna(0).astype(int)
        df["Delivery_PCS"] = pd.to_numeric(df["Delivery_PCS"], errors="coerce").fillna(0).astype(int)
        df["Pending"] = df["PCS"] - df["Delivery_PCS"]

        show_dashboard(df)
        st.markdown(get_csv_excel_download_links(df), unsafe_allow_html=True)
        df = filter_dataframe(df)

        for i, row in df.iterrows():
            row_num = i + 2
            with st.expander(f"{row_num}. {row['Company']} - {row['D.NO']}  | Pending: {row['Pending']}"):
                st.write(f"**Matching:**\n{row['Matching']}")
                st.write(f"PCS: {row['PCS']} | Delivered: {row['Delivery_PCS']} | Pending: {row['Pending']}")
                st.write(f"Diamond: {row['Diamond']} | Type: {row['Type']} | Assignee: {row['Assignee']}")
                st.write(f"Rate: ₹{row['Rate']} | Total: ₹{row['Total']} | Time: {row['Timestamp']}")
                if row["Image"]:
                    st.image(row["Image"], width=150)
    except Exception as e:
        st.error(f"❌ Failed to load data: {e}")

show_import_form()
show_add_form()
show_inventory()
