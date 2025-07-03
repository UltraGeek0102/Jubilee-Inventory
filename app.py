import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import pandas as pd
from PIL import Image
import os
import json
from datetime import datetime
import base64
import io
import altair as alt
import uuid

# --- Configuration and Credentials (PLACEHOLDERS - REPLACE WITH YOUR ACTUAL VALUES) ---
# For Google Sheets and Google Drive API access
# Refer to your Google Cloud Project and Google Sheets/Drive API setup
# For example, your service account key file path:
SERVICE_ACCOUNT_FILE = "your-service-account-key.json" # Replace with your service account key file path
SCOPES = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
SPREADSHEET_NAME = "Jubilee_Inventory" # Replace with your Google Sheet name
DRIVE_FOLDER_ID = "your_google_drive_folder_id" # Replace with your Google Drive Folder ID

# Fallback image URL if no image is uploaded or upload fails
FALLBACK_IMAGE = "https://via.placeholder.com/150" # Replace with a suitable fallback image URL

ROWS_PER_PAGE = 5 # Number of items to display per page in the inventory

# --- Google Sheets and Drive Setup ---
try:
    creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open(SPREADSHEET_NAME).sheet1 # Opens the first sheet
    drive_service = build('drive', 'v3', credentials=creds)
except Exception as e:
    st.error(f"Failed to connect to Google Sheets/Drive. Please check your credentials and configuration: {e}")
    st.stop() # Stop the app if connection fails

# --- Helper Functions for Download Links ---
def get_csv_excel_download_links(df):
    """Generates download links for CSV and Excel."""
    csv_file = df.to_csv(index=False).encode('utf-8')
    excel_file = io.BytesIO()
    df.to_excel(excel_file, index=False, engine='xlsxwriter')
    excel_file.seek(0)

    csv_b64 = base64.b64encode(csv_file).decode()
    excel_b64 = base64.b64encode(excel_file.read()).decode()

    csv_href = f'<a href="data:file/csv;base64,{csv_b64}" download="inventory.csv">Download CSV</a>'
    excel_href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{excel_b64}" download="inventory.xlsx">Download Excel</a>'

    return f"{csv_href} | {excel_href}"

# Placeholder for export_matching_table if it's used elsewhere for a specific table
def export_matching_table(df):
    """Placeholder for matching table export logic if needed."""
    # This function was called in the original code but its implementation was missing.
    # Add your logic here if you need to export a specific 'matching' related table.
    pass

# --- Upload to Drive ---
def upload_to_drive(uploaded_file):
    if uploaded_file is None:
        return FALLBACK_IMAGE
    try:
        ext = os.path.splitext(uploaded_file.name)[-1]
        safe_name = f"jubilee_{uuid.uuid4().hex}{ext}"
        file_stream = io.BytesIO(uploaded_file.getvalue())
        mime_type = uploaded_file.type or "image/jpeg" # Default to jpeg if type is not available
        file_metadata = {'name': safe_name, 'parents': [DRIVE_FOLDER_ID]}
        media = MediaIoBaseUpload(file_stream, mimetype=mime_type, resumable=True)
        uploaded = drive_service.files().create(body=file_metadata, media_body=media, fields="id").execute()
        # Make the file publicly readable
        drive_service.permissions().create(fileId=uploaded["id"], body={"role": "reader", "type": "anyone"}).execute()
        return f"https://drive.google.com/uc?id={uploaded['id']}"
    except Exception as e:
        st.error(f"Image upload error: {e}")
        return FALLBACK_IMAGE

