const BASE = '';
export async function fetchBulletin(basin = 'BOB') {
  const res = await fetch(`${BASE}/api/predictions/tracks/live/?basin=${basin}`, {
    cache: 'no-store',
    headers: {
      'Cache-Control': 'no-cache, no-store, must-revalidate',
      'Pragma': 'no-cache',
      'Expires': '0'
    }
  });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

export async function fetchAffectedArea({ pincode, district, lat, lon } = {}) {
  const params = new URLSearchParams();
  if (pincode) params.set('pincode', pincode);
  else if (district) params.set('district', district);
  else if (lat != null && lon != null) { params.set('lat', lat); params.set('lon', lon); }
  const res = await fetch(`${BASE}/api/predictions/affected-area/?${params}`);
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

export async function fetchDistrictRainfall(district, horizon) {
  const params = new URLSearchParams({ district });
  if (horizon) params.set('horizon', horizon);
  const res = await fetch(`${BASE}/api/predictions/rainfall/?${params}`);
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

export async function fetchShelters({ state, district } = {}) {
  const params = new URLSearchParams();
  if (state) params.set('state', state);
  if (district) params.set('district', district);
  const res = await fetch(`${BASE}/api/cyclones/shelters/?${params}`);
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

export async function fetchNearestShelters(lat, lon, limit = 5) {
  const res = await fetch(
    `${BASE}/api/cyclones/shelters/nearest/?lat=${lat}&lon=${lon}&limit=${limit}`
  );
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

export async function fetchShelterAvailability() {
  const res = await fetch(`${BASE}/api/cyclones/shelters/availability/`);
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

export async function fetchWindData({ refresh = false } = {}) {
  const url = `${BASE}/api/predictions/wind-data/latest/${refresh ? '?refresh=1' : ''}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}
