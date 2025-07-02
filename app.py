# jubilee_streamlit/app.py — Now Uploads Images to Google Drive with Public Preview
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

st.set_page_config(page_title="Jubilee Inventory (Enhanced)", layout="wide")

# Google Drive API Setup
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
    drive_service = build("drive", "v3", credentials=creds)
except Exception as e:
    st.error(f"❌ Google API error: {e}")
    st.stop()

# Upload to Google Drive Folder
DRIVE_FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID")  # Add this to your secrets

def upload_to_drive(uploaded_file):
    if uploaded_file is None:
        return ""
    file_stream = io.BytesIO(uploaded_file.getvalue())
    mime_type = uploaded_file.type or "image/jpeg"

    file_metadata = {
        'name': uploaded_file.name,
        'parents': [DRIVE_FOLDER_ID]
    }
    media = MediaIoBaseUpload(file_stream, mimetype=mime_type)

    try:
        uploaded = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id"
        ).execute()
        file_id = uploaded.get("id")

        # Make public
        drive_service.permissions().create(
            fileId=file_id,
            body={"role": "reader", "type": "anyone"},
            fields="id"
        ).execute()

        return f"https://drive.google.com/uc?id={file_id}"
    except Exception as e:
        st.warning(f"⚠️ Failed to upload image to Drive: {e}")
        return ""

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
            image_url = upload_to_drive(image)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            row = [company, dno, matching, diamond, pcs, delivery_pcs, assignee, ptype, rate, total, image_url, timestamp]
            try:
                sheet.append_row(row)
                st.success("✅ Product added successfully!")
                st.experimental_rerun()
            except Exception as e:
                st.error(f"❌ Error: {e}")

def show_inventory():
    st.subheader("📦 Inventory Table")
    try:
        df = pd.DataFrame(sheet.get_all_records())
        df["PCS"] = pd.to_numeric(df["PCS"], errors="coerce").fillna(0).astype(int)
        df["Delivery_PCS"] = pd.to_numeric(df["Delivery_PCS"], errors="coerce").fillna(0).astype(int)
        df["Pending"] = df["PCS"] - df["Delivery_PCS"]

        st.markdown(get_csv_excel_download_links(df), unsafe_allow_html=True)

        for i, row in df.iterrows():
            row_num = i + 2
            with st.expander(f"{row['Company']} - {row['D.NO']} | Pending: {row['Pending']}"):
                st.write(f"**Matching:** {row['Matching']}")
                st.write(f"PCS: {row['PCS']} | Delivered: {row['Delivery_PCS']} | Rate: ₹{row['Rate']} | Total: ₹{row['Total']}")
                if row["Image"]:
                    st.image(row["Image"], width=200)
                with st.form(f"edit_form_{i}"):
                    ec1, ec2, ec3 = st.columns(3)
                    company = ec1.text_input("Company", value=row["Company"])
                    dno = ec2.text_input("D.NO", value=row["D.NO"])
                    diamond = ec3.text_input("Diamond", value=row["Diamond"])

                    matching = st.text_area("Matching", value=row["Matching"])
                    try:
                        pcs = sum(int(item.split(":")[1]) for item in matching.split(",") if ":" in item)
                    except:
                        pcs = 0
                    delivery_pcs = st.number_input("Delivery PCS", min_value=0, value=row["Delivery_PCS"], format="%d")

                    ec4, ec5, ec6 = st.columns(3)
                    assignee = ec4.text_input("Assignee", value=row["Assignee"])
                    ptype = ec5.selectbox("Type", ["WITH LACE", "WITHOUT LACE", "With Lace", "Without Lace"], index=0)
                    rate = ec6.number_input("Rate", min_value=0.0, value=float(row["Rate"]), step=0.01)
                    st.write(f"🧮 Total: ₹{pcs * rate:.2f}")

                    image = st.file_uploader("Replace Image", type=["png", "jpg", "jpeg"])
                    colA, colB = st.columns(2)
                    if colA.form_submit_button("✏️ Update"):
                        image_url = row["Image"]
                        if image:
                            image_url = upload_to_drive(image)
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        new_row = [company, dno, matching, diamond, pcs, delivery_pcs, assignee, ptype, rate, pcs * rate, image_url, timestamp]
                        sheet.delete_row(row_num)
                        sheet.insert_row(new_row, row_num)
                        st.success("✅ Updated")
                        st.experimental_rerun()
                    if colB.form_submit_button("❌ Delete"):
                        sheet.delete_row(row_num)
                        st.warning("🚮 Deleted")
                        st.experimental_rerun()
    except Exception as e:
        st.error(f"❌ Failed to load data: {e}")

# Run App
show_add_form()
show_inventory()
