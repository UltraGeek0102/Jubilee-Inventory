# jubilee_streamlit/app.py — Google Sheets Version with Edit/Delete
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from PIL import Image
import os
import json

# ---------- SETUP ----------
st.set_page_config(page_title="Jubilee Inventory (Cloud)", layout="wide")
st.title("🧵 Jubilee Textile Inventory - Cloud Version")

# ---------- GOOGLE SHEETS AUTH via st.secrets ----------
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

try:
    creds_dict = json.loads(st.secrets["GCP_CREDENTIALS"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
    client = gspread.authorize(creds)
    spreadsheet = client.open("jubilee-inventory")
    sheet = spreadsheet.sheet1
except gspread.exceptions.SpreadsheetNotFound:
    st.error("❌ Google Sheet 'jubilee-inventory' not found. Please check the name or share it with your service account.")
    st.stop()
except Exception as e:
    st.error(f"❌ Unknown error connecting to Google Sheets: {type(e).__name__}: {e}")
    st.stop()

HEADERS = ["Company", "D.NO", "Matching", "Diamond", "PCS", "Delivery_PCS", "Assignee", "Type", "Rate", "Total", "Image"]

# ---------- IMAGE UPLOAD ----------
def save_image(uploaded_file):
    if uploaded_file is None:
        return ""
    file_path = os.path.join(UPLOAD_DIR, uploaded_file.name)
    image = Image.open(uploaded_file)
    image.thumbnail((800, 800))
    image.save(file_path)
    return file_path

# ---------- ADD PRODUCT FORM ----------
def show_add_form():
    st.subheader("➕ Add New Product")
    with st.form("add_form"):
        col1, col2, col3 = st.columns(3)
        company = col1.text_input("Company")
        dno = col2.text_input("D.NO")
        diamond = col3.text_input("Diamond")

        matching = st.text_area("Matching (format: Red:3, Blue:2)")
        pcs = st.number_input("PCS", min_value=0, value=0)
        delivery_pcs = st.number_input("Delivery PCS", min_value=0, value=0)

        col4, col5, col6 = st.columns(3)
        assignee = col4.text_input("Assignee")
        ptype = col5.selectbox("Type", ["WITH LACE", "WITHOUT LACE"])
        rate = col6.number_input("Rate", min_value=0.0, value=0.0)

        image = st.file_uploader("Upload Image", type=["png", "jpg", "jpeg"])

        submitted = st.form_submit_button("Add Product")
        if submitted:
            total = pcs * rate
            image_path = save_image(image)
            new_row = [company, dno, matching, diamond, pcs, delivery_pcs, assignee, ptype, rate, total, image_path]
            try:
                sheet.append_row(new_row)
                st.success("✅ Product added successfully!")
                st.experimental_rerun()
            except Exception as e:
                st.error(f"❌ Failed to write to sheet: {e}")

# ---------- DISPLAY + EDIT + DELETE SHEET DATA ----------
def show_inventory():
    st.subheader("📦 Inventory Table (Google Sheets)")
    try:
        data = sheet.get_all_records()
        if not data:
            st.info("No entries yet. Add a product above.")
            return

        df = pd.DataFrame(data)
        df["Pending"] = df["PCS"] - df["Delivery_PCS"]

        for i, row in df.iterrows():
            with st.expander(f"{i+2}. {row['Company']} - {row['D.NO']}"):
                st.write("**Matching:**")
                st.code(row["Matching"])
                st.write(f"**Diamond:** {row['Diamond']}, **Rate:** ₹{row['Rate']}, **Total:** ₹{row['Total']}")
                st.write(f"**PCS:** {row['PCS']} | **Delivered:** {row['Delivery_PCS']} | **Pending:** {row['Pending']}")
                st.write(f"**Assignee:** {row['Assignee']}, **Type:** {row['Type']}")
                if row["Image"] and os.path.exists(row["Image"]):
                    st.image(row["Image"], width=120)

                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"✏️ Edit", key=f"edit_{i}"):
                        with st.form(f"edit_form_{i}"):
                            ec1, ec2, ec3 = st.columns(3)
                            company = ec1.text_input("Company", value=row["Company"])
                            dno = ec2.text_input("D.NO", value=row["D.NO"])
                            diamond = ec3.text_input("Diamond", value=row["Diamond"])

                            matching = st.text_area("Matching", value=row["Matching"])
                            pcs = st.number_input("PCS", min_value=0, value=int(row["PCS"]))
                            delivery_pcs = st.number_input("Delivery PCS", min_value=0, value=int(row["Delivery_PCS"]))

                            ec4, ec5, ec6 = st.columns(3)
                            assignee = ec4.text_input("Assignee", value=row["Assignee"])
                            ptype = ec5.selectbox("Type", ["WITH LACE", "WITHOUT LACE"], index=["WITH LACE", "WITHOUT LACE"].index(row["Type"]))
                            rate = ec6.number_input("Rate", min_value=0.0, value=float(row["Rate"]))

                            image = st.file_uploader("Replace Image", type=["png", "jpg", "jpeg"])

                            submitted = st.form_submit_button("Update")
                            if submitted:
                                total = pcs * rate
                                image_path = row["Image"]
                                if image: image_path = save_image(image)
                                updated_row = [company, dno, matching, diamond, pcs, delivery_pcs, assignee, ptype, rate, total, image_path]
                                sheet.delete_row(i + 2)
                                sheet.insert_row(updated_row, i + 2)
                                st.success("✅ Updated successfully!")
                                st.experimental_rerun()
                with col2:
                    if st.button(f"❌ Delete", key=f"delete_{i}"):
                        sheet.delete_row(i + 2)  # Offset because headers are row 1
                        st.warning("Row deleted")
                        st.experimental_rerun()
    except Exception as e:
        st.error(f"❌ Failed to load data: {e}")

# ---------- MAIN ----------
show_add_form()
show_inventory()
