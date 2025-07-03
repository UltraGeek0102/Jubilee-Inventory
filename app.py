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

# ... [existing setup and credentials code assumed present] ...

# --- Upload to Drive ---
def upload_to_drive(uploaded_file):
    if uploaded_file is None:
        return FALLBACK_IMAGE
    try:
        ext = os.path.splitext(uploaded_file.name)[-1]
        safe_name = f"jubilee_{uuid.uuid4().hex}{ext}"
        file_stream = io.BytesIO(uploaded_file.getvalue())
        mime_type = uploaded_file.type or "image/jpeg"
        file_metadata = {'name': safe_name, 'parents': [DRIVE_FOLDER_ID]}
        media = MediaIoBaseUpload(file_stream, mimetype=mime_type)
        uploaded = drive_service.files().create(body=file_metadata, media_body=media, fields="id").execute()
        drive_service.permissions().create(fileId=uploaded["id"], body={"role": "reader", "type": "anyone"}).execute()
        return f"https://drive.google.com/uc?id={uploaded['id']}"
    except Exception as e:
        print("Upload error:", e)
        return FALLBACK_IMAGE

# --- Add Product Form ---
def show_add_form():
    st.subheader("➕ Add Product")
    if "matching_rows" not in st.session_state:
        st.session_state.matching_rows = ["Red", "Blue", "Green"]
    with st.form("add_form"):
        col1, col2, col3 = st.columns(3)
        company = col1.text_input("Company")
        dno = col2.text_input("D.NO")
        diamond = col3.text_input("Diamond")
        matching_dict = {}

        with st.expander("MATCHING (Color + PCS):"):
            st.markdown("<b>Color</b> and <b>PCS</b> entries — click ➕ to add more.", unsafe_allow_html=True)
            for idx, color in enumerate(st.session_state.matching_rows):
                cols = st.columns([0.2, 2, 1])
                cols[0].markdown(f"**{idx + 1}**")
                name = cols[1].text_input("Color", value=color, key=f"color_{color}")
                qty = cols[2].number_input("PCS", min_value=0, step=1, key=f"qty_{color}")
                if name:
                    matching_dict[name] = qty
            if st.button("➕ Add Color"):
                st.session_state.matching_rows.append(f"Color{len(st.session_state.matching_rows)+1}")

        matching = ", ".join(f"{k}:{v}" for k, v in matching_dict.items() if v > 0)
        pcs = sum(matching_dict.values())
        st.write(f"🎯 Total PCS: {pcs}")
        delivery = st.number_input("Delivery PCS", min_value=0, format="%d")
        a1, a2, a3 = st.columns(3)
        assignee = a1.text_input("Assignee")
        ptype = a2.selectbox("Type", ["WITH LACE", "WITHOUT LACE"])
        rate = a3.number_input("Rate", min_value=0.0, step=0.01)
        st.write(f"Total: ₹{pcs * rate:.2f}")
        image = st.file_uploader("Upload Image", type=["png", "jpg", "jpeg"])
        submit = st.form_submit_button("Add")
        if submit:
            if not company or not dno or pcs == 0:
                st.warning("❗ Company, D.NO and PCS are required.")
                return
            existing = sheet.get_all_records()
            conflict = next((r for r in existing if r["Company"] == company and r["D.NO"] == dno), None)
            if conflict:
                st.markdown(f"🚫 Duplicate entry: <b>{company} - {dno}</b> already exists.", unsafe_allow_html=True)
                return
            img_url = upload_to_drive(image)
            row = [company, dno, matching, diamond, pcs, delivery, assignee, ptype, rate, pcs * rate, img_url, datetime.now().isoformat()]
            try:
                sheet.append_row(row)
                st.success("✅ Product added!")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to add: {e}")

# --- Dashboard ---
def show_dashboard(df):
    st.subheader("📊 Dashboard")
    col1, col2, col3 = st.columns(3)
    col1.metric("Total PCS", int(df["PCS"].sum()))
    col2.metric("Pending", int((df["PCS"] - df["Delivery_PCS"]).sum()))
    col3.metric("Total Value", f"₹{int(df['Total'].sum())}")
    chart_data = df.groupby("Company")["PCS"].sum().reset_index()
    chart = alt.Chart(chart_data).mark_bar().encode(
        x=alt.X("Company", sort=None, axis=alt.Axis(labelAngle=-45)),
        y="PCS",
        tooltip=["Company", "PCS"]
    )
    st.altair_chart(chart, use_container_width=True)

