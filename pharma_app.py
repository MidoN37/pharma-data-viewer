import streamlit as st
import pandas as pd
import os
import numpy as np
import re
import html # For escaping HTML content
import streamlit.components.v1 as components
from pathlib import Path # For easier path handling
import unicodedata # Keep for normalization if needed elsewhere

# --- Page Config (MUST be the first Streamlit command) ---
st.set_page_config(layout="wide")

# --- Configuration ---
BASE_DIR = "/Users/user/Desktop/Pharm"
CATEGORY_SUBDIRS = [
    "Antibiotiques", "Comprimés", "Comprimes antalgiques",
    "Cremes - Pommades", "Gouttes", "Injections", "Ovules vaginaux",
    "Pulvérisations", "Sachets", "Sirop", "Suppositoires"
]
# Sheets/Categories where URLs are expected directly in cells
SPECIAL_HANDLING_CATEGORIES = ["Antibiotiques", "Sachets", "Sirops", "Suppositoires"]

# --- Populate Category Paths ---
category_path_map = {} # Initialize dictionary
for sub_dir in CATEGORY_SUBDIRS:
    full_path = os.path.join(BASE_DIR, sub_dir)
    if os.path.isdir(full_path):
        category_path_map[sub_dir] = full_path
    else:
        print(f"Warning: Directory not found and skipped: {full_path}")
# Get category names AFTER populating the map
category_names = list(category_path_map.keys())

# --- Load Image URL Mapping from CSV ---
project_root = Path("/Users/user/Downloads/Python scripts") # Or derive from __file__ if structure allows
csv_path = project_root / "github_image_urls_CATEGORIZED.csv" # Use the categorized CSV
# Map will hold { 'categorykey-filenamekey': url }
image_url_map = {}

@st.cache_data # Cache the loaded map for performance
def load_url_map(path):
    """Loads the CATEGORIZED CSV and creates a composite_key -> URL mapping."""
    url_map = {}
    try:
        if not path.exists():
            st.error(f"Image URL CSV not found at: {path}")
            return {}
        df_map = pd.read_csv(path)
        if 'composite_key' not in df_map.columns or 'raw_url' not in df_map.columns:
            st.error("CATEGORIZED CSV must contain 'composite_key' and 'raw_url' columns.")
            return {}

        for _, row in df_map.iterrows():
            try:
                 comp_key = str(row['composite_key']) if pd.notna(row['composite_key']) else None
                 raw_url = str(row['raw_url']) if pd.notna(row['raw_url']) else None
                 if comp_key and raw_url:
                     url_map[comp_key] = raw_url
            except Exception as e:
                 print(f"Skipping row in CSV due to error processing key/url: {row.get('composite_key','N/A')}, {e}")

        print(f"Loaded {len(url_map)} image URLs using composite keys from CSV.")
        return url_map
    except Exception as e:
        st.error(f"Failed to load or process CATEGORIZED Image URL CSV: {e}")
        return {}

# Load the map (this call is now safely AFTER set_page_config)
image_url_map = load_url_map(csv_path)


# --- Function to Read All Sheets from Excel ---
def read_excel_sheets(directory_path):
    """Reads all sheets from the first found Excel file in a directory."""
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


