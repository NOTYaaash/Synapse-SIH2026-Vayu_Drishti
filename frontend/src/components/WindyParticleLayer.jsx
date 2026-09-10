import { useEffect, useRef } from 'react';

// ─── Tuneable constants ────────────────────────────────────────────────────────
const MAX_AGE      = 160;  // frames before forced respawn (longer life = longer streak)
const SPAWN_AGE    = 10;   // frames for fade-in on spawn
const DEATH_AGE    = 130;  // frames before fade-out begins
const SPEED_SCALE  = 0.12; // pixels-per-frame per m/s — slower = smoother looking
const LINE_WIDTH   = 1.6;  // px
const TAIL_STEPS   = 14;   // number of segments per comet tail (longer = more visible)
const BOUNDS_PAD   = 20;   // px outside canvas before respawn

// ─── Theme-aware particle colour ─────────────────────────────────────────────
// Light theme: bright cyan-white  |  Dark theme: pale electric-blue
function baseColor() {
  return document.body.classList.contains('dark')
    ? [120, 200, 255]   // pale blue
    : [255, 255, 255];  // white
}

// ─── GFS bilinear interpolation ──────────────────────────────────────────────
function buildGFSField(windData) {
  const uComp = windData[0];
  const vComp = windData[1];
  const h = uComp.header;
  const { nx, ny, lo1, la1, dx, dy } = h;
  const uData = uComp.data;
  const vData = vComp.data;

  function sample(data, gx, gy) {
    const x0 = Math.floor(gx), y0 = Math.floor(gy);
    const x1 = Math.min(x0 + 1, nx - 1), y1 = Math.min(y0 + 1, ny - 1);
    const fx = gx - x0, fy = gy - y0;
    return (data[y0 * nx + x0] * (1 - fx) * (1 - fy) +
            data[y0 * nx + x1] * fx       * (1 - fy) +
            data[y1 * nx + x0] * (1 - fx) * fy       +
            data[y1 * nx + x1] * fx       * fy);
  }

  return function interpolate(lat, lon) {
    // Clamp to grid edges instead of returning null.
    // This means particles outside the data bounding box inherit the nearest
    // border wind value — no synthetic vortex, no visible box edge.
    const gx = Math.max(0, Math.min(nx - 1.001, (lon - lo1) / dx));
    const gy = Math.max(0, Math.min(ny - 1.001, (la1 - lat) / dy));
    return [sample(uData, gx, gy), sample(vData, gx, gy)];
  };
}

// ─── Synthetic vortex fallback ────────────────────────────────────────────────
function syntheticField(px, py, cx, cy, mswKt) {
  const dx = px - cx, dy = py - cy;
  const dist = Math.sqrt(dx * dx + dy * dy) || 1;
  const strength = (mswKt / 60) * Math.exp(-dist / 350) * 4.5;
  return [
    (-dy / dist * strength) + (-dx / dist * strength * 0.18) - 1.4,
    ( dx / dist * strength) + (-dy / dist * strength * 0.18) - 0.6,
  ];
}

