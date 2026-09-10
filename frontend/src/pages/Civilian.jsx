import React, { useState, useEffect, useContext } from 'react';
import { Link } from 'react-router-dom';
import Header from '../components/Header.jsx';
import OrbBackground from '../components/OrbBackground.jsx';
import { RISK, riskForRainfall } from '../utils.js';
import { fetchAffectedArea, fetchDistrictRainfall, fetchNearestShelters, fetchShelterAvailability } from '../api.js';
import { LocationContext } from '../App.jsx';

// ── helpers ──────────────────────────────────────────────────────────────────
const fmt2 = v => (v != null && !isNaN(v) ? Number(v).toFixed(2) : '--');
const fmtVal = v => (v != null && !isNaN(v) ? v : '--');

// Error Boundary
class CivilianErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { hasError: false }; }
  static getDerivedStateFromError() { return { hasError: true }; }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: '60px 20px', textAlign: 'center', color: 'var(--muted)', font: '500 14px/1.6 var(--body)' }}>
          ⚠️ Something went wrong rendering this page. Please{' '}
          <button onClick={() => window.location.reload()} style={{ textDecoration: 'underline', background: 'none', border: 'none', cursor: 'pointer', color: 'inherit' }}>reload</button>.
        </div>
      );
    }
    return this.props.children;
  }
}

