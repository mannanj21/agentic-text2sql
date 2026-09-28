from pathlib import Path
from urllib.request import urlretrieve

PAGILA_RELEASE = "pagila-v3.1.0"
BASE_URL = f"https://raw.githubusercontent.com/devrimgunduz/pagila/{PAGILA_RELEASE}/"

def download_pagila() -> None:
    files = {
        "pagila-schema.sql": "01_pagila-schema.sql",
        "pagila-data.sql": "02_pagila-data.sql"
    }
    
    base_dir = Path(__file__).resolve().parent
    
    for remote_name, local_name in files.items():
        url = BASE_URL + remote_name
        local_path = base_dir / local_name
        print(f"Downloading {url} to {local_path}...")
        urlretrieve(url, local_path)
        print("Done.")

    readme_content = f"""# Pagila Seed Database

Vendored from [devrimgunduz/pagila](https://github.com/devrimgunduz/pagila)
release `{PAGILA_RELEASE}`. This release is compatible with the project's
PostgreSQL 16 demo container.

License: PostgreSQL License; see the upstream `LICENSE.txt`.

To refresh the vendored SQL, run `python seeds/pagila/download.py`. Do not
replace it with the upstream default branch: newer Pagila releases require
PostgreSQL 18+.
"""
    readme_path = base_dir / "README.md"
    with readme_path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(readme_content)
        
if __name__ == "__main__":
    download_pagila()