# --- REVISED HTML Function - Added Debugging ---
def dataframe_to_html_universal_links(df, table_id="display-table", current_category_name="", url_map=None, name_col_index=0):
    """
    Converts DataFrame to HTML, handling merges and styling.
    Conditionally creates clickable links for images:
    - If url_map provided (normal sheets): Links medication name (col index name_col_index)
      using a composite key lookup ('category-name').
    - Also turns cells containing raw http/https URLs (in any column) into clickable links.
    Links trigger a JS popup for external URLs.
    """
    if df is None or df.empty:
        return "<p>Table is empty.</p>"

    df_processed = df.copy()
    df_processed.replace({'': np.nan}, inplace=True)

    # --- Pre-calculate rowspans ---
    rowspans = pd.DataFrame(1, index=df_processed.index, columns=df_processed.columns)
    merge_col_indices = [1, 2] # Example: Adjust if merging happens in other cols

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

    # --- Generate HTML Structure ---
    html_parts = []
    # Add CSS styles
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

    # Body generation (MODIFIED Link Logic with DEBUG)
    html_parts.append("<tbody>")
    category_key = re.sub(r'\W+', '_', current_category_name.lower())
    print(f"--- Processing Body for Category Key: {category_key} ---") # DEBUG: Show category key once

    # ---- DEBUG: Print first few keys from the actual map being used ----
    if url_map:
        print(f"DEBUG: First 5 keys in url_map: {list(url_map.keys())[:5]}")
    else:
        print("DEBUG: url_map is None for this sheet.")
    # ---- END DEBUG ----

    # Iterate through DataFrame rows using index
    for r_idx_abs in df_processed.index:
        html_parts.append("<tr>")
        # Iterate through columns
        for c_idx, col_name in enumerate(df_processed.columns):
            # Get pre-calculated span value using .loc
            span = rowspans.loc[r_idx_abs, rowspans.columns[c_idx]]
            if span == 0: continue # Skip rendering cell (covered by rowspan)
            else:
                rowspan_attr = f' rowspan="{span}"' if span > 1 else ""
                # Get cell value using .loc
                current_value = df_processed.loc[r_idx_abs, col_name]
                # Use .strip() to remove leading/trailing whitespace from Excel cell value
                cell_display_value = "" if pd.isna(current_value) else str(current_value).strip()
                # Escape cell content for HTML safety
                escaped_display_value = html.escape(cell_display_value)

                td_content = escaped_display_value # Default content is just escaped text
                link_url = None # URL to link to (if any)
                link_text = escaped_display_value # Text to display in the link (if any)
                filename_for_popup = "image" # Default popup window title

                # --- Link Logic ---
                # Condition 1: Use URL map based on category and name column index?
                if url_map and c_idx == name_col_index and cell_display_value:
                    # --- DEBUG ---
                    print(f"\n-- Checking Cell --")
                    print(f"  Raw Value (stripped): '{cell_display_value}'")
                    # --- END DEBUG ---
                    try:
                        # Use basic string processing for normalization, avoid Path if causing issues
                        name_part = cell_display_value.lower()
                        # Optional Robustness: Remove common extensions if user accidentally includes them in Excel?
                        # for ext in ['.jpg', '.jpeg', '.png']:
                        #    if name_part.endswith(ext):
                        #        name_part = name_part[:-len(ext)]
                        #        break
                        normalized_name_lookup = name_part # Use simplified name

                        # Create composite key using CURRENT category key
                        composite_key_lookup = f"{category_key}-{normalized_name_lookup}"
                        # --- DEBUG ---
                        print(f"  Category Key: '{category_key}'")
                        print(f"  Norm. Name  : '{normalized_name_lookup}'")
                        print(f"  Lookup Key  : '{composite_key_lookup}'")
                        # --- END DEBUG ---

                        # Check if this composite key exists in the loaded map
                        if composite_key_lookup in url_map:
                            # --- DEBUG ---
                            print(f"  FOUND in url_map!")
                            # --- END DEBUG ---
                            link_url = url_map[composite_key_lookup]
                            link_text = escaped_display_value # Keep original name as text
                            # Try to extract filename from the found URL for the popup title
                            try: filename_for_popup = link_url.split('/')[-1].split('?')[0]
                            except: pass # Keep default if extraction fails
                        else:
                            # --- DEBUG ---
                            print(f"  NOT FOUND in url_map!")
                            # --- END DEBUG ---
                    except Exception as e:
                        print(f"  ERROR during key creation/lookup for '{cell_display_value}': {e}")


                # Condition 2: Is the cell content itself a URL? (Handles special sheets)
                # Only check this if a link wasn't already found by the map lookup
                elif link_url is None and cell_display_value.startswith(("http://", "https://")):
                     link_url = cell_display_value # The URL is the content itself
                     try:
                         # Extract filename for display text and popup title
                         filename_for_popup = link_url.split('/')[-1].split('?')[0]
                         link_text = html.escape(filename_for_popup) # Use filename as link text
                     except:
                         link_text = "View Image" # Fallback link text if filename extraction fails

                # --- Generate <a> tag if a URL was found by either method ---
                if link_url:
                    # Escape URL and filename for HTML attributes
                    escaped_url = html.escape(link_url, quote=True)
                    escaped_filename = html.escape(filename_for_popup, quote=True)
                    # Create the link with class and data attributes for JS popup
                    td_content = (
                        f'<a href="#" class="external-image-popup" '
                        f'data-url="{escaped_url}" data-filename="{escaped_filename}">'
                        f'{link_text}</a>' # Display name or filename as link text
                    )
                # --- End Link Logic ---

                # Append the table data cell HTML
                html_parts.append(f"<td{rowspan_attr}>{td_content}</td>")
        html_parts.append("</tr>") # End of table row
    html_parts.append("</tbody></table>") # End of table body and table

    # Return the complete HTML string for the table (no script block here)
    return "".join(html_parts)

