from __future__ import annotations

from pathlib import Path
import sys

# Fix path per importare 'frontend'
ROOT_DIR = Path(__file__).resolve().parents[1]  # .../LargeScaleProject
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st
from frontend.utils.layout import init_page, render_header, render_sidebar, render_footer

init_page()
render_header()
render_sidebar()

st.title("Dashboard")
st.write("Usa la sidebar per navigare tra le pagine (Home, Debug, ecc.).")

render_footer()