# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import os
import numpy as np
import re
import html # For escaping HTML content
import streamlit.components.v1 as components
from pathlib import Path # For easier path handling
import unicodedata # For NFC normalization
# You need to install this: pip install unidecode
try:
    from unidecode import unidecode # For accent removal
except ImportError:
    # Define a dummy fallback function if unidecode is not installed
    def unidecode(x):
        # Display warning only once if possible
        if 'unidecode_warning_shown' not in st.session_state:
            st.warning("`unidecode` library not found (pip install unidecode). Accent handling in lookups may be less robust.")
            st.session_state.unidecode_warning_shown = True
        return str(x)


# --- Page Config (MUST be the first Streamlit command) ---
st.set_page_config(layout="wide")

# --- Determine Project Root Relative to THIS script ---
# Assumes script is at the root of the project structure cloned by Streamlit Cloud
APP_DIR = Path(__file__).parent
PROJECT_ROOT = APP_DIR

# --- Configuration ---
EXCEL_DATA_ROOT = PROJECT_ROOT / "excel_data" # <<< Path to Excel files WITHIN the repo

# CORRECTED LIST - Names must EXACTLY match folder names in excel_data on GitHub
CATEGORY_SUBDIRS = [
    "Antibiotiques",
    "Comprimés",  # NFC 'é'
    "Comprimes antalgiques",
    "Cremes - Pommades",
    "Gouttes",
    "Injections",
    "Ovules vaginaux",
    "Pulvérisations", # NFC 'é'
    "Sachets",
    "Sirop",
    "Suppositoires"
]
# Categories where URLs are expected directly in specific cells (will ignore name->URL map)
SPECIAL_HANDLING_CATEGORIES = ["Antibiotiques", "Sachets", "Sirop", "Suppositoires"] # Corrected 'Sirop'

# --- Populate Category Paths (Relative to repo) ---
# Map category name to its Excel file path IN THE REPO structure
category_excel_path_map = {}
for sub_dir in CATEGORY_SUBDIRS:
    # Use the name directly from the corrected list
    # No extra normalization needed here if list matches folders exactly
    normalized_subdir_name = sub_dir

    # --- Handle potential filename mismatch for specific categories ---
    # Example: If folder is "Cremes - Pommades" but file is "Pommade - Cremes.xlsx"
    # (Assuming you renamed the file to match the folder as recommended)
    excel_filename = f"{normalized_subdir_name}.xlsx"
    # --- Uncomment and modify below if you have other mismatches ---
    # if normalized_subdir_name == "Another Category":
    #     excel_filename = "DifferentExcelName.xlsx"

    # Construct the full path expected within the repository
    excel_file_path = EXCEL_DATA_ROOT / normalized_subdir_name / excel_filename
    # Store path as string
    category_excel_path_map[normalized_subdir_name] = str(excel_file_path)

# Category names for the dropdown come directly from the corrected list
category_names = CATEGORY_SUBDIRS


# --- Load Image URL Mapping from CSV ---
csv_path = PROJECT_ROOT / "github_image_urls_CATEGORIZED.csv" # Use the categorized CSV
# Map holds { 'categorykey-normalized_filename_stem': url }
image_url_map = {}

# Function for consistent normalization (used for map keys and lookups)
def normalize_for_lookup(text):
    """Lowercase, remove accents (best effort), replace non-alphanum with underscore."""
    if not isinstance(text, str): text = str(text)
    try:
        # NFC normalization first helps handle composed vs decomposed chars
        normalized = unicodedata.normalize('NFC', text)
        # Remove accents -> convert to closest ASCII representation
        ascii_text = unidecode(normalized)
    except Exception as e:
        print(f"Warning: Text normalization error for '{text}': {e}. Using original.")
        ascii_text = text # Fallback
    # Lowercase, replace one or more non-alphanumeric/non-underscore chars with a single underscore
    cleaned = re.sub(r'[^\w]+', '_', ascii_text, flags=re.UNICODE).lower()
    # Remove leading/trailing underscores
    cleaned = cleaned.strip('_')
    return cleaned

