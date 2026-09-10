import React, { useRef, useState, useEffect, useContext } from 'react';
import Header from '../components/Header.jsx';
import OrbBackground from '../components/OrbBackground.jsx';
import { RISK, TIERS, riskForRainfall, imdCategory } from '../utils.js';
import { fetchBulletin, fetchDistrictRainfall, fetchShelterAvailability, fetchAffectedArea } from '../api.js';
import { LocationContext } from '../App.jsx';

const TIER_COLORS = ['#c8dced', '#b3d7e0', '#c7e3ac', '#f0d79a', 'var(--r-high)', 'var(--r-sev)', '#5c1010'];

function buildWarnings(b, districtForecast, shelterCoverage) {
  const warnings = [];
  const peak = districtForecast?.forecasts ? Math.max(...districtForecast.forecasts.map(f => f.max_mm)) : 0;
  const peakForecast = districtForecast?.forecasts?.find(f => f.max_mm === peak);

  if (districtForecast && peakForecast && peak >= 200) {
    warnings.push({
      tag: 'SEVERE',
      risk: 'SEVERE',
      title: `Severe rainfall for ${districtForecast.district} at +${peakForecast.forecast_hour}h`,
      detail: `${peakForecast.max_mm.toFixed(1)} mm max, ${peakForecast.mean_mm.toFixed(1)} mm mean over the district grid.`,
    });
  } else if (districtForecast && peakForecast && peak >= 90) {
    warnings.push({
      tag: 'HIGH',
      risk: 'HIGH',
      title: `Heavy rainfall for ${districtForecast.district} at +${peakForecast.forecast_hour}h`,
      detail: `${peakForecast.max_mm.toFixed(1)} mm max, ${peakForecast.mean_mm.toFixed(1)} mm mean over the district grid.`,
    });
  }

  if (b) {
    warnings.push({
      tag: 'WIND',
      risk: 'HIGH',
      title: `${b.imd_category} winds`,
      detail: `MSW ${b.msw_3min} kt 3-min, gusting equivalent ${b.msw_1min} kt 1-min.`,
    });
  }

  if (shelterCoverage?.states_without_data?.length) {
    warnings.push({
      tag: 'DATA',
      risk: 'MODERATE',
      title: `Shelter coordinates missing for ${shelterCoverage.states_without_data.length} states`,
      detail: `${shelterCoverage.states_without_data.map(s => s.state).join(', ')} publish no geo-coordinates. ${shelterCoverage.total_shelters_loaded} shelters loaded across ${shelterCoverage.states_with_data.length} states.`,
    });
  }

  return warnings;
}

