export function imdCategory(knots) {
  if (knots < 34) return 'Depression';
  if (knots < 48) return 'Cyclonic Storm';
  if (knots < 64) return 'Severe Cyclonic Storm';
  if (knots < 90) return 'Very Severe Cyclonic Storm';
  if (knots < 120) return 'Extremely Severe Cyclonic Storm';
  return 'Super Cyclonic Storm';
}

export function getRiskColor(knots) {
  if (knots < 34) return 'var(--accent)';
  if (knots < 64) return 'var(--r-mod)';
  if (knots < 90) return 'var(--r-high)';
}

export function buildConePolygons(nodes) {
  // Returns an array of left and right points to form a polygon hull around the nodes
  const lefts = [];
  const rights = [];
  for (let i = 0; i < nodes.length; i++) {
    const n = nodes[i];
    const r_meters = 60000 + i * 55000;
    const r_deg = r_meters / 111320; // Approx degrees
    
    let heading;
    if (i < nodes.length - 1) {
      const n2 = nodes[i + 1];
      heading = Math.atan2(n2.lon - n.lon, n2.lat - n.lat);
    } else if (i > 0) {
      const n0 = nodes[i - 1];
      heading = Math.atan2(n.lon - n0.lon, n.lat - n0.lat);
    } else {
      heading = 0;
    }
    
    // Left and right normal vectors
    const dLatL = Math.cos(heading + Math.PI / 2) * r_deg;
    const dLonL = Math.sin(heading + Math.PI / 2) * r_deg / Math.cos(n.lat * Math.PI / 180);
    const dLatR = Math.cos(heading - Math.PI / 2) * r_deg;
    const dLonR = Math.sin(heading - Math.PI / 2) * r_deg / Math.cos(n.lat * Math.PI / 180);
    
    lefts.push([n.lat + dLatL, n.lon + dLonL]);
    rights.push([n.lat + dLatR, n.lon + dLonR]);
  }
  
  // To form a closed polygon: all lefts forward, then all rights backward
  rights.reverse();
  return [...lefts, ...rights];
}

export const RISK = {
  SEVERE: ['var(--r-sev)', '#fff'],
  HIGH: ['var(--r-high)', '#fff'],
  MODERATE: ['var(--r-mod)', '#000'],
  LOW: ['var(--accent)', '#fff'],
  NONE: ['rgba(127,127,127,0.2)', 'var(--ink)']
};

export const TIERS = [
  ['<28 kt', 'Depression'],
  ['28-33 kt', 'Deep Depression'],
  ['34-47 kt', 'Cyclonic Storm'],
  ['48-63 kt', 'Severe Cyclonic Storm'],
  ['64-89 kt', 'Very Severe Cyclonic Storm'],
  ['90-119 kt', 'Extremely Severe Cyclonic Storm'],
  ['>120 kt', 'Super Cyclonic Storm']
];

export function riskForRainfall(mm) {
  if (mm >= 200) return 'SEVERE';
  if (mm >= 90) return 'HIGH';
  if (mm >= 20) return 'MODERATE';
  return 'LOW';
}


