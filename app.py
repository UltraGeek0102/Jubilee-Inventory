# jubilee_streamlit/app.py — Complete Web App with Excel & CSV Export, Logo, Favicon, CRUD, Image Support
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

# ---------- SETUP ----------
st.set_page_config(page_title="Jubilee Inventory (Enhanced)", layout="wide")

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
    search_text = st.text_input("🔍 Search D.NO, Company or Matching")
    if search_text:
        df = df[df.apply(lambda row: search_text.lower() in str(row).lower(), axis=1)]
    filter_company = st.multiselect("🏷 Filter by Company", options=df["Company"].unique())
    if filter_company:
        df = df[df["Company"].isin(filter_company)]
    if st.checkbox("📦 Show only Pending Deliveries"):
        df = df[df["PCS"] > df["Delivery_PCS"]]
    return df

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
        pcs = st.number_input("PCS", min_value=0)
        delivery_pcs = st.number_input("Delivery PCS", min_value=0)

        col4, col5, col6 = st.columns(3)
        assignee = col4.text_input("Assignee")
        ptype = col5.selectbox("Type", ["WITH LACE", "WITHOUT LACE"])
        rate = col6.number_input("Rate", min_value=0.0)

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

# ---------- INVENTORY ----------
def show_inventory():
    st.subheader("📦 Inventory Table")
    try:
        df = pd.DataFrame(sheet.get_all_records())
        if "Timestamp" not in df.columns:
            df["Timestamp"] = ""
        df["PCS"] = pd.to_numeric(df["PCS"], errors="coerce").fillna(0).astype(int)
        df["Delivery_PCS"] = pd.to_numeric(df["Delivery_PCS"], errors="coerce").fillna(0).astype(int)
        df["Pending"] = df["PCS"] - df["Delivery_PCS"]

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
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("✏️ Edit", key=f"edit_{i}"):
                        with st.form(f"edit_form_{i}"):
                            ec1, ec2, ec3 = st.columns(3)
                            company = ec1.text_input("Company", value=row["Company"])
                            dno = ec2.text_input("D.NO", value=row["D.NO"])
                            diamond = ec3.text_input("Diamond", value=row["Diamond"])

                            matching = st.text_area("Matching", value=row["Matching"])
                            pcs = st.number_input("PCS", min_value=0, value=row["PCS"])
                            delivery_pcs = st.number_input("Delivery PCS", min_value=0, value=row["Delivery_PCS"])

                            ec4, ec5, ec6 = st.columns(3)
                            assignee = ec4.text_input("Assignee", value=row["Assignee"])
                            ptype = ec5.selectbox("Type", ["WITH LACE", "WITHOUT LACE"], index=["WITH LACE", "WITHOUT LACE"].index(row["Type"]))
                            rate = ec6.number_input("Rate", min_value=0.0, value=float(row["Rate"]))

                            image = st.file_uploader("Replace Image", type=["png", "jpg", "jpeg"])
                            if st.form_submit_button("Update"):
                                total = pcs * rate
                                image_url = row["Image"]
                                if image:
                                    local_path = save_image(image)
                                    image_url = f"https://raw.githubusercontent.com/ultrageek0102/Jubilee-Inventory/main/{local_path}"
                                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                new_row = [company, dno, matching, diamond, pcs, delivery_pcs, assignee, ptype, rate, total, image_url, timestamp]
                                sheet.delete_row(row_num)
                                sheet.insert_row(new_row, row_num)
                                st.success("✅ Updated")
                                st.experimental_rerun()
                with col2:
                    if st.button("❌ Delete", key=f"delete_{i}"):
                        sheet.delete_row(row_num)
                        st.warning("Deleted")
                        st.experimental_rerun()
    except Exception as e:
        st.error(f"❌ Failed to load data: {e}")

# ---------- MAIN ----------
show_import_form()
show_add_form()
show_inventory()