export default function Metrics() {
  const { pincode } = useContext(LocationContext);
  const mapRef = useRef(null);
  const frameRef = useRef(null);
  const [fs, setFs] = useState(false);
  const [b, setB] = useState(null);
  const [districtForecast, setDF] = useState(null);
  const [shelterCoverage, setSC] = useState(null);
  const [error, setError] = useState(null);

  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true);
        let currentDistrict = '';
        if (pincode && pincode.length === 6) {
          const area = await fetchAffectedArea({ pincode }).catch(() => null);
          if (area?.query?.district) {
            currentDistrict = area.query.district;
          }
        }
        
        const [bull, df, sc] = await Promise.all([
          fetchBulletin(),
          currentDistrict ? fetchDistrictRainfall(currentDistrict).catch(() => null) : Promise.resolve(null),
          fetchShelterAvailability(),
        ]);
        setB(bull); setDF(df); setSC(sc); setError(null);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    load();
    const id = setInterval(load, 5 * 60 * 1000);
    return () => clearInterval(id);
  }, [pincode]);

  useEffect(() => {
    const onFs = () => {
      const active = !!document.fullscreenElement;
      if (frameRef.current) frameRef.current.style.pointerEvents = active ? 'auto' : 'none';
      setFs(active);
    };
    document.addEventListener('fullscreenchange', onFs);
    return () => document.removeEventListener('fullscreenchange', onFs);
  }, []);

  function openMap() {
    if (document.fullscreenElement) { document.exitFullscreen(); return; }
    const el = mapRef.current;
    if (el && el.requestFullscreen) el.requestFullscreen().catch(() => { window.location.href = '/map'; });
    else window.location.href = '/map';
  }

  if (error) return (
    <>
      <OrbBackground />
      <Header />
      <div className="page" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ color: 'var(--r-sev)', font: '600 14px/1.5 var(--body)', textAlign: 'center' }}>
          {error}<br />
          <button onClick={() => window.location.reload()} style={{ marginTop: 12, padding: '8px 18px', border: '1px solid var(--line)', background: 'transparent', color: 'var(--ink)', font: '600 12px/1 var(--body)', cursor: 'pointer', borderRadius: 'var(--radius-xs)' }}>Retry</button>
        </div>
      </div>
    </>
  );

  if (loading) return (
    <>
      <OrbBackground />
      <Header />
      <div className="page" style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div className="card" style={{ padding: '32px 48px', textAlign: 'center' }}>
          <h2 style={{ fontSize: 20, marginBottom: 8 }}>📡 Acquiring Telemetry...</h2>
          <p className="muted">Fetching live prediction model data from Django API</p>
        </div>
      </div>
    </>
  );

  if (!b || !shelterCoverage) return (
    <>
      <OrbBackground />
      <Header />
      <div className="page" style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div className="card" style={{ padding: '32px 48px', textAlign: 'center', border: '1px solid var(--r-sev)' }}>
          <h2 style={{ fontSize: 20, marginBottom: 8, color: 'var(--r-sev)' }}>⚠️ Connection Error</h2>
          <p className="muted">Unable to reach the live prediction API. Ensure the backend is running.</p>
        </div>
      </div>
    </>
  );

  const peakRain = Math.max(...b.forecast_timeline.map(f => f.max_rainfall_mm));
  const kt = b.msw;
  const ACTIVE_TIER = (() => {
    if (kt < 28) return 0;
    if (kt < 34) return 1;
    if (kt < 48) return 2;
    if (kt < 64) return 3;
    if (kt < 90) return 4;
    if (kt < 120) return 5;
    return 6;
  })();
  const WARNINGS = buildWarnings(b, districtForecast, shelterCoverage);
  const issueTime = new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kolkata' }) + ' IST';

  return (
    <>
      <OrbBackground />
      <Header />
      <div className="page">
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'flex-end', justifyContent: 'space-between', gap: 18 }}>
          <div>
            <div className="label" style={{ marginBottom: 10 }}>Bulletin · {new Date().toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'Asia/Kolkata' })} · {issueTime}</div>
            <h1 style={{ margin: '0 0 12px', font: "700 clamp(26px,3.4vw,36px)/1.06 var(--head)" }}>{b.imd_category} - {b.basin === 'BOB' ? 'Bay of Bengal' : 'Arabian Sea'}</h1>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 1, background: 'var(--line)', border: '1px solid var(--line)', width: 'fit-content', borderRadius: 'var(--radius-sm)', overflow: 'hidden' }}>
              {[['Centre lat', b.center_lat + ' N'], ['Centre lon', b.center_lon + ' E'],
                ['Hemisphere', b.is_southern_hemisphere ? 'Southern' : 'Northern'], ['Source', b.satellite_source]].map(([k, v]) => (
                <div key={k} style={{ background: 'var(--surface)', padding: '8px 12px' }}>
                  <div style={{ font: "600 9px/1 var(--head)", letterSpacing: '.14em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 5 }}>{k}</div>
                  <div style={{ font: "600 13px/1 var(--head)" }}>{v}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <section className="card">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: '13px 18px', background: 'var(--r-sev)', color: '#fff', borderRadius: 'var(--radius) var(--radius) 0 0' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ font: "700 11px/1 var(--head)", letterSpacing: '.18em', textTransform: 'uppercase' }}>Warnings</span>
              <span style={{ font: "600 10.5px/1 var(--head)", letterSpacing: '.06em', padding: '4px 7px', background: 'rgba(255,255,255,.22)', borderRadius: 'var(--radius-xs)' }}>{WARNINGS.length} ACTIVE</span>
            </div>
            <span style={{ font: "500 11px/1 var(--body)", color: 'rgba(255,255,255,.85)' }}>Issued {issueTime} · next update in 5 min</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(280px,1fr))', gap: 1, background: 'var(--line)' }}>
            {WARNINGS.map(w => (
              <div key={w.title} style={{ background: 'var(--surface)', padding: '14px 18px', display: 'flex', gap: 11, alignItems: 'flex-start' }}>
                <span style={{ flex: 'none', marginTop: 1, font: "700 9px/1 var(--head)", letterSpacing: '.1em', padding: '4px 6px', background: RISK[w.risk][0], color: RISK[w.risk][1], borderRadius: 'var(--radius-xs)' }}>{w.tag}</span>
                <div>
                  <div style={{ font: "600 12.5px/1.35 var(--body)", marginBottom: 3 }}>{w.title}</div>
                  <div style={{ font: "400 11.5px/1.45 var(--body)", color: 'var(--muted)' }}>{w.detail}</div>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="card" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(190px,1fr))', gap: 1, background: 'var(--line)' }}>
          <div style={{ background: 'var(--surface)', padding: '18px 20px' }}>
            <div className="label" style={{ marginBottom: 10 }}>MSW · 3-min</div>
            <div className="figure">{b.msw_3min}<span className="unit">kt</span></div>
            <div style={{ font: "400 11px/1.5 var(--head)", color: 'var(--muted)', marginTop: 8 }}>10-min {b.msw_10min} · 1-min {b.msw_1min}</div>
          </div>
          <div style={{ background: 'var(--surface)', padding: '18px 20px' }}>
            <div className="label" style={{ marginBottom: 10 }}>Central pressure</div>
            <div className="figure">{b.central_pressure_hpa}<span className="unit">hPa</span></div>
            <div style={{ font: "400 11px/1.5 var(--head)", color: 'var(--muted)', marginTop: 8 }}>Deepening · 1013 hPa ambient</div>
          </div>
          <div style={{ background: 'var(--surface)', padding: '18px 20px' }}>
            <div className="label" style={{ marginBottom: 10 }}>Eye confidence</div>
            <div className="figure">{b.eye_confidence}</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginTop: 8 }}>
              <div style={{ flex: 1, height: 5, background: 'var(--line-2)', borderRadius: 'var(--radius-full)' }}>
                <div style={{ width: (b.eye_confidence * 100).toFixed(1) + '%', height: 5, background: '#0E7C66', borderRadius: 'var(--radius-full)' }} />
              </div>
              <span style={{ font: "500 11px/1 var(--head)", color: 'var(--muted)' }}>{b.eye_confidence_label}</span>
            </div>
          </div>
          {districtForecast ? (
            <div style={{ background: 'var(--surface)', padding: '18px 20px' }}>
              <div className="label" style={{ marginBottom: 10 }}>District tracked</div>
              <div className="figure" style={{ fontSize: 22 }}>{districtForecast.district}</div>
              <div style={{ font: "400 11px/1.5 var(--head)", color: 'var(--muted)', marginTop: 8 }}>{districtForecast.state}</div>
            </div>
          ) : (
            <div style={{ background: 'var(--surface)', padding: '18px 20px' }}>
              <div className="label" style={{ marginBottom: 10 }}>District tracked</div>
              <div className="figure" style={{ fontSize: 22 }}>None</div>
              <div style={{ font: "400 11px/1.5 var(--head)", color: 'var(--muted)', marginTop: 8 }}>Set a pincode</div>
            </div>
          )}
        </section>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(320px,1fr))', gap: 'clamp(22px,2.4vw,32px)', alignItems: 'start' }}>
          <section className="card" ref={mapRef} style={{ overflow: 'hidden' }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: '16px 20px', borderBottom: '1px solid var(--line)' }}>
              <h2 style={{ margin: 0, font: "700 15px/1.2 var(--head)" }}>Live map</h2>
              <button onClick={openMap} style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 34, padding: '0 14px',
                border: '1px solid var(--line)', background: 'transparent', color: 'var(--ink)', font: "600 11.5px/1 var(--head)", whiteSpace: 'nowrap', borderRadius: 'var(--radius-xs)' }}>
                {'⛶'} Open full screen
              </button>
            </div>
            <div onClick={openMap} style={{ position: 'relative', aspectRatio: '1 / 1', margin: 14, border: '1px solid var(--line)', overflow: 'hidden', cursor: 'pointer', background: 'var(--ph)', borderRadius: 'var(--radius-sm)' }}>
              <iframe ref={frameRef} src="/map" title="Live storm map preview" style={{ width: '100%', height: '100%', border: 0, display: 'block', pointerEvents: 'none' }} />
              <div style={{ position: 'absolute', left: 14, bottom: 14, padding: '7px 11px', background: 'var(--surface)', border: '1px solid var(--line)',
                font: "600 11px/1 var(--head)", letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--muted)', borderRadius: 'var(--radius-xs)' }}>
                {fs ? 'Press Esc to exit full screen' : 'Click to open full screen'}
              </div>
            </div>
          </section>

          <section className="card" style={{ overflow: 'hidden' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12, padding: '18px 20px 14px', borderBottom: '1px solid var(--line-2)' }}>
              <h2 style={{ margin: 0, font: "700 15px/1.2 var(--head)" }}>Bulletin payload</h2>
              <div style={{ display: 'flex', gap: 6 }}>
                <span style={{ font: "600 10px/1 var(--head)", letterSpacing: '.1em', padding: '5px 7px', background: 'var(--ink)', color: 'var(--surface)', borderRadius: 'var(--radius-xs)' }}>JSON</span>
              </div>
            </div>
            <pre style={{ margin: 0, padding: '18px 20px', maxHeight: 352, overflow: 'auto', background: 'var(--code-bg)', color: 'var(--code-ink)', font: "400 11.5px/1.7 var(--head)" }}>
{JSON.stringify(b, null, 2)}
            </pre>
            <div style={{ padding: '14px 20px', borderTop: '1px solid var(--line-2)' }}>
              <div className="label" style={{ marginBottom: 6 }}>Shelters loaded</div>
              <div style={{ font: "600 15px/1 var(--head)" }}>{shelterCoverage.total_shelters_loaded}</div>
            </div>
          </section>
        </div>

        <section className="card" style={{ overflow: 'hidden' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12, padding: '18px 20px 14px', borderBottom: '1px solid var(--line-2)' }}>
            <h2 style={{ margin: 0, font: "700 15px/1.2 var(--head)" }}>Forecast timeline</h2>
            <span className="eyebrow">0 to 24 h</span>
          </div>
          <div className="label" style={{ display: 'grid', gridTemplateColumns: '48px 118px 60px 1fr', gap: 12, padding: '10px 20px', background: 'var(--line-2)' }}>
            <span>Hour</span><span>Position</span><span>MSW</span><span>Max rainfall</span>
          </div>
          {b.forecast_timeline.filter(fc => fc.forecast_hour <= 24).map(fc => (
            <div key={fc.forecast_hour}>
              <div style={{ display: 'grid', gridTemplateColumns: '48px 118px 60px 1fr', gap: 12, alignItems: 'center', padding: '13px 20px', borderTop: '1px solid var(--line-2)' }}>
                <span style={{ font: "600 13px/1 var(--head)" }}>+{fc.forecast_hour}h</span>
                <span style={{ font: "400 11.5px/1.4 var(--head)", color: 'var(--muted)' }}>{fc.lat.toFixed(4)}, {fc.lon.toFixed(4)}</span>
                <span style={{ font: "500 12.5px/1 var(--head)" }}>{fc.msw_kt.toFixed(1)}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{ flex: 1, height: 6, background: 'var(--line-2)', borderRadius: 'var(--radius-full)' }}>
                    <div style={{ height: 6, width: Math.round((fc.max_rainfall_mm / peakRain) * 100) + '%', background: RISK[riskForRainfall(fc.max_rainfall_mm)][0], borderRadius: 'var(--radius-full)' }} />
                  </div>
                  <span style={{ font: "600 11.5px/1 var(--head)", minWidth: 58, textAlign: 'right' }}>{fc.max_rainfall_mm.toFixed(1)} mm</span>
                </div>
              </div>
              <div style={{ padding: '0 20px 12px 80px', font: "400 10.5px/1.4 var(--head)", color: 'var(--muted-2)' }}>{fc.imd_category}</div>
            </div>
          ))}
        </section>

        {districtForecast && (
          <section className="card" style={{ overflow: 'hidden' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12, padding: '18px 20px 14px', borderBottom: '1px solid var(--line-2)' }}>
              <h2 style={{ margin: 0, font: "700 15px/1.2 var(--head)" }}>District exposure - {districtForecast.district}, {districtForecast.state}</h2>
              <span className="eyebrow">{districtForecast.district_lat}, {districtForecast.district_lon}</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(200px,1fr))', gap: 1, background: 'var(--line)' }}>
              {districtForecast.forecasts.map(d => (
                <div key={d.forecast_hour} style={{ background: 'var(--surface)', padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 }}>
                    <span style={{ font: "600 14px/1 var(--head)" }}>+{d.forecast_hour}h</span>
                    <span style={{ font: "600 9.5px/1 var(--head)", letterSpacing: '.1em', padding: '4px 7px', background: RISK[d.risk_level][0], color: RISK[d.risk_level][1], borderRadius: 'var(--radius-xs)' }}>{d.risk_level}</span>
                  </div>
                  <div style={{ font: "600 24px/1 var(--head)" }}>{d.max_mm.toFixed(1)}<span className="unit">mm max</span></div>
                  <div style={{ font: "400 11px/1.4 var(--head)", color: 'var(--muted)' }}>mean {d.mean_mm.toFixed(1)} mm · storm at {d.storm_lat.toFixed(2)}, {d.storm_lon.toFixed(2)}</div>
                </div>
              ))}
            </div>
          </section>
        )}

        <section className="card" style={{ padding: '20px 22px' }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', justifyContent: 'space-between', gap: 12, marginBottom: 20 }}>
            <h2 style={{ margin: 0, font: "700 15px/1.2 var(--head)" }}>IMD classification tiers</h2>
            <span className="eyebrow">Current {b.msw} kt · {b.south_pacific_category}</span>
          </div>
          <div style={{ position: 'relative', paddingTop: 26 }}>
            <div style={{ position: 'absolute', top: 0, left: ((ACTIVE_TIER + 0.5) / TIERS.length * 100).toFixed(1) + '%',
              transform: 'translateX(-50%)', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3 }}>
              <span style={{ font: "600 10px/1 var(--head)", letterSpacing: '.08em', padding: '4px 6px', background: 'var(--ink)', color: 'var(--surface)', whiteSpace: 'nowrap', borderRadius: 'var(--radius-xs)' }}>{b.msw} KT</span>
              <span style={{ width: 1, height: 8, background: 'var(--ink)' }} />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7,1fr)', gap: 2 }}>
              {TIERS.map(([range, name], i) => (
                <div key={name} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <div style={{ height: 10, background: TIER_COLORS[i], outline: i === ACTIVE_TIER ? '2px solid var(--ink)' : 'none', borderRadius: 'var(--radius-xs)' }} />
                  <div style={{ font: "500 9.5px/1.35 var(--head)", color: 'var(--muted)' }}>{range}</div>
                  <div style={{ font: "600 10.5px/1.3 var(--body)", color: i === ACTIVE_TIER ? 'var(--ink)' : 'var(--muted)', textWrap: 'pretty' }}>{name}</div>
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>
    </>
  );
}
