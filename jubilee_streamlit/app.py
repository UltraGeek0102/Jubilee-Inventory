# jubilee_streamlit_app.py (Phase 3: Google Drive Image Upload)
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
sheet = client.open(SHEET_NAME).sheet1
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

# ========== Tab 1: Inventory Dashboard ==========
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
        selected_dno = st.selectbox("Select D.NO to Edit", df["D.NO."].unique()) if form_mode == "Edit Existing" and not df.empty else ""
        with st.form("product_form"):
            col1, col2 = st.columns(2)
            with col1:
                company = st.text_input("Company Name")
                dno = st.text_input("D.NO.", value=selected_dno)
                diamond = st.text_input("Diamond")
                assignee = st.text_input("Assignee")
            with col2:
                type_val = st.selectbox("Type", ["WITH LACE", "WITHOUT LACE"])
                rate = st.number_input("Rate", min_value=0.0)
                delivery_pcs = st.number_input("Delivery PCS", min_value=0)
            if form_mode == "Add New" and dno in df["D.NO."].values:
                st.error("D.NO. already exists. Use 'Edit Existing' to update.")
                st.stop()
            if not company.strip() or not dno.strip():
                st.warning("Company Name and D.NO. are required.")

            st.markdown("### Matching Colors")
            match_entries = []
            total_pcs = 0
            num_colors = st.number_input("Number of Colors", min_value=0, max_value=20, value=0)
            for i in range(num_colors):
                c1, c2 = st.columns([3, 1])
                color = c1.text_input(f"Color {i+1}", key=f"color_{i}")
                pcs = c2.number_input(f"PCS {i+1}", min_value=0, key=f"pcs_{i}")
                if color:
                    match_entries.append(f"{color}:{pcs}")
                    total_pcs += pcs

            image_file = st.file_uploader("Upload Image", type=["jpg", "jpeg", "png"])
            image_url = upload_image_to_drive(image_file) if image_file else ""

            if st.form_submit_button("Save Product"):
                now = datetime.now().isoformat()
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
                        for key in new_data:
                            df.at[index[0], key] = new_data[key]
                        st.success(f"Updated product: {selected_dno}")
                else:
                    new_data["Created At"] = now
                    df = pd.concat([df, pd.DataFrame([new_data])], ignore_index=True)
                    st.success(f"Added new product: {dno}")
                save_data(df)

    st.markdown("---")
    st.subheader("🔊 Delete Products")
    if not df.empty:
        selected = st.multiselect("Select D.NO. to delete", df["D.NO."].unique())
        if st.button("Delete Selected") and selected:
            df = df[~df["D.NO."].isin(selected)]
            save_data(df)
            st.success(f"Deleted: {', '.join(selected)}")
    else:
        st.info("No products available.")

    st.markdown("---")
    st.subheader("🖼️ Preview Images")
    for idx, row in filtered_df.iterrows():
        if row["Image"]:
            st.markdown(f"**{row['D.NO.']} - {row['COMPANY NAME']}**")
            st.image(row["Image"], width=300)
            st.markdown("---")

# ========== Tab 2: Analytics ==========
with tab2:
    st.title("📊 Inventory Analytics")
    if not df.empty:
        type_chart = alt.Chart(df).mark_bar().encode(
            x=alt.X('Type:N', title='Saree Type'),
            y=alt.Y('sum(PCS):Q', title='Total PCS'),
            color='Type'
        ).properties(title="Total PCS by Type")

        rate_chart = alt.Chart(df).mark_circle(size=80).encode(
            x='Rate', y='PCS', color='Type', tooltip=['D.NO.', 'COMPANY NAME', 'Rate', 'PCS']
        ).properties(title="Rate vs PCS")

        st.altair_chart(type_chart, use_container_width=True)
        st.altair_chart(rate_chart, use_container_width=True)
    else:
        st.info("No data available for analytics.")