# Cache the loaded map for performance. Show spinner during load.
@st.cache_data(show_spinner="Loading image URL map...")
def load_url_map(path):
    """Loads the CATEGORIZED CSV and creates a composite_key -> URL mapping using NORMALIZED names."""
    url_map = {}
    print(f"Attempting to load URL map from: {path}") # Log load attempt
    try:
        if not path.exists():
            st.error(f"Image URL CSV not found at specified path: {path}")
            return {}

        # Specify dtype to avoid issues with numeric-like strings
        df_map = pd.read_csv(path, dtype=str)
        required_cols = ['category', 'filename', 'raw_url']
        if not all(col in df_map.columns for col in required_cols):
            st.error(f"Image URL CSV ('{path.name}') must contain columns: {required_cols}")
            return {}

        processed_count = 0; skipped_count = 0; duplicate_keys = 0
        # Iterate through rows to build the map
        for index, row in df_map.iterrows():
            try:
                 # Get data, handling potential missing values
                 category = str(row['category']) if pd.notna(row['category']) else None
                 filename = str(row['filename']) if pd.notna(row['filename']) else None
                 raw_url = str(row['raw_url']) if pd.notna(row['raw_url']) else None

                 # Check if all necessary data is present for this row
                 if category and filename and raw_url:
                     # Normalize category name for the key
                     category_key = normalize_for_lookup(category)
                     # Normalize filename stem (remove extension) for the key
                     filename_stem = Path(filename).stem
                     filename_key = normalize_for_lookup(filename_stem)

                     # Create the composite key
                     composite_key = f"{category_key}-{filename_key}"

                     # Add to map, handle potential duplicates (overwrite keeps last found)
                     if composite_key in url_map: duplicate_keys += 1
                     url_map[composite_key] = str(raw_url) # Ensure URL is string
                     processed_count += 1
                 else: skipped_count += 1
            except Exception as e:
                 skipped_count += 1
                 print(f"Error processing CSV row {index+2}: {e}, Row data: {row.to_dict()}")

        print(f"Loaded {processed_count} image URLs (skipped {skipped_count}, dups overwritten: {duplicate_keys}).")
        if not url_map: st.warning(f"Image URL map loaded empty from '{path.name}'. Check CSV content and paths.")
        # print(f"DEBUG MAP KEYS (first 10): {list(url_map.keys())[:10]}") # Optional Debug
        return url_map
    except Exception as e:
        st.error(f"FATAL: Failed to load/process CSV '{path.name}': {e}")
        return {} # Return empty on major failure

# Load the map (now occurs after set_page_config)
image_url_map = load_url_map(csv_path)


# --- Function to Read All Sheets from Excel (using path within repo) ---
def read_excel_sheets(excel_file_path_str): # Takes the full path string
    """Reads all sheets from the specified Excel file path."""
    excel_file_path = Path(excel_file_path_str) # Convert string path to Path object
    excel_filename = excel_file_path.name

    # Check if the file exists at the calculated path WITHIN THE REPO
    if not excel_file_path.is_file():
        st.error(f"Excel file not found at expected path: '{excel_file_path}'. Check file exists in repo structure ('excel_data' folder).")
        return None, None # Return None if file not found

    st.info(f"Reading sheets from file: {excel_filename}")
    try:
        # Read all sheets, assume header row 0, handle blanks, read as string
        all_sheets_data = pd.read_excel(
            excel_file_path, # Use the Path object
            sheet_name=None, # Read all sheets
            header=0,        # Use first row as header
            keep_default_na=False, # Keep blanks initially
            na_values=[''],  # Treat blanks as NaN for pandas logic
            dtype=str        # Attempt to read all data as string initially
        )
        # Clean column names for all loaded sheets
        for sheet_name, df in all_sheets_data.items():
            if df is not None:
                 # Ensure column names are strings and clean up "Unnamed: N"
                 df.columns = [str(col) if not str(col).startswith("Unnamed:") else "" for col in df.columns]
        return all_sheets_data, excel_filename
    except Exception as read_error:
        st.error(f"Error reading Excel file '{excel_filename}': {read_error}")
        return None, excel_filename


