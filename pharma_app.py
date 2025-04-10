import streamlit as st
import pandas as pd
import os
import numpy as np
import re
import html # Still needed for escaping general content
import streamlit.components.v1 as components
# NO base64, mimetypes, streamlit_js_eval needed anymore

# --- Configuration (remains the same) ---
BASE_DIR = "/Users/user/Desktop/Pharm"
CATEGORY_SUBDIRS = [
    "Antibiotiques", "Comprimés", "Comprimes antalgiques",
    "Cremes - Pommades", "Gouttes", "Injections", "Ovules vaginaux",
    "Pulvérisations", "Sachets", "Sirop", "Suppositoires"
]
category_path_map = {}
for sub_dir in CATEGORY_SUBDIRS:
    full_path = os.path.join(BASE_DIR, sub_dir)
    if os.path.isdir(full_path):
        category_path_map[sub_dir] = full_path
    else:
        print(f"Warning: Directory not found and skipped: {full_path}")
category_names = list(category_path_map.keys())

# --- Session State NOT needed for this approach ---
# Remove initialization for clicked_image_uri / filename

# --- Function to Read All Sheets (remains the same) ---
def read_excel_sheets(directory_path):
    excel_file_path = None
    excel_filename = None
    try:
        for filename in os.listdir(directory_path):
            if filename.lower().endswith(('.xlsx', '.xls')) and not filename.startswith('~'):
                excel_file_path = os.path.join(directory_path, filename)
                excel_filename = filename
                break
        if not excel_file_path:
            st.warning(f"No Excel file (.xlsx or .xls) found in '{directory_path}'.")
            return None, None
        st.info(f"Reading sheets from file: {excel_filename}")
        try:
            all_sheets_data = pd.read_excel(
                excel_file_path,
                sheet_name=None,
                header=0,
                keep_default_na=False,
                na_values=['']
            )
            for df in all_sheets_data.values():
                 df.columns = [str(col) if not str(col).startswith("Unnamed:") else "" for col in df.columns]
            return all_sheets_data, excel_filename
        except Exception as read_error:
            st.error(f"Error reading Excel file '{excel_filename}': {read_error}")
            return None, excel_filename
    except FileNotFoundError:
        st.error(f"Error: Directory not found: {directory_path}")
        return None, None
    except Exception as e:
        st.error(f"An error occurred reading sheets: {e}")
        return None, None


# --- SIMPLIFIED HTML Function - Creates standard links for URLs ---
def dataframe_to_html_with_links(df, table_id="display-table"):
    """
    Converts DataFrame to HTML, handling merges and styling.
    Turns cells containing valid URLs into clickable links.
    """
    if df is None or df.empty:
        return "<p>Table is empty.</p>"

    df_processed = df.copy()
    df_processed.replace({'': np.nan}, inplace=True)

    # Pre-calculate rowspans
    rowspans = pd.DataFrame(1, index=df_processed.index, columns=df_processed.columns)
    merge_col_indices = [1, 2] # Example: Columns B and C

    for c_idx in merge_col_indices:
        if c_idx >= len(df_processed.columns): continue
        active_span_start_row = -1
        for r_idx_rel, r_idx_abs in enumerate(df_processed.index):
            current_val = df_processed.loc[r_idx_abs, df_processed.columns[c_idx]]
            if pd.notna(current_val):
                 if active_span_start_row != -1:
                     span_len = r_idx_rel - df_processed.index.get_loc(active_span_start_row)
                     if span_len > 1:
                         rowspans.loc[active_span_start_row, rowspans.columns[c_idx]] = span_len
                         for i in range(1, span_len):
                             row_to_mark = df_processed.index[df_processed.index.get_loc(active_span_start_row) + i]
                             rowspans.loc[row_to_mark, rowspans.columns[c_idx]] = 0
                 active_span_start_row = r_idx_abs
            elif active_span_start_row == -1:
                 rowspans.loc[r_idx_abs, rowspans.columns[c_idx]] = 1
        if active_span_start_row != -1:
             span_len = len(df_processed) - df_processed.index.get_loc(active_span_start_row)
             if span_len > 1:
                 rowspans.loc[active_span_start_row, rowspans.columns[c_idx]] = span_len
                 for i in range(1, span_len):
                     row_to_mark = df_processed.index[df_processed.index.get_loc(active_span_start_row) + i]
                     rowspans.loc[row_to_mark, rowspans.columns[c_idx]] = 0

    # Generate HTML Structure
    html_parts = []
    html_parts.append(f"""
    <style>
        /* CSS can remain largely the same */
        table#{table_id} {{ border-collapse: collapse; width: 100%; font-family: sans-serif; }}
        table#{table_id} th, table#{table_id} td {{ border: 1px solid #cccccc; padding: 8px; text-align: center; vertical-align: middle; }}
        table#{table_id} th {{ background-color: #e8e8e8; color: #000000; font-weight: bold; }}
        table#{table_id} td {{ background-color: #ffffff; color: #000000; }}
        table#{table_id} tbody tr:nth-child(even) td {{ background-color: #f2f2f2; }}
        /* Standard link styling */
        table#{table_id} td a {{ color: #0066cc; text-decoration: none; }}
        table#{table_id} td a:hover {{ text-decoration: underline; }}
    </style>
    <table class="dataframe" id="{table_id}">
    """)
    # Header
    html_parts.append("<thead><tr>")
    skip_next_header_cols = 0
    for c_idx, col_name in enumerate(df_processed.columns):
        if skip_next_header_cols > 0: skip_next_header_cols -= 1; continue
        colspan = 1
        for lookahead_c_idx in range(c_idx + 1, len(df_processed.columns)):
            if df_processed.columns[lookahead_c_idx] == "": colspan += 1
            else: break
        colspan_attr = f' colspan="{colspan}"' if colspan > 1 else ""
        escaped_col_name = html.escape(str(col_name))
        html_parts.append(f"<th{colspan_attr}>{escaped_col_name}</th>")
        if colspan > 1: skip_next_header_cols = colspan - 1
    html_parts.append("</tr></thead>")

    # Body generation (Check for URLs)
    html_parts.append("<tbody>")
    for r_idx_abs in df_processed.index:
        html_parts.append("<tr>")
        for c_idx, col_name in enumerate(df_processed.columns):
            span = rowspans.loc[r_idx_abs, rowspans.columns[c_idx]]
            if span == 0: continue
            else:
                rowspan_attr = f' rowspan="{span}"' if span > 1 else ""
                current_value = df_processed.loc[r_idx_abs, col_name]
                cell_display_value = "" if pd.isna(current_value) else str(current_value)
                escaped_display_value = html.escape(cell_display_value)

                td_content = escaped_display_value # Default is just escaped text

                # Check if the cell content looks like a URL
                if cell_display_value.startswith(("http://", "https://")):
                    # Create a standard link opening in a new tab
                    # Escape the URL itself for the href attribute
                    escaped_url = html.escape(cell_display_value, quote=True)
                    # Use the URL as the link text, or shorten it if desired
                    link_text = escaped_display_value # Or potentially shorten: cell_display_value.split('/')[-1]
                    td_content = f'<a href="{escaped_url}" target="_blank">{link_text}</a>'

                html_parts.append(f"<td{rowspan_attr}>{td_content}</td>")
        html_parts.append("</tr>")
    html_parts.append("</tbody></table>")

    # NO <script> block needed
    return "".join(html_parts)


