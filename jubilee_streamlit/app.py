# jubilee_streamlit_app.py
import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from PIL import Image
import io
import base64
import uuid

# Google Sheets config
SHEET_NAME = "JubileeInventory"
CREDENTIALS_FILE = "your_service_account.json"  # Replace with your credentials

# Setup Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
client = gspread.authorize(creds)
sheet = client.open(SHEET_NAME).sheet1

# App Config
st.set_page_config(page_title="Jubilee Inventory", layout="wide", page_icon="📦")
st.title("Jubilee Inventory Management System")

# Helpers
@st.cache_data(show_spinner=False)
def load_data():
    return pd.DataFrame(sheet.get_all_records())

def save_data(df):
    sheet.clear()
    sheet.update([df.columns.tolist()] + df.values.tolist())

def image_to_base64(image_file):
    img = Image.open(image_file)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

def base64_to_image(base64_str):
    return Image.open(io.BytesIO(base64.b64decode(base64_str)))

# Load inventory
df = load_data()

# Sidebar filters
with st.sidebar:
    st.header("🔍 Filter")
    type_filter = st.selectbox("Type", ["All"] + df["Type"].unique().tolist()) if not df.empty else "All"
    search = st.text_input("Search D.NO. or Company")
    st.markdown("---")
    export_format = st.selectbox("Export Format", ["CSV", "Excel"])
    if st.button("Export Data"):
        filtered = df.copy()
        if type_filter != "All":
            filtered = filtered[filtered["Type"] == type_filter]
        if search:
            filtered = filtered[
                filtered["D.NO."].str.contains(search, case=False) |
                filtered["COMPANY NAME"].str.contains(search, case=False)
            ]
        if export_format == "CSV":
            st.download_button("Download CSV", filtered.to_csv(index=False).encode(), "jubilee_inventory.csv")
        else:
            towrite = io.BytesIO()
            with pd.ExcelWriter(towrite, engine='openpyxl') as writer:
                filtered.to_excel(writer, index=False)
            st.download_button("Download Excel", towrite.getvalue(), "jubilee_inventory.xlsx")

# Filtered view
filtered_df = df.copy()
if type_filter != "All":
    filtered_df = filtered_df[filtered_df["Type"] == type_filter]
if search:
    filtered_df = filtered_df[
        filtered_df["D.NO."].str.contains(search, case=False, na=False) |
        filtered_df["COMPANY NAME"].str.contains(search, case=False, na=False)
    ]
st.dataframe(filtered_df, use_container_width=True)

# Product form
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

        # Matching
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
        img_base64 = image_to_base64(image_file) if image_file else ""

        submitted = st.form_submit_button("Save Product")
        if submitted:
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
                "Image": img_base64
            }

            if form_mode == "Edit Existing" and selected_dno:
                df.loc[df["D.NO."] == selected_dno] = new_data
                st.success(f"Updated product: {selected_dno}")
            else:
                df = pd.concat([df, pd.DataFrame([new_data])], ignore_index=True)
                st.success(f"Added new product: {dno}")
            save_data(df)

# Delete products
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

# Image Preview
st.markdown("---")
st.subheader("🖼️ Preview Images")
for idx, row in filtered_df.iterrows():
    if row["Image"]:
        st.markdown(f"**{row['D.NO.']} - {row['COMPANY NAME']}**")
        st.image(base64_to_image(row["Image"]), width=300)
        st.markdown("---")
