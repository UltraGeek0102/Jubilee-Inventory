# jubilee_inventory_app.py

# --- IMPORTS ---
import io
import uuid
import base64
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image
import numpy as np
from streamlit_gsheets import GSheetsConnection

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials as UserCreds

# --- CONFIG ---
REQUIRED_COLUMNS = [
    "D.NO.", "Company", "Type", "PCS", "Rate", "Total", "Matching", "Image",
    "Created", "Updated", "Status", "Delivery PCS", "Difference in PCS"
]

# Minimized scopes (principle of least privilege)
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",  # per-file access; not full drive
]

# Asset paths (optional)
LOGO_PATH = Path(__file__).parent / "logo.png"
FAVICON_PATH = Path(__file__).parent / "favicon.ico"

# --- PAGE SETUP ---
st.set_page_config(page_title="Jubilee Inventory", page_icon="logo.png", layout="centered")

if FAVICON_PATH.exists():
    try:
        favicon_b64 = base64.b64encode(FAVICON_PATH.read_bytes()).decode()
        # No-op styling hook; keep if you later inline favicon via HTML
        st.markdown("", unsafe_allow_html=True)
    except Exception:
        pass

# --- HELPERS ---
def calculate_status(pcs):
    try:
        pcs_val = int(float(pcs or 0))
    except Exception:
        pcs_val = 0
    if pcs_val == 0:
        return "OUT OF STOCK"
    elif pcs_val < 5:
        return "LOW STOCK"
    return "IN STOCK"

def ensure_required_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            df[col] = "" if col not in ("PCS", "Rate", "Total") else 0
    return df

