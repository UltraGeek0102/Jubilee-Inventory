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
    csv = df["Difference in PCS"] = df["PCS"] - df["Delivery_PCS"]
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
    if "matching_rows" not in st.session_state:
        st.session_state.matching_rows = ["Red", "Blue", "Green", "Yellow", "Black"]

    with st.form("add_form"):
        col1, col2, col3 = st.columns(3)
        company = col1.text_input("Company")
        dno = col2.text_input("D.NO")
        diamond = col3.text_input("Diamond")
        matching_dict = {}
        with st.expander("Matching Table"):
            st.markdown("<b>Enter color and PCS. Total updates live below.</b>", unsafe_allow_html=True)
            colm1, colm2 = st.columns([2, 1])
            if "matching_rows" not in st.session_state:
                st.session_state.matching_rows = ["Red", "Blue", "Green", "Yellow", "Black"]
            remove_keys = []
            for color in st.session_state.matching_rows:
                with colm1:
                    name = st.text_input(f"Color ({color})", value=color, key=f"color_{color}")
                with colm2:
                    qty = st.number_input(f"PCS", min_value=0, step=1, key=f"qty_{color}")
                if name:
                    matching_dict[name] = qty
            if st.button("➕ Add New Matching Row"):
                st.session_state.matching_rows.append(f"Color{len(st.session_state.matching_rows)+1}")
        matching = ", ".join(f"{k}:{v}" for k, v in matching_dict.items() if v > 0)
        pcs = sum(matching_dict.values())
        st.write(f"🎯 Total PCS: {pcs}")
        st.write(f"🎯 Total PCS: {pcs}")
        delivery = st.number_input("Delivery PCS", min_value=0, format="%d")
        a1, a2, a3 = st.columns(3)
        assignee = a1.text_input("Assignee")
        ptype = a2.selectbox("Type", ["WITH LACE", "WITHOUT LACE", "With Lace", "Without Lace"])
        rate = a3.number_input("Rate", min_value=0.0, step=0.01)
        st.write(f"Total: ₹{pcs * rate:.2f}")
        image = st.file_uploader("Upload Image", type=["png", "jpg", "jpeg"])
        submit = st.form_submit_button("Add")
        if submit:
            existing = sheet.get_all_records()
            conflict = next((r for r in existing if r["Company"] == company and r["D.NO"] == dno), None)
            if conflict:
                msg = f"🚫 Duplicate entry: <b>{company} - {dno}</b> already exists with rate ₹{conflict['Rate']} and PCS {conflict['PCS']}."
                st.markdown(msg, unsafe_allow_html=True)
                return

            img_url = upload_to_drive(image)
            row = [company, dno, matching, diamond, pcs, delivery, assignee, ptype, rate, pcs * rate, img_url, datetime.now().isoformat()]
            try:
                sheet.append_row(row)
                st.success("✅ Product added!")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to add: {e}")

