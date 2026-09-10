# 🌀 Vayu Drishti

## 1. Project Information
- **Title**: Vayu Drishti
- **Theme**: Disaster Management
- **Category**: Software
- **Problem Statement**: To develop an Artificial Intelligence (AI) / Machine Learning (ML) based system for identification, classification, and prediction of different tropical cyclone patterns using multi-source satellite data.
- **Problem Statement ID**: 26070
- **Team Name**: Synapse

## 2. Problem Statement
The current standard for cyclone tracking relies on heavily generalized forecasts that lack pinpoint accuracy for hyper-local impact zones. Affected citizens and local disaster response teams struggle with delayed actionable intelligence, coarse regional warnings instead of pincode-level risk mapping, and a lack of dynamic routing to the nearest secure government shelters. Additionally, integrating live multi-source satellite data streams resiliently is challenging when network conditions are poor.

## 3. Proposed Solution
**Vayu Drishti** is an end-to-end cyclone tracking and disaster management platform. We automate the ingestion of live optical/infrared satellite imagery and fuse it with environmental parameters. This data drives a 4-model PyTorch ML ensemble (Vortex Detection, Intensity Classification, Track Prediction, and Rainfall U-Net). The output provides hyper-local rainfall forecasting, dynamic risk mapping, and nearest-shelter routing for vulnerable pincodes.

## 4. Key Features
- **Strict 24-Hour Forecast Capping**: Ensures high-fidelity short-term track and intensity accuracy without long-term divergence hallucination.
- **Dynamic 4-Model ML Pipeline**: Extracts the eye, classifies intensity (MSW/pressure), predicts the track, and generates geospatial rainfall matrices.
- **Live NOAA Wind Flow & MOSDAC Integration**: Connects directly to ISRO/NOAA data streams, rendering live environmental physics on the map.
- **Anti-Hallucination Safe-State Fallback**: Safely defaults to a "No Active Cyclone Threat" state during calm weather.
- **Geospatial Nearest Shelter Routing**: Automatically filters by state and calculates Haversine distances to direct civilians to the closest secure shelters.

## 5. Technology Stack
- **Frontend**: React, Vite, Leaflet, GeoJSON (with a modern glassmorphism UI)
- **Backend**: Python 3, Django REST Framework, Celery, Redis
- **Database**: GeoDjango / SpatiaLite / SQLite
- **Machine Learning**: PyTorch (RainfallUNet, TrackPredictor), NumPy, Pandas
- **Geospatial & Data**: GDAL, h5py, NetCDF4, ISRO MOSDAC, NOAA GFS

## 6. Architecture

See [docs/architecture.md](docs/architecture.md) for full details.

```text
[ Live Satellite Data ] --> ( MOSDAC API / Local HDF5 Archives )
                                      |
                                      v
[ Automated Celery Worker ] -> [ SatelliteStreamRouter ]
                                      |
                                      v
[ AI Intelligence Engine ] (PyTorch)
   1. Vortex Detection (Locate storm eye)
   2. Intensity Classification (MSW, category, pressure)
   3. Track Prediction (Next 24h coordinates)
   4. Rainfall Engine (U-Net spatial grid)
                                      |
                                      v
[ Geo-Spatial Risk Engine ] (GeoDjango)
   - Map 24h tracks and rainfall to Indian Pincodes
   - Calculate distances to local government shelters
                                      |
                                      v
[ REST API endpoints ]
                                      |
                                      v
[ Vayu Drishti Frontend ] (React + Leaflet)
   - Renders live weather map, wind particles
   - Displays shelter table and district rainfall projections
```

## 7. Repository Structure
- **`apps/`**: Django REST API applications (`predictions`, `cyclones`, etc.) serving model inference and data.
- **`config/`**: Django root configuration and settings.
- **`ml_engine/`**: Core Machine Learning intelligence (U-Net spatial grids, Intensity Classifiers, and unified `CyclonePipeline`).
- **`frontend/`**: Vite + React client.
- **`tests/`**: Pytest suite ensuring the reliability of the ML inference pipelines.
- **`docs/`**: Detailed architectural and technical documentation.
- **`submission/`**: Links to our demo video and final SIH presentation.
- **`assets/screenshots/`**: Visual assets of the user interface and prototype.

## 8. Final Presentation
[Link to Presentation](./submission/PRESENTATION.md)

## 9. Demo Video
[Link to Demo Video](./submission/DEMO.md)

## 10. Screenshots / Prototype Photos
Please see the `assets/screenshots/` directory for visual demonstrations of the Live Map and the hyper-local "Your Area" risk dashboard.

## 11. Installation
1. Clone the repository: `git clone <repo-url>`
2. Setup the backend:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Install GDAL (Windows):
   Ensure `fetch_gdal.py` or equivalent setup script is run to download the SpatiaLite/PROJ libraries required by GeoDjango.
4. Setup the frontend:
   ```bash
   cd frontend
   npm install
   ```

### Setting up Datasets

Refer to [docs/mosdac_guide.md](docs/mosdac_guide.md) for information regarding the setup of MOSDAC client.

The global cyclone dataset (IBTrACS) is critical for our ML pipeline (specifically the IntensityClassifier) and historical data analysis. Due to GitHub's 100 MB file size limit, this dataset is excluded from version control and must be downloaded manually.

Please download the **CSV** format for version **v04r01** directly from the official NOAA NCEI IBTrACS archive.

The downloaded file must be placed exactly at this path so the backend scripts can find it:

```text
Vayu_Drishti/
├── data/
│   └── ibtracs.ALL.list.v04r01.csv
```

**Quick Download Command:**
You can use the following command in your terminal to fetch the file directly into your `data/` folder:

```bash
curl -o data/ibtracs.ALL.list.v04r01.csv https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/csv/ibtracs.ALL.list.v04r01.csv
```

## 12. Run
This project requires running the Django backend and Vite frontend simultaneously.
1. Start the Django API (Window 1):
   ```bash
   python manage.py runserver
   ```
2. Start the Vite Frontend (Window 2):
   ```bash
   cd frontend
   npm run dev
   ```
3. Start the Celery Worker (Optional/Window 3):
   ```bash
   celery -A config worker --loglevel=info
   ```

## 13. Future Scope
- **Extended Integration**: Add live flood-inundation mapping by linking rainfall grids with local topological DEM data.
- **Multilingual Support**: Implement localized translations for advisory texts so rural communities receive warnings in native regional languages.
- **Edge Deployment**: Optimize the PyTorch ONNX models to run efficiently on low-power edge nodes deployed in coastal regions.