# --- Add Product Form ---
def show_add_form():
    st.subheader("➕ Add Product")
    if "matching_rows" not in st.session_state:
        st.session_state.matching_rows = ["Red", "Blue", "Green"] # Initial colors

    with st.form("add_form"):
        col1, col2, col3 = st.columns(3)
        company = col1.text_input("Company").strip()
        dno = col2.text_input("D.NO").strip()
        diamond = col3.text_input("Diamond").strip()

        matching_dict = {}
        st.markdown("---") # Separator for better UI

        with st.expander("MATCHING (Color + PCS):", expanded=True):
            st.markdown("<b>Color</b> and <b>PCS</b> entries — click ➕ to add more.", unsafe_allow_html=True)
            new_matching_rows_added = False # Flag to detect if new rows were added to avoid immediate rerun issues

            current_matching_rows_state = list(st.session_state.matching_rows) # Create a copy to iterate
            for idx, color_placeholder in enumerate(current_matching_rows_state):
                cols = st.columns([0.2, 2, 1])
                cols[0].markdown(f"**{idx + 1}**")
                # Use a unique key for each text_input and number_input
                name = cols[1].text_input("Color", value=color_placeholder, key=f"add_color_{idx}")
                qty = cols[2].number_input("PCS", min_value=0, step=1, key=f"add_qty_{idx}")
                if name:
                    matching_dict[name] = qty

            if st.button("➕ Add New Color Field"):
                st.session_state.matching_rows.append(f"Color{len(st.session_state.matching_rows) + 1}")
                new_matching_rows_added = True
                st.rerun() # Rerun to display the new input field

        st.markdown("---") # Separator for better UI

        matching = ", ".join(f"{k}:{v}" for k, v in matching_dict.items() if v > 0)
        pcs = sum(matching_dict.values())
        st.write(f"🎯 Total PCS: {pcs}")

        delivery = st.number_input("Delivery PCS", min_value=0, format="%d", value=0) # Default to 0
        a1, a2, a3 = st.columns(3)
        assignee = a1.text_input("Assignee").strip()
        ptype = a2.selectbox("Type", ["WITH LACE", "WITHOUT LACE"])
        rate = a3.number_input("Rate", min_value=0.0, step=0.01, value=0.0)

        st.write(f"Total: ₹{pcs * rate:.2f}")
        image = st.file_uploader("Upload Image", type=["png", "jpg", "jpeg"])
        submit = st.form_submit_button("Add")

        if submit:
            if not company or not dno or pcs == 0:
                st.warning("❗ Company, D.NO, and PCS (must be greater than 0) are required.")
                return

            existing = sheet.get_all_records()
            # Check for duplicate entry based on Company and D.NO (case-insensitive for robustness)
            conflict = next((r for r in existing if r.get("Company", "").lower() == company.lower() and r.get("D.NO", "").lower() == dno.lower()), None)
            if conflict:
                st.markdown(f"🚫 Duplicate entry: <b>{company} - {dno}</b> already exists.", unsafe_allow_html=True)
                return

            img_url = upload_to_drive(image)
            row = [company, dno, matching, diamond, pcs, delivery, assignee, ptype, rate, pcs * rate, img_url, datetime.now().isoformat()]
            try:
                sheet.append_row(row)
                st.success("✅ Product added!")
                st.session_state.matching_rows = ["Red", "Blue", "Green"] # Reset matching rows for next add
                st.rerun() # Rerun to clear the form and update inventory
            except Exception as e:
                st.error(f"Failed to add product: {e}")

