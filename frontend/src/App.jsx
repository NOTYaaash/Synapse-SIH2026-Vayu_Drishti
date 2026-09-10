import React, { useEffect, useState } from 'react';
import { Routes, Route } from 'react-router-dom';
import Metrics from './pages/Metrics.jsx';
import StormMap from './pages/StormMap.jsx';
import Civilian from './pages/Civilian.jsx';
export const ThemeContext = React.createContext({ dark: false, toggle: () => {} });
export const LocationContext = React.createContext({ pincode: '', setPincode: () => {} });

export default function App() {
  const [dark, setDark] = useState(true);
  const [pincode, setPincode] = useState('');

  useEffect(() => {
    let v = null;
    try { v = localStorage.getItem('vd-theme'); } catch (e) {}
    apply(v ? v === 'dark' : true);
  }, []);

  function apply(next) {
    document.body.classList.toggle('dark', next);
    try { localStorage.setItem('vd-theme', next ? 'dark' : 'light'); } catch (e) {}
    setDark(next);
  }

  return (
    <LocationContext.Provider value={{ pincode, setPincode }}>
      <ThemeContext.Provider value={{ dark, toggle: () => apply(!dark) }}>
        <Routes>
          <Route path="/" element={<Metrics />} />
          <Route path="/map" element={<StormMap />} />
          <Route path="/area" element={<Civilian />} />
        </Routes>
      </ThemeContext.Provider>
    </LocationContext.Provider>
  );
}
