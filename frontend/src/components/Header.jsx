import React, { useContext, useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ThemeContext, LocationContext } from '../App.jsx';

export function Logo({ size = 26 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" aria-label="Vayu Drishti">
      <circle cx="24" cy="24" r="4.6" fill="var(--accent)" />
      <path d="M24 24 A 15 15 0 0 0 33 6" fill="none" stroke="var(--accent)" strokeWidth="5" strokeLinecap="round" />
      <path d="M24 24 A 15 15 0 0 0 15 42" fill="none" stroke="var(--accent)" strokeWidth="5" strokeLinecap="round" />
      <path d="M24 24 A 9 9 0 0 1 32 31" fill="none" stroke="var(--accent)" strokeWidth="4" strokeLinecap="round" opacity=".45" />
      <path d="M24 24 A 9 9 0 0 1 16 17" fill="none" stroke="var(--accent)" strokeWidth="4" strokeLinecap="round" opacity=".45" />
    </svg>
  );
}

const NAV = [
  { to: '/', label: 'IMD metrics' },
  { to: '/map', label: 'Live map' },
  { to: '/area', label: 'Your area' }
];

export default function Header() {
  const { dark, toggle } = useContext(ThemeContext);
  const { pincode, setPincode } = useContext(LocationContext);
  const { pathname } = useLocation();
  const [pinInput, setPinInput] = useState(pincode);

  useEffect(() => {
    setPinInput(pincode);
  }, [pincode]);

  return (
    <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 24,
      padding: '0 clamp(16px,3vw,32px)', height: 64, borderBottom: '1px solid var(--glass-border)',
      background: 'var(--glass-bg)', backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)',
      boxShadow: 'var(--glass-shadow)', position: 'sticky', top: 0, zIndex: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <Logo size={24} />
        <span style={{ font: "700 14px/1 var(--head)", letterSpacing: '.1em', textTransform: 'uppercase', whiteSpace: 'nowrap' }}>
          Vayu <span style={{ color: 'var(--accent)' }}>Drishti</span>
        </span>
      </div>
      <nav style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'var(--glass-bg)', backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)', border: '1px solid var(--glass-border)', padding: '0 14px', height: 34, borderRadius: 'var(--radius-full)', marginRight: 16 }}>
          <span style={{ font: "600 11px/1 var(--head)", color: 'var(--muted)', textTransform: 'uppercase' }}>PIN</span>
          <input
            value={pinInput}
            onChange={e => setPinInput(e.target.value.replace(/\D/g, '').slice(0, 6))}
            onBlur={() => { if (pinInput.length === 6) setPincode(pinInput); else setPinInput(pincode); }}
            onKeyDown={e => {
              if (e.key === 'Enter') {
                if (pinInput.length === 6) setPincode(pinInput);
                e.target.blur();
              }
            }}
            placeholder="530001"
            style={{ font: "600 13px/1 var(--head)", letterSpacing: '.06em', border: 'none', background: 'transparent', color: 'var(--ink)', width: 60, outline: 'none' }}
          />
        </div>
        {NAV.map(n => {
          const here = pathname === n.to;
          return here ? (
            <span key={n.to} style={{ font: "600 12px/1 var(--body)", padding: '8px 14px', background: 'var(--ink)', color: 'var(--surface)', borderRadius: 'var(--radius-full)' }}>{n.label}</span>
          ) : (
            <Link key={n.to} to={n.to} style={{ font: "600 12px/1 var(--body)", padding: '8px 14px', color: 'var(--muted)', borderRadius: 'var(--radius-full)' }}>{n.label}</Link>
          );
        })}
        <button onClick={toggle} title="Toggle dark theme" style={{ marginLeft: 6, width: 36, height: 36,
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center', border: '1px solid var(--glass-border)',
          background: 'var(--glass-bg)', backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)', borderRadius: '50%', color: 'var(--ink)', fontSize: 15, flex: 'none' }}>
          {dark ? '\u2600' : '\u263e'}
        </button>
      </nav>
    </header>
  );
}