def export_matching_table(df):
    matching_data = []
    for _, row in df.iterrows():
        for pair in row["Matching"].split(","):
            if ":" in pair:
                color, qty = pair.strip().split(":")
                matching_data.append({
                    "Company": row["Company"],
                    "D.NO": row["D.NO"],
                    "Color": color.strip(),
                    "PCS": int(qty.strip())
                })
    export_df = pd.DataFrame(matching_data)
    excel_buf = io.BytesIO()
    with pd.ExcelWriter(excel_buf, engine='xlsxwriter') as writer:
        export_df.to_excel(writer, index=False, sheet_name="Matching")
    st.download_button(
        label="📤 Export Matching Table (All Rows)",
        data=excel_buf.getvalue(),
        file_name="matching_export.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

def show_inventory():
    st.subheader("📦 Inventory")
    df = pd.DataFrame(sheet.get_all_records())
    export_matching_table(df)
    df["SheetRowNum"] = df.index + 2
    df["PCS"] = pd.to_numeric(df["PCS"], errors="coerce").fillna(0).astype(int)
    df["Delivery_PCS"] = pd.to_numeric(df["Delivery_PCS"], errors="coerce").fillna(0).astype(int)
    df["Pending"] = df["PCS"] - df["Delivery_PCS"]
    df["Difference in PCS"] = df["PCS"] - df["Delivery_PCS"]

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
        row = sliced_df.loc[i]
        row_num = int(row["SheetRowNum"])
        with st.expander(f"{row['Company']} - {row['D.NO']} | Pending: {row['Pending']}"):
            if st.button(f"⬇️ Export Matching Only — {row['Company']} {row['D.NO']}", key=f"export_match_{i}"):
                match_pairs = [s.strip() for s in row["Matching"].split(",") if ":" in s]
                match_data = [{"Color": k.split(":")[0].strip(), "PCS": int(k.split(":")[1])} for k in match_pairs]
                match_df = pd.DataFrame(match_data)
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                    match_df.to_excel(writer, index=False, sheet_name="Matching")
                st.download_button(
                    label="📤 Download This Matching Table",
                    data=buf.getvalue(),
                    file_name=f"matching_{row['Company']}_{row['D.NO']}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"match_dl_{i}"
                )
            st.markdown(f'<a href="{row["Image"] or FALLBACK_IMAGE}" target="_blank"><img src="{row["Image"] or FALLBACK_IMAGE}" width="200"></a>', unsafe_allow_html=True)
            st.write(f"Diamond: {row['Diamond']} | Type: {row['Type']} | Assignee: {row['Assignee']}")
            st.write(f"PCS: {row['PCS']} | Delivered: {row['Delivery_PCS']} | ➖ Difference: {row['Difference in PCS']} | Rate: ₹{row['Rate']} | Total: ₹{row['Total']}")
            st.write(f"Matching: {row['Matching']}")
            with st.form(f"edit_{i}"):
                col1, col2, col3 = st.columns(3)
                company = col1.text_input("Company", value=row["Company"])
                dno = col2.text_input("D.NO", value=row["D.NO"])
                diamond = col3.text_input("Diamond", value=row["Diamond"])
                matching_dict = {}
                with st.expander("Matching Table", expanded=False):
                    if f"edit_rows_{i}" not in st.session_state:
                        st.session_state[f"edit_rows_{i}"] = [s.split(":" )[0] for s in row["Matching"].split(",") if ":" in s]
                    colm1, colm2 = st.columns([2, 1])
                    for color in st.session_state[f"edit_rows_{i}"]:
                        val = next((int(s.split(":" )[1]) for s in row["Matching"].split(",") if s.split(":" )[0] == color), 0)
                        with colm1:
                            name = st.text_input(f"Color ({color})", value=color, key=f"edit_color_{i}_{color}")
                        with colm2:
                            qty = st.number_input(f"PCS", value=val, min_value=0, step=1, key=f"edit_qty_{i}_{color}")
                        if name:
                            matching_dict[name] = qty
                    if st.button(f"➕ Add New Matching Row", key=f"add_edit_row_{i}"):
                        st.session_state[f"edit_rows_{i}"].append(f"Color{len(st.session_state[f"edit_rows_{i}"])+1}")
                        with colm1:
                            color = st.text_input(f"Color ({name})", value=name, key=f"edit_color_{i}_{name}")
                        with colm2:
                            pcs_val = st.number_input(f"PCS", value=int(qty), min_value=0, step=1, key=f"edit_qty_{i}_{name}")
                        if color:
                            matching_dict[color] = pcs_val
                matching = ", ".join(f"{k}:{v}" for k, v in matching_dict.items() if v > 0)
                pcs = sum(matching_dict.values())
                st.write(f"🎯 Total PCS: {pcs}")
                st.write(f"💰 Total Value: ₹{pcs * rate:.2f}")
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
                    matching_str = ", ".join(f"{k}:{v}" for k, v in matching_dict.items() if v > 0)
                    pcs = sum(matching_dict.values())
                    new_row = [company, dno, matching_str, diamond, pcs, delivery, assignee, ptype, rate, pcs * rate, image_url, datetime.now().isoformat()]
                    sheet.delete_rows(row_num)
                    sheet.insert_row(new_row, row_num)
                    st.success("✅ Updated")
                    st.rerun()
                if c2.form_submit_button("Delete"):
                    sheet.delete_rows(row_num)
                    st.warning("❌ Deleted")
                    st.experimental_rerun()

show_add_form()
show_inventory()
