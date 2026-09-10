import React, { useContext, useEffect, useState } from 'react';
import { ThemeContext } from '../App.jsx';

export default function OrbBackground() {
  const { dark } = useContext(ThemeContext);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const orbsDark = [
    { bg: 'rgba(79,70,229,0.50)' }, // Indigo
    { bg: 'rgba(147,51,234,0.40)' }, // Purple
    { bg: 'rgba(13,148,136,0.38)' }, // Teal
    { bg: 'rgba(6,182,212,0.22)' },  // Cyan
    { bg: 'rgba(236,72,153,0.20)' }  // Pink
  ];

  const orbsLight = [
    { bg: 'rgba(59,130,246,0.30)' }, // Blue
    { bg: 'rgba(147,51,234,0.22)' }, // Purple
    { bg: 'rgba(13,148,136,0.25)' }, // Teal
    { bg: 'rgba(245,158,11,0.18)' }, // Amber
    { bg: 'rgba(225,29,72,0.12)' }   // Rose
  ];

  const orbs = dark ? orbsDark : orbsLight;

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: -1, overflow: 'hidden', background: 'var(--bg)' }}>
      <style>{`
        @keyframes orbIn {
          0% { transform: scale(0) translate(0, 0); opacity: 0; }
          100% { opacity: 1; }
        }
        @keyframes orbFloat1 { 0%, 100% { transform: translate(-10%, 10%) scale(1); } 50% { transform: translate(15%, -15%) scale(1.1); } }
        @keyframes orbFloat2 { 0%, 100% { transform: translate(15%, -20%) scale(1.05); } 50% { transform: translate(-20%, 15%) scale(0.95); } }
        @keyframes orbFloat3 { 0%, 100% { transform: translate(-25%, -15%) scale(0.9); } 50% { transform: translate(10%, 25%) scale(1.15); } }
        @keyframes orbFloat4 { 0%, 100% { transform: translate(20%, 20%) scale(1.2); } 50% { transform: translate(-15%, -10%) scale(0.9); } }
        @keyframes orbFloat5 { 0%, 100% { transform: translate(-15%, 25%) scale(1.1); } 50% { transform: translate(25%, -20%) scale(0.95); } }
      `}</style>
      
      {orbs.map((orb, i) => {
        // We use inline styles for the base positions and animations
        const positions = [
          { top: '10%', left: '20%', width: '45vw', height: '45vw' },
          { top: '40%', right: '10%', width: '35vw', height: '35vw' },
          { bottom: '10%', left: '15%', width: '50vw', height: '50vw' },
          { top: '20%', right: '30%', width: '40vw', height: '40vw' },
          { bottom: '20%', right: '20%', width: '60vw', height: '60vw' },
        ];
        
        const pos = positions[i];
        
        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              ...pos,
              background: orb.bg,
              filter: 'blur(80px)',
              borderRadius: '50%',
              opacity: mounted ? 1 : 0,
              transform: mounted ? 'scale(1)' : 'scale(0)',
              transition: `opacity 2.4s ease-out ${i * 0.1}s, transform 2.4s cubic-bezier(0.34, 1.56, 0.64, 1) ${i * 0.1}s`,
              animation: mounted ? `orbFloat${i + 1} ${18 + i * 3}s ease-in-out infinite alternate ${2.5 + i * 0.1}s` : 'none',
              transformOrigin: 'center center'
            }}
          />
        );
      })}

      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: dark ? 'rgba(15,23,42,0.40)' : 'rgba(255,255,255,0.40)',
          backdropFilter: 'blur(4px)',
          opacity: mounted ? 1 : 0,
          transition: 'opacity 3s ease-in 1.2s',
          zIndex: 1
        }}
      />
    </div>
  );
}
