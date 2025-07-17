# jubilee_inventory_app_optimized.py

# --- IMPORTS ---
import streamlit as st
import pandas as pd
import gspread
import base64
import io
import uuid
from datetime import datetime
from pathlib import Path
from PIL import Image
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials as UserCreds
from thefuzz import process

# --- CONFIG ---
SHEET_NAME = "jubilee-inventory"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
REQUIRED_COLUMNS = [
    "D.NO.", "Company", "Type", "PCS", "Rate", "Total",
    "Matching", "Image", "Created", "Updated", "Status",
    "Delivery PCS", "Difference in PCS"
]

# --- INIT ---
sheet_creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"], scopes=SCOPES
)
gclient = gspread.authorize(sheet_creds)
sheet = gclient.open(SHEET_NAME).sheet1

LOGO_PATH = Path(__file__).parent / "logo.png"
FAVICON_PATH = Path(__file__).parent / "favicon.ico"

# --- PAGE SETUP ---
st.set_page_config(page_title="Jubilee Inventory", page_icon="logo.png", layout="centered")
if FAVICON_PATH.exists():
    favicon_b64 = base64.b64encode(FAVICON_PATH.read_bytes()).decode()
    st.markdown(f"<link rel='shortcut icon' href='data:image/x-icon;base64,{favicon_b64}'>", unsafe_allow_html=True)

st.markdown("""
    <meta name='viewport' content='width=device-width, initial-scale=1.0'>
    <style>
    .scroll-table-wrapper {
        max-height: 500px;
        overflow-y: auto;
        overflow-x: auto;
        border: 1px solid #555;
        border-radius: 6px;
        background-color: #111;
    }
    
    .scroll-table-wrapper table {
        width: 100%;
        border-collapse: collapse;
        table-layout: fixed;
        min-width: 1000px;
    }
    
    .scroll-table-wrapper thead th {
        position: sticky;
        top: 0;
        z-index: 2;
        background-color: #222;
        color: white;
        padding: 8px;
        border-bottom: 1px solid #777;
        text-align: left;
    }
    
    .scroll-table-wrapper td {
        color: white;
        padding: 8px;
        border-bottom: 1px solid #333;
        word-wrap: break-word;
    }
    
    .scroll-table-wrapper img {
        display: block;
        margin: auto;
    }
    
    /* Sticky first column */
    .scroll-table-wrapper th:first-child,
    .scroll-table-wrapper td:first-child {
        position: sticky;
        left: 0;
        background-color: #222;
        z-index: 3;
        border-right: 1px solid #555;
    }
    </style>
    """, unsafe_allow_html=True)

# --- UTILS ---
def calculate_status(pcs):
    pcs = int(float(pcs or 0))
    if pcs == 0: return "OUT OF STOCK"
    elif pcs < 5: return "LOW STOCK"
    return "IN STOCK"

def load_data():
    df = pd.DataFrame(sheet.get_all_records())
    df = df.drop_duplicates("D.NO.").reset_index(drop=True)
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df["Created"] = pd.to_datetime(df["Created"], errors="coerce").fillna("")
    df["Updated"] = pd.to_datetime(df["Updated"], errors="coerce").fillna("")
    df["Status"] = df["PCS"].apply(calculate_status)
    return df.sort_values("Created", ascending=False)

def save_data(df):
    df_copy = df.copy()
    for col in ["Created", "Updated"]:
        df_copy[col] = df_copy[col].apply(lambda x: x.strftime("%Y-%m-%d %H:%M:%S") if isinstance(x, datetime) else "")
    df_copy = df_copy[[col for col in REQUIRED_COLUMNS if col in df_copy.columns]]
    sheet.clear()
    sheet.update([df_copy.columns.tolist()] + df_copy.astype(str).values.tolist())

def get_default(data, key, default):
    return data.get(key, default) if isinstance(data, pd.Series) else default

def upload_image_to_drive(image_file):
    creds = UserCreds(
        token=st.session_state["token"]["access_token"],
        refresh_token=st.session_state["token"].get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=st.secrets["gcp_oauth"]["client_id"],
        client_secret=st.secrets["gcp_oauth"]["client_secret"],
        scopes=SCOPES
    )
    drive = build("drive", "v3", credentials=creds)
    meta = {"name": f"{uuid.uuid4()}.jpg", "parents": [st.secrets["gcp_oauth"]["upload_folder_id"]]}
    media = MediaIoBaseUpload(io.BytesIO(image_file.read()), mimetype=image_file.type)
    try:
        f = drive.files().create(body=meta, media_body=media, fields="id").execute()
        drive.permissions().create(fileId=f["id"], body={"type": "anyone", "role": "reader"}).execute()
        return f"https://drive.google.com/uc?id={f['id']}"
    except Exception as e:
        st.error(f"Image upload failed: {e}")
        return ""

def render_image_thumbnails(df):
    df = df.copy()
    df["Image"] = df["Image"].apply(lambda url: f'<img src="{url}" width="60">' if url else "")
    return df

def generate_html_report(data):
    return f"""
    <html><head><style>
    body {{ font-family: sans-serif; padding: 20px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border: 1px solid #ccc; padding: 8px; }}
    </style></head><body>
    <h2>Jubilee Inventory Report</h2>
    {data.to_html(index=False)}
    </body></html>
    """

