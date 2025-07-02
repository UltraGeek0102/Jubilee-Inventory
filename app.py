# jubilee_streamlit/app.py — Full Inventory Web App with Drive Uploads, Filters, Auth, Print View
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import pandas as pd
from PIL import Image
import os
import json
from datetime import datetime
import base64
import io
import altair as alt
import uuid

st.set_page_config(
    page_title="Jubilee Inventory",
    page_icon="https://raw.githubusercontent.com/ultrageek0102/Jubilee-Inventory/main/favicon.ico",
    layout="wide"
)

# --- Logo + Favicon ---
st.markdown("""
    <style>
        .logo-container {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 1rem;
            margin-top: 1rem;
            margin-bottom: 1rem;
        }
        .logo-container img {
            height: 60px;
        }
        .logo-container h1 {
            font-size: 2rem;
            font-weight: 600;
            color: white;
        }
    </style>
    <div class="logo-container">
        <img src="https://raw.githubusercontent.com/ultrageek0102/Jubilee-Inventory/main/logo.png" alt="logo">
        <h1>JUBILEE TEXTILE PROCESSORS</h1>
    </div>
    <link rel="icon" href="https://raw.githubusercontent.com/ultrageek0102/Jubilee-Inventory/main/favicon.ico" type="image/x-icon">
""", unsafe_allow_html=True)

SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]

FALLBACK_IMAGE = "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0a/No-image-available.png/600px-No-image-available.png"
ROWS_PER_PAGE = 50

# --- Auth ---
if "PASSWORD" in st.secrets:
    pw = st.text_input("🔐 Enter password to access:", type="password")
    if pw != st.secrets["PASSWORD"]:
        st.stop()

