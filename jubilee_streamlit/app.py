# jubilee_inventory_app.py

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
import os
from pathlib import Path

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

# === PAGE CONFIG ===
st.set_page_config(
    page_title="Jubilee Inventory",
    page_icon="logo.png",
    layout="wide",
    initial_sidebar_state="expanded"  # Ensures sidebar remains visible by default
)

# === TOGGLE SIDEBAR BUTTON OUTSIDE SIDEBAR ===
with st.container():
    st.markdown("""
        <style>
        .toggle-button {
            position: fixed;
            top: 15px;
            left: 15px;
            z-index: 9999;
            background-color: #333;
            color: white;
            padding: 8px 12px;
            border-radius: 6px;
            font-weight: bold;
            cursor: pointer;
        }
        </style>
        <script>
        function toggleSidebar() {
            const sidebar = window.parent.document.querySelector("section[data-testid='stSidebar']");
            if (sidebar) sidebar.style.display = sidebar.style.display === 'none' ? 'block' : 'none';
        }
        </script>
        <div class="toggle-button" onclick="toggleSidebar()">🔁 Toggle Sidebar</div>
    """, unsafe_allow_html=True)

# === PATH CONFIG ===
logo_path = Path(__file__).parent / "logo.png"

# === HELPERS ===
def load_data():
    df = pd.DataFrame(sheet.get_all_records())
    df = df.drop_duplicates(subset=["D.NO."]).reset_index(drop=True)
    for col in required_columns:
        if col not in df.columns:
            df[col] = ""
    df["Created"] = pd.to_datetime(df["Created"], errors="coerce")
    df["Updated"] = pd.to_datetime(df["Updated"], errors="coerce")
    df["Status"] = df["PCS"].apply(calculate_status)
    return df.sort_values("Created", ascending=False)

def save_data(df):
    df = df[required_columns]
    sheet.clear()
    sheet.update([df.columns.tolist()] + df.astype(str).values.tolist())

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

def make_clickable(url):
    return f'<img src="{url}" width="100">' if url else ""

def calculate_status(pcs):
    pcs = int(float(pcs or 0))
    if pcs == 0:
        return "OUT OF STOCK"
    elif pcs < 5:
        return "LOW STOCK"
    else:
        return "IN STOCK"

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

# === INIT ===
required_columns = ["D.NO.", "Company", "Type", "PCS", "Rate", "Total", "Matching", "Image", "Created", "Updated", "Status"]

if "force_reload" not in st.session_state:
    st.session_state.force_reload = False

if "highlight_dno" not in st.session_state:
    st.session_state.highlight_dno = None

df = load_data()

# === FILTERING ===
filtered_df = df.copy()
type_filter = st.selectbox("Type", ["All"] + sorted(df["Type"].dropna().unique().tolist()))
search = st.text_input("Search D.NO. or Company")

if type_filter != "All":
    filtered_df = filtered_df[filtered_df["Type"] == type_filter]
if search:
    all_text = df["D.NO."].fillna("").tolist() + df["Company"].fillna("").tolist()
    matched = process.extract(search, all_text, limit=20)
    hits = set([m[0] for m in matched if m[1] > 60])
    filtered_df = df[df["D.NO."].isin(hits) | df["Company"].isin(hits)]

# === Safe rerun ===
def safe_rerun():
    st.session_state.force_reload = False
    try:
        st.experimental_rerun()
    except st.script_run_context.RerunException:
        pass

if st.session_state.get("force_reload"):
    safe_rerun()

# === BRAND HEADER ===
st.markdown("""
    <style>
        .block-container { padding-top: 1rem; }
        header { visibility: hidden; }
    </style>
""", unsafe_allow_html=True)

col1, col2 = st.columns([1, 6])
with col1:
    if logo_path.exists():
        st.image(str(logo_path), width=40)
    else:
        st.markdown("<p style='color:red;'>[Logo not found]</p>", unsafe_allow_html=True)
with col2:
    st.markdown("<h1 style='margin-top: 16px;'>JUBILEE TEXTILE PROCESSORS</h1>", unsafe_allow_html=True)

