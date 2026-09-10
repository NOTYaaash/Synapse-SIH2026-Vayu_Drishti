# Technical Architecture

## Data Flow Overview

**Vayu Drishti** handles real-time meteorological data ingestion, intelligent inference, and geospatial distribution in a fully automated pipeline.

1. **Ingestion Layer (MOSDAC/NOAA)**
   - The `SatelliteStreamRouter` continuously polls the ISRO MOSDAC API for real-time Thermal Infrared (TIR1) satellite frames (`.h5` format).
   - In the event of API downtime, the system fails over to a local historical archive of HDF5 data or GPM IMERG precipitation data, seamlessly providing testing and fallback capabilities via the `data_mode` flag (`live` vs. `archived`).

2. **ML Pipeline (PyTorch)**
   - The fetched array is passed to the `CyclonePipeline` singleton.
   - **Gatekeeper Module**: Validates the presence of cyclonic systems. If the scene is calm, the pipeline immediately returns a `no_cyclone_detected` state, preventing hallucination.
   - **Vortex Detector**: Extracts the precise geographic coordinates of the cyclone center.
   - **Intensity Classifier**: Predicts Maximum Sustained Wind (MSW), central pressure, and applies standard IMD classifications (e.g., Deep Depression, Severe Cyclonic Storm).
   - **Track Predictor**: Extrapolates the storm's trajectory strictly capped at T+24 hours.
   - **Rainfall Engine**: Evaluates expected rainfall distribution, outputting a spatial grid mapping predicted `mm` per cell.

3. **Geospatial Processing (GeoDjango)**
   - PostGIS / SpatiaLite maps the rainfall grid array to real-world latitude/longitude blocks.
   - Distances from the storm center and rainfall cells to the queried Indian district and pincode are calculated.
   - A Haversine algorithm dynamically locates the nearest government cyclone shelters, factoring in their capacity and state-level availability.

4. **Frontend Delivery (React + Leaflet)**
   - A React client queries the Django `/api/predictions/` and `/api/cyclones/` endpoints.
   - Leaflet renders the 24h timeline track, custom yellow vulnerability radii, and interactive shelter markers.
   - A responsive "Your Area" dashboard summarizes local risk severity (LOW, MODERATE, HIGH, SEVERE) to civilians in real-time.