// ─── Main Component ───────────────────────────────────────────────────────────
export default function WindyParticleLayer({
  map, windData, visible,
  numParticles = 1400,
  hourRef,
  bulletin,
}) {
  const canvasRef = useRef(null);
  const stateRef  = useRef({ raf: null, active: false });
  const trailRef  = useRef([]); // stores per-particle position history for comet tails

  // ── Mount canvas directly on the map container (NOT inside overlayPane) ────
  // overlayPane gets CSS-transformed by Leaflet during pan/zoom, which would
  // cause the canvas to double-shift. The container div stays fixed in place.
  useEffect(() => {
    if (!map) return;
    const container = map.getContainer();
    const cv = document.createElement('canvas');
    cv.style.cssText =
      'position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:450;';
    container.appendChild(cv);
    canvasRef.current = cv;
    return () => { canvasRef.current?.remove(); canvasRef.current = null; };
  }, [map]);

  // ── Particle animation loop ───────────────────────────────────────────────
  useEffect(() => {
    const cv = canvasRef.current;
    if (!cv || !map) return;

    const state = stateRef.current;
    if (state.raf) { cancelAnimationFrame(state.raf); state.raf = null; }
    state.active = false;

    if (!visible) {
      cv.getContext('2d').clearRect(0, 0, cv.width, cv.height);
      return;
    }

    // Respect OS reduced-motion preference
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    state.active = true;
    const gfsField = windData ? buildGFSField(windData) : null;
    const ctx = cv.getContext('2d');
    const dpr = Math.min(window.devicePixelRatio || 1, 2);

    let W = 0, H = 0;
    let particles = [];

    function spawn() {
      return {
        x: Math.random() * W,
        y: Math.random() * H,
        age: Math.floor(Math.random() * MAX_AGE),
        // history ring: stores [x, y] of last TAIL_STEPS positions
        trail: [],
      };
    }

    function resize() {
      const el = map.getContainer();
      W = el.clientWidth;
      H = el.clientHeight;
      cv.width  = W * dpr;
      cv.height = H * dpr;
      cv.style.width  = W + 'px';
      cv.style.height = H + 'px';
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      particles = Array.from({ length: numParticles }, () => spawn());
    }

    // Get storm position in screen coordinates for synthetic field fallback
    function getStormScreenPt() {
      const hr  = hourRef?.current ?? 0;
      const tl  = bulletin?.forecast_timeline ?? [];
      let lat   = bulletin?.center_lat ?? 16;
      let lon   = bulletin?.center_lon ?? 85;
      for (let i = 1; i < tl.length; i++) {
        const a = i === 1
          ? { forecast_hour: 0, lat: bulletin.center_lat, lon: bulletin.center_lon }
          : tl[i - 2];
        const b = tl[i - 1];
        if (hr <= (b.forecast_hour ?? 72)) {
          const t = Math.max(0, Math.min(1,
            (hr - (a.forecast_hour ?? 0)) / ((b.forecast_hour ?? 6) - (a.forecast_hour ?? 0))
          ));
          lat = (a.lat ?? lat) + ((b.lat ?? lat) - (a.lat ?? lat)) * t;
          lon = (a.lon ?? lon) + ((b.lon ?? lon) - (a.lon ?? lon)) * t;
          break;
        }
      }
      try { return map.latLngToContainerPoint([lat, lon]); } catch (_) { return null; }
    }

    function frame() {
      if (!state.active) return;

      // ── MOSDAC style: clear canvas on every frame (no fading accumulation) ──
      ctx.clearRect(0, 0, W, H);

      const [r, g, b] = baseColor();
      const mswKt = bulletin?.msw ?? 60;
      const stormPt = getStormScreenPt();

      // ── One path per frame, one stroke ────────────────────────────────────
      for (const pt of particles) {
        // --- Get wind vector at this particle's location ---
        let vx, vy;

        if (gfsField) {
          let latlng;
          try { latlng = map.containerPointToLatLng([pt.x, pt.y]); } catch (_) {
            Object.assign(pt, spawn()); continue;
          }
          // gfsField always returns a value — clamped to grid edges, no null
          const [u, v] = gfsField(latlng.lat, latlng.lng);
          vx =  u * SPEED_SCALE;
          vy = -v * SPEED_SCALE;
        } else if (stormPt) {
          [vx, vy] = syntheticField(pt.x, pt.y, stormPt.x, stormPt.y, mswKt);
        } else {
          Object.assign(pt, spawn()); continue;
        }


        // --- Advance particle ---
        pt.trail.push([pt.x, pt.y]);
        if (pt.trail.length > TAIL_STEPS) pt.trail.shift();

        const nx = pt.x + vx;
        const ny = pt.y + vy;
        pt.x = nx;
        pt.y = ny;
        pt.age++;

        // --- Compute lifecycle opacity (fade-in on spawn, fade-out before death) ---
        let lifeAlpha = 1;
        if (pt.age < SPAWN_AGE) {
          lifeAlpha = pt.age / SPAWN_AGE;
        } else if (pt.age > DEATH_AGE) {
          lifeAlpha = 1 - (pt.age - DEATH_AGE) / (MAX_AGE - DEATH_AGE);
        }
        lifeAlpha = Math.max(0, Math.min(1, lifeAlpha));

        // --- Draw comet: tail segments with decreasing opacity ---
        if (pt.trail.length >= 2) {
          for (let i = 1; i < pt.trail.length; i++) {
            const segAlpha = (i / pt.trail.length) * lifeAlpha * 0.85;
            const [x0, y0] = pt.trail[i - 1];
            const [x1, y1] = pt.trail[i];
            ctx.beginPath();
            ctx.moveTo(x0, y0);
            ctx.lineTo(x1, y1);
            ctx.strokeStyle = `rgba(${r},${g},${b},${segAlpha.toFixed(3)})`;
            ctx.lineWidth = LINE_WIDTH * (i / pt.trail.length);
            ctx.stroke();
          }
        }

        // --- Draw bright head dot ---
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, LINE_WIDTH * 0.85, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${r},${g},${b},${(lifeAlpha * 0.95).toFixed(3)})`;
        ctx.fill();

        // --- Respawn when old or out of bounds ---
        if (
          pt.age > MAX_AGE ||
          nx < -BOUNDS_PAD || ny < -BOUNDS_PAD ||
          nx > W + BOUNDS_PAD || ny > H + BOUNDS_PAD
        ) {
          Object.assign(pt, spawn());
        }
      }

      state.raf = requestAnimationFrame(frame);
    }

    resize();

    // No transform needed — canvas is fixed to the container, not a moving pane.
    // containerPointToLatLng handles all coordinate math per-frame.
    function onZoomEnd() { resize(); }

    map.on('zoomend', onZoomEnd);
    window.addEventListener('resize', onZoomEnd);

    state.raf = requestAnimationFrame(frame);

    return () => {
      state.active = false;
      cancelAnimationFrame(state.raf);
      state.raf = null;
      map.off('zoomend', onZoomEnd);
      window.removeEventListener('resize', onZoomEnd);
    };
  }, [map, windData, visible, numParticles, bulletin]);

  return null;
}