# --- HTML Function to Generate Table with Merging and Conditional Links ---
def dataframe_to_html_universal_links(df, table_id="display-table", current_category_name="", url_map=None, name_col_index=0):
    """
    Converts DataFrame to HTML, handling merges and styling.
    Conditionally creates clickable links for images based on url_map or raw URLs.
    Links trigger a JS popup for external URLs.
    """
    if df is None or df.empty:
        return "<p>Table is empty.</p>"

    df_processed = df.copy()
    df_processed.replace(['', None, 'nan', 'NaN', pd.NA], np.nan, inplace=True) # Robust NaN replacement

    # --- Pre-calculate rowspans ---
    rowspans = pd.DataFrame(1, index=df_processed.index, columns=df_processed.columns)
    merge_col_indices = [1, 2] # Example: Adjust if necessary

    for c_idx in merge_col_indices:
        if c_idx >= len(df_processed.columns): continue
        active_span_start_row_index = np.nan
        for r_idx_pos, r_idx_abs in enumerate(df_processed.index):
            # Check index existence before accessing .loc
            if r_idx_abs not in df_processed.index or df_processed.columns[c_idx] not in df_processed.columns: continue
            current_val = df_processed.loc[r_idx_abs, df_processed.columns[c_idx]]

            if pd.notna(current_val):
                 if pd.notna(active_span_start_row_index):
                     span_len = r_idx_pos - df_processed.index.get_loc(active_span_start_row_index)
                     if span_len > 1:
                         rowspans.loc[active_span_start_row_index, rowspans.columns[c_idx]] = span_len
                         for i in range(1, span_len):
                             row_to_mark = df_processed.index[df_processed.index.get_loc(active_span_start_row_index) + i]
                             if row_to_mark in rowspans.index: rowspans.loc[row_to_mark, rowspans.columns[c_idx]] = 0
                 active_span_start_row_index = r_idx_abs
            elif pd.isna(active_span_start_row_index):
                 if r_idx_abs in rowspans.index: rowspans.loc[r_idx_abs, rowspans.columns[c_idx]] = 1
        if pd.notna(active_span_start_row_index):
             span_len = len(df_processed) - df_processed.index.get_loc(active_span_start_row_index)
             if span_len > 1:
                 rowspans.loc[active_span_start_row_index, rowspans.columns[c_idx]] = span_len
                 for i in range(1, span_len):
                     row_to_mark = df_processed.index[df_processed.index.get_loc(active_span_start_row_index) + i]
                     if row_to_mark in rowspans.index: rowspans.loc[row_to_mark, rowspans.columns[c_idx]] = 0

    # --- Generate HTML Structure ---
    html_parts = []
    html_parts.append(f"""
    <style>
        table#{table_id} {{ border-collapse: collapse; width: 100%; font-family: sans-serif; }}
        table#{table_id} th, table#{table_id} td {{ border: 1px solid #cccccc; padding: 8px; text-align: center; vertical-align: middle; }}
        table#{table_id} th {{ background-color: #e8e8e8; color: #000000; font-weight: bold; }}
        table#{table_id} td {{ background-color: #ffffff; color: #000000; }}
        table#{table_id} tbody tr:nth-child(even) td {{ background-color: #f2f2f2; }}
        table#{table_id} td a.external-image-popup {{ color: #0066cc; text-decoration: none; cursor: pointer; }}
        table#{table_id} td a.external-image-popup:hover {{ text-decoration: underline; }}
    </style>
    <table class="dataframe" id="{table_id}">
    """)

    # Generate Table Header
    html_parts.append("<thead><tr>")
    skip_next_header_cols = 0
    for c_idx, col_name in enumerate(df_processed.columns):
        if skip_next_header_cols > 0: skip_next_header_cols -= 1; continue
        colspan = 1
        for lookahead_c_idx in range(c_idx + 1, len(df_processed.columns)):
            # Check if column name is empty string (result of merge or unnamed)
            if df_processed.columns[lookahead_c_idx] == "": colspan += 1
            else: break
        colspan_attr = f' colspan="{colspan}"' if colspan > 1 else ""
        escaped_col_name = html.escape(str(col_name))
        html_parts.append(f"<th{colspan_attr}>{escaped_col_name}</th>")
        if colspan > 1: skip_next_header_cols = colspan - 1
    html_parts.append("</tr></thead>")

    # Generate Table Body
    html_parts.append("<tbody>")
    category_key = normalize_for_lookup(current_category_name)
    # print(f"HTML Body Gen: Category Key = {category_key}") # Optional Debug

    for r_idx_abs in df_processed.index:
        html_parts.append("<tr>")
        for c_idx, col_name in enumerate(df_processed.columns):
            # Check index exists before accessing rowspans and df_processed
            if r_idx_abs not in rowspans.index or r_idx_abs not in df_processed.index: continue
            if col_name not in df_processed.columns: continue # Check column exists

            span = rowspans.loc[r_idx_abs, col_name] # Access using column name
            if span == 0: continue
            else:
                rowspan_attr = f' rowspan="{span}"' if span > 1 else ""
                current_value = df_processed.loc[r_idx_abs, col_name]
                cell_display_value = "" if pd.isna(current_value) else str(current_value).strip()
                escaped_display_value = html.escape(cell_display_value)

                td_content = escaped_display_value
                link_url = None; link_text = escaped_display_value; filename_for_popup = "image"

                # --- Link Logic ---
                if url_map and c_idx == name_col_index and cell_display_value:
                    try:
                        normalized_name_lookup = normalize_for_lookup(cell_display_value)
                        composite_key_lookup = f"{category_key}-{normalized_name_lookup}"
                        # print(f" Checking Name: '{cell_display_value}' -> Key: '{composite_key_lookup}'") # Debug
                        if composite_key_lookup in url_map:
                            link_url = url_map[composite_key_lookup]
                            link_text = escaped_display_value
                            try: filename_for_popup = link_url.split('/')[-1].split('?')[0]
                            except: pass
                            # print(f"    FOUND URL: {link_url}") # Debug
                        # else: print(f"    NOT FOUND in map.") # Debug
                    except Exception as e: print(f"Error link lookup: {e}");

                elif link_url is None and cell_display_value.startswith(("http://", "https://")):
                     link_url = cell_display_value
                     try: filename_for_popup = link_url.split('/')[-1].split('?')[0]; link_text = html.escape(filename_for_popup)
                     except: link_text = "View Image"

                if link_url:
                    escaped_url = html.escape(link_url, quote=True)
                    escaped_filename = html.escape(filename_for_popup, quote=True)
                    td_content = (f'<a href="#" class="external-image-popup" data-url="{escaped_url}" data-filename="{escaped_filename}">{link_text}</a>')

                html_parts.append(f"<td{rowspan_attr}>{td_content}</td>")
        html_parts.append("</tr>")
    html_parts.append("</tbody></table>")

    return "".join(html_parts)

