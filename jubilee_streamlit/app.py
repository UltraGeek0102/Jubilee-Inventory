# app.py
import os
import io
import sqlite3
from datetime import datetime
from dataclasses import dataclass
from typing import List, Tuple, Optional

import pandas as pd
import streamlit as st
from PIL import Image

# ----------------------------
# Config & constants
# ----------------------------
DB_PATH = "inventory.db"
UPLOAD_DIR = "uploads"
COMPRESSED_DIR = "compressed"
ASSETS_NO_IMAGE = os.path.join("assets", "no-image.png")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(COMPRESSED_DIR, exist_ok=True)
os.makedirs("assets", exist_ok=True)

# ----------------------------
# Database layer (reused logic)
# ----------------------------
class DatabaseManager:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def init_db(self):
        conn = self._connect()
        conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT,
            dno TEXT,
            matching TEXT,
            diamond TEXT,
            pcs INTEGER,
            delivery_pcs INTEGER DEFAULT 0,
            assignee TEXT,
            type TEXT,
            rate REAL,
            total REAL,
            image TEXT
        )""")
        conn.commit()
        conn.close()

    def get_all_products(self):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT * FROM products")
        rows = cur.fetchall()
        conn.close()
        return rows

    def dno_exists(self, dno: str, exclude_id: Optional[int] = None) -> bool:
        conn = self._connect()
        if exclude_id is not None:
            cur = conn.execute("SELECT COUNT(*) FROM products WHERE dno = ? AND id != ?", (dno, exclude_id))
        else:
            cur = conn.execute("SELECT COUNT(*) FROM products WHERE dno = ?", (dno,))
        result = cur.fetchone()
        conn.close()
        return result > 0

    def add_product(self, data: Tuple):
        conn = self._connect()
        conn.execute("""
        INSERT INTO products (company, dno, matching, diamond, pcs, delivery_pcs, assignee, type, rate, total, image)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, data)
        conn.commit()
        conn.close()

    def update_product(self, product_id: int, data: Tuple):
        conn = self._connect()
        conn.execute("""
        UPDATE products SET company=?, dno=?, matching=?, diamond=?, pcs=?, delivery_pcs=?, assignee=?, type=?, rate=?, total=?, image=?
        WHERE id=?
        """, data + (product_id,))
        conn.commit()
        conn.close()

    def delete_products(self, product_ids: List[int]):
        if not product_ids:
            return
        conn = self._connect()
        conn.executemany("DELETE FROM products WHERE id = ?", [(pid,) for pid in product_ids])
        conn.commit()
        conn.close()

# ----------------------------
# Utilities
# ----------------------------
def compress_image_bytes(file_bytes: bytes, filename: str, max_size=(800, 800), quality=85) -> str:
    """Compress an uploaded image and save to COMPRESSED_DIR; returns path."""
    im = Image.open(io.BytesIO(file_bytes))
    im.thumbnail(max_size)
    out_path = os.path.join(COMPRESSED_DIR, filename)
    # Ensure extension preserved; default to JPEG if missing alpha
    save_kwargs = dict(optimize=True, quality=quality)
    ext = os.path.splitext(filename)[1].lower()
    if ext in [".jpg", ".jpeg"]:
        fmt = "JPEG"
    elif ext in [".png"]:
        fmt = "PNG"
        # PNG ignores 'quality', but optimize works
        save_kwargs.pop("quality", None)
    else:
        # Fallback to PNG
        fmt = "PNG"
        save_kwargs.pop("quality", None)
        if not out_path.lower().endswith(".png"):
            out_path += ".png"
    im.save(out_path, format=fmt, **save_kwargs)
    return out_path

def parse_matching_string(matching: str) -> List[Tuple[str, int]]:
    out = []
    if matching:
        for pair in matching.split(","):
            if ":" in pair:
                color, pcs = pair.split(":")
                color = color.strip()
                pcs = pcs.strip()
                if pcs.isdigit():
                    out.append((color, int(pcs)))
    return out

