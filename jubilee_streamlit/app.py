# Jubilee Inventory (Streamlit version replicating PySide6 UI/behavior)

import os
import io
import csv
import sqlite3
from pathlib import Path
from datetime import datetime

import pandas as pd
from PIL import Image

import streamlit as st

# --- PAGE CONFIG / THEME ---
st.set_page_config(page_title="Jubilee Inventory", layout="wide", page_icon="🧵")

ASSETS_DIR = Path("assets")
LOGO_PATH = ASSETS_DIR / "logo.png"
NO_IMAGE_PATH = ASSETS_DIR / "no-image.png"
DB_PATH = Path("inventory.db")
COMPRESSED_DIR = Path("compressed")
COMPRESSED_DIR.mkdir(exist_ok=True)

DARK_CSS = """
<style>
:root { --bg:#121212; --panel:#1e1e1e; --border:#2a2a2a; --text:#ffffff; }
html, body, [data-testid="stAppViewContainer"] { background-color: var(--bg); color: var(--text); }
.block-container { padding-top: 0.5rem; padding-bottom: 1rem; }
.header-box {
  background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
  padding: 16px 20px; display:flex; align-items:center; gap:14px;
}
.toolbar {
  background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
  padding: 10px; display:flex; gap:10px; align-items:center; flex-wrap: wrap;
}
.toolbar .stButton>button, .stButton>button {
  padding: 8px 14px; border: 1px solid var(--border); background:#242424; color:#fff;
  border-radius: 8px; line-height: 1.1; font-weight: 500;
}
.toolbar .stButton>button:hover { background:#2a2a2a; }
[data-testid="stHorizontalBlock"] { gap: 0.75rem !important; } /* column gaps */
div[data-testid="stDataFrame"] { border: 1px solid var(--border); border-radius: 8px; }
.img-preview {
  border: 1px solid var(--border); border-radius: 8px; padding: 12px; background: var(--panel);
}
.tag-muted { color:#a0a0a0; font-size: 0.9rem; }
</style>
"""
st.markdown(DARK_CSS, unsafe_allow_html=True)

# --- DB LAYER (SQLite) ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS products(
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
    )
    """)
    conn.commit()
    conn.close()

def fetch_all():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM products")
    rows = cur.fetchall()
    conn.close()
    return rows

def dno_exists(dno: str, exclude_id=None) -> bool:
    conn = sqlite3.connect(DB_PATH)
    if exclude_id:
        cur = conn.execute("SELECT COUNT(*) FROM products WHERE dno=? AND id != ?", (dno, exclude_id))
    else:
        cur = conn.execute("SELECT COUNT(*) FROM products WHERE dno=?", (dno,))
    exists = cur.fetchone() > 0
    conn.close()
    return exists

def add_product(data_tuple):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO products (company, dno, matching, diamond, pcs, delivery_pcs, assignee, type, rate, total, image)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, data_tuple)
    conn.commit()
    conn.close()

def update_product(product_id, data_tuple):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        UPDATE products SET company=?, dno=?, matching=?, diamond=?, pcs=?, delivery_pcs=?, assignee=?, type=?, rate=?, total=?, image=?
        WHERE id=?
    """, data_tuple + (product_id,))
    conn.commit()
    conn.close()

def delete_products(ids):
    if not ids:
        return
    conn = sqlite3.connect(DB_PATH)
    conn.executemany("DELETE FROM products WHERE id = ?", [(i,) for i in ids])
    conn.commit()
    conn.close()

# --- MATCHING HELPERS ---
def parse_matching_string(matching: str):
    # "Red:2, Blue:3" -> list of (color, pcs)
    pairs = []
    total = 0
    if matching:
        for part in matching.split(","):
            if ":" in part:
                color, pcs = part.split(":", 1)
                color = color.strip()
                pcs = pcs.strip()
                if pcs.isdigit():
                    v = int(pcs)
                    pairs.append((color, v))
                    total += v
    return pairs, total

