import { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet-velocity';

const WIND_COLORS = [
  'rgba(50, 195, 130, 0.8)',
  'rgba(140, 220, 90, 0.9)',
  'rgba(255, 235, 60, 0.9)',
  'rgba(255, 160, 30, 0.9)',
  'rgba(230, 70, 40, 0.9)',
  'rgba(170, 30, 100, 0.95)',
];

const PANE_NAME = 'windPane';
const PANE_Z   = 450;

export default function WindLayer({ map, windData, visible }) {
  const velocityRef = useRef(null);

  useEffect(() => {
    if (!map) return;
    if (!map.getPane(PANE_NAME)) {
      map.createPane(PANE_NAME);
      map.getPane(PANE_NAME).style.zIndex = String(PANE_Z);
      map.getPane(PANE_NAME).style.pointerEvents = 'none';
    }
  }, [map]);

  useEffect(() => {
    if (!map || !windData || !visible) {
      if (velocityRef.current) {
        map?.removeLayer(velocityRef.current);
        velocityRef.current = null;
      }
      return;
    }

    if (!L.velocityLayer) return;

    if (velocityRef.current) {
      map.removeLayer(velocityRef.current);
      velocityRef.current = null;
    }

    const layer = L.velocityLayer({
      displayValues: true,
      displayOptions: {
        velocityType: 'Wind',
        position: 'bottomleft',
        emptyString: 'No wind data',
        angleConvention: 'bearingCCW',
        speedUnit: 'kt',
      },
      data: windData,
      maxVelocity: 60,
      velocityScale: 0.008,
      colorScale: WIND_COLORS,
      particleAge: 90,
      lineWidth: 1.5,
      particleMultiplier: 0.004,
      frameRate: 15,
      pane: PANE_NAME,
    });

    layer.addTo(map);
    velocityRef.current = layer;

    return () => {
      if (velocityRef.current) {
        map.removeLayer(velocityRef.current);
        velocityRef.current = null;
      }
    };
  }, [map, windData, visible]);

  return null;
}