# --- JavaScript block for the popup (Identical) ---
javascript_popup_script = """
<script>
(function() {
    function openExternalPopup(event) {
        event.preventDefault(); const link = event.currentTarget;
        const imageUrl = link.getAttribute('data-url');
        const filename = link.getAttribute('data-filename') || 'image';
        if (imageUrl) {
            console.log(`Opening popup for ${filename} at ${imageUrl}`);
            const popupWidth = 800; const popupHeight = 600;
            try { window.open(imageUrl, filename, `width=${popupWidth},height=${popupHeight},scrollbars=yes,resizable=yes`); }
            catch (e) { console.error('Error opening popup:', e); alert('Could not open image popup. Check blocker. Err: ' + e); }
        } else { console.error('Could not find URL for link:', link); alert('Could not retrieve image URL.'); }
    }
    setTimeout(function() {
        // Consider targeting links only within the specific table ID if multiple tables might use this class
        const links = document.querySelectorAll('a.external-image-popup');
        console.log('Found ' + links.length + ' external image links to attach listeners.');
        links.forEach(link => {
            if (!link.dataset.listenerAttached) {
                 link.addEventListener('click', openExternalPopup);
                 link.dataset.listenerAttached = 'true';
            }
        });
     }, 500); // 500ms delay
})();
</script>
"""


