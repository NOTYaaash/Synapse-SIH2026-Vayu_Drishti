# Vayu Drishti - frontend

React + Vite frontend for the cyclone forecast and public advisory platform.

## Run

```bash
cd frontend
npm install
npm run dev
```

## Routes

| Route | Surface |
| --- | --- |
| `/` | IMD metrics console (landing) |
| `/map` | Full-screen live storm map |
| `/area` | Civilian pincode lookup |

## Structure

```
src/
  theme.css          theme tokens (light + dark), resets, motion
  data.js            model payloads and IMD classification helpers
  components/Header.jsx
  pages/Metrics.jsx  warnings panel, KPIs, map preview, bulletin, timeline, scale
  pages/StormMap.jsx Leaflet map, timeline scrubber, wind flow field, layers
  pages/Civilian.jsx pincode result, shelters, district forecast
```

## Wiring the model

`src/data.js` holds the four payloads as static objects. Replace each export with a
fetch against the model API; field names match the documented contract, so no
component changes are needed. Placeholders that must be replaced before release:
population affected, bulletin issue time, and the cloud/wind texture layers
(which need real grids clipped to water geometry).

## Notes

- Basemap tiles: OpenStreetMap (attribution required) and Esri World Imagery.
  Confirm a licensed imagery source before production.
- Theme choice persists in `localStorage` under `vd-theme`.