# --- LOAD DATA ---
if "df" not in st.session_state:
    st.session_state.df = load_data()
df = st.session_state.df

# --- LOGO ---
if LOGO_PATH.exists():
    b64_logo = base64.b64encode(LOGO_PATH.read_bytes()).decode()
    st.markdown(f"<div style='text-align:center;'><img src='data:image/png;base64,{b64_logo}' width='180'></div>", unsafe_allow_html=True)

# --- FORM ---
st.subheader("📝 Add or Edit Product")
mode = st.radio("Mode", ["Add New", "Edit Existing"], horizontal=True)
selected_dno = st.selectbox("Select D.NO.", [""] + sorted(df["D.NO."].unique())) if mode == "Edit Existing" else ""
selected_data = df[df["D.NO."] == selected_dno].iloc[0] if selected_dno else {}

with st.form("product_form"):
    col1, col2 = st.columns(2)
    with col1:
        company = st.text_input("Company", get_default(selected_data, "Company", ""))
        dno = st.text_input("D.NO.", get_default(selected_data, "D.NO.", ""))
        rate = st.number_input("Rate", min_value=0.0, value=float(get_default(selected_data, "Rate", 0)))
        pcs = st.number_input("PCS", min_value=0, value=int(float(get_default(selected_data, "PCS", 0))))
    with col2:
        type_ = st.selectbox("Type", ["WITH LACE", "WITHOUT LACE"],
            index=["WITH LACE", "WITHOUT LACE"].index(get_default(selected_data, "Type", "WITH LACE")))
        image_file = st.file_uploader("Upload Image", type=["jpg", "jpeg", "png"])

    matching_raw = get_default(selected_data, "Matching", "")
    match_rows = [{"Color": c.strip(), "PCS": int(float(p))} for c, p in 
                  (item.split(":") for item in matching_raw.split(",") if ":" in item)] if matching_raw else [{"Color": "", "PCS": 0}]

    matching_table = st.data_editor(match_rows, num_rows="dynamic", key="match_editor")

    delivery_pcs = int(float(get_default(selected_data, "Delivery PCS", 0)))
    delivery_input = st.number_input("Delivery PCS", min_value=0, value=delivery_pcs)
    diff_pcs = pcs - delivery_input
    st.markdown(f"**Difference in PCS:** {diff_pcs}")

    if st.form_submit_button("💾 Save Product"):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        image_url = upload_image_to_drive(image_file) if image_file else get_default(selected_data, "Image", "")
        match_str = ", ".join([f"{r['Color']}:{int(r['PCS'])}" for r in matching_table if r['Color']])
        row = {
            "D.NO.": dno.strip().upper(),
            "Company": company.strip().upper(),
            "Type": type_,
            "PCS": pcs,
            "Rate": rate,
            "Total": rate * pcs,
            "Matching": match_str,
            "Image": image_url,
            "Created": get_default(selected_data, "Created", now),
            "Updated": now,
            "Status": calculate_status(pcs),
            "Delivery PCS": delivery_input,
            "Difference in PCS": diff_pcs
        }
        df = df[df["D.NO."] != dno.strip().upper()]
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        st.session_state.df = df
        save_data(df)
        st.success("✅ Product saved successfully!")
        st.experimental_rerun()

# --- SIDEBAR ---
with st.sidebar:
    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), width=150)
    st.metric("Total PCS", int(df["PCS"].fillna(0).sum()))
    st.metric("Total Value", f"₹{df['Total'].fillna(0).sum():,.2f}")
    st.subheader("🗑️ Delete Product")
    del_dno = st.selectbox("Select D.NO. to Delete", df["D.NO."].unique())
    if st.button("Delete Selected Product"):
        df = df[df["D.NO."] != del_dno]
        st.session_state.df = df
        save_data(df)
        st.success(f"Deleted {del_dno}")

# --- FILTER & EXPORT ---
st.subheader("🔍 Filter/Search")
search = st.text_input("Search by D.NO. or Company")
type_filter = st.selectbox("Filter by Type", ["All"] + sorted(df["Type"].dropna().unique()))

filtered_df = df.copy()
if search:
    results = process.extract(search, df["D.NO."].astype(str).tolist() + df["Company"].astype(str).tolist(), limit=25)
    match_keys = {r[0] for r in results if r[1] > 60}
    filtered_df = df[df["D.NO."].isin(match_keys) | df["Company"].isin(match_keys)]
if type_filter != "All":
    filtered_df = filtered_df[filtered_df["Type"] == type_filter]

st.subheader("⬇️ Export")
format_ = st.radio("Choose format", ["Excel", "Printable HTML"])
if format_ == "Excel":
    excel_buf = io.BytesIO()
    with pd.ExcelWriter(excel_buf, engine="xlsxwriter") as writer:
        filtered_df.to_excel(writer, index=False)
    st.download_button("Download Excel", excel_buf.getvalue(), "jubilee_inventory.xlsx")
elif format_ == "Printable HTML":
    html = generate_html_report(filtered_df)
    st.download_button("Download HTML Report", html.encode(), "jubilee_inventory.html")

# --- DISPLAY TABLE ---
st.subheader("📋 Inventory Table with Images")
st.markdown("<div class='scroll-table-wrapper'>", unsafe_allow_html=True)
st.markdown(render_image_thumbnails(filtered_df).to_html(escape=False, index=False), unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)