def serialize_datetimes(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ["Created", "Updated"]:
        df[col] = df[col].apply(
            lambda x: x.strftime("%Y-%m-%d %H:%M:%S") if isinstance(x, datetime) else ("" if pd.isna(x) else str(x))
        )
    return df

def parse_datetimes(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ["Created", "Updated"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    return df

def build_drive_client_from_session():
    # Requires st.session_state["token"] populated by your OAuth login step (not included here).
    token = st.session_state.get("token")
    if not token or "access_token" not in token:
        raise RuntimeError("Missing user token in session for Drive upload")

    oauth = st.secrets.get("gcp_oauth", {})
    if not oauth:
        raise RuntimeError("Missing gcp_oauth in secrets")

    creds = UserCreds(
        token=token["access_token"],
        refresh_token=token.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=oauth.get("client_id"),
        client_secret=oauth.get("client_secret"),
        scopes=SCOPES,
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)

def upload_image_to_drive(image_file) -> str:
    """
    Uploads file to Drive folder defined in secrets: gcp_oauth.upload_folder_id
    Returns a web-accessible link if configured; avoids public permission by default.
    """
    try:
        drive = build_drive_client_from_session()
        folder_id = st.secrets["gcp_oauth"]["upload_folder_id"]
        media = MediaIoBaseUpload(io.BytesIO(image_file.read()), mimetype=image_file.type, resumable=False)
        meta = {"name": f"{uuid.uuid4()}.jpg", "parents": [folder_id]}
        f = drive.files().create(body=meta, media_body=media, fields="id,webViewLink,webContentLink").execute()

        # By default, do NOT set public permissions. If you must, toggle via secrets.
        make_public = bool(st.secrets.get("gcp_oauth", {}).get("public_image_links", False))
        if make_public:
            drive.permissions().create(
                fileId=f["id"], body={"type": "anyone", "role": "reader"}
            ).execute()

        # Prefer webViewLink; if public, webContentLink may be downloadable.
        return f.get("webViewLink") or f.get("webContentLink") or f"https://drive.google.com/uc?id={f['id']}"
    except HttpError as e:
        st.error(f"Google Drive error: {e}")
        return ""
    except Exception as e:
        st.error(f"Image upload failed: {e}")
        return ""

def load_data(conn, worksheet=None):
    try:
        df = conn.read(worksheet=worksheet, ttl=0)
        if df is None or len(getattr(df, "columns", [])) == 0:
            df = pd.DataFrame(columns=REQUIRED_COLUMNS)
        df = ensure_required_columns(df)
        if "D.NO." in df.columns:
            df = df.drop_duplicates("D.NO.").reset_index(drop=True)
        pcs_series = df["PCS"] if "PCS" in df.columns else pd.Series(np.zeros(len(df), dtype=int))
        df["Status"] = pcs_series.apply(calculate_status)
        df = parse_datetimes(df)
        if "Created" in df.columns:
            df = df.sort_values("Created", ascending=False, na_position="last").reset_index(drop=True)
        return df
    except Exception as e:
        st.error(f"Failed to load data from Google Sheets: {e}")
        return pd.DataFrame(columns=REQUIRED_COLUMNS)

def save_data(conn: GSheetsConnection, df: pd.DataFrame, worksheet: str = None):
    if df is None:
        st.error("No data to save.")
        return
    try:
        df_out = ensure_required_columns(df)
        df_out = serialize_datetimes(df_out)
        # only write required columns to keep sheet schema stable
        ordered = [c for c in REQUIRED_COLUMNS if c in df_out.columns]
        df_out = df_out[ordered]
        conn.update(worksheet=worksheet, data=df_out)
        st.success("Saved to Google Sheets.")
    except Exception as e:
        st.error(f"Failed to save data to Google Sheets: {e}")

def render_image_thumbnails(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    def _html(url: str) -> str:
        if isinstance(url, str) and url.strip():
            # Basic thumbnail rendering; Streamlit will safely render via st.markdown if unsafe_allow_html=True
            return f'<img src="{url}" alt="image" style="height:64px;border:1px solid #ddd;border-radius:6px;" />'
        return ""
    if "Image" in df.columns:
        df["Image"] = df["Image"].apply(_html)
    return df

# --- APP BODY ---
st.title("Jubilee Inventory")

# Streamlit GSheets connection (requires secrets)
# .streamlit/secrets.toml must define [connections.gsheets] with spreadsheet and service_account fields
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.stop()

worksheet_name = st.secrets.get("connections", {}).get("gsheets", {}).get("worksheet", None)

# Load data
df = load_data(conn, worksheet=worksheet_name)

# Quick controls (example)
st.subheader("Inventory")
st.caption("Edit fields and click Save to persist changes.")

if not df.empty:
    # editable data editor; avoid editing Image HTML directly
    display_cols = [c for c in df.columns if c != "Image"]
    edited = st.data_editor(
    df[display_cols],
    num_rows="dynamic",
    use_container_width=True,
    disabled=["Status", "Created", "Updated"],
    key="editor",
    )
    if isinstance(edited, pd.DataFrame):
        pcs_series = edited["PCS"] if "PCS" in edited.columns else pd.Series(np.zeros(len(edited), dtype=int))
        edited["Status"] = pcs_series.apply(calculate_status)
        now = datetime.now()
        if "Created" in edited.columns:
            created_mask = edited["Created"].isna() | (edited["Created"] == "") | (edited["Created"].astype(str) == "NaT")
            edited.loc[created_mask, "Created"] = now
        if "Updated" in edited.columns:
            edited["Updated"] = now
        if "Image" in df.columns:
            edited["Image"] = df["Image"]


        if st.button("Save"):
            save_data(conn, edited, worksheet=worksheet_name)
else:
    st.info("No rows yet. Use the editor below to add records.")
    # Start an empty editor aligned with schema
    empty_df = pd.DataFrame([{c: "" for c in REQUIRED_COLUMNS}])
    created = st.data_editor(empty_df, num_rows="dynamic", use_container_width=True, key="creator")
    if st.button("Save initial"):
        save_data(conn, created, worksheet=worksheet_name)

# Image upload
st.subheader("Upload Item Image")
img_file = st.file_uploader("Select image", type=["png", "jpg", "jpeg"], accept_multiple_files=False)
if img_file:
    col1, col2 = st.columns(2)
    with col1:
        try:
            st.image(Image.open(img_file), caption="Preview", use_container_width=True)
        except Exception:
            st.warning("Unable to preview image.")

    if st.button("Upload to Drive"):
        url = upload_image_to_drive(img_file)
        if url:
            st.success("Image uploaded.")
            st.write(url)
        else:
            st.error("Upload failed. Check OAuth login and folder permissions.")

st.divider()
st.caption("Powered by Google Sheets + Streamlit Connection. Images stored in Drive with minimal scopes.")