# === SIDEBAR ===
with st.sidebar:
    if logo_path.exists():
        st.image(str(logo_path), width=120)
    else:
        st.text("[Logo not found]")
    st.markdown("<h3 style='text-align:center; color:white;'>JUBILEE TEXTILE PROCESSORS</h3>", unsafe_allow_html=True)
    st.header("🔍 Filter")
    # type_filter and search already handled

    st.metric("Total PCS", int(df["PCS"].fillna(0).sum()))
    st.metric("Total Value", f"₹{df['Total'].fillna(0).sum():,.2f}")

    with st.expander("⬇️ Export Options"):
        export_format = st.radio("Select format", ["CSV", "Excel"], horizontal=True)
        export_df = filtered_df[required_columns]
        if export_format == "CSV":
            csv = export_df.to_csv(index=False).encode("utf-8")
            st.download_button("Download CSV", csv, "jubilee_inventory.csv", "text/csv")
        else:
            from io import BytesIO
            excel_io = BytesIO()
            with pd.ExcelWriter(excel_io, engine="xlsxwriter") as writer:
                export_df.to_excel(writer, index=False, sheet_name="Inventory")
            st.download_button("Download Excel", excel_io.getvalue(), "jubilee_inventory.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with st.expander("🧾 Printable Report"):
        html_report = generate_html_report(filtered_df[required_columns])
        st.download_button("Download HTML Report", html_report.encode(), "jubilee_inventory_report.html", "text/html")

# === SCROLLABLE DATA TABLE ===
st.markdown("""
    <style>
    .scroll-table-wrapper {
        max-height: 400px;
        overflow-y: scroll;
        overflow-x: auto;
        border: 1px solid #444;
        border-radius: 6px;
        padding: 10px;
        background-color: #111;
    }
    .scroll-table-wrapper table {
        color: white;
        width: 100%;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown("### 📊 Inventory Table")
highlight_dno = st.session_state.get("highlight_dno")
highlighted_df = filtered_df.copy()

with st.container():
    if highlight_dno:
        highlighted_df["__highlight__"] = highlighted_df["D.NO."].apply(lambda x: "background-color: #ffe599" if x == highlight_dno else "")
        html_table = highlighted_df.drop(columns="__highlight__") \
            .assign(Image=highlighted_df["Image"].apply(make_clickable)) \
            .style.apply(lambda x: highlighted_df["__highlight__"], axis=1) \
            .to_html(escape=False, index=False)
    else:
        html_table = filtered_df.assign(Image=filtered_df["Image"].apply(make_clickable)) \
            .to_html(escape=False, index=False)

    st.markdown('<div class="scroll-table-wrapper">' + html_table + '</div>', unsafe_allow_html=True)


# === FORM: ADD / EDIT PRODUCT ===
st.markdown("---")
st.subheader("➕ Add / Edit Product")
form_mode = st.radio("Mode", ["Add New", "Edit Existing"], horizontal=True)
selected_dno = st.selectbox("Select D.NO. to Edit", sorted(filtered_df["D.NO."].dropna().unique())) if form_mode == "Edit Existing" else ""

if form_mode == "Edit Existing" and selected_dno:
    selected_row = df[df["D.NO."] == selected_dno]
    selected_data = selected_row.iloc[0] if not selected_row.empty else {}
else:
    selected_data = {}

def get_default(key, default):
    if isinstance(selected_data, pd.Series) and key in selected_data:
        return selected_data.get(key, default)
    return default

with st.form("product_form"):
    col1, col2 = st.columns(2)
    with col1:
        company = st.text_input("Company", value=get_default("Company", ""))
        dno = st.text_input("D.NO.", value=get_default("D.NO.", ""))
        rate = st.number_input("Rate", min_value=0.0, value=float(get_default("Rate", 0)))
        pcs = st.number_input("PCS", min_value=0, value=int(float(get_default("PCS", 0))))
    with col2:
        type_options = ["WITH LACE", "WITHOUT LACE"]
        default_type = get_default("Type", "WITH LACE")
        type_ = st.selectbox("Type", type_options, index=type_options.index(default_type) if default_type in type_options else 0)
        matching_table = st.data_editor(
            [{"Color": "", "PCS": 0}] if get_default("Matching", "") == "" else
            [{"Color": m.split(":")[0], "PCS": int(m.split(":")[1])} for m in get_default("Matching", "").split(",") if ":" in m],
            num_rows="dynamic", key="match_editor",
            column_config={"PCS": st.column_config.NumberColumn("PCS", min_value=0)}
        )
        image_file = st.file_uploader("Upload Image", type=["jpg", "jpeg", "png"])

        # === Preview uploaded image or existing one ===
        preview_url = get_default("Image", "")
        if image_file:
            st.image(image_file, caption="Preview (New Upload)", use_column_width=True)
        elif preview_url:
            st.image(preview_url, caption="Preview (Current)", use_column_width=True)

    submitted = st.form_submit_button("Save Product")

    if submitted:
        match_entries, total_pcs = [], 0
        for row in matching_table:
            color_val = str(row.get("Color") or "").strip()
            pcs_val = int(float(row.get("PCS") or 0))
            if color_val:
                match_entries.append(f"{color_val}:{pcs_val}")
                total_pcs += pcs_val

        if not company or not dno:
            st.warning("Company and D.NO. are required.")
        else:
            image_url = upload_image(image_file) if image_file else get_default("Image", "")
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            df = df[df["D.NO."] != dno]
            df = pd.concat([df, pd.DataFrame([{
                "D.NO.": dno.strip().upper(), "Company": company.strip().upper(), "Type": type_,
                "PCS": total_pcs, "Rate": rate, "Total": rate * total_pcs,
                "Matching": ", ".join(match_entries), "Image": image_url,
                "Updated": now, "Created": get_default("Created", now), "Status": calculate_status(total_pcs)
            }])], ignore_index=True)
            save_data(df)
            st.success("Changes saved successfully.")
            st.toast("✅ Product updated.")
            st.session_state.force_reload = True
            st.session_state.highlight_dno = dno.strip().upper()

# === DELETE ===
st.markdown("---")
st.subheader("🗑️ Delete Product")
if not df.empty:
    del_dno = st.selectbox("Select D.NO. to Delete", df["D.NO."].unique())
    if st.button("Confirm Delete"):
        if del_dno and "D.NO." in df.columns:
            df = df[df["D.NO."] != del_dno]
            save_data(df)
            st.success(f"Deleted {del_dno}")
            st.toast("🗑️ Product deleted.")
            st.session_state.force_reload = True
        else:
            st.warning("⚠️ Unable to delete: Invalid D.NO. or missing column.")
