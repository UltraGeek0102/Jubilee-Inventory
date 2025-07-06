# jubilee_streamlit_app.py (Final Fixes - Submit Button & Validation)
import streamlit as st
import pandas as pd
import gspread
import json
from google.oauth2.service_account import Credentials
from PIL import Image
import io
from datetime import datetime
from thefuzz import process
import altair as alt
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import base64

# Google Sheets and Drive config using st.secrets
SHEET_NAME = "JubileeInventory"
creds_dict = st.secrets["gcp_service_account"]
drive_folder_id = st.secrets["drive"]["folder_id"]
creds = Credentials.from_service_account_info(creds_dict, scopes=[
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets"])
client = gspread.authorize(creds)
sheet = client.open("jubilee-inventory").sheet1
drive_service = build("drive", "v3", credentials=creds)

# App Config
st.set_page_config(page_title="Jubilee Inventory", layout="wide", page_icon="📦")
tab1, tab2 = st.tabs(["📦 Inventory Dashboard", "📊 Analytics"])

@st.cache_data(show_spinner=False)
def load_data():
    return pd.DataFrame(sheet.get_all_records())

def save_data(df):
    sheet.clear()
    sheet.update([df.columns.tolist()] + df.values.tolist())

def upload_image_to_drive(image_file):
    if not image_file:
        return ""
    file_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{image_file.name}"
    file_metadata = {
        'name': file_name,
        'parents': [drive_folder_id],
        'mimeType': 'image/png'
    }
    image = Image.open(image_file).convert("RGB")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)
    media = MediaIoBaseUpload(buf, mimetype='image/png')
    uploaded = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    file_id = uploaded.get('id')
    drive_service.permissions().create(fileId=file_id, body={"role": "reader", "type": "anyone"}).execute()
    return f"https://drive.google.com/uc?id={file_id}"

# Load inventory
df = load_data()
required_columns = ["COMPANY NAME", "D.NO.", "MATCHING", "Diamond", "PCS", "DELIVERY PCS", "Assignee", "Type", "Rate", "Total", "Image", "Created At", "Updated At"]
if df.empty:
    df = pd.DataFrame(columns=required_columns)
else:
    for col in required_columns:
        if col not in df.columns:
            df[col] = ""

# jubilee_streamlit_app.py (Final Fixes - Submit Button & Validation)
# [... keep all existing import and setup code unchanged ...]

# (BEGINNING OF FIXED MAIN BODY)

# === Tab 1 Layout ===
with tab1:
    st.title("Jubilee Inventory Management System")
    with st.sidebar:
        st.header("🔍 Filter")
        type_filter = st.selectbox("Type", ["All"] + df["Type"].dropna().unique().tolist()) if not df.empty else "All"
        search = st.text_input("Fuzzy Search D.NO. or Company")
        st.markdown("---")
        st.header("📊 Totals")
        st.metric("Total PCS", df["PCS"].sum())
        st.metric("Total Value", f"₹{df['Total'].sum():,.2f}")
        st.metric("Total Delivery PCS", df["DELIVERY PCS"].sum())
        st.markdown("---")
        export_format = st.selectbox("Export Format", ["CSV", "Excel"])
        if st.button("Export Data"):
            filtered = df.copy()
            if type_filter != "All":
                filtered = filtered[filtered["Type"] == type_filter]
            if search:
                all_text = df["D.NO."].fillna("").tolist() + df["COMPANY NAME"].fillna("").tolist()
                matched = process.extract(search, all_text, limit=20)
                hits = set([m[0] for m in matched if m[1] > 60])
                filtered = df[df["D.NO."].isin(hits) | df["COMPANY NAME"].isin(hits)]
            if export_format == "CSV":
                st.download_button("Download CSV", filtered.to_csv(index=False).encode(), "jubilee_inventory.csv")
            else:
                towrite = io.BytesIO()
                with pd.ExcelWriter(towrite, engine='openpyxl') as writer:
                    filtered.to_excel(writer, index=False)
                st.download_button("Download Excel", towrite.getvalue(), "jubilee_inventory.xlsx")

    filtered_df = df.copy()
    if type_filter != "All":
        filtered_df = filtered_df[filtered_df["Type"] == type_filter]
    if search:
        all_text = df["D.NO."].fillna("").tolist() + df["COMPANY NAME"].fillna("").tolist()
        matched = process.extract(search, all_text, limit=20)
        hits = set([m[0] for m in matched if m[1] > 60])
        filtered_df = df[df["D.NO."].isin(hits) | df["COMPANY NAME"].isin(hits)]

    st.dataframe(filtered_df, use_container_width=True)

    st.markdown("---")
    with st.expander("+ Add / Edit Product"):
        form_mode = st.radio("Mode", ["Add New", "Edit Existing"])
        selected_dno = st.selectbox("Select D.NO to Edit", sorted(df["D.NO."].dropna().unique())) if form_mode == "Edit Existing" and not df.empty else ""
        with st.form("product_form"):
            delete_clicked = False

            # Pre-fill values if editing
            if form_mode == "Edit Existing" and selected_dno:
                selected_row = df[df["D.NO."] == selected_dno]
                if not selected_row.empty:
                    selected_data = selected_row.iloc[0]
                    default_company = selected_data["COMPANY NAME"]
                    default_diamond = selected_data["Diamond"]
                    default_assignee = selected_data["Assignee"]
                    default_type = selected_data["Type"]
                    default_rate = float(selected_data["Rate"])
                    default_delivery = int(selected_data["DELIVERY PCS"])
                    default_image = selected_data["Image"]

                    # Load MATCHING back into editable table
                    parsed_match = []
                    try:
                        parts = str(selected_data["MATCHING"]).split(",")
                        for p in parts:
                            if ":" in p:
                                color, pcs = p.strip().split(":")
                                parsed_match.append({"Color": color.strip(), "PCS": int(pcs.strip())})
                        st.session_state.match_data = parsed_match if parsed_match else [{"Color": "", "PCS": 0}]
                    except:
                        st.session_state.match_data = [{"Color": "", "PCS": 0}]
                else:
                    default_company = default_diamond = default_assignee = default_type = ""
                    default_rate = default_delivery = 0.0
                    default_image = ""
            else:
                default_company = default_diamond = default_assignee = default_type = ""
                default_rate = default_delivery = 0.0
                default_image = ""
            col1, col2 = st.columns(2)
            with col1:
                company = st.text_input("Company Name", value=default_company)
                dno = st.text_input("D.NO.", value=selected_dno)
                diamond = st.text_input("Diamond", value=default_diamond)
                assignee = st.text_input("Assignee", value=default_assignee)
            with col2:
                type_val = st.selectbox("Type", ["WITH LACE", "WITHOUT LACE"], index=["WITH LACE", "WITHOUT LACE"].index(default_type) if default_type else 0)
                rate = st.number_input("Rate", min_value=0.0, value=default_rate)
                delivery_pcs = st.number_input("Delivery PCS", min_value=0, value=default_delivery)

            image_file = st.file_uploader("Upload Image", type=["jpg", "jpeg", "png"])
            image_url = upload_image_to_drive(image_file) if image_file else ""

            col_save, col_delete = st.columns([1, 1])
            with col_save:
                submitted = st.form_submit_button("Save Product")
            with col_delete:
                delete_clicked = st.form_submit_button("Delete Product")

            if delete_clicked:
                if form_mode == "Edit Existing" and selected_dno:
                    df = df[df["D.NO."] != selected_dno]
                    save_data(df)
                    st.success(f"Deleted product: {selected_dno}")
                else:
                    st.warning("Please select a product to delete in 'Edit Existing' mode.")

            if submitted:
                now = datetime.now().isoformat()
                match_entries = []
                total_pcs = 0
                for row in st.session_state.match_data:
                    color = str(row.get("Color", "")).strip()
                    try:
                        pcs = int(float(row.get("PCS") or 0))
                    except:
                        pcs = 0
                    if color:
                        match_entries.append(f"{color}:{pcs}")
                        total_pcs += pcs

                if not company.strip() or not dno.strip():
                    st.warning("Company Name and D.NO. are required.")
                elif form_mode == "Add New" and dno in df["D.NO."].values:
                    st.error("D.NO. already exists. Use 'Edit Existing' to update.")
                else:
                    new_data = {
                        "COMPANY NAME": company,
                        "D.NO.": dno,
                        "MATCHING": ", ".join(match_entries),
                        "Diamond": diamond,
                        "PCS": total_pcs,
                        "DELIVERY PCS": delivery_pcs,
                        "Assignee": assignee,
                        "Type": type_val,
                        "Rate": rate,
                        "Total": rate * total_pcs,
                        "Image": image_url,
                        "Updated At": now
                    }
                    if form_mode == "Edit Existing" and selected_dno:
                        index = df[df["D.NO."] == selected_dno].index
                        if not index.empty:
                            if not image_url:
                                new_data["Image"] = df.at[index[0], "Image"]
                            for key in new_data:
                                df.at[index[0], key] = new_data[key]
                            st.success(f"Updated product: {selected_dno}")
                    else:
                        new_data["Created At"] = now
                        df = pd.concat([df, pd.DataFrame([new_data])], ignore_index=True)
                        st.success(f"Added new product: {dno}")
                    save_data(df)

                st.markdown("### MATCHING (Color + PCS)")
            if "match_data" not in st.session_state:
                st.session_state.match_data = [{"Color": "", "PCS": 0}]

            updated_match_df = st.data_editor(
                st.session_state.match_data,
                num_rows="dynamic",
                use_container_width=True,
                key="match_editor",
                column_config={
                    "PCS": st.column_config.NumberColumn("PCS", min_value=0)
                }
            )

            if updated_match_df != st.session_state.match_data:
                st.session_state.match_data = updated_match_df

            clear_match = st.checkbox("Clear Matching Table")
            if clear_match:
                st.session_state.match_data = [{"Color": "", "PCS": 0}]

            total_pcs_preview = 0
            match_preview = []
            for row in st.session_state.match_data:
                try:
                    pcs_val = int(float(row.get("PCS") or 0))
                    color_val = str(row.get("Color") or "").strip()
                    if color_val:
                        match_preview.append(f"{color_val}:{pcs_val}")
                        total_pcs_preview += pcs_val
                except:
                    continue
            st.markdown(f"**Total PCS:** {total_pcs_preview}")
            st.caption("MATCHING Preview: " + ", ".join(match_preview))