def build_matching_string(pairs):
    # list of (color, pcs) -> "Color:pcs, Color:pcs"
    parts = []
    total = 0
    for color, pcs in pairs:
        color = (color or "").strip()
        pcs_str = str(pcs).strip()
        if color and pcs_str.isdigit():
            v = int(pcs_str)
            parts.append(f"{color}:{v}")
            total += v
    return ", ".join(parts), total

# --- IMAGE HELPERS ---
def compress_image(path: str, max_size=(800, 800)) -> str:
    try:
        img = Image.open(path)
        img.thumbnail(max_size)
        out_path = COMPRESSED_DIR / Path(path).name
        img.save(out_path, optimize=True, quality=85)
        return str(out_path)
    except Exception:
        return path

def show_thumbnail(path: str, size=(60, 60)) -> Image.Image | None:
    try:
        if path and os.path.exists(path):
            img = Image.open(path)
        elif NO_IMAGE_PATH.exists():
            img = Image.open(NO_IMAGE_PATH)
        else:
            return None
        img.thumbnail(size)
        return img
    except Exception:
        return None

# --- UI HELPERS ---
def header():
    box = st.container(border=True, gap="small")
    with box:
        col_logo, col_title = st.columns([0.08, 0.92], gap="large")
        with col_logo:
            if LOGO_PATH.exists():
                st.image(str(LOGO_PATH), width=60)
        with col_title:
            st.markdown('<div class="header-box"><h2 style="margin:0">Jubilee Textile Processors</h2></div>', unsafe_allow_html=True)

def toolbar():
    box = st.container(border=True, gap="small")
    with box:
        c0, c1, c2, c3, c4, c5, c6, c7, c8 = st.columns([0.22,0.12,0.10,0.12,0.14,0.16,0.16,0.12,0.12], gap="small")
        with c0: search = st.text_input("Search", key="search", placeholder="Search…", label_visibility="collapsed")
        with c1: type_filter = st.selectbox("Type", ["All","WITH LACE","WITHOUT LACE"], index=0, label_visibility="collapsed")
        with c2: add_click = st.button("Add Product", use_container_width=True)
        with c3: edit_click = st.button("Edit Product", use_container_width=True)
        with c4: del_click = st.button("Delete Product(s)", use_container_width=True)
        with c5: exp_match = st.button("Export MATCHING (CSV)", use_container_width=True)
        with c6: exp_all_csv = st.button("Export All (CSV)", use_container_width=True)
        with c7: exp_all_xlsx = st.button("Export All (Excel)", use_container_width=True)
        with c8: imp_csv = st.button("Import CSV", use_container_width=True)
    return dict(search=search, type_filter=type_filter, add=add_click, edit=edit_click, delete=del_click,
                exp_match=exp_match, exp_all_csv=exp_all_csv, exp_all_xlsx=exp_all_xlsx, imp_csv=imp_csv)



def load_table_dataframe():
    # Build DataFrame with computed Pending and a thumbnail helper column
    rows = fetch_all()
    cols = ["ID","COMPANY NAME","D.NO.","MATCHING","Diamond","PCS","DELIVERY PCS","Pending","Assignee","Type","Rate","Total","Image"]
    data = []
    for r in rows:
        # r indexes: 0..11
        try:
            pending = int(r[27] or 0) - int(r[28] or 0)
        except Exception:
            pending = 0
        data.append([
            r, r[1], r[24], r[25], r[26],
            r[27], r[28], pending, r[29], r[30], r[31], r[32], r[33]
        ])
    df = pd.DataFrame(data, columns=cols)
    return df

def filter_df(df: pd.DataFrame, search: str, type_filter: str):
    if df.empty:
        return df
    sub = df.copy()

    # Type filter
    if type_filter and type_filter.lower() != "all":
        sub = sub[sub["Type"].astype(str).str.lower() == type_filter.lower()]

    # Search in any column
    if search:
        s = search.lower()
        mask = pd.Series(False, index=sub.index)
        for col in sub.columns:
            mask = mask | sub[col].astype(str).str.lower().str.contains(s, na=False)
        sub = sub[mask]
    return sub

