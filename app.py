# Enhanced Jubilee Inventory Management System with Full Features — with Add/Edit/Delete, Filters, Export, and Report

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
import numpy as np

# --- Configuration ---
SERVICE_ACCOUNT_FILE = "streamlit-sheet-access@jubilee-inventory.iam.gserviceaccount.com"
SCOPES = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
SPREADSHEET_NAME = "Jubilee_Inventory"
LOG_SHEET_NAME = "Logs"
DRIVE_FOLDER_ID = "your_google_drive_folder_id"
FALLBACK_IMAGE = "https://via.placeholder.com/150"
ROWS_PER_PAGE = 5
RESIZED_IMAGE_DIM = (600, 600)

# --- Google Auth ---
creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, SCOPES)
client = gspread.authorize(creds)
sheet = client.open(SPREADSHEET_NAME).sheet1
log_sheet = client.open(SPREADSHEET_NAME).worksheet(LOG_SHEET_NAME)
drive_service = build('drive', 'v3', credentials=creds)

# --- Auth (Simple) ---
def check_auth():
    users = {"admin": "1234"}
    username = st.sidebar.text_input("Username")
    password = st.sidebar.text_input("Password", type="password")
    if st.sidebar.button("Login"):
        if users.get(username) == password:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.sidebar.error("Invalid credentials")
    return st.session_state.get("authenticated", False)

# --- Logging ---
def log_action(action, details):
    log_sheet.append_row([datetime.now().isoformat(), action, details])

# --- Upload to Drive ---
def upload_to_drive(uploaded_file):
    if uploaded_file is None:
        return FALLBACK_IMAGE
    try:
        image = Image.open(uploaded_file)
        image.thumbnail(RESIZED_IMAGE_DIM)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG")
        buffer.seek(0)
        name = f"jubilee_{uuid.uuid4().hex}.jpg"
        meta = {'name': name, 'parents': [DRIVE_FOLDER_ID]}
        media = MediaIoBaseUpload(buffer, mimetype="image/jpeg", resumable=True)
        file = drive_service.files().create(body=meta, media_body=media, fields="id").execute()
        drive_service.permissions().create(fileId=file['id'], body={"role": "reader", "type": "anyone"}).execute()
        return f"https://drive.google.com/uc?id={file['id']}"
    except:
        return FALLBACK_IMAGE

# --- Undo ---
UNDO_KEY = "_last_deleted_"
def cache_deleted(row):
    st.session_state[UNDO_KEY] = row

def undo_delete():
    if row := st.session_state.get(UNDO_KEY):
        sheet.append_row(row)
        log_action("Undo Delete", f"Restored {row[0]} - {row[1]}")
        del st.session_state[UNDO_KEY]
        st.success("Undo successful!")
        st.rerun()
    else:
        st.warning("Nothing to undo")

# --- Export ---
def get_download_links(df):
    csv = df.to_csv(index=False).encode('utf-8')
    excel = io.BytesIO()
    df.to_excel(excel, index=False)
    excel.seek(0)
    b64_csv = base64.b64encode(csv).decode()
    b64_excel = base64.b64encode(excel.read()).decode()
    link_csv = f'<a href="data:file/csv;base64,{b64_csv}" download="inventory.csv">Download CSV</a>'
    link_excel = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64_excel}" download="inventory.xlsx">Download Excel</a>'
    return f"{link_csv} | {link_excel}"

# --- Printable Report ---
def get_printable_html(df):
    df_html = df.copy()
    if "Image" in df_html.columns:
        df_html["Image"] = df_html["Image"].apply(lambda x: f'<img src="{x or FALLBACK_IMAGE}" width="100">')
    html = f"""
    <html><head><style>
    body {{ font-family: Arial; padding: 20px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; }}
    th {{ background-color: #f4f4f4; }}
    img {{ display: block; margin: 5px 0; }}
    </style></head><body>
    <h2>Jubilee Inventory Report</h2>
    <p>Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    {df_html.to_html(escape=False, index=False)}
    </body></html>
    """
    return html

def download_html_report(df):
    html = get_printable_html(df)
    b64 = base64.b64encode(html.encode()).decode()
    href = f'<a href="data:text/html;base64,{b64}" download="jubilee_inventory_report.html">📄 Download Printable Report</a>'
    st.markdown(href, unsafe_allow_html=True)

