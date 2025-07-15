# jubilee_inventory_app.py (Polished Full Version with Matching Table and Delivery Tracking)

# --- IMPORTS ---
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from datetime import datetime
from pathlib import Path
from PIL import Image
import base64
import io
import os

# OAuth-related
from google_auth_oauthlib.flow import Flow
from thefuzz import process

# --- CONFIG ---
SHEET_NAME = "jubilee-inventory"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# --- SETUP ---
sheet_creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"], scopes=SCOPES
)
client = gspread.authorize(sheet_creds)
sheet = client.open(SHEET_NAME).sheet1

# --- GOOGLE DRIVE (OAuth) ---
def get_drive_service():
    if "drive_creds" not in st.session_state:
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": st.secrets["google_oauth"]["client_id"],
                    "client_secret": st.secrets["google_oauth"]["client_secret"],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://localhost:8501"]
                }
            },
            scopes=["https://www.googleapis.com/auth/drive.file"],
            redirect_uri="http://localhost:8501"
        )
        auth_url, _ = flow.authorization_url(prompt="consent")
        st.warning("Authorize the app to upload to your Google Drive.")
        st.markdown(f"[Click here to authorize]({auth_url})", unsafe_allow_html=True)

        code = st.text_input("Paste the code here after authorization:")
        if code:
            flow.fetch_token(code=code)
            creds = flow.credentials
            st.session_state["drive_creds"] = creds
    else:
        creds = st.session_state["drive_creds"]

    return build("drive", "v3", credentials=creds)

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="Jubilee Inventory",
    page_icon="logo.png",
    layout="centered"
)

# --- STYLE ---
st.markdown("""
    <meta name='viewport' content='width=device-width, initial-scale=1.0'>
    <style>
        @media (max-width: 768px) {
            .block-container { padding: 1rem !important; }
            h1 { font-size: 1.5rem !important; }
        }
        footer { visibility: hidden; }
        .fixed-table-wrapper {
            max-height: 500px;
            overflow-y: scroll;
            overflow-x: auto;
            border: 1px solid #555;
            padding: 10px;
            border-radius: 8px;
            background: #111;
        }
        .fixed-table-wrapper table {
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
            color: #fff;
        }
        .fixed-table-wrapper th,
        .fixed-table-wrapper td {
            padding: 8px;
            border: 1px solid #333;
        }
        .fixed-table-wrapper thead {
            background-color: #222;
            position: sticky;
            top: 0;
            z-index: 1;
        }
    </style>
""", unsafe_allow_html=True)

# --- GLOBAL VARS ---
REQUIRED_COLUMNS = [
    "D.NO.", "Company", "Type", "PCS", "Rate", "Total",
    "Matching", "Image", "Created", "Updated", "Status",
    "Delivery PCS", "Difference in PCS"
]
LOGO_PATH = Path(__file__).parent / "logo.png"

# --- HELPERS ---
def load_data():
    df = pd.DataFrame(sheet.get_all_records())
    df = df.drop_duplicates(subset=["D.NO."]).reset_index(drop=True)
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df["Created"] = pd.to_datetime(df["Created"], errors="coerce")
    df["Updated"] = pd.to_datetime(df["Updated"], errors="coerce")
    df["Status"] = df["PCS"].apply(calculate_status)
    df["Created"] = df["Created"].fillna("")
    df["Updated"] = df["Updated"].fillna("")
    return df.sort_values("Created", ascending=False)

def save_data(df):
    df = df[REQUIRED_COLUMNS]
    sheet.clear()
    sheet.update([df.columns.tolist()] + df.astype(str).values.tolist())

def calculate_status(pcs):
    pcs = int(float(pcs or 0))
    if pcs == 0:
        return "OUT OF STOCK"
    elif pcs < 5:
        return "LOW STOCK"
    else:
        return "IN STOCK"

def upload_image(image_file):
    if image_file is None:
        return ""

    drive_service = get_drive_service()
    image_file.seek(0)
    file_bytes = image_file.read()
    image_file.seek(0)

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"{Path(image_file.name).stem}_{timestamp}.png"
    file_metadata = {
        "name": filename,
        "parents": [st.secrets["drive"].get("folder_id", "")]
    }

    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=image_file.type, resumable=True)
    uploaded = drive_service.files().create(body=file_metadata, media_body=media, fields="id").execute()
    file_id = uploaded.get("id")
    return f"https://drive.google.com/uc?id={file_id}"

def make_clickable(url):
    if not url:
        return ""
    if "drive.google.com/uc?id=" in url:
        return f'<img src="{url}" style="width:100px; height:auto; border-radius:8px;">'
    return ""

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

def get_default(selected_data, key, default):
    return selected_data.get(key, default) if isinstance(selected_data, pd.Series) else default

# --- FORM EXAMPLE ---
with st.form("product_form"):
    col1, col2 = st.columns(2)
    with col1:
        company = st.text_input("Company")
        dno = st.text_input("D.NO.")
        rate = st.number_input("Rate", min_value=0.0, value=0.0)
    with col2:
        type_ = st.selectbox("Type", ["WITH LACE", "WITHOUT LACE"])
        image_file = st.file_uploader("Upload Image", type=["jpg", "jpeg", "png"])

    matching_table = st.data_editor(
        [{"Color": "", "PCS": 0}],
        num_rows="dynamic",
        key="match_editor",
        column_config={"PCS": st.column_config.NumberColumn("PCS", min_value=0)}
    )

    # Calculate total PCS from matching table
    total_pcs = sum(int(float(row.get("PCS", 0))) for row in matching_table if row.get("Color"))
    st.markdown(f"**Total PCS:** {total_pcs}")

    delivery_pcs = st.number_input("Delivery PCS", min_value=0, value=0)
    difference_pcs = total_pcs - delivery_pcs
    st.markdown(f"**Difference in PCS:** {difference_pcs}")

    submitted = st.form_submit_button("Save Product")
    if submitted:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        image_url = upload_image(image_file) if image_file else ""

        matching_str = ", ".join([
            f"{row['Color']}:{int(float(row['PCS']))}"
            for row in matching_table if row.get("Color")
        ])

        new_row = {
            "D.NO.": dno.strip().upper(),
            "Company": company.strip().upper(),
            "Type": type_,
            "PCS": total_pcs,
            "Rate": rate,
            "Total": rate * total_pcs,
            "Matching": matching_str,
            "Image": image_url,
            "Created": now,
            "Updated": now,
            "Status": calculate_status(total_pcs),
            "Delivery PCS": delivery_pcs,
            "Difference in PCS": difference_pcs
        }

        df = load_data()
        df = df[df["D.NO."] != dno.strip().upper()]
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        save_data(df)
        st.success("✅ Product saved successfully")
