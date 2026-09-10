import re
import time
import argparse
import urllib.request
import urllib.error
from http.cookiejar import CookieJar
from datetime import datetime, timedelta
from pathlib import Path

URL_LIST_PATH = Path(__file__).parent.parent.parent / "data" / "subset_GPM_3IMERGHH_07_20260906_085336_.txt"
IBTRACS_PATH  = Path(__file__).parent.parent.parent / "data" / "ibtracs.ALL.list.v04r01.csv"
OUTPUT_DIR    = Path(__file__).parent.parent.parent / "data" / "gpm_imerg"
NASA_HOST     = "urs.earthdata.nasa.gov"

NIO_BASINS = {"NI", "BB", "AS"}

URL_TIMESTAMP_RE = re.compile(r'(\d{8})-S(\d{6})-E(\d{6})')


def _load_nio_cyclone_windows(ibtracs_path: Path, pad_hours: int = 6):
    windows = []
    with open(ibtracs_path, "r", encoding="utf-8", errors="ignore") as f:
        for i, line in enumerate(f):
            if i < 2:
                continue
            parts = line.split(",")
            if len(parts) < 12:
                continue
            basin = parts[3].strip()
            if basin not in NIO_BASINS:
                continue
            iso_time = parts[6].strip()
            if not iso_time or len(iso_time) < 16:
                continue
            try:
                dt = datetime.strptime(iso_time[:16], "%Y-%m-%d %H:%M")
                windows.append((dt - timedelta(hours=pad_hours), dt + timedelta(hours=pad_hours)))
            except ValueError:
                continue
    return windows


def _url_to_datetime(url: str):
    m = URL_TIMESTAMP_RE.search(url)
    if not m:
        return None
    date_str, start_str = m.group(1), m.group(2)
    try:
        return datetime.strptime(date_str + start_str, "%Y%m%d%H%M%S")
    except ValueError:
        return None


def _in_any_window(dt: datetime, windows):
    for lo, hi in windows:
        if lo <= dt <= hi:
            return True
    return False


def _setup_netrc(username: str, password: str):
    netrc_path = Path.home() / ".netrc"
    entry = f"machine {NASA_HOST} login {username} password {password}\n"
    if netrc_path.exists():
        content = netrc_path.read_text()
        if NASA_HOST in content:
            print(f".netrc already has an entry for {NASA_HOST}.")
            return
        netrc_path.write_text(content + entry)
    else:
        netrc_path.write_text(entry)
        netrc_path.chmod(0o600)
    print(f"Saved NASA Earthdata credentials to {netrc_path}")


def _download_url(url: str, dest: Path, username: str, password: str):
    password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    # NASA redirects to urs.earthdata.nasa.gov, so we need to auth there too
    password_mgr.add_password(None, "https://urs.earthdata.nasa.gov", username, password)
    password_mgr.add_password(None, url, username, password)
    
    # Earthdata requires cookies to survive the redirect back to the data server
    cookie_jar = CookieJar()
    
    auth_handler = urllib.request.HTTPBasicAuthHandler(password_mgr)
    cookie_handler = urllib.request.HTTPCookieProcessor(cookie_jar)
    
    opener = urllib.request.build_opener(auth_handler, cookie_handler)
    urllib.request.install_opener(opener)
    
    try:
        urllib.request.urlretrieve(url, dest)
        return True
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} for {dest.name} — skipping.")
        return False
    except Exception as e:
        print(f"  Error downloading {dest.name}: {e}")
        return False


def run(username: str, password: str, limit: int = 0, dry_run: bool = False):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Loading IBTrACS NIO cyclone windows from {IBTRACS_PATH.name}...")
    windows = _load_nio_cyclone_windows(IBTRACS_PATH)
    print(f"  Found {len(windows)} cyclone observation windows.")

    if not dry_run:
        _setup_netrc(username, password)

    print(f"Reading URL list from {URL_LIST_PATH.name}...")
    with open(URL_LIST_PATH, "r", encoding="utf-8") as f:
        all_urls = [line.strip() for line in f if line.strip().startswith("http")]
    print(f"  Total URLs in list: {len(all_urls):,}")

    matched, downloaded, skipped = 0, 0, 0
    for url in all_urls:
        if limit and downloaded >= limit:
            break
        dt = _url_to_datetime(url)
        if dt is None:
            continue
        if not _in_any_window(dt, windows):
            continue
        matched += 1

        fname_m = re.search(r'LABEL=([^&]+)', url)
        fname = fname_m.group(1) if fname_m else f"gpm_{dt.strftime('%Y%m%d_%H%M%S')}.nc4"
        fname = fname.replace(".SUB.nc4", ".nc4")
        dest = OUTPUT_DIR / fname

        if dest.exists():
            skipped += 1
            continue

        if dry_run:
            print(f"  [DRY RUN] Would download: {fname} ({dt})")
            downloaded += 1
            continue

        print(f"  Downloading {fname} ({matched} matched)...", end="", flush=True)
        ok = _download_url(url, dest, username, password)
        if ok:
            downloaded += 1
            print(" ✓")
        time.sleep(0.2)

    print(f"\nDone. Matched: {matched} | Downloaded: {downloaded} | Skipped (exists): {skipped}")
    print(f"Files saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download NASA GPM IMERG files for NIO cyclone periods.")
    parser.add_argument("--username", required=True, help="NASA Earthdata username")
    parser.add_argument("--password", required=True, help="NASA Earthdata password")
    parser.add_argument("--limit",    type=int, default=0,   help="Max files to download (0 = no limit)")
    parser.add_argument("--dry-run",  action="store_true",   help="List matched files without downloading")
    args = parser.parse_args()
    run(args.username, args.password, args.limit, args.dry_run)
