# app.py — Full Jubilee Inventory Management with All Features

import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import pandas as pd
from PIL import Image
import io
import base64
from datetime import datetime
import uuid
import altair as alt
import os

# --- CONFIG ---
SERVICE_ACCOUNT_FILE = "streamlit-sheet-access@jubilee-inventory.iam.gserviceaccount.com"
SCOPES = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
SPREADSHEET_NAME = "Jubilee_Inventory"
LOG_SHEET_NAME = "Logs"
DRIVE_FOLDER_ID = "your_google_drive_folder_id"
FALLBACK_IMAGE = "https://via.placeholder.com/150"
ROWS_PER_PAGE = 5

# --- Google Auth ---
creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, SCOPES)
client = gspread.authorize(creds)
sheet = client.open(SPREADSHEET_NAME).sheet1
log_sheet = client.open(SPREADSHEET_NAME).worksheet(LOG_SHEET_NAME)
drive_service = build('drive', 'v3', credentials=creds)

# --- Helpers ---
def log_action(action, details):
    log_sheet.append_row([datetime.now().isoformat(), action, details])

def upload_image_to_drive(uploaded_file):
    if uploaded_file is None:
        return FALLBACK_IMAGE
    try:
        image = Image.open(uploaded_file)
        image.thumbnail((600, 600))
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

def get_download_links(df):
    csv = df.to_csv(index=False).encode()
    excel_buffer = io.BytesIO()
    df.to_excel(excel_buffer, index=False)
    excel_buffer.seek(0)
    csv_b64 = base64.b64encode(csv).decode()
    excel_b64 = base64.b64encode(excel_buffer.read()).decode()
    return f"<a href='data:file/csv;base64,{csv_b64}' download='inventory.csv'>CSV</a> | <a href='data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{excel_b64}' download='inventory.xlsx'>Excel</a>"

def printable_html(df):
    html = f"""
    <html><head><style>
    body {{ font-family: Arial; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; }}
    th {{ background-color: #f2f2f2; }}
    img {{ max-height: 100px; }}
    </style></head><body>
    <h2>Jubilee Inventory Report</h2>
    <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    """
    df = df.copy()
    if "Image" in df.columns:
        df["Image"] = df["Image"].apply(lambda x: f"<img src='{x or FALLBACK_IMAGE}' />")
    html += df.to_html(index=False, escape=False)
    html += "</body></html>"
    b64 = base64.b64encode(html.encode()).decode()
    return f"<a href='data:text/html;base64,{b64}' download='report.html'>📄 Download Printable HTML</a>"

# --- UI Logic ---
def add_product_ui():
    st.subheader("➕ Add Product")
    with st.form("add_form"):
        c1, c2, c3 = st.columns(3)
        company = c1.text_input("Company")
        dno = c2.text_input("D.NO")
        diamond = c3.text_input("Diamond")

        matching = {}
        if "add_colors" not in st.session_state:
            st.session_state.add_colors = ["Red", "Blue"]

        with st.expander("Matching (Color + PCS)", expanded=True):
            for i, color in enumerate(st.session_state.add_colors):
                col1, col2, col3 = st.columns([0.2, 2, 1])
                col1.write(f"{i+1}")
                color_val = col2.text_input("Color", value=color, key=f"match_color_{i}")
                pcs_val = col3.number_input("PCS", min_value=0, key=f"match_pcs_{i}")
                if color_val:
                    matching[color_val] = pcs_val
            if st.button("➕ Add More Colors"):
                st.session_state.add_colors.append(f"Color{len(st.session_state.add_colors)+1}")
                st.rerun()

        total_pcs = sum(matching.values())
        delivery = st.number_input("Delivery PCS", min_value=0)
        a1, a2, a3 = st.columns(3)
        assignee = a1.text_input("Assignee")
        ptype = a2.selectbox("Type", ["WITH LACE", "WITHOUT LACE"])
        rate = a3.number_input("Rate", min_value=0.0, step=0.01)
        image = st.file_uploader("Upload Image", type=["jpg", "jpeg", "png"])

        submit = st.form_submit_button("Add Product")
        if submit:
            if not company or not dno or total_pcs == 0:
                st.warning("Company, D.NO, and PCS are required.")
                return
            all_rows = sheet.get_all_records()
            if any(r["Company"].lower() == company.lower() and r["D.NO"].lower() == dno.lower() for r in all_rows):
                st.error("Duplicate entry")
                return
            img_url = upload_image_to_drive(image)
            matching_str = ", ".join(f"{k}:{v}" for k, v in matching.items())
            row = [company, dno, matching_str, diamond, total_pcs, delivery, assignee, ptype, rate, total_pcs*rate, img_url, datetime.now().isoformat()]
            sheet.append_row(row)
            log_action("Add", f"{company}-{dno}")
            st.success("Product added!")
            st.rerun()

