import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import Header from '../components/Header.jsx';
import WindyParticleLayer from '../components/WindyParticleLayer.jsx';
import { imdCategory, buildConePolygons } from '../utils.js';
import { fetchBulletin, fetchShelters, fetchAffectedArea, fetchWindData } from '../api.js';
import { LocationContext } from '../App.jsx';


const PALETTES = {
  standard: ['#F2C230', '#E4761B', '#C62828'],
  contrast: ['#FFD400', '#FF6A00', '#7F0000'],
  cvd: ['#E69F00', '#D55E00', '#882255']
};

const DEFAULT_CENTER = [16.6, 85.4];
const DEFAULT_ZOOM = 5;

function buildNodes(bulletin) {
  if (!bulletin || bulletin.status === 'no_cyclone_detected' || typeof bulletin.center_lat !== 'number' || !Array.isArray(bulletin.forecast_timeline)) {
    return [];
  }
  return [
    { h: 0, lat: bulletin.center_lat, lon: bulletin.center_lon, msw: bulletin.msw, pres: bulletin.central_pressure_hpa, rain: bulletin.max_rainfall_mm ?? 0 },
    ...bulletin.forecast_timeline.map((f) => ({
      h: f.forecast_hour, lat: f.lat, lon: f.lon, msw: f.msw_kt,
      pres: f.central_pressure_hpa ?? 990,
      rain: f.max_rainfall_mm
    }))
  ];
}

function interpolate(nodes, hour) {
  if (hour <= 0) return { ...nodes[0], h: 0 };
  for (let i = 1; i < nodes.length; i++) {
    const a = nodes[i - 1], b = nodes[i];
    if (hour <= b.h) {
      const t = (hour - a.h) / (b.h - a.h);
      return {
        h: hour,
        lat: a.lat + (b.lat - a.lat) * t,
        lon: a.lon + (b.lon - a.lon) * t,
        msw: a.msw + (b.msw - a.msw) * t,
        pres: a.pres + (b.pres - a.pres) * t,
        rain: a.rain + (b.rain - a.rain) * t
      };
    }
  }
  return nodes[nodes.length - 1];
}

// Error Boundary to catch unexpected render crashes
class MapErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { hasError: false, error: null }; }
  static getDerivedStateFromError(error) { return { hasError: true, error }; }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', color: 'var(--muted)', font: '500 14px/1.6 var(--body)' }}>
          <div style={{ padding: '24px 32px', background: 'var(--glass-bg)', backdropFilter: 'blur(12px)', borderRadius: 'var(--radius)', border: '1px solid var(--line)', textAlign: 'center', maxWidth: 480 }}>
            <h3 style={{ margin: '0 0 8px', fontSize: 18 }}>⚠️ Map Render Error</h3>
            <p style={{ margin: '0 0 16px', fontSize: 13, color: 'var(--muted)' }}>{String(this.state.error?.message ?? 'Unknown error')}</p>
            <button onClick={() => window.location.reload()} style={{ padding: '10px 20px', borderRadius: 'var(--radius-xs)', background: 'var(--ink)', color: 'var(--surface)', border: 'none', cursor: 'pointer', font: '600 13px/1 var(--body)' }}>Reload</button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