def selectable_table(df: pd.DataFrame):
    # Show image preview alongside the table
    left, right = st.columns([0.72, 0.28])
    with left:
        # Show a grid-like editor but non-editable; selection integers input
        st.caption("Select rows by ID using the control below. The table is read-only; use Add/Edit for changes.")
        st.dataframe(df, use_container_width=True)
        selected_ids_csv = st.text_input(     "Selected IDs (comma-separated)",     value="",     placeholder="e.g. 1,3,8",     key="selected_ids_csv_main"  )
        try:
            selected_ids = [int(x) for x in selected_ids_csv.split(",") if x.strip().isdigit()]
        except Exception:
            selected_ids = []
    with right:
        st.markdown('<div class="img-preview">', unsafe_allow_html=True)
        st.subheader("Image Preview")
        preview_id = st.number_input(     "Preview by ID",     min_value=0,     step=1,     value=0,     key="preview_id_main"   )
        if preview_id:
            row = df[df["ID"] == preview_id]
            if not row.empty:
                img_path = str(row.iloc["Image"] or "")
                img = show_thumbnail(img_path, size=(500, 500))
                if img:
                    st.image(img, caption=img_path, use_container_width=True)
                else:
                    st.info("No image available.")
            else:
                st.info("ID not found in table.")
        else:
            st.write("Select an ID to preview image.")
        st.markdown('</div>', unsafe_allow_html=True)
    return selected_ids

def matching_editor(existing: str | None = ""):
    st.write("Enter color/pcs pairs. Add multiple rows. Total PCS is calculated.")
    pairs, _ = parse_matching_string(existing or "")
    # Render editable table using two columns repeatedly
    num_rows = st.number_input("Matching rows", min_value=0, step=1, value=max(1, len(pairs) or 1))
    colors = []
    quantities = []
    for i in range(num_rows):
        col1, col2 = st.columns([0.6, 0.4])
        default_color = pairs[i] if i < len(pairs) else ""
        default_pcs = pairs[i][1] if i < len(pairs) else 0
        with col1:
            colors.append(st.text_input(f"Color {i+1}", value=default_color, key=f"match_color_{i}"))
        with col2:
            quantities.append(st.number_input(f"PCS {i+1}", min_value=0, step=1, value=int(default_pcs), key=f"match_pcs_{i}"))
    pairs_now = [(c, q) for c, q in zip(colors, quantities) if str(c).strip() != ""]
    mstring, mtotal = build_matching_string(pairs_now)
    st.caption(f"Total PCS: {mtotal}")
    return mstring, mtotal

def add_or_edit_dialog(mode="add", row=None):
    st.subheader(f"{'Add' if mode=='add' else 'Edit'} Product")

    company = st.text_input("Company Name", value=(row["COMPANY NAME"] if row is not None else ""))
    dno = st.text_input("D.NO.", value=(row["D.NO."] if row is not None else ""))
    diamond = st.text_input("Diamond", value=(row["Diamond"] if row is not None else ""))

    mstring_init = row["MATCHING"] if row is not None else ""
    mstring, pcs_total = matching_editor(mstring_init)

    delivery_pcs = st.number_input("Delivery PCS", min_value=0, step=1, value=int(row["DELIVERY PCS"]) if row is not None else 0)
    assignee = st.text_input("Assignee", value=(row["Assignee"] if row is not None else ""))
    type_val = st.selectbox("Type", ["WITH LACE", "WITHOUT LACE"], index=0 if (row is None or str(row["Type"]).upper()=="WITH LACE") else 1)
    rate = st.number_input("Rate", min_value=0.0, step=1.0, value=float(row["Rate"]) if row is not None else 0.0)

    # Image input: either pick from disk to compress, or type existing path
    img_col1, img_col2 = st.columns([0.6, 0.4])
    with img_col1:
        uploaded = st.file_uploader("Choose image (optional)", type=["png", "jpg", "jpeg", "bmp"])
        chosen_path = ""
        if uploaded is not None:
            # Save temp to disk then compress to compressed/
            temp_path = Path("temp_upload_" + uploaded.name)
            temp_path.write_bytes(uploaded.read())
            chosen_path = compress_image(str(temp_path))
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass
            st.success(f"Compressed to: {chosen_path}")
        manual_path = st.text_input("Or path on disk", value=(row["Image"] if row is not None else ""))
        image_path = chosen_path if chosen_path else manual_path
    with img_col2:
        thumb = show_thumbnail(image_path)
        if thumb:
            st.image(thumb, caption="Image", use_container_width=True)
        else:
            st.caption("No image preview")

    total = pcs_total * (rate or 0.0)

    payload = dict(
        company=company.strip(),
        dno=dno.strip(),
        matching=mstring,
        diamond=diamond.strip(),
        pcs=int(pcs_total),
        delivery_pcs=int(delivery_pcs or 0),
        assignee=assignee.strip(),
        type=type_val,
        rate=float(rate or 0.0),
        total=float(total),
        image=image_path.strip()
    )
    return payload

