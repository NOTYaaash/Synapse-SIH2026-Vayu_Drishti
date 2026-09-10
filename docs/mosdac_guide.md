# MOSDAC Data Integration & Setup Guide

This guide details the data ingestion pipeline for Vayu Drishti, specifically focusing on how to configure the system to fetch live data from the Meteorological and Oceanographic Satellite Data Archival Centre (MOSDAC), ISRO, and how to seamlessly fall back to local historical archives.

## 1. Live Data Authentication (Credentials Setup)

Our data ingestion pipeline (driven by Celery and `SatelliteStreamRouter`) requires valid MOSDAC credentials to pull real-time satellite imagery and live standing data (such as AWS station updates). 

The system securely uses these credentials for API/SFTP requests. **If these credentials are missing, invalid, or if the API is unreachable, the system will not crash. It will gracefully fall back to local offline data.**

### Configuring your environment
To enable live fetching, you must create a `.env` file in the project root directory and add your MOSDAC credentials:

```env
MOSDAC_USERNAME=your_username_here
MOSDAC_PASSWORD=your_password_here
```

*Note: In addition to the username and password, the pipeline also supports `MOSDAC_API_KEY` for specific endpoints that require Bearer token authentication.*

---

## 2. Offline Archive Data Configuration (Fallback Mode)

For development, testing, or offline evaluations (e.g., during hackathon judging), the pipeline is designed to automatically process historical satellite data if the live fetch fails or is not configured.

### Setting up the local archive
To utilize the fallback mechanism, you must place your unzipped HDF5 (`.h5`) or NetCDF (`.nc`) archive files in a specific directory structure. 

The `predict_mosdac.py` script and the Celery workers automatically scan the `data/Order/Order/` directory when running in archive/fallback mode.

Your directory tree must look exactly like this once the data is correctly placed:

```text
Vayu_Drishti/
├── data/
│   └── Order/
│       └── Order/
│           ├── 3DIMG_01SEP2026_0000_L1B_STD.h5
│           ├── 3SIMG_25MAY2024_0600_L1C_SGP.h5
│           └── ... (other historical satellite files)
```

### Standing Data Fallback
Similarly, if live fetching for standing data fails, the `standing_data_loader.py` module will automatically read from the local CSV archive located at `data/cyclone_shelters.csv`.

---

## 3. Pipeline Routing Logic Overview

1. **Attempt Live Fetch**: The `MOSDACClient` attempts to contact `mosdac.gov.in/api/v1/latest` using the credentials from `.env`.
2. **Handle Exceptions**: If the request raises an HTTP 401 (Unauthorized) or a Timeout, the exception is caught, and a warning is logged: 
   `"Live MOSDAC credentials missing. Falling back to local archive data..."`
3. **Redirect to Local Storage**: 
   - Satellite frames drop back to the `.h5` files in `data/Order/Order`.
   - Standing data drops back to `data/cyclone_shelters.csv`.
4. **Continuous Inference**: The ML engine processes the offline data exactly as it would the live stream, ensuring continuous end-to-end functionality.

---

## 4. Supplementary Data (NetCDF)
For derived products like GPM IMERG rainfall or Sea Surface Temperature (SST), the pipeline utilizes a dedicated `MOSDACNetCDFReader`. These files should be placed in `data/gpm_imerg/` or `data/sst/` respectively. The pipeline uses the same graceful fallback logic to find these files if the live API is unavailable.