# --- JavaScript block for the popup (to be injected via components.html) ---
javascript_popup_script = """
<script>
(function() {
    // Define the function to handle link clicks
    function openExternalPopup(event) {
        event.preventDefault(); // Stop page from jumping to '#'
        const link = event.currentTarget; // The <a> element that was clicked
        const imageUrl = link.getAttribute('data-url'); // Get URL from data attribute
        const filename = link.getAttribute('data-filename') || 'image'; // Get filename for popup title

        if (imageUrl) {
            console.log(`Opening popup for ${filename} at ${imageUrl}`); // Debugging
            const popupWidth = 800; const popupHeight = 600; // Popup dimensions
            try {
                // Open the external image URL in a new popup window
                window.open(imageUrl, filename, `width=${popupWidth},height=${popupHeight},scrollbars=yes,resizable=yes`);
            } catch (e) {
                // Handle potential errors (like popup blockers)
                console.error('Error opening popup:', e);
                alert('Could not open image popup. Please check browser popup blocker settings. Error: ' + e);
            }
        } else {
            // Handle case where data-url attribute was missing
            console.error('Could not find image URL in data-url attribute for link:', link);
            alert('Could not retrieve image URL for this link.');
        }
    }

    // Use a timeout to ensure the table elements are likely in the DOM
    // Adjust timeout if needed, 500ms is usually safe
    setTimeout(function() {
        // Select all links with the specific class
        const links = document.querySelectorAll('a.external-image-popup');
        console.log('Found ' + links.length + ' external image links to attach listeners.'); // Debugging

        // Attach the click event listener to each found link
        links.forEach(link => {
            // Simple check to avoid attaching multiple listeners if the script runs again
            // in the same component instance (though usually components rerender fully)
            if (!link.dataset.listenerAttached) {
                 link.addEventListener('click', openExternalPopup);
                 link.dataset.listenerAttached = 'true'; // Mark that listener has been attached
            }
        });
     }, 500); // Wait 500ms

})(); // End of IIFE
</script>
"""


# --- Streamlit App Layout ---
st.title("Pharmaceutical Data Viewer")
st.markdown("Select a category and sheet to view data. Click medication names or image links for popup.")

# Main application logic
if not category_names:
    st.error("No valid category directories found. Check configuration.")
else:
    # Dropdown for selecting the main category
    selected_category_name = st.selectbox(
        "Select Pharmaceutical Category:",
        options=category_names,
        index=None, # Default to no selection
        placeholder="Choose a category..."
        # key='category_select' # Optional: Persist category selection
    )

    # Only proceed if a category is selected
    if selected_category_name:
        st.header(f"Category: {selected_category_name}")
        # Get the directory path for the selected category
        selected_dir_path = category_path_map[selected_category_name]

        # Read all sheets from the Excel file in that directory
        sheets_data, filename_read = read_excel_sheets(selected_dir_path)

        # Handle cases where reading failed or file was empty
        if sheets_data is None:
            pass # Error was displayed in the read function
        elif not sheets_data:
            st.warning(f"Excel file '{filename_read}' contains no sheets or data.")
        else:
            # Get sheet names for selection
            sheet_names = list(sheets_data.keys())
            selected_sheet_name = None

            # Handle sheet selection (auto-select if only one, dropdown if multiple)
            if len(sheet_names) == 1:
                selected_sheet_name = sheet_names[0]
            else:
                # Use session state to remember sheet selection across reruns
                session_key_sheet = f'{selected_category_name}_sheet_selection'
                if session_key_sheet not in st.session_state:
                    st.session_state[session_key_sheet] = None # Initialize if not present
                st.markdown("---") # Visual separator
                selected_sheet_name = st.selectbox(
                    f"Select Sheet from '{filename_read}':",
                    options=[None] + sheet_names, # Allow 'None' for placeholder behavior
                    format_func=lambda x: "Choose a sheet..." if x is None else x,
                    key=session_key_sheet # Use the dynamic key to store state
                )

            # If a sheet is selected, display its content
            if selected_sheet_name:
                st.subheader(f"Data for Sheet: {selected_sheet_name}")
                df_original = sheets_data.get(selected_sheet_name)

                if df_original is None:
                    st.error("Could not retrieve data for the selected sheet.")
                elif df_original.empty:
                     st.write("_Sheet appears to be empty._")
                else:
                    # Generate a unique table ID based on category and sheet name
                    # Further sanitize ID by replacing any non-alphanumeric/underscore
                    sanitized_category = re.sub(r'[^a-zA-Z0-9_]+', '_', selected_category_name)
                    sanitized_sheet = re.sub(r'[^a-zA-Z0-9_]+', '_', selected_sheet_name)
                    table_id = f"table_{sanitized_category}_{sanitized_sheet}"

                    # Determine if the URL map should be used for linking names
                    use_url_map = selected_category_name not in SPECIAL_HANDLING_CATEGORIES
                    # Pass the loaded map only if needed for this category
                    current_url_map = image_url_map if use_url_map else None
                    # Assume the medication name is in the first column (index 0)
                    name_column_to_link = 0

                    # Generate the HTML table string using the universal function
                    # Pass the current category name for composite key generation
                    html_table_content = dataframe_to_html_universal_links(
                        df_original,
                        table_id=table_id,
                        current_category_name=selected_category_name,
                        url_map=current_url_map,
                        name_col_index=name_column_to_link
                    )

                    # Combine the generated table HTML with the JavaScript for popups
                    full_html_content = html_table_content + javascript_popup_script

                    # Render the combined HTML and script using components.html
                    components.html(full_html_content, height=800, scrolling=True) # Adjust height as needed

            # Prompt user if multiple sheets exist but none selected
            elif len(sheet_names) > 1 and not selected_sheet_name:
                st.info("Please select a sheet from the dropdown above.")

    # Prompt user if no category is selected initially
    elif not selected_category_name:
         st.info("Please select a category to load data.")


# Footer
st.markdown("---")
st.caption("App displaying pharmaceutical data with external image popups.")