function StormMapInner() {
  const { pincode } = React.useContext(LocationContext);
  const hostRef = useRef(null);
  const mapRef = useRef(null);
  const layersRef = useRef({});
  const hourRef = useRef(0);
  const nodesRef = useRef([]);

  const isEmbedded = typeof window !== 'undefined' && window.self !== window.top;
  const [tweaks, setTweaks] = useState({ palette: 'standard', heat: 100, track: 3, windArrows: 8, windParticles: 1400 });
  const reducedMotion = typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const [layers, setLayers] = useState({ sat: true, rain: true, wind: !reducedMotion, track: true, shelters: true });
  const [bulletin, setBulletin] = useState(null);
  const [noCyclone, setNoCyclone] = useState(false);
  const [shelterList, setShelterList] = useState([]);
  const [affectedArea, setAffectedArea] = useState(null);
  const [loading, setLoading] = useState(true);
  const [windData, setWindData] = useState(null);
  const [playHour, setPlayHour] = useState(0);
  const [playing, setPlaying] = useState(false);
  const playRef = useRef(null);
  const MAX_HOURS = 24;

  function fetchAll() {
    Promise.all([
      fetchBulletin(),
      fetchShelters(),
      pincode?.length === 6 ? fetchAffectedArea({ pincode }).catch(() => null) : Promise.resolve(null),
    ]).then(([bull, sh, area]) => {
      const nodes = buildNodes(bull);
      if (bull?.status === 'no_cyclone_detected' || nodes.length === 0) {
        setNoCyclone(true);
        setBulletin(null);
        nodesRef.current = [];
      } else {
        setNoCyclone(false);
        setBulletin(bull);
        nodesRef.current = nodes;
      }
      setShelterList(Array.isArray(sh) ? sh : sh?.results ?? []);
      setAffectedArea(area);
      setLoading(false);
    }).catch(err => {
      console.error("Telemetry fetch failed:", err);
      setNoCyclone(true);
      setBulletin(null);
      nodesRef.current = [];
      setLoading(false);
    });

    fetchWindData().then(setWindData).catch(() => null);
  }

  useEffect(() => {
    fetchAll();
    const id = setInterval(() => {
      fetchBulletin().then(bull => {
        const nodes = buildNodes(bull);
        if (bull?.status === 'no_cyclone_detected' || nodes.length === 0) {
          setNoCyclone(true);
          setBulletin(null);
          nodesRef.current = [];
        } else {
          setNoCyclone(false);
          setBulletin(bull);
          nodesRef.current = nodes;
        }
      }).catch(err => console.error("Bulletin refetch failed:", err));
    }, 5 * 60 * 1000);
    const windId = setInterval(() => {
      fetchWindData().then(setWindData).catch(() => null);
    }, 30 * 60 * 1000);
    return () => { clearInterval(id); clearInterval(windId); };
  }, []);

  // Timeline playback: steps through 0→24h at ~4 steps/s, then stops
  useEffect(() => {
    if (playing && nodesRef.current.length > 0) {
      playRef.current = setInterval(() => {
        setPlayHour(h => {
          const next = h + 1;
          if (next >= MAX_HOURS) { setPlaying(false); clearInterval(playRef.current); return MAX_HOURS; }
          return next;
        });
      }, 250);
    } else {
      clearInterval(playRef.current);
    }
    return () => clearInterval(playRef.current);
  }, [playing]);




  // Map always mounts after loading finishes — independent of whether a cyclone exists
  useEffect(() => {
    if (loading) return;
    if (mapRef.current) return; // already initialized

    const center = nodesRef.current.length > 0
      ? [nodesRef.current[0].lat, nodesRef.current[0].lon]
      : DEFAULT_CENTER;

    const map = L.map(hostRef.current, {
      zoomControl: false,
      minZoom: 4,
      maxBounds: [[-90, -Infinity], [90, Infinity]],
      maxBoundsViscosity: 1.0,
      worldCopyJump: true
    }).setView(center, nodesRef.current.length > 0 ? 6 : DEFAULT_ZOOM);
    L.control.zoom({ position: 'bottomright' }).addTo(map);
    L.control.scale({ position: 'bottomright', imperial: false }).addTo(map);

    const osm = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '\u00a9 OpenStreetMap contributors', maxZoom: 18 });
    const sat = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      { attribution: 'Imagery \u00a9 Esri, Maxar | \u00a9 OpenStreetMap contributors', maxZoom: 18 });
    sat.addTo(map);

    const eyeLatLng = nodesRef.current[0]
      ? [nodesRef.current[0].lat, nodesRef.current[0].lon]
      : [-9999, -9999]; // park off-screen when no storm

    layersRef.current = {
      map, osm, sat,
      track: L.layerGroup().addTo(map),
      rain: L.layerGroup().addTo(map),
      wind: L.layerGroup().addTo(map),
      shelters: L.layerGroup().addTo(map),
      eye: L.marker(eyeLatLng, {
        icon: L.divIcon({ className: '', iconSize: [14, 14], html: '<div class="vd-eye"></div>' }), zIndexOffset: 1000
      }).addTo(map)
    };
    mapRef.current = map;

    return () => { map.remove(); mapRef.current = null; };
  }, [loading]);

  useEffect(() => {
    const { map, osm, sat } = layersRef.current;
    if (!map) return;
    if (layers.sat) { map.removeLayer(osm); sat.addTo(map); } else { map.removeLayer(sat); osm.addTo(map); }
  }, [layers.sat]);

  useEffect(() => {
    const r = layersRef.current;
    if (!r.map) return;
    ['track', 'rain', 'wind', 'shelters'].forEach(k => {
      if (layers[k]) r[k].addTo(r.map); else r.map.removeLayer(r[k]);
    });
  }, [layers.track, layers.rain, layers.wind, layers.shelters]);

  useEffect(() => {
    const r = layersRef.current;
    if (!r.map) return;
    const nodes = nodesRef.current;
    r.track.clearLayers();
    r.shelters.clearLayers();
    if (nodes.length === 0) return;
    const palette = PALETTES[tweaks.palette];
    const sev = palette[2];
    L.polyline(nodes.map(n => [n.lat, n.lon]), { color: sev, weight: tweaks.track, opacity: .9 }).addTo(r.track);
    if (nodes.length > 0) {
      const conePts = buildConePolygons(nodes);
      L.polygon(conePts, { color: sev, weight: 1, opacity: 0.45, fillColor: sev, fillOpacity: 0.1 }).addTo(r.track);
    }
    nodes.forEach((n) => {
      L.circleMarker([n.lat, n.lon], { radius: 4 + tweaks.track * 0.6, color: '#fff', weight: 2, fillColor: sev, fillOpacity: 1 })
        .bindTooltip('T+' + n.h + 'h · ' + n.msw.toFixed(1) + ' kt · ' + imdCategory(n.msw), { direction: 'top' }).addTo(r.track);
    });
    shelterList.forEach(s => {
      L.marker([s.lat, s.lon], { icon: L.divIcon({ className: '', iconSize: [12, 12], html: '<div class="vd-shelter"></div>' }) })
        .bindTooltip(s.name + ' · cap ' + s.capacity, { direction: 'top' }).addTo(r.shelters);
    });
    if (affectedArea?.location) {
      L.circleMarker([affectedArea.location.lat, affectedArea.location.lon], { radius: 6, color: '#1F5FD0', weight: 2, fillColor: '#fff', fillOpacity: 1 })
        .bindTooltip((affectedArea.query?.district ?? 'Query') + ' · pincode ' + (affectedArea.query?.pincode ?? ''), { direction: 'top' }).addTo(r.shelters);
    }
  }, [tweaks.track, tweaks.palette, bulletin, shelterList, affectedArea]);

  useEffect(() => {
    const r = layersRef.current;
    if (!r.map) return;
    const nodes = nodesRef.current;
    const palette = PALETTES[tweaks.palette];
    const riskColor = mm => (mm >= 200 ? palette[2] : mm >= 90 ? palette[1] : palette[0]);

    if (nodes.length === 0) {
      r.rain.clearLayers();
      r.wind.clearLayers();
      if (r.eye) r.eye.setLatLng([-9999, -9999]);
      return;
    }

    // Interpolate to the active playHour position so rain/wind follow the eye
    const cappedNodes = nodes.filter(n => n.h <= MAX_HOURS);
    const p = cappedNodes.length > 0 ? interpolate(cappedNodes, playHour) : { ...nodes[0], h: 0 };

    r.eye.setLatLng([p.lat, p.lon]);
    const col = riskColor(p.rain);
    const k = tweaks.heat / 100;
    const radiusKm = 350;
    const R = radiusKm * 1000;

    r.rain.clearLayers();
    [[R, .10], [R * 0.63, .16], [R * 0.26, .26]].forEach(([rad, op], i) => {
      L.circle([p.lat, p.lon], { radius: rad, stroke: i === 0, color: col, weight: 1, opacity: .5 * k, fillColor: col, fillOpacity: Math.min(op * k, .6) }).addTo(r.rain);
    });

    r.wind.clearLayers();
    for (let i = 0; i < tweaks.windArrows; i++) {
      const ang = (i / tweaks.windArrows) * Math.PI * 2;
      const rot = ((-ang * 180 / Math.PI) + 270) % 360;
      L.marker([p.lat + Math.cos(ang) * (radiusKm / 171), p.lon + Math.sin(ang) * (radiusKm / 163)], {
        icon: L.divIcon({ className: '', iconSize: [16, 16], html: '<div class="vd-arrow" style="transform:rotate(' + rot.toFixed(0) + 'deg)">\u2191</div>' })
      }).addTo(r.wind);
    }
  }, [tweaks.heat, tweaks.windArrows, tweaks.palette, bulletin, playHour]);

  const panel = { position: 'absolute', background: 'var(--glass-bg)', backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)', border: '1px solid var(--glass-border)', borderRadius: 'var(--radius)', zIndex: 500, boxShadow: 'var(--glass-shadow)' };
  const rowStyle = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, padding: '7px 0', font: '500 12.5px/1.2 var(--body)', whiteSpace: 'nowrap', cursor: 'pointer' };

  const Toggle = ({ k, label, ph }) => (
    <div style={rowStyle} onClick={() => setLayers(s => ({ ...s, [k]: !s[k] }))}>
      <span>{label}{ph && <span style={{ font: '500 9px/1 var(--head)', letterSpacing: '.08em', padding: '3px 4px', border: '1px solid var(--line)', color: 'var(--muted)', marginLeft: 6 }}>PLACEHOLDER</span>}</span>
      <span style={{ flex: 'none', width: 30, height: 16, background: layers[k] ? 'var(--accent)' : 'rgba(127,127,127,.32)', position: 'relative', borderRadius: 'var(--radius-full)' }}>
        <i style={{ position: 'absolute', top: 2, left: layers[k] ? 16 : 2, width: 12, height: 12, background: '#fff', transition: 'left .16s', borderRadius: '50%' }} />
      </span>
    </div>
  );

  const Slider = ({ k, label, min, max, step, fmt }) => (
    <div style={{ padding: '8px 0', borderTop: '1px solid var(--line)' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 8, font: '500 11.5px/1.2 var(--body)', whiteSpace: 'nowrap' }}>
        <span>{label}</span><span style={{ font: '600 11px/1 var(--body)', color: 'var(--muted)' }}>{fmt(tweaks[k])}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={tweaks[k]}
        onChange={e => setTweaks(t => ({ ...t, [k]: +e.target.value }))}
        style={{ width: '100%', margin: '9px 0 4px', accentColor: 'var(--accent)' }} />
    </div>
  );

  return (
    <div style={{ position: 'absolute', inset: 0 }}>
      <style>{`
        .vd-eye{width:14px;height:14px;border-radius:50%;background:var(--r-sev);border:2px solid #fff;box-shadow:0 0 0 6px rgba(198,40,40,.22)}
        .vd-shelter{width:100%;height:100%;background:#0E7C66;border:2px solid #fff;border-radius:50%}
        .vd-arrow{font:600 15px/1 var(--body);color:var(--accent);opacity:.9}
        .leaflet-bar{border-radius:var(--radius-sm) !important;overflow:hidden;backdrop-filter:blur(16px);background:var(--glass-bg) !important;border:1px solid var(--glass-border) !important;box-shadow:var(--glass-shadow) !important}
        .leaflet-bar a{border-radius:0 !important;background:transparent !important;color:var(--ink) !important;border-bottom:1px solid var(--glass-border) !important}
        .leaflet-bar a:last-child{border-bottom:none !important}
        .leaflet-tooltip{border-radius:var(--radius-xs) !important;backdrop-filter:blur(12px);background:var(--glass-bg) !important;border:1px solid var(--glass-border) !important;color:var(--ink) !important;box-shadow:var(--glass-shadow) !important}
        .leaflet-control-attribution{border-radius:var(--radius-xs) !important;backdrop-filter:blur(12px);background:var(--glass-bg) !important}
        .leaflet-control-scale-line{border-radius:var(--radius-xs) !important}
        .leaflet-container{font-family:var(--body);font-size:11px}
        body.dark .leaflet-tile-pane{filter:brightness(.82) saturate(.85)}
      `}</style>
      {!isEmbedded && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, zIndex: 1000 }}>
          <Header />
        </div>
      )}

      {/* Loading overlay — shown while fetching, map not yet mounted */}
      {loading && (
        <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 600, background: 'var(--bg)' }}>
          <div style={{ padding: '16px 24px', background: 'var(--glass-bg)', backdropFilter: 'blur(12px)', borderRadius: 'var(--radius)', color: 'var(--muted)', font: '500 15px/1 var(--body)' }}>
            📡 Acquiring live telemetry from Django API...
          </div>
        </div>
      )}

      {/* Map host — ALWAYS rendered after loading, never conditionally removed */}
      <div ref={hostRef} style={{ position: 'absolute', inset: 0, background: 'var(--bg)' }} />

      {/* No-cyclone banner — non-blocking, floats over the base map tiles */}
      {!loading && noCyclone && (
        <div style={{ position: 'absolute', bottom: 28, left: 14, zIndex: 700, maxWidth: 380 }}>
          <div style={{ padding: '16px 20px', background: 'var(--glass-bg)', backdropFilter: 'blur(16px)', borderRadius: 'var(--radius)', border: '1px solid var(--r-sev)', boxShadow: 'var(--glass-shadow)' }}>
            <p style={{ margin: '0 0 4px', font: '600 13px/1.3 var(--body)', color: 'var(--r-sev)' }}>⚠️ No Active Cyclone Data Found</p>
            <p style={{ margin: '0 0 12px', font: '400 12px/1.5 var(--body)', color: 'var(--muted)' }}>The live prediction API is unreachable or returned empty tracking nodes.</p>
            <button
              onClick={() => { setLoading(true); setNoCyclone(false); fetchAll(); }}
              style={{ padding: '8px 16px', borderRadius: 'var(--radius-xs)', background: 'var(--r-sev)', color: '#fff', border: 'none', cursor: 'pointer', font: '600 12px/1 var(--body)' }}>
              Retry Connection
            </button>
          </div>
        </div>
      )}

      {/* Layer panel — only render controls when map is ready */}
      {!loading && (
        <>
          <WindyParticleLayer
            map={mapRef.current}
            windData={windData}
            visible={layers.wind}
            numParticles={tweaks.windParticles}
            hourRef={hourRef}
            bulletin={bulletin}
          />
          <div style={{ ...panel, top: 78, left: 14, bottom: 122, width: 230, padding: 14, overflow: 'hidden auto' }}>
            <div className="eyebrow">Layers</div>
            <Toggle k="sat" label="Satellite imagery" />
            <Toggle k="rain" label="Rainfall heat" />
            <Toggle k="wind" label="Wind flow" />
            <Toggle k="track" label="Track & cone" />
            <Toggle k="shelters" label="Your location" />

            <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--line)' }}>
              <div className="eyebrow" style={{ marginBottom: 4 }}>Tweaks</div>
              <div style={{ display: 'flex', gap: 3, marginTop: 8 }}>
                {['standard', 'contrast', 'cvd'].map(v => (
                  <button key={v} onClick={() => setTweaks(t => ({ ...t, palette: v }))}
                    style={{ flex: 1, padding: '6px 4px', border: '1px solid var(--line)', font: '600 10px/1.2 var(--head)', borderRadius: 'var(--radius-xs)',
                      background: tweaks.palette === v ? 'var(--ink)' : 'transparent', color: tweaks.palette === v ? 'var(--surface)' : 'var(--muted)' }}>
                    {v === 'standard' ? 'IMD' : v === 'contrast' ? 'Contrast' : 'Colour-safe'}
                  </button>
                ))}
              </div>
              <Slider k="heat" label="Heat opacity" min={20} max={180} step={5} fmt={v => v + '%'} />
              <Slider k="track" label="Track weight" min={1} max={8} step={1} fmt={v => v + ' px'} />
              <Slider k="windArrows" label="Wind arrows" min={4} max={12} step={4} fmt={v => v} />
              <Slider k="windParticles" label="Wind particles" min={300} max={3000} step={100} fmt={v => v.toLocaleString()} />
            </div>
          </div>

          {/* 24h Timeline player — bottom-centre, only shown when a cyclone is active */}
          {!noCyclone && nodesRef.current.length > 0 && (
            <div style={{
              ...panel,
              bottom: 24, left: '50%', transform: 'translateX(-50%)',
              padding: '12px 18px', display: 'flex', flexDirection: 'column', gap: 10,
              minWidth: 320, maxWidth: 440
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <button
                  onClick={() => { if (playHour >= MAX_HOURS) setPlayHour(0); setPlaying(p => !p); }}
                  style={{ flex: 'none', height: 30, padding: '0 14px', border: '1px solid var(--glass-border)', background: playing ? 'var(--accent)' : 'transparent', color: playing ? '#fff' : 'var(--ink)', font: '600 11px/1 var(--body)', borderRadius: 'var(--radius-xs)', cursor: 'pointer', whiteSpace: 'nowrap' }}>
                  {playing ? '⏸ Pause' : playHour >= MAX_HOURS ? '↺ Replay 24h' : '▶ Play 24h'}
                </button>
                <input
                  type="range" min={0} max={MAX_HOURS} step={1} value={playHour}
                  onChange={e => { setPlaying(false); setPlayHour(+e.target.value); }}
                  style={{ flex: 1, accentColor: 'var(--accent)' }}
                />
                <span style={{ font: '600 11.5px/1 var(--head)', color: 'var(--muted)', minWidth: 32, textAlign: 'right' }}>T+{playHour}h</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', font: '500 9.5px/1 var(--head)', color: 'var(--muted)', paddingRight: 40 }}>
                {[0, 6, 12, 18, 24].map(h => (
                  <span key={h} style={{ color: h === playHour ? 'var(--accent)' : undefined, fontWeight: h === playHour ? 700 : undefined }}>+{h}h</span>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default function StormMap() {
  return (
    <MapErrorBoundary>
      <StormMapInner />
    </MapErrorBoundary>
  );
}