def dashboard_ui(df):
    st.subheader("📊 Dashboard")
    df["PCS"] = pd.to_numeric(df["PCS"], errors="coerce").fillna(0)
    df["Delivery_PCS"] = pd.to_numeric(df["Delivery_PCS"], errors="coerce").fillna(0)
    df["Total"] = pd.to_numeric(df["Total"], errors="coerce").fillna(0)
    df["Pending"] = df["PCS"] - df["Delivery_PCS"]

    col1, col2, col3 = st.columns(3)
    col1.metric("Total PCS", int(df["PCS"].sum()))
    col2.metric("Pending", int(df["Pending"].sum()))
    col3.metric("Total Value", f"₹{int(df['Total'].sum())}")

    chart_data = df.groupby("Company")["PCS"].sum().reset_index()
    if not chart_data.empty:
        chart = alt.Chart(chart_data).mark_bar().encode(
            x=alt.X("Company", sort=None),
            y="PCS",
            tooltip=["Company", "PCS"]
        ).properties(title="Total PCS by Company")
        st.altair_chart(chart, use_container_width=True)

def inventory_ui():
    st.subheader("📦 Inventory")
    df = pd.DataFrame(sheet.get_all_records())
    if df.empty:
        st.info("No data in inventory.")
        return

    dashboard_ui(df)
    st.markdown(get_download_links(df), unsafe_allow_html=True)
    st.markdown(printable_html(df), unsafe_allow_html=True)

    with st.expander("🔍 Filter"):
        c1, c2 = st.columns(2)
        f_company = c1.multiselect("Company", options=df["Company"].unique())
        f_type = c2.multiselect("Type", options=df["Type"].unique())
        search = st.text_input("Search")
        if f_company:
            df = df[df["Company"].isin(f_company)]
        if f_type:
            df = df[df["Type"].isin(f_type)]
        if search:
            df = df[df.apply(lambda x: search.lower() in str(x).lower(), axis=1)]

    for idx, row in df.iterrows():
        with st.expander(f"{row['Company']} - {row['D.NO']} | Pending: {row['PCS'] - row['Delivery_PCS']}"):
            st.image(row["Image"] or FALLBACK_IMAGE, width=200)
            st.write(f"**Diamond:** {row['Diamond']}")
            st.write(f"**PCS:** {row['PCS']} | Delivered: {row['Delivery_PCS']} | Rate: ₹{row['Rate']} | Total: ₹{row['Total']}")
            st.write(f"**Matching:** {row['Matching']} | Assignee: {row['Assignee']} | Type: {row['Type']}")
            # Editing / Deleting code can be added here as per need

# --- Main ---
def main():
    st.set_page_config(layout="wide", page_title="Jubilee Inventory")
    st.title("Jubilee Inventory Management")
    tab1, tab2 = st.tabs(["➕ Add Product", "📦 Inventory"])

    with tab1:
        add_product_ui()
    with tab2:
        inventory_ui()

if __name__ == "__main__":
    main()
