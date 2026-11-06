'use client';

import Link from 'next/link';

export default function HomePage() {
  const features = [
    {
      href: '/live',
      icon: '◉',
      title: 'Live Monitor',
      description: 'Stream real-time transactions and detect fraud as it happens with instant alerts.',
      tag: 'Real-Time',
      tagClass: 'badge-live',
      accent: 'var(--safe)',
      accentBg: 'var(--safe-bg)',
    },
    {
      href: '/predict',
      icon: '⬡',
      title: 'Single Predict',
      description: 'Enter transaction details manually and get an instant fraud probability score.',
      tag: 'Analysis',
      tagClass: 'badge-blue',
      accent: 'var(--accent)',
      accentBg: 'var(--accent-bg)',
    },
    {
      href: '/batch',
      icon: '⊞',
      title: 'Batch Analysis',
      description: 'Upload a CSV file with multiple transactions and analyze them all at once.',
      tag: 'Bulk',
      tagClass: 'badge-bulk',
      accent: 'var(--text-2)',
      accentBg: 'var(--bg-2)',
    },
  ];

  return (
    <div style={{ maxWidth: 960, margin: '48px auto 0' }}>
      {/* Hero */}
      <div style={{ marginBottom: 72 }}>
        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: 7,
          padding: '4px 14px', borderRadius: 20,
          border: '1px solid #c7d4f8',
          background: '#eef2ff',
          fontSize: 11, fontWeight: 600, letterSpacing: '0.06em',
          color: '#2d5be3', textTransform: 'uppercase', marginBottom: 24,
        }}>
          <span style={{ width: 5, height: 5, borderRadius: '50%', background: '#2d5be3', display: 'inline-block' }} />
          AI-Powered Fraud Detection
        </div>

        <h1 style={{
          fontFamily: 'var(--font-sans)',
          fontSize: 'clamp(38px, 6vw, 62px)',
          fontWeight: 800, letterSpacing: '-2px', lineHeight: 1.08,
          color: 'var(--text-1)', marginBottom: 20, maxWidth: 680,
        }}>
          <span style={{ color: '#1a1a1a' }}>Detect Fraud.</span><br />
          <span style={{ color: '#2d5be3' }}>
            Protect Revenue.
          </span>
        </h1>

        <p style={{
          fontSize: 15, color: 'var(--text-3)', maxWidth: 480,
          lineHeight: 1.7, marginBottom: 36,
        }}>
          Machine learning model trained on millions of transactions to identify fraudulent activity with high precision.
        </p>

        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <Link href="/live" className="btn-primary" style={{ textDecoration: 'none' }}>
            Start Live Monitor
          </Link>
          <Link href="/predict" className="btn-secondary" style={{ textDecoration: 'none' }}>
            Try Prediction
          </Link>
        </div>
      </div>

      {/* Divider */}
      <div style={{ borderTop: '1px solid var(--border)', marginBottom: 40 }} />

      {/* Feature cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 16 }}>
        {features.map(({ href, icon, title, description, tag, tagClass, accent, accentBg }) => (
          <Link key={href} href={href} style={{ textDecoration: 'none' }}>
            <div
              className="card"
              style={{ padding: '24px', height: '100%', cursor: 'pointer' }}
              onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.transform = 'translateY(-3px)'; }}
              onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.transform = 'translateY(0)'; }}
            >
              <div style={{
                width: 44, height: 44, borderRadius: 10,
                background: accentBg, border: '1px solid var(--border)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 20, color: accent, marginBottom: 18,
              }}>
                {icon}
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                <h3 style={{ fontFamily: 'var(--font-sans)', fontSize: 16, fontWeight: 700, color: 'var(--text-1)', letterSpacing: '-0.2px' }}>
                  {title}
                </h3>
                <span className={`badge ${tagClass}`}>{tag}</span>
              </div>

              <p style={{ fontSize: 13, color: 'var(--text-3)', lineHeight: 1.65 }}>
                {description}
              </p>

              <div style={{ marginTop: 18, fontSize: 12, color: accent, fontWeight: 600, letterSpacing: '0.01em' }}>
                Open →
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}