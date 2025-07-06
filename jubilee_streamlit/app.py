import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from PIL import Image
import io
from datetime import datetime
from thefuzz import process

# === CONFIG ===
SHEET_NAME = "jubilee-inventory"
scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# === AUTH ===
creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
client = gspread.authorize(creds)
sheet = client.open("jubilee-inventory").sheet1
drive_service = build("drive", "v3", credentials=creds)
drive_folder_id = st.secrets["drive"]["folder_id"]

# === HELPERS ===
def load_data():
    return pd.DataFrame(sheet.get_all_records())

def save_data(df):
    sheet.clear()
    sheet.update([df.columns.tolist()] + df.values.tolist())

def upload_image(image_file):
    if not image_file:
        return ""
    image = Image.open(image_file).convert("RGB")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)
    filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{image_file.name}"
    file_metadata = {"name": filename, "parents": [drive_folder_id], "mimeType": "image/png"}
    media = MediaIoBaseUpload(buf, mimetype="image/png")
    uploaded = drive_service.files().create(body=file_metadata, media_body=media, fields="id").execute()
    file_id = uploaded.get("id")
    drive_service.permissions().create(fileId=file_id, body={"role": "reader", "type": "anyone"}).execute()
    return f"https://drive.google.com/uc?id={file_id}"

# === INIT ===
st.set_page_config(page_title="Jubilee Inventory", layout="wide")
st.title("📦 Jubilee Inventory Management System")

df = load_data()
required_columns = ["D.NO.", "Company", "Type", "PCS", "Rate", "Total", "Matching", "Image", "Created", "Updated"]
for col in required_columns:
    if col not in df.columns:
        df[col] = ""

# === FILTERS ===
with st.sidebar:
    st.header("🔍 Filter")
    type_filter = st.selectbox("Type", ["All"] + df["Type"].dropna().unique().tolist())
    search = st.text_input("Search D.NO. or Company")
    filtered_df = df.copy()
    if type_filter != "All":
        filtered_df = filtered_df[filtered_df["Type"] == type_filter]
    if search:
        all_text = df["D.NO."].fillna("").tolist() + df["Company"].fillna("").tolist()
        matched = process.extract(search, all_text, limit=20)
        hits = set([m[0] for m in matched if m[1] > 60])
        filtered_df = df[df["D.NO."].isin(hits) | df["Company"].isin(hits)]

    st.metric("Total PCS", int(df["PCS"].fillna(0).sum()))
    st.metric("Total Value", f"₹{df['Total'].fillna(0).sum():,.2f}")

st.dataframe(filtered_df, use_container_width=True)

# === FORM ===
st.markdown("---")
st.subheader("➕ Add / Edit Product")
form_mode = st.radio("Mode", ["Add New", "Edit Existing"], horizontal=True)
selected_dno = st.selectbox("Select D.NO. to Edit", sorted(filtered_df["D.NO."].dropna().unique())) if form_mode == "Edit Existing" else ""

if form_mode == "Edit Existing" and selected_dno:
    selected_row = filtered_df[filtered_df["D.NO."] == selected_dno]
    if not selected_row.empty:
        selected_data = selected_row.iloc[0]
        default_company = selected_data["Company"]
        default_type = selected_data["Type"]
        default_rate = float(selected_data["Rate"] or 0)
        default_pcs = int(float(selected_data["PCS"] or 0))
        default_matching = selected_data["Matching"]
        default_image = selected_data["Image"]
    else:
        default_company = default_type = default_matching = default_image = ""
        default_rate = default_pcs = 0
else:
    default_company = default_type = default_matching = default_image = ""
    default_rate = default_pcs = 0

with st.form("product_form"):
    col1, col2 = st.columns(2)
    with col1:
        company = st.text_input("Company", value=default_company)
        dno = st.text_input("D.NO.", value=selected_dno)
        rate = st.number_input("Rate", min_value=0.0, value=default_rate)
        pcs = st.number_input("PCS", min_value=0, value=default_pcs)
    with col2:
        type_ = st.selectbox("Type", ["WITH LACE", "WITHOUT LACE"], index=["WITH LACE", "WITHOUT LACE"].index(default_type) if default_type else 0)
        matching_table = st.data_editor(
            [{"Color": "", "PCS": 0}] if default_matching == "" else
            [{"Color": m.split(":")[0], "PCS": int(m.split(":")[1])} for m in default_matching.split(",") if ":" in m],
            num_rows="dynamic", key="match_editor",
            column_config={"PCS": st.column_config.NumberColumn("PCS", min_value=0)}
        )
        image_file = st.file_uploader("Upload Image", type=["jpg", "jpeg", "png"])

    submitted = st.form_submit_button("Save Product")

    if submitted:
        match_entries = []
        total_pcs = 0
        for row in matching_table:
            try:
                pcs_val = int(float(row.get("PCS") or 0))
                color_val = str(row.get("Color") or "").strip()
                if color_val:
                    match_entries.append(f"{color_val}:{pcs_val}")
                    total_pcs += pcs_val
            except:
                continue
        if not company or not dno:
            st.warning("Company and D.NO. are required.")
        else:
            image_url = upload_image(image_file) if image_file else default_image
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            df = df[df["D.NO."] != dno]
            df = pd.concat([df, pd.DataFrame([{
                "D.NO.": dno, "Company": company, "Type": type_, "PCS": total_pcs,
                "Rate": rate, "Total": rate * total_pcs,
                "Matching": ", ".join(match_entries), "Image": image_url,
                "Updated": timestamp, "Created": timestamp if form_mode == "Add New" else selected_data["Created"]
            }])], ignore_index=True)
            save_data(df)
            st.success(f"{'Added' if form_mode == 'Add New' else 'Updated'}: {dno}")
            st.balloons()
            st.toast("✅ Product saved.")
            st.experimental_rerun()

# === DELETE ===
st.markdown("---")
st.subheader("🗑️ Delete Product")
if not df.empty:
    del_dno = st.selectbox("Select D.NO. to Delete", df["D.NO."].unique())
    if st.button("Delete"):
        df = df[df["D.NO."] != del_dno]
        save_data(df)
        st.success(f"Deleted {del_dno}")
        st.toast("🗑️ Product deleted.")
        st.experimental_rerun()
