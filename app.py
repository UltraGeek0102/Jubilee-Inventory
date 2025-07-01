# jubilee_streamlit/app.py — Enhanced Cloud Version with All Features
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from PIL import Image
import os
import json
from datetime import datetime
import base64



# ---------- SETUP ----------
st.set_page_config(page_title="Jubilee Inventory (Enhanced)", layout="wide")
st.image("logo.png", width=150)
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

# ---------- FILTER & SEARCH ----------
def filter_dataframe(df):
    search_text = st.text_input("🔍 Search D.NO, Company or Matching")
    if search_text:
        df = df[df.apply(lambda row: search_text.lower() in str(row).lower(), axis=1)]

    filter_company = st.multiselect("🏷 Filter by Company", options=df["Company"].unique())
    if filter_company:
        df = df[df["Company"].isin(filter_company)]

    only_pending = st.checkbox("📦 Show only Pending Deliveries")
    if only_pending:
        df = df[df["Pending"] > 0]

    return df

# ---------- CSV EXPORT ----------
def get_csv_download_link(df):
    csv = df.to_csv(index=False).encode('utf-8')
    b64 = base64.b64encode(csv).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="inventory_export.csv">📥 Download CSV</a>'
    return href

# ---------- ADD PRODUCT FORM ----------
def show_add_form():
    st.subheader("➕ Add New Product")
    with st.form("add_form"):
        col1, col2, col3 = st.columns(3)
        company = col1.text_input("Company")
        dno = col2.text_input("D.NO")
        diamond = col3.text_input("Diamond")

        matching = st.text_area("Matching (format: Red:3, Blue:2)")
        pcs = st.number_input("PCS", min_value=0, value=0)
        delivery_pcs = st.number_input("Delivery PCS", min_value=0, value=0)

        col4, col5, col6 = st.columns(3)
        assignee = col4.text_input("Assignee")
        ptype = col5.selectbox("Type", ["WITH LACE", "WITHOUT LACE"])
        rate = col6.number_input("Rate", min_value=0.0, value=0.0)

        image = st.file_uploader("Upload Image", type=["png", "jpg", "jpeg"])

        submitted = st.form_submit_button("Add Product")
        if submitted:
            total = pcs * rate
            image_path = save_image(image)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            new_row = [company, dno, matching, diamond, pcs, delivery_pcs, assignee, ptype, rate, total, image_path, timestamp]
            try:
                sheet.append_row(new_row)
                st.success("✅ Product added successfully!")
                st.experimental_rerun()
            except Exception as e:
                st.error(f"❌ Failed to write to sheet: {e}")

# ---------- DISPLAY SHEET DATA ----------
def show_inventory():
    st.subheader("📦 Inventory Table (Google Sheets)")
    try:
        data = sheet.get_all_records()
        if not data:
            st.info("No entries yet. Add a product above.")
            return

        df = pd.DataFrame(data)
        if "Timestamp" not in df.columns:
            df["Timestamp"] = ""
        df["Pending"] = df["PCS"] - df["Delivery_PCS"]

        st.markdown(get_csv_download_link(df), unsafe_allow_html=True)

        df = filter_dataframe(df)

        for i, row in df.iterrows():
            with st.expander(f"{i+2}. {row['Company']} - {row['D.NO']}  | Pending: {row['Pending']}"):
                st.write(f"**Matching:**")
                st.code(row["Matching"])
                st.write(f"**PCS:** {row['PCS']}, **Delivered:** {row['Delivery_PCS']}, **Pending:** {row['Pending']}")
                st.write(f"**Diamond:** {row['Diamond']} | **Type:** {row['Type']} | **Assignee:** {row['Assignee']}")
                st.write(f"**Rate:** ₹{row['Rate']} | **Total:** ₹{row['Total']} | **Time:** {row['Timestamp']}")

                if row["Image"] and os.path.exists(row["Image"]):
                    st.image(row["Image"], width=150)
    except Exception as e:
        st.error(f"❌ Failed to load data: {e}")

# ---------- MAIN ----------
show_add_form()
show_inventory()
