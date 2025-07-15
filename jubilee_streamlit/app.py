# jubilee_inventory_app.py (Fixed with session state df caching)

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

# --- PAGE CONFIG ---
st.set_page_config(page_title="Jubilee Inventory", page_icon="logo.png", layout="centered")

# --- FAVICON ---
FAVICON_PATH = Path(__file__).parent / "favicon.ico"
if FAVICON_PATH.exists():
    favicon_bytes = FAVICON_PATH.read_bytes()
    favicon_base64 = base64.b64encode(favicon_bytes).decode()
    st.markdown(
        f"""
        <head>
        <link rel="shortcut icon" href="data:image/x-icon;base64,{favicon_base64}">
        </head>
        """,
        unsafe_allow_html=True
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
        .scroll-table-wrapper {
            max-height: 600px;
            overflow-y: auto;
            border: 1px solid #555;
            border-radius: 6px;
            padding: 10px;
        }
        .scroll-table-wrapper table {
            width: 100%;
            font-size: 15px;
            color: white;
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
    df_to_save = df.copy()
    for col in ["Created", "Updated"]:
        if col in df_to_save.columns:
            df_to_save[col] = df_to_save[col].apply(
                lambda x: x.strftime("%Y-%m-%d %H:%M:%S")
                if isinstance(x, datetime) and not pd.isna(x)
                else ""
            )
    df_to_save = df_to_save[[col for col in REQUIRED_COLUMNS if col in df_to_save.columns]]
    sheet.clear()
    sheet.update([df_to_save.columns.tolist()] + df_to_save.astype(str).values.tolist())

def calculate_status(pcs):
    pcs = int(float(pcs or 0))
    if pcs == 0:
        return "OUT OF STOCK"
    elif pcs < 5:
        return "LOW STOCK"
    else:
        return "IN STOCK"

def get_default(selected_data, key, default):
    return selected_data.get(key, default) if isinstance(selected_data, pd.Series) else default

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

# --- SESSION STATE DATAFRAME INIT ---
if "df" not in st.session_state:
    st.session_state.df = load_data()

st.subheader("📝 Add or Edit Product")
df = st.session_state.df
form_mode = st.radio("Mode", ["Add New", "Edit Existing"], horizontal=True)
selected_dno = st.selectbox("Select D.NO.", [""] + sorted(df["D.NO."].unique())) if form_mode == "Edit Existing" else ""
selected_data = df[df["D.NO."] == selected_dno].iloc[0] if selected_dno else {}

with st.form("product_form"):
    col1, col2 = st.columns(2)
    with col1:
        company = st.text_input("Company", value=get_default(selected_data, "Company", ""))
        dno = st.text_input("D.NO.", value=get_default(selected_data, "D.NO.", ""))
        rate = st.number_input("Rate", min_value=0.0, value=float(get_default(selected_data, "Rate", 0)))
        pcs = st.number_input("PCS (Total)", min_value=0, value=int(float(get_default(selected_data, "PCS", 0))))
    with col2:
        type_ = st.selectbox(
            "Type",
            ["WITH LACE", "WITHOUT LACE"],
            index=["WITH LACE", "WITHOUT LACE"].index(get_default(selected_data, "Type", "WITH LACE").upper())
        )
        image_file = st.file_uploader("Upload Image", type=["jpg", "jpeg", "png"])

    st.markdown("**Matching (Optional): Color + PCS Table**")
    matching_raw = get_default(selected_data, "Matching", "")
    matching_rows = []
    if matching_raw:
        try:
            for item in matching_raw.split(","):
                if ":" in item:
                    color, pcs_val = item.split(":")
                    matching_rows.append({"Color": color.strip(), "PCS": int(float(pcs_val.strip()))})
        except Exception:
            matching_rows = [{"Color": "", "PCS": 0}]
    else:
        matching_rows = [{"Color": "", "PCS": 0}]

    matching_table = st.data_editor(
        matching_rows,
        num_rows="dynamic",
        key="match_editor",
        column_config={"PCS": st.column_config.NumberColumn("PCS", min_value=0)},
    )

    raw_delivery = get_default(selected_data, "Delivery PCS", 0)
    try:
        delivery_val = int(float(raw_delivery)) if raw_delivery not in ["", None] else 0
    except:
        delivery_val = 0

    delivery_pcs = st.number_input("Delivery PCS", min_value=0, value=delivery_val)
    difference_pcs = pcs - delivery_pcs
    st.markdown(f"**Difference in PCS:** {difference_pcs}")

    submitted = st.form_submit_button("💾 Save Product")
    if submitted:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        image_url = get_default(selected_data, "Image", "")

        matching_str = ", ".join([
            f"{row['Color']}:{int(float(row['PCS']))}"
            for row in matching_table if row.get("Color")
        ])

        new_row = {
            "D.NO.": dno.strip().upper(),
            "Company": company.strip().upper(),
            "Type": type_,
            "PCS": pcs,
            "Rate": rate,
            "Total": rate * pcs,
            "Matching": matching_str,
            "Image": image_url,
            "Created": get_default(selected_data, "Created", now),
            "Updated": now,
            "Status": calculate_status(pcs),
            "Delivery PCS": delivery_pcs,
            "Difference in PCS": difference_pcs
        }

        df = df[df["D.NO."] != dno.strip().upper()]
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        st.session_state.df = df
        save_data(df)
        st.success("✅ Product saved successfully!")
        st.experimental_rerun()

# --- SIDEBAR ---
with st.sidebar:
    if LOGO_PATH.exists():
        logo_base64 = base64.b64encode(open(str(LOGO_PATH), "rb").read()).decode()
        st.markdown(f"""
        <div style='text-align:center;'>
            <img src='data:image/png;base64,{logo_base64}' width='150'><br>
            <h3 style='color:white;'>JUBILEE TEXTILE PROCESSORS</h3>
        </div>
        """, unsafe_allow_html=True)

    st.metric("Total PCS", int(df["PCS"].fillna(0).sum()))
    st.metric("Total Value", f"\u20B9{df['Total'].fillna(0).sum():,.2f}")

    st.subheader("\U0001F5D1\uFE0F Delete Product")
    del_dno = st.selectbox("Select D.NO. to Delete", df["D.NO."].unique())
    if st.button("Delete Selected Product"):
        df = df[df["D.NO."] != del_dno]
        save_data(df)
        st.session_state.df = df
        st.success(f"Deleted {del_dno}")
        
# --- MAIN PAGE LOGO ---
if LOGO_PATH.exists():
    logo_base64 = base64.b64encode(open(str(LOGO_PATH), "rb").read()).decode()
    st.markdown(f"""
    <div style="display: flex; justify-content: center; margin-bottom: 20px;">
        <img src="data:image/png;base64,{logo_base64}" width="180" />
    </div>
    """, unsafe_allow_html=True)
else:
    st.warning("Main page logo not found.")


# --- FILTER + EXPORT ---
df = load_data()
st.subheader("🔍 Filter/Search")
search_term = st.text_input("Search by D.NO. or Company")
type_filter = st.selectbox("Filter by Type", ["All"] + sorted(df["Type"].dropna().unique()))

filtered_df = df.copy()
if search_term:
    search_results = process.extract(search_term, df["D.NO."].astype(str).tolist() + df["Company"].astype(str).tolist(), limit=25)
    matched = set([r[0] for r in search_results if r[1] > 60])
    filtered_df = df[df["D.NO."].isin(matched) | df["Company"].isin(matched)]

if type_filter != "All":
    filtered_df = filtered_df[filtered_df["Type"] == type_filter]

# --- EXPORT ---
st.subheader("⬇️ Export")
export_format = st.radio("Choose format", ["Excel", "Printable HTML"])
if export_format == "Excel":
    from io import BytesIO
    excel_io = BytesIO()
    with pd.ExcelWriter(excel_io, engine="xlsxwriter") as writer:
        filtered_df.to_excel(writer, index=False, sheet_name="Inventory")
    st.download_button("Download Excel", excel_io.getvalue(), "jubilee_inventory.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
elif export_format == "Printable HTML":
    html_report = generate_html_report(filtered_df)
    st.download_button("Download HTML Report", html_report.encode(), "jubilee_inventory.html", mime="text/html")

# --- DISPLAY SORTABLE TABLE ---
st.subheader("📋 Inventory Table")
st.markdown("<div class='scroll-table-wrapper'>", unsafe_allow_html=True)
st.dataframe(filtered_df, use_container_width=True)
st.markdown("</div>", unsafe_allow_html=True)

# --- CONTINUE WITH Add/Edit form and delete section here ---

# --- FORM ---
form_mode = st.radio("Mode", ["Add New", "Edit Existing"], horizontal=True)
selected_dno = st.selectbox("Select D.NO.", [""] + sorted(df["D.NO."].unique())) if form_mode == "Edit Existing" else ""
selected_data = df[df["D.NO."] == selected_dno].iloc[0] if selected_dno else {}

with st.form("product_form"):
    col1, col2 = st.columns(2)
    with col1:
        company = st.text_input("Company", value=get_default(selected_data, "Company", ""))
        dno = st.text_input("D.NO.", value=get_default(selected_data, "D.NO.", ""))
        rate = st.number_input("Rate", min_value=0.0, value=float(get_default(selected_data, "Rate", 0)))
        pcs = st.number_input("PCS (Total)", min_value=0, value=int(float(get_default(selected_data, "PCS", 0))))
    with col2:
        type_ = st.selectbox(
            "Type",
            ["WITH LACE", "WITHOUT LACE"],
            index=["WITH LACE", "WITHOUT LACE"].index(get_default(selected_data, "Type", "WITH LACE").upper())
        )
        image_file = st.file_uploader("Upload Image", type=["jpg", "jpeg", "png"])

    st.markdown("**Matching (Optional): Color + PCS Table**")
    matching_raw = get_default(selected_data, "Matching", "")
    matching_rows = []
    if matching_raw:
        try:
            for item in matching_raw.split(","):
                if ":" in item:
                    color, pcs_val = item.split(":")
                    matching_rows.append({"Color": color.strip(), "PCS": int(float(pcs_val.strip()))})
        except Exception:
            matching_rows = [{"Color": "", "PCS": 0}]
    else:
        matching_rows = [{"Color": "", "PCS": 0}]

    matching_table = st.data_editor(
        matching_rows,
        num_rows="dynamic",
        key="match_editor",
        column_config={"PCS": st.column_config.NumberColumn("PCS", min_value=0)},
    )

    st.markdown(f"**Delivery PCS**")
    raw_delivery = get_default(selected_data, "Delivery PCS", 0)
    try:
        delivery_val = int(float(raw_delivery)) if raw_delivery not in ["", None] else 0
    except:
        delivery_val = 0

    delivery_pcs = st.number_input("Delivery PCS", min_value=0, value=delivery_val)

    difference_pcs = pcs - delivery_pcs
    st.markdown(f"**Difference in PCS:** {difference_pcs}")

    submitted = st.form_submit_button("💾 Save Product")
    if submitted:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        image_url = upload_image(image_file) if image_file else get_default(selected_data, "Image", "")

        # Process matching table to string
        matching_str = ", ".join([
            f"{row['Color']}:{int(float(row['PCS']))}"
            for row in matching_table if row.get("Color")
        ])

        new_row = {
            "D.NO.": dno.strip().upper(),
            "Company": company.strip().upper(),
            "Type": type_,
            "PCS": pcs,
            "Rate": rate,
            "Total": rate * pcs,
            "Matching": matching_str,
            "Image": image_url,
            "Created": get_default(selected_data, "Created", now),
            "Updated": now,
            "Status": calculate_status(pcs),
            "Delivery PCS": delivery_pcs,
            "Difference in PCS": difference_pcs
        }

        # Remove old entry with same D.NO.
        df = df[df["D.NO."] != dno.strip().upper()]
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        save_data(df)
        st.success("✅ Product saved successfully!", icon="💾")
        