# --- Dashboard ---
def show_dashboard(df):
    st.subheader("📊 Dashboard")
    # Ensure numerical columns are handled correctly
    df["PCS"] = pd.to_numeric(df["PCS"], errors="coerce").fillna(0)
    df["Delivery_PCS"] = pd.to_numeric(df["Delivery_PCS"], errors="coerce").fillna(0)
    df["Total"] = pd.to_numeric(df["Total"], errors="coerce").fillna(0)

    col1, col2, col3 = st.columns(3)
    col1.metric("Total PCS", int(df["PCS"].sum()))
    col2.metric("Pending", int((df["PCS"] - df["Delivery_PCS"]).sum()))
    col3.metric("Total Value", f"₹{int(df['Total'].sum())}")

    # Bar chart for PCS by Company
    chart_data = df.groupby("Company")["PCS"].sum().reset_index()
    if not chart_data.empty:
        chart = alt.Chart(chart_data).mark_bar().encode(
            x=alt.X("Company", sort=None, axis=alt.Axis(labelAngle=-45)),
            y="PCS",
            tooltip=["Company", "PCS"]
        ).properties(
            title="Total PCS by Company"
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("No data to display in the dashboard chart.")

# --- PDF / Print View ---
def generate_printable_html(df_to_print):
    html = """
    <html><head><style>
    body { font-family: Arial, sans-serif; padding: 40px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { border: 1px solid #999; padding: 8px; text-align: left; }
    th { background-color: #f2f2f2; }
    h2 { margin-top: 40px; }
    img { max-width: 150px; height: auto; display: block; margin: 5px 0;}
    </style></head><body>
    <h1>Jubilee Inventory Report</h1>
    <p>Generated on: """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + "</p>"

    # Convert Image URLs to actual image tags for HTML export
    df_html = df_to_print.copy()
    if "Image" in df_html.columns:
        df_html["Image"] = df_html["Image"].apply(lambda x: f'<img src="{x or FALLBACK_IMAGE}" />')

    html += df_html.to_html(index=False, escape=False) # escape=False to render HTML tags
    html += "</body></html>"
    return html

def download_print_view(df_to_print):
    st.subheader("🖨️ Print View / PDF Report")
    html_content = generate_printable_html(df_to_print)
    b64 = base64.b64encode(html_content.encode()).decode()
    href = f'<a href="data:text/html;base64,{b64}" download="jubilee_inventory_report.html" style="text-decoration: none; padding: 10px 15px; background-color: #4CAF50; color: white; border-radius: 5px;">📄 Download Printable HTML Report</a>'
    st.markdown(href, unsafe_allow_html=True)


# --- Inventory Display ---
def show_inventory():
    st.subheader("📦 Inventory")
    df = pd.DataFrame(sheet.get_all_records())

    # Data cleaning and type conversion
    df["PCS"] = pd.to_numeric(df["PCS"], errors="coerce").fillna(0).astype(int)
    df["Delivery_PCS"] = pd.to_numeric(df["Delivery_PCS"], errors="coerce").fillna(0).astype(int)
    df["Rate"] = pd.to_numeric(df["Rate"], errors="coerce").fillna(0.0)
    df["Total"] = pd.to_numeric(df["Total"], errors="coerce").fillna(0.0)

    df["Pending"] = df["PCS"] - df["Delivery_PCS"]
    df["Difference in PCS"] = df["Pending"] # This seems redundant with 'Pending' but kept as per original

    # Add a SheetRowNum for direct row manipulation in Google Sheet
    # +2 because gspread is 0-indexed and Google Sheets is 1-indexed, and first row is header
    df["SheetRowNum"] = df.index + 2

    # Call dashboard with the full DataFrame (before filtering/pagination for overall stats)
    show_dashboard(df.copy()) # Pass a copy to avoid modifying the original df for dashboard


    # Filter / Search section
    with st.expander("🔎 Filter / Search"):
        f1, f2 = st.columns(2)
        company_filter = f1.multiselect("Company", options=df["Company"].unique())
        type_filter = f2.multiselect("Type", options=df["Type"].unique())
        search = st.text_input("Search keyword").strip()
        sort_by = st.selectbox("Sort by", ["PCS", "Pending", "Rate", "Total"], index=1) # Default to sort by Pending
        ascending = st.checkbox("⬆️ Sort Ascending", value=False) # Default to descending for Pending

        filtered_df = df.copy() # Use a copy for filtering
        if company_filter:
            filtered_df = filtered_df[filtered_df["Company"].isin(company_filter)]
        if type_filter:
            filtered_df = filtered_df[filtered_df["Type"].isin(type_filter)]
        if search:
            filtered_df = filtered_df[filtered_df.apply(lambda row: search.lower() in str(row).lower(), axis=1)]

        # Apply sorting
        filtered_df = filtered_df.sort_values(by=sort_by, ascending=ascending)

    # Download links for filtered data
    st.markdown(get_csv_excel_download_links(filtered_df), unsafe_allow_html=True)
    download_print_view(filtered_df)

    # Pagination
    total_pages = len(filtered_df) // ROWS_PER_PAGE + (1 if len(filtered_df) % ROWS_PER_PAGE > 0 else 0)
    if total_pages == 0: # Handle case where there are no results
        st.info("No products found matching your criteria.")
        return

    page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1)
    start = (page - 1) * ROWS_PER_PAGE
    end = start + ROWS_PER_PAGE
    sliced_df = filtered_df.iloc[start:end]

    # Display inventory items with edit/delete functionality
    for i in sliced_df.index:
        row = sliced_df.loc[i]
        row_num = int(row["SheetRowNum"])

        # Expander for each product
        with st.expander(f"{row['Company']} - {row['D.NO']} | Pending: {row['Pending']}"):
            st.markdown(f'<a href="{row["Image"] or FALLBACK_IMAGE}" target="_blank"><img src="{row["Image"] or FALLBACK_IMAGE}" width="200" style="border-radius: 8px;"></a>', unsafe_allow_html=True)
            st.write(f"**Diamond:** {row['Diamond']} | **Type:** {row['Type']} | **Assignee:** {row['Assignee']}")
            st.write(f"**PCS:** {row['PCS']} | **Delivered:** {row['Delivery_PCS']} | **Rate:** ₹{row['Rate']:.2f} | **Total:** ₹{row['Total']:.2f}")
            st.write(f"**Matching:** {row['Matching']}")
            st.markdown("---") # Separator for edit form

            # Edit Form
            with st.form(f"edit_form_{row_num}"): # Use row_num for unique form key
                col1, col2, col3 = st.columns(3)
                company = col1.text_input("Company", value=row["Company"]).strip()
                dno = col2.text_input("D.NO", value=row["D.NO"]).strip()
                diamond = col3.text_input("Diamond", value=row["Diamond"]).strip()

                matching_edit_dict = {}
                # Initialize edit_rows for current product if not already done
                if f"edit_rows_{row_num}" not in st.session_state:
                    # Parse existing matching string into a list of "Color" strings
                    existing_matching_parts = [s.strip().split(":")[0] for s in row["Matching"].split(",") if ":" in s]
                    # Ensure some default colors if none exist for editing
                    st.session_state[f"edit_rows_{row_num}"] = existing_matching_parts if existing_matching_parts else ["Color1"]

                with st.expander("MATCHING (Color + PCS):", expanded=False):
                    st.markdown("<b>Color</b> and <b>PCS</b> entries — click ➕ to add more.", unsafe_allow_html=True)
                    current_edit_rows_state = list(st.session_state[f"edit_rows_{row_num}"])
                    for idx, color_name in enumerate(current_edit_rows_state):
                        # Get existing PCS value for this color, defaulting to 0
                        val = next((int(s.strip().split(":")[1]) for s in row["Matching"].split(",") if s.strip().split(":")[0] == color_name), 0)

                        cols = st.columns([0.2, 2, 1])
                        cols[0].markdown(f"**{idx + 1}**")
                        # Use unique keys for edit fields
                        name = cols[1].text_input("Color", value=color_name, key=f"edit_color_{row_num}_{idx}")
                        qty = cols[2].number_input("PCS", value=val, min_value=0, step=1, key=f"edit_qty_{row_num}_{idx}")
                        if name:
                            matching_edit_dict[name] = qty

                    if st.button(f"➕ Add New Matching Field for {row['D.NO']}", key=f"add_edit_row_{row_num}"):
                        st.session_state[f"edit_rows_{row_num}"].append(f"Color{len(st.session_state[f'edit_rows_{row_num}'])+1}")
                        st.rerun() # Rerun to show new input field

                matching_str = ", ".join(f"{k}:{v}" for k, v in matching_edit_dict.items() if v > 0)
                pcs = sum(matching_edit_dict.values())
                st.write(f"🎯 Total PCS: {pcs}")
                st.write(f"💰 Total Value: ₹{pcs * float(row['Rate']):.2f}") # Use current rate for calculation

                delivery = st.number_input("Delivery PCS", value=row["Delivery_PCS"], min_value=0, key=f"edit_delivery_{row_num}")
                a1, a2, a3 = st.columns(3)
                assignee = a1.text_input("Assignee", value=row["Assignee"]).strip()
                # Ensure selectbox options are consistent
                ptype = a2.selectbox("Type", ["WITH LACE", "WITHOUT LACE"], index=["WITH LACE", "WITHOUT LACE"].index(row["Type"]) if row["Type"] in ["WITH LACE", "WITHOUT LACE"] else 0, key=f"edit_type_{row_num}")
                rate = a3.number_input("Rate", value=float(row["Rate"]), step=0.01, key=f"edit_rate_{row_num}")
                image = st.file_uploader("Replace Image", type=["png", "jpg", "jpeg"], key=f"edit_image_{row_num}")

                c1, c2 = st.columns(2)
                if c1.form_submit_button("Update"):
                    # Check for self-conflict (editing own D.NO) or conflict with other existing entries
                    is_duplicate_dno = False
                    for existing_row in existing:
                        if existing_row.get("Company", "").lower() == company.lower() and \
                           existing_row.get("D.NO", "").lower() == dno.lower() and \
                           int(existing_row["SheetRowNum"]) != row_num: # Exclude the current row being edited
                            is_duplicate_dno = True
                            break

                    if is_duplicate_dno:
                        st.warning(f"🚫 Cannot update: A product with Company '{company}' and D.NO '{dno}' already exists.")
                    else:
                        image_url = row["Image"]
                        if image:
                            image_url = upload_to_drive(image)

                        # Create new row data based on form inputs
                        new_row_data = [
                            company, dno, matching_str, diamond, pcs,
                            delivery, assignee, ptype, rate, pcs * rate,
                            image_url, datetime.now().isoformat()
                        ]
                        try:
                            # Update the row in Google Sheet
                            sheet.update(f'A{row_num}:L{row_num}', [new_row_data])
                            st.success("✅ Product updated successfully!")
                            st.rerun() # Rerun to refresh the inventory display
                        except Exception as e:
                            st.error(f"Failed to update product: {e}")

                if c2.form_submit_button("Delete"):
                    try:
                        sheet.delete_rows(row_num)
                        st.warning("❌ Product deleted successfully!")
                        # Remove the deleted item's edit_rows state
                        if f"edit_rows_{row_num}" in st.session_state:
                            del st.session_state[f"edit_rows_{row_num}"]
                        st.rerun() # Rerun to refresh the inventory display
                    except Exception as e:
                        st.error(f"Failed to delete product: {e}")


# --- Main Application Logic ---
def main():
    st.set_page_config(layout="wide", page_title="Jubilee Inventory Management")
    st.title("Jubilee Inventory Management System")

    # Use tabs for better navigation
    tab1, tab2 = st.tabs(["➕ Add Product", "📦 Inventory & Dashboard"])

    with tab1:
        show_add_form()

    with tab2:
        show_inventory()

if __name__ == "__main__":
    main()
```