export default function Civilian() {
  const { pincode, setPincode } = useContext(LocationContext);
  const [units, setUnits] = useState('knots');
  const [pinInput, setPinInput] = useState(pincode || '');
  const [q, setQ] = useState(null);
  const [noCyclone, setNoCyclone] = useState(false);
  const [districtForecast, setDF] = useState(null);
  const [shelters, setShelters] = useState([]);
  const [shelterCoverage, setSC] = useState(null);
  const [loading, setLoading] = useState(false);
  const [initialLoad, setInitialLoad] = useState(true);
  const [error, setError] = useState(null);

  function loadData(pin) {
    setLoading(true);
    setError(null);
    setNoCyclone(false);
    fetchAffectedArea({ pincode: pin })
      .then(async area => {
        // If backend says no cyclone detected, show safe state
        if (area?.status === 'no_cyclone_detected') {
          setNoCyclone(true);
          setQ(null);
          setDF(null);
          setShelters([]);
          setSC(null);
          return;
        }
        setQ(area);

        // Use nearest-shelter endpoint (lat/lon-based) — the state-filter endpoint
        // returns GeoJSON and yields 0 results; nearest already includes distance_km.
        const userLat = area.location?.lat;
        const userLon = area.location?.lon;

        const [df, nearestShelters, sc] = await Promise.all([
          fetchDistrictRainfall(area.query?.district ?? '').catch(() => null),
          (userLat != null && userLon != null)
            ? fetchNearestShelters(userLat, userLon, 10).catch(() => [])
            : Promise.resolve([]),
          fetchShelterAvailability().catch(() => null),
        ]);
        setDF(df);

        // Nearest endpoint already returns a flat array sorted by distance
        const sorted = Array.isArray(nearestShelters)
          ? nearestShelters
          : nearestShelters?.results ?? [];

        setShelters(sorted);
        setSC(sc);
      })
      .catch(err => setError(err.message))
      .finally(() => { setLoading(false); setInitialLoad(false); });
  }

  useEffect(() => {
    if (pincode && pincode.length === 6) {
      setPinInput(pincode);
      loadData(pincode);
    } else {
      setQ(null);
      setInitialLoad(false);
    }
  }, [pincode]);

  const msw = q?.msw_knots != null
    ? (units === 'knots' ? fmt2(q.msw_knots) : fmt2(q.msw_knots * 1.852))
    : '--';

  const peak = districtForecast?.forecasts?.length
    ? Math.max(...districtForecast.forecasts.map(f => f.max_mm))
    : 0;
  const peakScale = peak || 1;

  // Build shelter rows: prefer the fetched & sorted list, fall back to nearest_shelter in q
  const shelterRows = shelters.length
    ? shelters
    : q?.nearest_shelter
      ? [{
          id: 'ns',
          name: q.nearest_shelter.name,
          state: q.nearest_shelter.state,
          district: q.nearest_shelter.district,
          capacity: q.nearest_shelter.capacity,
          shelter_type: 'MPCS',
          distance_km: q.nearest_shelter.distance_km
        }]
      : [];

  // Risk card colour: red if affected, green if safe/no threat
  const isAffected = q?.is_affected === true;
  const riskBg = isAffected ? 'var(--r-sev)' : '#16a34a';

  // Build location description safely
  const locationParts = [q?.query?.district, q?.query?.state].filter(Boolean);
  const locationStr = locationParts.length ? locationParts.join(', ') : null;

  return (
    <CivilianErrorBoundary>
      <>
        <OrbBackground />
        <Header />
        <div className="page">
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'flex-end', justifyContent: 'space-between', gap: 16 }}>
            <div>
              <div className="label" style={{ marginBottom: 10 }}>Check your area</div>
              <h1 style={{ margin: 0, font: "700 clamp(28px,4vw,40px)/1.05 var(--head)", textWrap: 'pretty' }}>
                Is my pincode in the threat region?
              </h1>
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, background: 'var(--surface)', border: '1px solid var(--line)', padding: '0 14px', height: 46, borderRadius: 'var(--radius-sm)' }}>
                <span className="label">Pin</span>
                <input
                  value={pinInput}
                  onChange={e => setPinInput(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  onKeyDown={e => { if (e.key === 'Enter' && pinInput.length === 6) setPincode(pinInput); }}
                  maxLength={6}
                  placeholder="Enter 6-digit pin"
                  style={{ font: "600 20px/1 var(--head)", letterSpacing: '.06em', border: 'none', background: 'transparent', color: 'var(--ink)', width: 90, outline: 'none' }}
                />
              </div>
              <button
                onClick={() => pinInput.length === 6 && setPincode(pinInput)}
                disabled={loading || pinInput.length !== 6}
                style={{ height: 46, padding: '0 20px', border: 'none', background: 'var(--ink)', color: 'var(--surface)', font: "600 13px/1 var(--body)", opacity: loading || pinInput.length !== 6 ? 0.5 : 1, cursor: loading ? 'wait' : 'pointer', borderRadius: 'var(--radius-xs)' }}>
                {loading ? 'Checking…' : 'Check'}
              </button>
              <button onClick={() => setUnits(units === 'knots' ? 'kmph' : 'knots')}
                style={{ height: 46, padding: '0 14px', border: '1px solid var(--line)', background: 'transparent', color: 'var(--ink)', font: "600 12px/1 var(--body)", whiteSpace: 'nowrap', borderRadius: 'var(--radius-xs)' }}>
                {units === 'knots' ? 'kt' : 'km/h'}
              </button>
            </div>
          </div>

          {error && (
            <div style={{ padding: '18px 22px', background: 'var(--r-sev)', color: '#fff', font: '600 13px/1.5 var(--body)', borderRadius: 'var(--radius-sm)' }}>
              {error}
            </div>
          )}

          {/* No-cyclone safe state */}
          {!initialLoad && !error && noCyclone && (
            <section className="card" style={{ background: '#16a34a', border: 'none', padding: 'clamp(20px,3vw,30px)', color: '#fff', textAlign: 'center' }}>
              <div style={{ font: "600 11px/1 var(--head)", letterSpacing: '.18em', textTransform: 'uppercase', marginBottom: 14 }}>
                Status · CLEAR
              </div>
              <p style={{ margin: '0 0 6px', font: "700 clamp(22px,2.6vw,30px)/1.15 var(--head)" }}>
                ✅ No Active Cyclone Threat
              </p>
              <p style={{ margin: 0, font: "400 14px/1.5 var(--body)", color: 'rgba(255,255,255,.86)' }}>
                No active cyclonic system has been detected in this basin. Your area is currently safe. Monitor IMD advisories for updates.
              </p>
            </section>
          )}

          {!initialLoad && !error && q && (
            <>
              {/* Risk card with safe null-guards */}
              <section className="card" style={{ background: riskBg, border: 'none', padding: 'clamp(20px,3vw,30px)', color: '#fff',
                display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(240px,1fr))', gap: 'clamp(20px,3vw,36px)', alignItems: 'center' }}>
                <div>
                  <div style={{ font: "600 11px/1 var(--head)", letterSpacing: '.18em', textTransform: 'uppercase', marginBottom: 14 }}>
                    Risk level · {q.risk_level ?? 'NONE'}
                  </div>
                  <p style={{ margin: '0 0 6px', font: "700 clamp(22px,2.6vw,30px)/1.15 var(--head)", textWrap: 'pretty' }}>{q.advisory ?? 'No advisory issued.'}</p>
                  <p style={{ margin: 0, font: "400 14px/1.5 var(--body)", color: 'rgba(255,255,255,.86)' }}>
                    {locationStr && <>{locationStr} · </>}
                    {q.distance_km != null ? <>{fmt2(q.distance_km)} km from the storm centre</> : 'Distance unavailable'}
                    {q.affected_radius_km != null ? <>, inside the {fmt2(q.affected_radius_km)} km affected radius.</> : '.'}
                  </p>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1, background: 'rgba(255,255,255,.28)', borderRadius: 'var(--radius-sm)', overflow: 'hidden' }}>
                  {[
                    ['Expected rain', fmt2(q.expected_rainfall_mm), 'mm'],
                    ['Wind (MSW)', msw, units === 'knots' ? 'kt' : 'km/h'],
                    ['Pressure', fmt2(q.central_pressure_hpa), 'hPa'],
                    ['Eye confidence', q.eye_confidence != null ? fmt2(q.eye_confidence) : 'N/A', '']
                  ].map(([k, v, u]) => (
                    <div key={k} style={{ background: riskBg, padding: '16px 18px' }}>
                      <div style={{ font: "500 10px/1 var(--head)", letterSpacing: '.14em', textTransform: 'uppercase', color: 'rgba(255,255,255,.72)', marginBottom: 8 }}>{k}</div>
                      <div style={{ font: "600 26px/1 var(--head)" }}>
                        {v}<span style={{ fontSize: 13, marginLeft: 3, color: 'rgba(255,255,255,.72)' }}>{u}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </section>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(320px,1fr))', gap: 'clamp(22px,2.4vw,32px)', alignItems: 'start' }}>
                <section className="card">
                  <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12, padding: '18px 20px 14px', borderBottom: '1px solid var(--line-2)' }}>
                    <h2 style={{ margin: 0, font: "700 15px/1.2 var(--head)" }}>Nearest shelters</h2>
                    {shelterCoverage && (
                      <span className="eyebrow">
                        {shelterCoverage.total_shelters_loaded ?? shelterCoverage.count ?? '—'} loaded
                        {shelterCoverage.states_with_data?.length != null
                          ? ` · ${shelterCoverage.states_with_data.length} states`
                          : ''}
                      </span>
                    )}
                  </div>
                  {q.nearest_shelter && (
                    <div style={{ padding: '18px 20px', display: 'flex', flexDirection: 'column', gap: 14, borderBottom: '1px solid var(--line-2)', background: 'var(--tint)' }}>
                      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 }}>
                        <div>
                          <div style={{ font: "500 10px/1 var(--head)", letterSpacing: '.14em', textTransform: 'uppercase', color: 'var(--accent)', marginBottom: 8 }}>Go here</div>
                          <div style={{ font: "700 18px/1.2 var(--body)" }}>{q.nearest_shelter.name}</div>
                          <div style={{ font: "400 13px/1.5 var(--body)", color: 'var(--muted)' }}>
                            {[q.nearest_shelter.district, q.nearest_shelter.state].filter(Boolean).join(', ')}
                            {q.nearest_shelter.lat != null && q.nearest_shelter.lon != null && (
                              <> · {fmt2(q.nearest_shelter.lat)}, {fmt2(q.nearest_shelter.lon)}</>
                            )}
                          </div>
                        </div>
                        <div style={{ textAlign: 'right', flex: 'none' }}>
                          <div style={{ font: "600 24px/1 var(--head)" }}>{fmt2(q.nearest_shelter.distance_km)}<span className="unit">km</span></div>
                          <div style={{ font: "500 11px/1.4 var(--head)", color: 'var(--muted)', marginTop: 4 }}>Cap {fmtVal(q.nearest_shelter.capacity)}</div>
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: 8 }}>
                        <Link to="/map" style={{ flex: 1, textAlign: 'center', padding: '11px 14px', background: 'var(--ink)', color: 'var(--surface)', font: "600 12px/1 var(--body)", borderRadius: 'var(--radius-xs)' }}>Directions on map</Link>
                        <a href="tel:1078" style={{ padding: '11px 14px', border: '1px solid var(--line)', background: 'transparent', color: 'var(--ink)', font: "600 12px/1 var(--body)", whiteSpace: 'nowrap', textDecoration: 'none', borderRadius: 'var(--radius-xs)' }}>Call helpline</a>
                      </div>
                    </div>
                  )}
                  {q.shelter_data_note && (
                    <div style={{ padding: '14px 20px', background: 'var(--tint)', font: '400 12px/1.5 var(--body)', color: 'var(--muted)' }}>
                      {q.shelter_data_note}
                    </div>
                  )}
                  <div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr auto auto', gap: 12, padding: '10px 20px', background: 'var(--line-2)', borderRadius: 'var(--radius-xs) var(--radius-xs) 0 0' }} className="label">
                      <span>Shelter</span><span>Capacity</span><span>Distance</span>
                    </div>
                    {shelterRows.length === 0 ? (
                      <div style={{ padding: '20px', font: '400 13px/1.5 var(--body)', color: 'var(--muted)', textAlign: 'center' }}>
                        No shelter data available for this state.
                      </div>
                    ) : shelterRows.map((s, idx) => (
                      <div key={s.id ?? idx} style={{ display: 'grid', gridTemplateColumns: '1fr auto auto', gap: 12, padding: '14px 20px', borderTop: '1px solid var(--line-2)', alignItems: 'center' }}>
                        <div>
                          <div style={{ font: "600 13px/1.3 var(--body)" }}>{s.name ?? '—'}</div>
                          <div style={{ font: "400 11px/1.4 var(--head)", color: 'var(--muted)' }}>{s.shelter_type ?? 'Shelter'} · {s.state ?? '—'}</div>
                          {s.lat != null && s.lon != null && (
                            <div style={{ font: "400 10px/1.3 var(--head)", color: 'var(--muted-2)', marginTop: 2, letterSpacing: '.02em' }}>
                              {Number(s.lat).toFixed(4)}, {Number(s.lon).toFixed(4)}
                            </div>
                          )}
                        </div>
                        <span style={{ font: "500 13px/1 var(--head)" }}>{fmtVal(s.capacity)}</span>
                        <span style={{ font: "600 13px/1 var(--head)", minWidth: 64, textAlign: 'right' }}>
                          {s.distance_km != null ? `${fmt2(s.distance_km)} km` : '—'}
                        </span>
                      </div>
                    ))}
                    {shelterCoverage?.states_without_data?.length > 0 && (
                      <div style={{ padding: '14px 20px', borderTop: '1px solid var(--line-2)', display: 'flex', gap: 10, alignItems: 'flex-start', background: 'var(--tint)' }}>
                        <span style={{ font: "600 10px/1 var(--head)", letterSpacing: '.1em', padding: '4px 6px', background: 'var(--r-mod)', color: '#111318', flex: 'none', borderRadius: 'var(--radius-xs)' }}>GAP</span>
                        <p style={{ margin: 0, font: "400 12px/1.5 var(--body)", color: 'var(--muted)', textWrap: 'pretty' }}>
                          No shelter coordinates published for {shelterCoverage.states_without_data.map(s => s.state ?? s).join(', ')}. Coverage in those states falls back to state helplines.
                        </p>
                      </div>
                    )}
                  </div>
                </section>

                {districtForecast?.forecasts?.length > 0 && (
                  <section className="card">
                    <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12, padding: '18px 20px 14px', borderBottom: '1px solid var(--line-2)' }}>
                      <h2 style={{ margin: 0, font: "700 15px/1.2 var(--head)" }}>Next 24 hours here</h2>
                      <span className="eyebrow">District rainfall</span>
                    </div>
                    {districtForecast.forecasts.filter(r => r.forecast_hour <= 24).map(r => (
                      <div key={r.forecast_hour} style={{ display: 'grid', gridTemplateColumns: '56px 1fr 96px', gap: 14, alignItems: 'center', padding: '14px 20px', borderBottom: '1px solid var(--line-2)' }}>
                        <div style={{ font: "600 15px/1 var(--head)" }}>+{r.forecast_hour}h</div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                            <span style={{ font: "600 13px/1 var(--body)" }}>{fmt2(r.max_mm)} mm max</span>
                            <span style={{ font: "400 11px/1 var(--head)", color: 'var(--muted)' }}>mean {fmt2(r.mean_mm)}</span>
                          </div>
                          <div style={{ height: 6, background: 'var(--line-2)', borderRadius: 'var(--radius-full)' }}>
                            <div style={{ height: 6, width: Math.round((r.max_mm / peakScale) * 100) + '%', background: RISK[r.risk_level]?.[0] ?? '#aaa', borderRadius: 'var(--radius-full)' }} />
                          </div>
                        </div>
                        <span style={{ justifySelf: 'end', font: "600 10px/1 var(--head)", letterSpacing: '.1em', padding: '5px 8px',
                          background: RISK[r.risk_level]?.[0] ?? '#aaa', color: RISK[r.risk_level]?.[1] ?? '#fff', borderRadius: 'var(--radius-xs)' }}>{r.risk_level}</span>
                      </div>
                    ))}
                    <div style={{ padding: '16px 20px' }}>
                      <p style={{ margin: 0, font: "400 11px/1.5 var(--head)", color: 'var(--muted)' }}>
                        Storm centre {fmt2(districtForecast.forecasts[0].storm_lat)}, {fmt2(districtForecast.forecasts[0].storm_lon)} · {q.imd_category ?? '—'} · issued from INSAT-3D/3DS imagery.
                      </p>
                    </div>
                  </section>
                )}
              </div>
            </>
          )}

          {initialLoad && !error && (
            <div style={{ color: 'var(--muted)', font: '500 13px/1 var(--body)' }}>Loading area data…</div>
          )}
          {!initialLoad && !q && !noCyclone && !error && (
            <div style={{ padding: '60px 20px', textAlign: 'center', color: 'var(--muted)', font: '500 15px/1.5 var(--body)' }}>
              Enter a pincode in the top bar to check your area's risk.
            </div>
          )}
        </div>
      </>
    </CivilianErrorBoundary>
  );
}