# --- APP START ---
init_db()

header()
actions = toolbar()

# Data and view
df_full = load_table_dataframe()
df_view = filter_df(df_full, actions["search"], actions["type_filter"])

selected_ids = selectable_table(df_view)

st.divider()

# Wrap table + preview in a container for internal spacing
content = st.container(gap="medium")
with content:
    left, right = st.columns([0.68, 0.32], gap="large")
    with left:
        st.caption("Select rows by ID. Table is read-only; use Add/Edit for changes.", help="Use filters above to narrow results.")
        st.dataframe(df_view, use_container_width=True, height=420)  # shorter table avoids crowding below
        selected_ids_csv = st.text_input(     "Selected IDs (comma-separated)",     value="",     placeholder="e.g. 1,3,8",     key="selected_ids_csv_main"   )
    with right:
        st.markdown('<div class="img-preview">', unsafe_allow_html=True)
        st.subheader("Image Preview")
        preview_id = st.number_input(     "Preview by ID",     min_value=0,     step=1,     value=0,     key="preview_id_main"  )
        # ... image preview code ...
        st.markdown('</div>', unsafe_allow_html=True)

st.divider()

# --- ACTION HANDLERS ---
# Add
if actions["add"]:
    with st.expander("Add Product", expanded=True):
        payload = add_or_edit_dialog(mode="add", row=None)
        col_a, col_b = st.columns([0.15, 0.85])
        with col_a:
            if st.button("Save New"):
                if not payload["dno"]:
                    st.error("D.NO. is required.")
                elif dno_exists(payload["dno"]):
                    st.error(f"A product with D.NO. '{payload['dno']}' already exists.")
                else:
                    add_product(tuple(payload.values()))
                    st.success("Product added. Refresh the page to see it in the table.")

# Edit
if actions["edit"]:
    if not selected_ids:
        st.warning("Select one ID to edit.")
    elif len(selected_ids) > 1:
        st.warning("Please select only one ID to edit.")
    else:
        pid = selected_ids
        row = df_full[df_full["ID"] == pid]
        if row.empty:
            st.error("Selected ID not found.")
        else:
            with st.expander(f"Edit Product #{pid}", expanded=True):
                rowdict = row.iloc.to_dict()
                payload = add_or_edit_dialog(mode="edit", row=rowdict)
                col_a, col_b = st.columns([0.15, 0.85])
                with col_a:
                    if st.button("Save Changes"):
                        if not payload["dno"]:
                            st.error("D.NO. is required.")
                        elif dno_exists(payload["dno"], exclude_id=pid):
                            st.error(f"A product with D.NO. '{payload['dno']}' already exists.")
                        else:
                            update_product(pid, tuple(payload.values()))
                            st.success("Product updated. Refresh the page to see it in the table.")