# --- Main ---
def main():
    st.set_page_config(layout="wide", page_title="Jubilee Inventory")
    st.title("Jubilee Inventory Management System")

    if not check_auth():
        st.stop()

    tab1, tab2 = st.tabs(["➕ Add Product", "📦 Inventory"])

    with tab1:
        add_product()

    with tab2:
        df = pd.DataFrame(sheet.get_all_records())
        df["PCS"] = pd.to_numeric(df["PCS"], errors="coerce").fillna(0).astype(int)
        df["Delivery_PCS"] = pd.to_numeric(df["Delivery_PCS"], errors="coerce").fillna(0).astype(int)
        df["Rate"] = pd.to_numeric(df["Rate"], errors="coerce").fillna(0.0)
        df["Total"] = pd.to_numeric(df["Total"], errors="coerce").fillna(0.0)
        df["Pending"] = df["PCS"] - df["Delivery_PCS"]

        st.metric("Total PCS", df["PCS"].sum())
        st.metric("Pending PCS", df["Pending"].sum())
        st.metric("Total Value", f"₹{df['Total'].sum():,.0f}")

        st.markdown(get_download_links(df), unsafe_allow_html=True)
        download_html_report(df)

        # Altair Chart
        if not df.empty:
            chart = alt.Chart(df).mark_bar().encode(
                x=alt.X("Company", sort='-y'),
                y="PCS",
                tooltip=["Company", "PCS"]
            ).properties(title="PCS by Company")
            st.altair_chart(chart, use_container_width=True)

        with st.expander("🔍 Filter"):
            f1, f2 = st.columns(2)
            company = f1.multiselect("Company", df["Company"].unique())
            ptype = f2.multiselect("Type", df["Type"].unique())
            search = st.text_input("Keyword Search").lower()
            if company:
                df = df[df["Company"].isin(company)]
            if ptype:
                df = df[df["Type"].isin(ptype)]
            if search:
                df = df[df.apply(lambda r: search in str(r).lower(), axis=1)]

        for idx, row in df.iterrows():
            with st.expander(f"{row['Company']} - {row['D.NO']} | Pending: {row['Pending']}"):
                st.image(row['Image'] or FALLBACK_IMAGE, width=200)
                st.write(f"**PCS**: {row['PCS']} | **Delivered**: {row['Delivery_PCS']} | **Rate**: ₹{row['Rate']:.2f} | **Total**: ₹{row['Total']:.2f}")
                st.write(f"**Matching**: {row['Matching']} | **Type**: {row['Type']} | **Assignee**: {row['Assignee']}")

                with st.form(f"edit_{idx}"):
                    e1, e2, e3 = st.columns(3)
                    company = e1.text_input("Company", value=row["Company"])
                    dno = e2.text_input("D.NO", value=row["D.NO"])
                    diamond = e3.text_input("Diamond", value=row["Diamond"])
                    delivery = st.number_input("Delivery PCS", value=row["Delivery_PCS"], min_value=0)
                    rate = st.number_input("Rate", value=row["Rate"], step=0.01)
                    assignee = st.text_input("Assignee", value=row["Assignee"])
                    ptype = st.selectbox("Type", ["WITH LACE", "WITHOUT LACE"], index=0 if row["Type"] == "WITH LACE" else 1)
                    image = st.file_uploader("Replace Image", type=["jpg", "jpeg", "png"])
                    update_btn, delete_btn = st.columns(2)

                    if update_btn.form_submit_button("Update"):
                        new_img = upload_to_drive(image) if image else row["Image"]
                        new_row = [company, dno, row["Matching"], diamond, row["PCS"], delivery, assignee, ptype, rate, row["PCS"] * rate, new_img, datetime.now().isoformat()]
                        sheet.update(f"A{idx+2}:L{idx+2}", [new_row])
                        log_action("Update", f"{company} - {dno}")
                        st.success("Updated!")
                        st.rerun()

                    if delete_btn.form_submit_button("Delete"):
                        cache_deleted(row.tolist())
                        sheet.delete_rows(idx+2)
                        log_action("Delete", f"{row['Company']} - {row['D.NO']}")
                        st.warning("Deleted!")
                        st.rerun()

        if st.button("Undo Last Delete"):
            undo_delete()

if __name__ == "__main__":
    main()