# --- Streamlit App Layout ---
st.title("Pharmaceutical Data Viewer")
st.markdown("Select a category and sheet. Click medication names or image links for popup.")

if not category_names: st.error("No categories defined or found. Check `CATEGORY_SUBDIRS` and `excel_data` structure.")
else:
    selected_category_name = st.selectbox("Select Pharmaceutical Category:", options=category_names, index=None, placeholder="Choose a category...")

    if selected_category_name:
        st.header(f"Category: {selected_category_name}")

        # --- Get the EXPECTED Excel file path WITHIN the repo ---
        # Use the name from the dropdown (which matches CATEGORY_SUBDIRS exactly)
        selected_excel_path_str = category_excel_path_map.get(selected_category_name)

        if not selected_excel_path_str:
             st.error(f"Internal setup error: No Excel path configured for category '{selected_category_name}'. Check `category_excel_path_map` construction.")
        else:
            # --- Read Excel file using the path relative to the repo ---
            sheets_data, filename_read = read_excel_sheets(selected_excel_path_str)

            # --- Handle results of reading Excel ---
            if sheets_data is None: pass # Error displayed by function
            elif not sheets_data: st.warning(f"Excel file '{filename_read}' (for {selected_category_name}) appears empty or unreadable.")
            else:
                sheet_names = list(sheets_data.keys()); selected_sheet_name = None
                if len(sheet_names) == 1: selected_sheet_name = sheet_names[0]
                else:
                    session_key_sheet = f'{selected_category_name}_sheet_selection';
                    if session_key_sheet not in st.session_state: st.session_state[session_key_sheet] = None
                    st.markdown("---")
                    selected_sheet_name = st.selectbox(f"Select Sheet from '{filename_read}':", options=[None] + sheet_names, format_func=lambda x: "Choose..." if x is None else x, key=session_key_sheet)

                # --- Display selected sheet data ---
                if selected_sheet_name:
                    st.subheader(f"Data for Sheet: {selected_sheet_name}")
                    df_original = sheets_data.get(selected_sheet_name)
                    if df_original is None: st.error(f"Could not retrieve data for sheet '{selected_sheet_name}'.")
                    elif df_original.empty: st.write(f"_Sheet '{selected_sheet_name}' is empty._")
                    else:
                        # Generate unique table ID using sanitized names
                        sanitized_category = re.sub(r'[^a-zA-Z0-9_]+', '_', selected_category_name)
                        sanitized_sheet = re.sub(r'[^a-zA-Z0-9_]+', '_', selected_sheet_name)
                        table_id = f"table_{sanitized_category}_{sanitized_sheet}"

                        # Determine linking strategy based on category name
                        use_url_map = selected_category_name not in SPECIAL_HANDLING_CATEGORIES
                        current_url_map = image_url_map if use_url_map else None
                        name_column_to_link = 0 # Assume name is in first col (index 0)

                        # Generate HTML table string
                        html_table_content = dataframe_to_html_universal_links(
                            df_original,
                            table_id=table_id,
                            current_category_name=selected_category_name, # Pass category name
                            url_map=current_url_map,
                            name_col_index=name_column_to_link
                        )

                        # Combine table HTML and the JavaScript for popups
                        full_html_content = html_table_content + javascript_popup_script

                        # Render using components.html
                        components.html(full_html_content, height=800, scrolling=True) # Adjust height

                elif len(sheet_names) > 1 and not selected_sheet_name: st.info("Please select a sheet.")
    elif not selected_category_name: st.info("Please select a category.")

st.markdown("---"); st.caption("App data with external image popups.")