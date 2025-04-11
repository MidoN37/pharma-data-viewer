import os
import csv
from pathlib import Path
import unicodedata
import re # To sanitize category name for key

# --- !!! IMPORTANT: CONFIGURE THESE VARIABLES !!! ---

GITHUB_USERNAME = "MidoN37"
REPO_NAME = "pharma-data-viewer"
BRANCH_NAME = "master" # Or "main"
PROJECT_ROOT = Path("/Users/user/Downloads/Python scripts")
IMAGE_BASE_DIR_RELATIVE = Path("assets/images")
# Output CSV filename
OUTPUT_CSV_FILE = "github_image_urls_CATEGORIZED.csv" # New name

# --- End of Configuration ---

# --- Script Logic ---

def generate_raw_urls(base_url_prefix, image_dir_full_path, project_root_path):
    """
    Walks through image directories, determines category,
    and generates raw GitHub URLs with composite keys.
    """
    image_data = []
    image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')

    if not image_dir_full_path.is_dir():
        print(f"Error: Image directory not found at: {image_dir_full_path}")
        return None

    print(f"Scanning for images in: {image_dir_full_path}...")

    for root, _, files in os.walk(image_dir_full_path):
        current_dir_path = Path(root)
        # --- Determine Category from Path ---
        try:
            # Get path relative to the *base image directory*
            relative_to_images = current_dir_path.relative_to(image_dir_full_path)
            # The first part of this relative path should be the category
            category_name = relative_to_images.parts[0] if relative_to_images.parts else "unknown"
            # Sanitize category name for use in keys (lowercase, replace non-alphanum)
            category_key = re.sub(r'\W+', '_', category_name.lower())
        except ValueError:
            # Happens if root is the image_dir_full_path itself or outside
            category_name = "root_or_unknown"
            category_key = "root_or_unknown"
            if current_dir_path != image_dir_full_path:
                 print(f"Warning: Could not determine category for path {current_dir_path}")


        for filename in files:
            if filename.lower().endswith(image_extensions) and not filename.startswith('.'):
                full_local_path = current_dir_path / filename
                try:
                    relative_path_obj = full_local_path.relative_to(project_root_path)
                    relative_path_str = relative_path_obj.as_posix()
                    normalized_path_str = unicodedata.normalize('NFC', relative_path_str)
                    raw_url = f"{base_url_prefix}{normalized_path_str}"

                    # --- Create Composite Key ---
                    normalized_filename = Path(filename).stem.lower()
                    composite_key = f"{category_key}-{normalized_filename}"

                    image_data.append({
                        'composite_key': composite_key, # ADDED
                        'category': category_name,      # ADDED for info
                        'filename': filename,
                        'relative_path': normalized_path_str,
                        'raw_url': raw_url
                    })
                except ValueError:
                     print(f"Warning: Could not determine relative path for {full_local_path}.")
                except Exception as e:
                     print(f"Error processing file {full_local_path}: {e}")

    print(f"Found {len(image_data)} image files.")
    return image_data

def write_to_csv(data, output_filename):
    """Writes the collected image data to a CSV file."""
    if not data:
        print("No image data to write.")
        return
    try:
        print(f"Writing data to {output_filename}...")
        output_path = PROJECT_ROOT / output_filename # Ensure path is correct
        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = data[0].keys() # Dynamically get headers from first dict
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        print(f"Successfully wrote CSV file: {output_path}")
    except IOError as e:
        print(f"Error writing CSV file {output_filename}: {e}")
    except Exception as e:
         print(f"An unexpected error occurred during CSV writing: {e}")

# --- Main Execution ---
if __name__ == "__main__":
    base_raw_url = f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{REPO_NAME}/{BRANCH_NAME}/"
    image_dir_absolute = PROJECT_ROOT / IMAGE_BASE_DIR_RELATIVE
    collected_data = generate_raw_urls(base_raw_url, image_dir_absolute, PROJECT_ROOT)
    if collected_data:
        write_to_csv(collected_data, OUTPUT_CSV_FILE)
    else:
        print("Script finished with errors or no images found.")