def build_matching_string(rows_df: pd.DataFrame) -> Tuple[str, int]:
    """Build 'Color:PCS, ...' and return total pcs."""
    rows_df = rows_df.dropna(subset=["Color"]).copy()
    rows_df["PCS"] = pd.to_numeric(rows_df["PCS"], errors="coerce").fillna(0).astype(int)
    parts = [f"{r.Color.strip()}:{int(r.PCS)}" for r in rows_df.itertuples(index=False) if str(r.Color).strip()]
    total = int(rows_df["PCS"].sum())
    return ", ".join(parts), total

def to_excel_bytes(df: pd.DataFrame, sheet_name: str = "Products") -> bytes:
    buff = io.BytesIO()
    with pd.ExcelWriter(buff, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return buff.getvalue()

# ----------------------------
# Streamlit App
# ----------------------------
st.set_page_config(page_title="Jubilee Inventory", layout="wide")
st.title("Jubilee Textile Processors — Inventory")

# Global DB (per session)
if "db" not in st.session_state:
    st.session_state.db = DatabaseManager()

db: DatabaseManager = st.session_state.db

# Sidebar: actions
with st.sidebar:
    st.header("Actions")
    # Import CSV
    import_file = st.file_uploader("Import CSV", type=["csv"])  # replaces QFileDialog [24]
    if import_file is not None:
        try:
            df_imp = pd.read_csv(import_file)
            expected = ["ID", "COMPANY NAME", "D.NO.", "MATCHING", "Diamond", "PCS", "DELIVERY PCS", "Assignee", "Type", "Rate", "Total", "Image"]
            if list(df_imp.columns) != expected:
                st.error(f"Invalid CSV headers. Expected: {expected}")
            else:
                imported = 0
                for _, r in df_imp.iterrows():
                    # Normalize types
                    pid = int(r["ID"]) if pd.notna(r["ID"]) and str(r["ID"]).isdigit() else None
                    pcs = int(r["PCS"]) if pd.notna(r["PCS"]) and str(r["PCS"]).isdigit() else 0
                    dpcs = int(r["DELIVERY PCS"]) if pd.notna(r["DELIVERY PCS"]) and str(r["DELIVERY PCS"]).isdigit() else 0
                    rate = float(r["Rate"]) if pd.notna(r["Rate"]) and str(r["Rate"]) != "" else 0.0
                    total = float(r["Total"]) if pd.notna(r["Total"]) and str(r["Total"]) != "" else 0.0
                    values = (
                        r["COMPANY NAME"] if pd.notna(r["COMPANY NAME"]) else "",
                        r["D.NO."] if pd.notna(r["D.NO."]) else "",
                        r["MATCHING"] if pd.notna(r["MATCHING"]) else "",
                        r["Diamond"] if pd.notna(r["Diamond"]) else "",
                        pcs,
                        dpcs,
                        r["Assignee"] if pd.notna(r["Assignee"]) else "",
                        r["Type"] if pd.notna(r["Type"]) else "",
                        rate,
                        total,
                        r["Image"] if pd.notna(r["Image"]) else "",
                    )
                    if pid is not None:
                        # Upsert by ID
                        db.update_product(pid, values)
                    else:
                        db.add_product(values)
                    imported += 1
                st.success(f"Imported {imported} records")
        except Exception as e:
            st.error(f"Import failed: {e}")
    st.divider()

# Load data for display
rows = db.get_all_products()
cols = ["ID", "COMPANY NAME", "D.NO.", "MATCHING", "Diamond", "PCS", "DELIVERY PCS", "Assignee", "Type", "Rate", "Total", "Image"]
df = pd.DataFrame(rows, columns=cols)
if not df.empty:
    df["Pending"] = df["PCS"].fillna(0).astype(int) - df["DELIVERY PCS"].fillna(0).astype(int)
    # Reorder to include Pending like the desktop table
    df = df[["ID","COMPANY NAME","D.NO.","MATCHING","Diamond","PCS","DELIVERY PCS","Pending","Assignee","Type","Rate","Total","Image"]]

# Top controls: search + type filter + export buttons
c1, c2, c3, c4, c5 = st.columns([3,2,2,2,2])
with c1:
    search = st.text_input("Search", "")
with c2:
    type_filter = st.selectbox("Type", ["All", "WITH LACE", "WITHOUT LACE"])
with c3:
    export_all_csv = st.button("Export All (CSV)")
with c4:
    export_all_xlsx = st.button("Export All (Excel)")
with c5:
    export_matching_csv = st.button("Export MATCHING (CSV)")

# Filter by type and search
df_view = df.copy()
if type_filter != "All":
    df_view = df_view[df_view["Type"].str.lower() == type_filter.lower()]
if search:
    s = search.lower()
    df_view = df_view[df_view.apply(lambda r: any(s in str(v).lower() for v in r.values), axis=1)]

# Display table with selection
st.subheader("Inventory")
if "selected_ids" not in st.session_state:
    st.session_state.selected_ids = []

# Use a selection widget because st.data_editor doesn’t support direct row select retrieval
ids_all = df_view["ID"].tolist() if not df_view.empty else []
selected_ids = st.multiselect("Select rows by ID for delete/export", ids_all, default=st.session_state.selected_ids)
st.session_state.selected_ids = selected_ids

# Show dataframe for read-only display
st.dataframe(df_view, use_container_width=True)  # read-only view [2]

# Image preview for a selected item
with st.expander("Image preview"):
    preview_id = st.selectbox("Choose ID to preview", ids_all) if ids_all else None
    if preview_id is not None:
        row = df[df["ID"] == preview_id].iloc
        img_path = row["Image"]
        if isinstance(img_path, str) and os.path.exists(img_path):
            st.image(img_path, width=400)  # st.image replacement for QPixmap preview [25]
        else:
            if os.path.exists(ASSETS_NO_IMAGE):
                st.image(ASSETS_NO_IMAGE, width=200)  # placeholder [25]

# Export handlers
if export_all_csv and not df.empty:
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button("Download products_export.csv", data=csv_bytes, file_name=f"products_export_{datetime.now():%Y%m%d_%H%M%S}.csv", mime="text/csv")  # [7][10][13]
if export_all_xlsx and not df.empty:
    xlsx_bytes = to_excel_bytes(df, sheet_name="Products")
    st.download_button("Download products_export.xlsx", data=xlsx_bytes, file_name=f"products_export_{datetime.now():%Y%m%d_%H%M%S}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")  # [7][13]
if export_matching_csv:
    # Build a long CSV with D.NO., Color, PCS and totals between groups
    buffer = io.StringIO()
    writer = pd.ExcelWriter  # just to keep importers happy in requirements; not used here
    buffer.write("D.NO.,Color,PCS\n")
    for _, r in df.iterrows():
        dno = r["D.NO."]
        parts = parse_matching_string(str(r["MATCHING"]) if pd.notna(r["MATCHING"]) else "")
        total = sum(p for _, p in parts)
        for color, pcs in parts:
            buffer.write(f"{dno},{color},{pcs}\n")
        if parts:
            buffer.write(",,\n")
            buffer.write(f",,Total PCS: {total}\n")
            buffer.write(",,\n")
    st.download_button("Download matching_export.csv", data=buffer.getvalue().encode("utf-8"), file_name=f"matching_export_{datetime.now():%Y%m%d_%H%M%S}.csv", mime="text/csv")  # [7][10]

st.divider()

# Add / Edit form
st.subheader("Add or Edit Product")
with st.form("product_form", clear_on_submit=False):
    mode = st.selectbox("Mode", ["Add", "Edit"])
    edit_id = None
    if mode == "Edit":
        edit_id = st.selectbox("Select ID to edit", df["ID"].tolist() if not df.empty else [])
    company = st.text_input("Company Name")
    dno = st.text_input("D.NO.")
    diamond = st.text_input("Diamond")
    assignee = st.text_input("Assignee")
    type_val = st.selectbox("Type", ["WITH LACE", "WITHOUT LACE"])
    rate = st.number_input("Rate", min_value=0.0, step=0.5, format="%.2f")

    # Matching editor table (Color, PCS) using data_editor [2]
    if "match_df" not in st.session_state:
        st.session_state.match_df = pd.DataFrame(columns=["Color","PCS"])
    st.write("MATCHING (Color + PCS)")
    match_df = st.data_editor(
        st.session_state.match_df,
        num_rows="dynamic",
        column_config={
            "Color": st.column_config.TextColumn(),
            "PCS": st.column_config.NumberColumn(min_value=0, step=1)
        },
        use_container_width=True,
        key="matching_editor"
    )  # [2]

    delivery_pcs = st.number_input("Delivery PCS", min_value=0, step=1)

    # Image upload & compression [24][25]
    img_file = st.file_uploader("Choose Image", type=["png","jpg","jpeg","bmp"])  # [24]
    current_image_path = st.text_input("Current Image Path (leave or override by upload)", "")

    submitted = st.form_submit_button("Save")

    if submitted:
        # Build matching string and pcs_total
        matching_str, pcs_total = build_matching_string(match_df)
        total = pcs_total * float(rate or 0)
        # Handle image upload if present
        image_path_to_store = current_image_path.strip()
        if img_file is not None:
            filename = os.path.basename(img_file.name)
            bytes_data = img_file.getvalue()
            image_path_to_store = compress_image_bytes(bytes_data, filename)
        # D.NO. uniqueness check
        exclude = int(edit_id) if mode == "Edit" and edit_id is not None else None
        if db.dno_exists(dno.strip(), exclude):
            st.error(f"Duplicate D.NO. '{dno}'. Not saved.")
        else:
            data_tuple = (
                company.strip(),
                dno.strip(),
                matching_str,
                diamond.strip(),
                int(pcs_total),
                int(delivery_pcs or 0),
                assignee.strip(),
                type_val,
                float(rate or 0),
                float(total),
                image_path_to_store
            )
            if mode == "Edit" and edit_id is not None:
                db.update_product(int(edit_id), data_tuple)
                st.success(f"Updated ID {edit_id}")
            else:
                db.add_product(data_tuple)
                st.success("Added product")
        # Reset editor buffer to reflect new form state on next render
        st.session_state.match_df = pd.DataFrame(columns=["Color","PCS"])

# Pre-fill on selecting Edit
if st.session_state.get("product_form-mode", None) == "Edit" and st.session_state.get("product_form-Select ID to edit") and not df.empty:
    try:
        edit_id_prefill = st.session_state["product_form-Select ID to edit"]
        r = df[df["ID"] == edit_id_prefill].iloc
        # Write defaults into widget state keys for next rerun using session_state [14][17][20]
        st.session_state["product_form-Company Name"] = r["COMPANY NAME"]
        st.session_state["product_form-D.NO."] = r["D.NO."]
        st.session_state["product_form-Diamond"] = r["Diamond"]
        st.session_state["product_form-Assignee"] = r["Assignee"]
        st.session_state["product_form-Type"] = r["Type"]
        st.session_state["product_form-Rate"] = float(r["Rate"] or 0)
        # Matching back to editor
        pairs = parse_matching_string(str(r["MATCHING"]) if pd.notna(r["MATCHING"]) else "")
        st.session_state.match_df = pd.DataFrame(pairs, columns=["Color","PCS"])
        st.session_state["product_form-Delivery PCS"] = int(r["DELIVERY PCS"] or 0)
        st.session_state["product_form-Current Image Path (leave or override by upload)"] = r["Image"] if pd.notna(r["Image"]) else ""
    except Exception:
        pass

st.divider()

# Delete selected
col_del1, col_del2 = st.columns([1, 9])
with col_del1:
    if st.button("Delete selected"):
        try:
            db.delete_products([int(x) for x in st.session_state.selected_ids])
            st.success(f"Deleted {len(st.session_state.selected_ids)} product(s)")
            st.session_state.selected_ids = []
        except Exception as e:
            st.error(f"Delete failed: {e}")
with col_del2:
    st.info("Use the multiselect above the table to choose IDs to delete.")

# Footer note: persistence on Community Cloud
st.caption("Note: On Streamlit Community Cloud, local file changes may reset on app restart; consider external storage for images if long-term persistence is required.")  # [23]