# Delete
if actions["delete"]:
    if not selected_ids:
        st.warning("Select one or more IDs to delete.")
    else:
        if st.confirm("Are you sure you want to delete the selected product(s)?"):
            delete_products(selected_ids)
            st.success("Deleted. Refresh the page to update the table.")

# Export MATCHING CSV
if actions["exp_match"]:
    # All rows or selected rows; mirror desktop app: export selected if any, else all
    if selected_ids:
        sub = df_full[df_full["ID"].isin(selected_ids)]
    else:
        sub = df_full
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["D.NO.", "Color", "PCS"])
    for _, r in sub.iterrows():
        dno = str(r["D.NO."] or "")
        pairs, total_pcs = parse_matching_string(str(r["MATCHING"] or ""))
        for color, pcs in pairs:
            writer.writerow([dno, color, pcs])
        if pairs:
            writer.writerow(["", "", ""])
            writer.writerow(["", "", f"Total PCS: {total_pcs}"])
            writer.writerow(["", "", ""])
    st.download_button(
        "Download MATCHING CSV",
        data=out.getvalue().encode("utf-8"),
        file_name=f"matching_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )

# Export All CSV
if actions["exp_all_csv"]:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["ID","COMPANY NAME","D.NO.","MATCHING","Diamond","PCS","DELIVERY PCS","Assignee","Type","Rate","Total","Image"])
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM products")
    for row in cur.fetchall():
        # Note: Pending is computed, not stored; export columns align with desktop
        writer.writerow(row)
    conn.close()
    st.download_button(
        "Download All (CSV)",
        data=out.getvalue().encode("utf-8"),
        file_name=f"products_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )

# Export All Excel
if actions["exp_all_xlsx"]:
    from openpyxl import Workbook
    wb = Workbook()
    sh = wb.active
    headers = ["ID","COMPANY NAME","D.NO.","MATCHING","Diamond","PCS","DELIVERY PCS","Pending","Assignee","Type","Rate","Total","Image"]
    sh.append(headers)
    for _, r in df_full.iterrows():
        sh.append([
            r["ID"], r["COMPANY NAME"], r["D.NO."], r["MATCHING"], r["Diamond"], r["PCS"],
            r["DELIVERY PCS"], r["Pending"], r["Assignee"], r["Type"], r["Rate"], r["Total"], r["Image"]
        ])
    out = io.BytesIO()
    wb.save(out)
    st.download_button(
        "Download All (Excel)",
        data=out.getvalue(),
        file_name=f"products_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# Import CSV
if actions["imp_csv"]:
    up = st.file_uploader("Upload products CSV", type=["csv"], accept_multiple_files=False)
    if up is not None:
        try:
            text = up.read().decode("utf-8")
            reader = csv.reader(io.StringIO(text))
            headers = next(reader, None)
            expected = ["ID","COMPANY NAME","D.NO.","MATCHING","Diamond","PCS","DELIVERY PCS","Assignee","Type","Rate","Total","Image"]
            if headers != expected:
                st.error(f"CSV headers do not match expected format:\n{expected}")
            else:
                conn = sqlite3.connect(DB_PATH)
                cur = conn.cursor()
                imported = 0
                for row in reader:
                    if len(row) != 12:
                        continue
                    try:
                        pid = int(row) if row.strip().isdigit() else None
                        pcs = int(row[27]) if row[27].strip().isdigit() else 0
                        delv = int(row[28]) if row[28].strip().isdigit() else 0
                        rate = float(row[31]) if row[31].strip() else 0.0
                        total = float(row[32]) if row[32].strip() else 0.0
                        values = (pid, row[1], row[24], row[25], row[26], pcs, delv, row[29], row[30], rate, total, row[33])
                        cur.execute("""
                            INSERT OR REPLACE INTO products(
                                id, company, dno, matching, diamond, pcs, delivery_pcs, assignee, type, rate, total, image
                            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, values)
                        imported += 1
                    except Exception:
                        continue
                conn.commit()
                conn.close()
                st.success(f"Imported {imported} records. Refresh to view.")
        except Exception as e:
            st.error(f"Import failed: {e}")