# --- Inventory Display ---
def show_inventory():
    st.subheader("📦 Inventory")
    df = pd.DataFrame(sheet.get_all_records())
    export_matching_table(df)
    df["SheetRowNum"] = df.index + 2
    df["PCS"] = pd.to_numeric(df["PCS"], errors="coerce").fillna(0).astype(int)
    df["Delivery_PCS"] = pd.to_numeric(df["Delivery_PCS"], errors="coerce").fillna(0).astype(int)
    df["Pending"] = df["PCS"] - df["Delivery_PCS"]
    df["Difference in PCS"] = df["Pending"]

    with st.expander("🔎 Filter / Search"):
        f1, f2 = st.columns(2)
        company_filter = f1.multiselect("Company", options=df["Company"].unique())
        type_filter = f2.multiselect("Type", options=df["Type"].unique())
        search = st.text_input("Search keyword")
        sort_by = st.selectbox("Sort by", ["PCS", "Pending", "Rate", "Total"], index=0)
        ascending = st.checkbox("⬆️ Sort Ascending", value=True)

        if company_filter:
            df = df[df["Company"].isin(company_filter)]
        if type_filter:
            df = df[df["Type"].isin(type_filter)]
        if search:
            df = df[df.apply(lambda row: search.lower() in str(row).lower(), axis=1)]
        df = df.sort_values(by=sort_by, ascending=ascending)

    # Call print view AFTER filtering
    download_print_view(df)

    st.markdown(get_csv_excel_download_links(df), unsafe_allow_html=True)

    total_pages = len(df) // ROWS_PER_PAGE + (1 if len(df) % ROWS_PER_PAGE > 0 else 0)
    page = st.number_input("Page", min_value=1, max_value=total_pages, step=1)
    start = (page - 1) * ROWS_PER_PAGE
    end = start + ROWS_PER_PAGE
    sliced_df = df.iloc[start:end]

    show_dashboard(df)
    # ... [rest of show_inventory() continues unchanged]

# --- Main ---
show_add_form()
show_inventory()
with st.expander("🔎 Filter / Search"):
            f1, f2 = st.columns(2)
            company_filter = f1.multiselect("Company", options=df["Company"].unique())
            type_filter = f2.multiselect("Type", options=df["Type"].unique())
            search = st.text_input("Search keyword")
            sort_by = st.selectbox("Sort by", ["PCS", "Pending", "Rate", "Total"], index=0)
            ascending = st.checkbox("⬆️ Sort Ascending", value=True)

            if company_filter:
                df = df[df["Company"].isin(company_filter)]
            if type_filter:
                df = df[df["Type"].isin(type_filter)]
            if search:
                df = df[df.apply(lambda row: search.lower() in str(row).lower(), axis=1)]
            df = df.sort_values(by=sort_by, ascending=ascending)

            st.markdown(get_csv_excel_download_links(df), unsafe_allow_html=True)
