# jubilee_streamlit/app.py
import streamlit as st
import sqlite3
import os
from PIL import Image
from datetime import datetime

db_path = "inventory.db"
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

st.set_page_config(page_title="Jubilee Inventory", layout="wide")
st.title("🧵 Jubilee Textile Inventory")

# ---------- DATABASE HELPERS ----------
def get_db():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def get_products():
    conn = get_db()
    rows = conn.execute("SELECT * FROM products").fetchall()
    conn.close()
    return rows

def add_product(data):
    conn = get_db()
    conn.execute("""
        INSERT INTO products (company, dno, matching, diamond, pcs, delivery_pcs,
        assignee, type, rate, total, image) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, data)
    conn.commit()
    conn.close()

def delete_product(product_id):
    conn = get_db()
    conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()

# ---------- IMAGE UTILS ----------
def save_image(uploaded_file):
    if uploaded_file is None:
        return ""
    file_path = os.path.join(UPLOAD_DIR, uploaded_file.name)
    image = Image.open(uploaded_file)
    image.thumbnail((800, 800))
    image.save(file_path)
    return file_path

# ---------- UI: ADD FORM ----------
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

        image = st.file_uploader("Image", type=["png", "jpg", "jpeg"])

        submitted = st.form_submit_button("Add Product")
        if submitted:
            total = pcs * rate
            image_path = save_image(image)
            add_product((company, dno, matching, diamond, pcs, delivery_pcs, assignee, ptype, rate, total, image_path))
            st.success("Product added successfully!")
            st.experimental_rerun()

# ---------- UI: DISPLAY TABLE ----------
def show_inventory():
    st.subheader("📦 Inventory Table")
    rows = get_products()

    if rows:
        for i, row in enumerate(rows, start=1):
            with st.expander(f"{i}. {row['company']} - {row['dno']}"):
                cols = st.columns([1, 1, 2, 1, 1])
                with cols[0]:
                    st.write(f"**Diamond**: {row['diamond']}")
                    st.write(f"**PCS**: {row['pcs']}")
                    st.write(f"**Delivery**: {row['delivery_pcs']}")
                    st.write(f"**Pending**: {row['pcs'] - row['delivery_pcs']}")
                with cols[1]:
                    st.write(f"**Assignee**: {row['assignee']}")
                    st.write(f"**Type**: {row['type']}")
                    st.write(f"**Rate**: ₹{row['rate']}")
                    st.write(f"**Total**: ₹{row['total']}")
                with cols[2]:
                    st.write(f"**Matching**:")
                    st.code(row['matching'] or "-", language="text")
                with cols[3]:
                    if row['image'] and os.path.exists(row['image']):
                        st.image(row['image'], width=100)
                    else:
                        st.write("No image")
                with cols[4]:
                    if st.button("❌ Delete", key=f"del_{row['id']}"):
                        delete_product(row['id'])
                        st.warning("Product deleted")
                        st.experimental_rerun()
    else:
        st.info("No products found. Add your first entry above.")

# ---------- MAIN ----------
show_add_form()
show_inventory()
