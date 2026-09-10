import zipfile
import urllib.request
from pathlib import Path

def download_and_extract_geonames():
    url = "http://download.geonames.org/export/zip/IN.zip"
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(exist_ok=True)
    zip_path = data_dir / "IN.zip"
    txt_path = data_dir / "IN.txt"
    csv_path = data_dir / "full_pincodes.csv"

    print("Downloading IN.zip...")
    urllib.request.urlretrieve(url, zip_path)

    print("Extracting...")
    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extract("IN.txt", data_dir)

    print("Converting to CSV...")
    with open(txt_path, 'r', encoding='utf-8') as fin, open(csv_path, 'w', encoding='utf-8') as fout:
        fout.write("pincode,district,state,lat,lon\n")
        for line in fin:
            parts = line.split('\t')
            if len(parts) >= 11:
                pincode = parts[1].strip()
                state = parts[3].strip()
                district = parts[5].strip()
                lat = parts[9].strip()
                lon = parts[10].strip()
                fout.write(f"{pincode},{district},{state},{lat},{lon}\n")

    print(f"Done! Saved to {csv_path}")

if __name__ == "__main__":
    download_and_extract_geonames()