total_pages = len(df) // ROWS_PER_PAGE + (1 if len(df) % ROWS_PER_PAGE > 0 else 0)
page = st.number_input("Page", min_value=1, max_value=total_pages, step=1)
    start = (page - 1) * ROWS_PER_PAGE
        end = start + ROWS_PER_PAGE
        sliced_df = df.iloc[start:end]

        for i in sliced_df.index:
            row = sliced_df.loc[i]
            row_num = int(row["SheetRowNum"])
            with st.expander(f"{row['Company']} - {row['D.NO']} | Pending: {row['Pending']}"):
                st.markdown(f'<a href="{row["Image"] or FALLBACK_IMAGE}" target="_blank"><img src="{row["Image"] or FALLBACK_IMAGE}" width="200"></a>', unsafe_allow_html=True)
                st.write(f"Diamond: {row['Diamond']} | Type: {row['Type']} | Assignee: {row['Assignee']}")
                st.write(f"PCS: {row['PCS']} | Delivered: {row['Delivery_PCS']} | Rate: ₹{row['Rate']} | Total: ₹{row['Total']}")
                st.write(f"Matching: {row['Matching']}")

                with st.form(f"edit_{i}"):
                    col1, col2, col3 = st.columns(3)
                    company = col1.text_input("Company", value=row["Company"])
                    dno = col2.text_input("D.NO", value=row["D.NO"])
                    diamond = col3.text_input("Diamond", value=row["Diamond"])
                    matching_dict = {}

                    with st.expander("MATCHING (Color + PCS):", expanded=False):
                        st.markdown("<b>Color</b> and <b>PCS</b> entries — click ➕ to add more.", unsafe_allow_html=True)
                        if f"edit_rows_{i}" not in st.session_state:
                            st.session_state[f"edit_rows_{i}"] = [s.split(":")[0] for s in row["Matching"].split(",") if ":" in s]
                        for idx, color in enumerate(st.session_state[f"edit_rows_{i}"]):
                            val = next((int(s.split(":")[1]) for s in row["Matching"].split(",") if s.split(":")[0] == color), 0)
                            cols = st.columns([0.2, 2, 1])
                            cols[0].markdown(f"**{idx + 1}**")
                            name = cols[1].text_input("Color", value=color, key=f"edit_color_{i}_{color}")
                            qty = cols[2].number_input("PCS", value=val, min_value=0, step=1, key=f"edit_qty_{i}_{color}")
                            if name:
                                matching_dict[name] = qty
                        if st.button(f"➕ Add New Matching Row", key=f"add_edit_row_{i}"):
                            st.session_state[f"edit_rows_{i}"].append(f"Color{len(st.session_state[f'edit_rows_{i}'])+1}")
                            st.rerun()

                    matching = ", ".join(f"{k}:{v}" for k, v in matching_dict.items() if v > 0)
                    pcs = sum(matching_dict.values())
                    st.write(f"🎯 Total PCS: {pcs}")
                    st.write(f"💰 Total Value: ₹{pcs * float(row['Rate']):.2f}")
                    delivery = st.number_input("Delivery PCS", value=row["Delivery_PCS"], min_value=0)
                    a1, a2, a3 = st.columns(3)
                    assignee = a1.text_input("Assignee", value=row["Assignee"])
                    ptype = a2.selectbox("Type", ["WITH LACE", "WITHOUT LACE", "With Lace", "Without Lace"], index=0)
                    rate = a3.number_input("Rate", value=float(row["Rate"]), step=0.01)
                    image = st.file_uploader("Replace Image")
                    c1, c2 = st.columns(2)
                        if c1.form_submit_button("Update"):
                        image_url = row["Image"]
                        if image:
                            image_url = upload_to_drive(image)
                        matching_str = ", ".join(f"{k}:{v}" for k, v in matching_dict.items() if v > 0)
                        pcs = sum(matching_dict.values())
                        new_row = [company, dno, matching_str, diamond, pcs, delivery, assignee, ptype, rate, pcs * rate, image_url, datetime.now().isoformat()]
                        sheet.delete_rows(row_num)
                        sheet.insert_row(new_row, row_num)
                        st.success("✅ Updated")
                        st.rerun()
                        if c2.form_submit_button("Delete"):
                        sheet.delete_rows(row_num)
                        st.warning("❌ Deleted")
                        st.rerun()
    # --- PDF / Print View ---
    def generate_printable_html(df):
        html = """
        <html><head><style>
        body { font-family: Arial, sans-serif; padding: 40px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { border: 1px solid #999; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
        h2 { margin-top: 40px; }
        </style></head><body>
        <h1>Jubilee Inventory Report</h1>
        <p>Generated on: """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + "</p>"
        html += df.to_html(index=False, escape=False)
        html += "</body></html>"
        return html

    def download_print_view(df):
        st.subheader("🖨️ Print View / PDF Report")
        html_content = generate_printable_html(df)
        b64 = base64.b64encode(html_content.encode()).decode()
        href = f'<a href="data:text/html;base64,{b64}" download="jubilee_inventory_report.html">📄 Download Printable HTML</a>'
        st.markdown(href, unsafe_allow_html=True)

    # Add this call after filtering and slicing the DataFrame inside show_inventory()
    download_print_view(df)

# --- Main ---
show_add_form()
show_inventory()