try:
    creds_dict = json.loads(st.secrets["GCP_CREDENTIALS"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
    client = gspread.authorize(creds)
    spreadsheet = client.open("jubilee-inventory")
    sheet = spreadsheet.sheet1
    drive_service = build("drive", "v3", credentials=creds)
except Exception as e:
    st.error(f"❌ Google API error: {e}")
    st.stop()

DRIVE_FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID")

def upload_to_drive(uploaded_file):
    if uploaded_file is None:
        return FALLBACK_IMAGE
    try:
        ext = os.path.splitext(uploaded_file.name)[-1]
        safe_name = f"jubilee_{uuid.uuid4().hex}{ext}"
        file_stream = io.BytesIO(uploaded_file.getvalue())
        mime_type = uploaded_file.type or "image/jpeg"
        file_metadata = {'name': safe_name, 'parents': [DRIVE_FOLDER_ID]}
        media = MediaIoBaseUpload(file_stream, mimetype=mime_type)
        uploaded = drive_service.files().create(body=file_metadata, media_body=media, fields="id").execute()
        drive_service.permissions().create(fileId=uploaded["id"], body={"role": "reader", "type": "anyone"}).execute()
        return f"https://drive.google.com/uc?id={uploaded['id']}"
    except:
        return FALLBACK_IMAGE

def get_csv_excel_download_links(df):
    csv = df.to_csv(index=False).encode('utf-8')
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Inventory')
    excel_data = excel_buffer.getvalue()
    b64_csv = base64.b64encode(csv).decode()
    b64_excel = base64.b64encode(excel_data).decode()
    return f'<a href="data:file/csv;base64,{b64_csv}" download="inventory.csv">📥 CSV</a> | <a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64_excel}" download="inventory.xlsx">📥 Excel</a>'

def show_dashboard(df):
    st.subheader("📊 Dashboard")
    col1, col2 = st.columns(2)
    col1.metric("Total PCS", int(df["PCS"].sum()))
    col2.metric("Pending", int((df["PCS"] - df["Delivery_PCS"]).sum()))
    chart_data = df.groupby("Company")["PCS"].sum().reset_index()
    chart = alt.Chart(chart_data).mark_bar().encode(x="Company", y="PCS", tooltip=["Company", "PCS"])
    st.altair_chart(chart, use_container_width=True)

def show_add_form():
    st.subheader("➕ Add Product")
    with st.form("add_form"):
        col1, col2, col3 = st.columns(3)
        company = col1.text_input("Company")
        dno = col2.text_input("D.NO")
        diamond = col3.text_input("Diamond")
        matching = st.text_area("Matching (Red:3, Blue:2)")
        try:
            pcs = sum(int(i.split(":")[1]) for i in matching.split(",") if ":" in i)
        except:
            pcs = 0
        delivery = st.number_input("Delivery PCS", min_value=0, format="%d")
        a1, a2, a3 = st.columns(3)
        assignee = a1.text_input("Assignee")
        ptype = a2.selectbox("Type", ["WITH LACE", "WITHOUT LACE", "With Lace", "Without Lace"])
        rate = a3.number_input("Rate", min_value=0.0, step=0.01)
        st.write(f"Total: ₹{pcs * rate:.2f}")
        image = st.file_uploader("Upload Image", type=["png", "jpg", "jpeg"])
        submit = st.form_submit_button("Add")
        if submit:
            img_url = upload_to_drive(image)
            row = [company, dno, matching, diamond, pcs, delivery, assignee, ptype, rate, pcs * rate, img_url, datetime.now().isoformat()]
            try:
                sheet.append_row(row)
                st.success("✅ Product added!")
                st.experimental_rerun()
            except Exception as e:
                st.error(f"Failed to add: {e}")

def show_inventory():
    st.subheader("📦 Inventory")
    df = pd.DataFrame(sheet.get_all_records())
    df["PCS"] = pd.to_numeric(df["PCS"], errors="coerce").fillna(0).astype(int)
    df["Delivery_PCS"] = pd.to_numeric(df["Delivery_PCS"], errors="coerce").fillna(0).astype(int)
    df["Pending"] = df["PCS"] - df["Delivery_PCS"]

    show_dashboard(df)

    with st.expander("🔎 Filter / Search"):
        f1, f2 = st.columns(2)
        company_filter = f1.multiselect("Company", options=df["Company"].unique())
        type_filter = f2.multiselect("Type", options=df["Type"].unique())
        search = st.text_input("Search keyword")
        sort_by = st.selectbox("Sort by", ["PCS", "Pending", "Rate", "Total"], index=0)
        ascending = st.checkbox("⬆️ Sort Ascending", value=True)

        if company_filter:
            df = df[df["Company"].isin(company_filter)]
        if type_filter:
            df = df[df["Type"].isin(type_filter)]
        if search:
            df = df[df.apply(lambda row: search.lower() in str(row).lower(), axis=1)]
        df = df.sort_values(by=sort_by, ascending=ascending)

    st.markdown(get_csv_excel_download_links(df), unsafe_allow_html=True)

    total_pages = len(df) // ROWS_PER_PAGE + 1
    page = st.number_input("Page", min_value=1, max_value=total_pages, step=1)
    start = (page - 1) * ROWS_PER_PAGE
    end = start + ROWS_PER_PAGE
    sliced_df = df.iloc[start:end]

    for i in sliced_df.index:
        row = df.loc[i]
        row_num = i + 2
        with st.expander(f"{row['Company']} - {row['D.NO']} | Pending: {row['Pending']}"):
            st.markdown(f'<a href="{row["Image"] or FALLBACK_IMAGE}" target="_blank"><img src="{row["Image"] or FALLBACK_IMAGE}" width="200"></a>', unsafe_allow_html=True)
            st.write(f"Diamond: {row['Diamond']} | Type: {row['Type']} | Assignee: {row['Assignee']}")
            st.write(f"PCS: {row['PCS']} | Delivered: {row['Delivery_PCS']} | Rate: ₹{row['Rate']} | Total: ₹{row['Total']}")
            st.write(f"Matching: {row['Matching']}")
            with st.form(f"edit_{i}"):
                col1, col2, col3 = st.columns(3)
                company = col1.text_input("Company", value=row["Company"])
                dno = col2.text_input("D.NO", value=row["D.NO"])
                diamond = col3.text_input("Diamond", value=row["Diamond"])
                matching = st.text_area("Matching", value=row["Matching"])
                try:
                    pcs = sum(int(i.split(":")[1]) for i in matching.split(",") if ":" in i)
                except:
                    pcs = 0
                delivery = st.number_input("Delivery PCS", value=row["Delivery_PCS"], min_value=0)
                a1, a2, a3 = st.columns(3)
                assignee = a1.text_input("Assignee", value=row["Assignee"])
                ptype = a2.selectbox("Type", ["WITH LACE", "WITHOUT LACE", "With Lace", "Without Lace"], index=0)
                rate = a3.number_input("Rate", value=float(row["Rate"]), step=0.01)
                image = st.file_uploader("Replace Image")
                c1, c2 = st.columns(2)
                if c1.form_submit_button("Update"):
                    image_url = row["Image"]
                    if image:
                        image_url = upload_to_drive(image)
                    new_row = [company, dno, matching, diamond, pcs, delivery, assignee, ptype, rate, pcs * rate, image_url, datetime.now().isoformat()]
                    sheet.delete_row(row_num)
                    sheet.insert_row(new_row, row_num)
                    st.success("✅ Updated")
                    st.experimental_rerun()
                if c2.form_submit_button("Delete"):
                    sheet.delete_row(row_num)
                    st.warning("❌ Deleted")
                    st.experimental_rerun()

show_add_form()
show_inventory()