# --- Streamlit App Layout ---
st.set_page_config(layout="wide")
st.title("Pharmaceutical Data Viewer")
st.markdown("Select a category and sheet to view data. Image URLs may be clickable.")

# No Image Modal section needed
# if st.session_state.clicked_image_uri: ... REMOVE THIS BLOCK ...

# --- Main Content Area ---
if not category_names:
    st.error("No valid category directories found. Check configuration.")
else:
    selected_category_name = st.selectbox(
        "Select Pharmaceutical Category:",
        options=category_names,
        index=None,
        placeholder="Choose a category..."
    )

    if selected_category_name:
        st.header(f"Category: {selected_category_name}")
        selected_dir_path = category_path_map[selected_category_name]

        sheets_data, filename_read = read_excel_sheets(selected_dir_path)

        if sheets_data is None:
            pass
        elif not sheets_data:
            st.warning(f"Excel file '{filename_read}' contains no sheets or data.")
        else:
            sheet_names = list(sheets_data.keys())
            selected_sheet_name = None

            if len(sheet_names) == 1:
                selected_sheet_name = sheet_names[0]
            else:
                # Persist sheet selection
                session_key_sheet = f'{selected_category_name}_sheet_selection'
                if session_key_sheet not in st.session_state:
                    st.session_state[session_key_sheet] = None
                st.markdown("---")
                selected_sheet_name = st.selectbox(
                    f"Select Sheet from '{filename_read}':",
                    options=[None] + sheet_names,
                    format_func=lambda x: "Choose a sheet..." if x is None else x,
                    key=session_key_sheet
                )

            if selected_sheet_name:
                st.subheader(f"Data for Sheet: {selected_sheet_name}")
                df_original = sheets_data.get(selected_sheet_name)

                if df_original is None:
                    st.error("Could not retrieve data for the selected sheet.")
                elif df_original.empty:
                     st.write("_Sheet appears to be empty._")
                else:
                    # Generate unique table ID
                    sanitized_category = re.sub(r'\W+', '_', selected_category_name)
                    sanitized_sheet = re.sub(r'\W+', '_', selected_sheet_name)
                    table_id = f"table_{sanitized_category}_{sanitized_sheet}"

                    # Generate HTML table string using the SIMPLIFIED function
                    html_content = dataframe_to_html_with_links(
                        df_original,
                        table_id=table_id
                    )

                    # Render using st.markdown or components.html
                    # st.markdown is fine now as there's no complex JS
                    st.markdown(html_content, unsafe_allow_html=True)

                    # REMOVE the "Show Clicked Image" button
                    # if st.button("Show Clicked Image", ...): ... REMOVE THIS BLOCK ...

            elif len(sheet_names) > 1 and not selected_sheet_name:
                st.info("Please select a sheet from the dropdown above.")

    elif not selected_category_name:
         st.info("Please select a category to load data.")


st.markdown("---")
st.caption("App displaying pharmaceutical data with external image links.")