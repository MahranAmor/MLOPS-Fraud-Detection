'use client';

import { useEffect, useState, useRef } from 'react';
import { createLiveStream } from '@/services/api';

interface LiveTransaction {
  id?: string;
  name?: string;
  merchant?: string;
  category?: string;
  amount?: number;
  amt?: number;
  is_fraud: boolean;
  prediction?: 0 | 1;
  probability?: number;
  timestamp?: string;
}

const CATEGORY_EMOJI: Record<string, string> = {
  grocery_pos: '🛒',
  gas_transport: '⛽',
  home: '🏠',
  shopping_net: '🛍',
  entertainment: '🎭',
  food_dining: '🍽',
  personal_care: '💅',
  health_fitness: '💊',
  shopping_pos: '🏪',
  kids_pets: '🐾',
  misc_net: '🌐',
  misc_pos: '💳',
  travel: '✈️',
};

export default function LivePage() {
  const [transactions, setTransactions] = useState<LiveTransaction[]>([]);
  const [connected, setConnected] = useState(false);
  const [stats, setStats] = useState({ total: 0, frauds: 0 });
  const esRef = useRef<EventSource | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const es = createLiveStream(
      (data: LiveTransaction) => {
        const tx = {
          ...data,
          id: data.id || Date.now().toString(),
          timestamp: data.timestamp || new Date().toLocaleTimeString(),
        };
        setTransactions(prev => [tx, ...prev].slice(0, 50));
        setStats(prev => ({
          total: prev.total + 1,
          frauds: prev.frauds + (tx.is_fraud ? 1 : 0),
        }));
      },
      () => setConnected(false),
    );
    esRef.current = es;
    es.onopen = () => setConnected(true);

    return () => {
      es.close();
    };
  }, []);

  const fraudRate = stats.total > 0 ? ((stats.frauds / stats.total) * 100).toFixed(1) : '0.0';

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 32, flexWrap: 'wrap', gap: 16 }}>
        <div>
          <h1 className="section-title">
            <span style={{
              width: 42,
              height: 42,
              borderRadius: 12,
              background: 'rgba(0,230,118,0.1)',
              border: '1px solid rgba(0,230,118,0.25)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 20,
              flexShrink: 0,
            }}>◉</span>
            Live Monitor
          </h1>
          <p className="section-subtitle">Real-time transaction stream — fraud flagged instantly.</p>
        </div>

        {/* Connection status */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 16px', borderRadius: 24, border: '1px solid', borderColor: connected ? 'rgba(0,230,118,0.3)' : 'rgba(255,51,85,0.3)', background: connected ? 'rgba(0,230,118,0.05)' : 'rgba(255,51,85,0.05)' }}>
          <span className={`status-dot ${connected ? 'online' : ''}`} style={!connected ? { background: 'var(--fraud-red)', boxShadow: '0 0 8px var(--fraud-red)' } : {}} />
          <span style={{ fontSize: 12, fontWeight: 700, color: connected ? 'var(--safe-green)' : 'var(--fraud-red)' }}>
            {connected ? 'Connected' : 'Connecting...'}
          </span>
        </div>
      </div>

      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 28 }}>
        <div className="stat-block">
          <div className="stat-value">{stats.total}</div>
          <div className="stat-label">Total Seen</div>
        </div>
        <div className="stat-block">
          <div className="stat-value" style={{ WebkitTextFillColor: 'var(--fraud-red)', color: 'var(--fraud-red)' }}>{stats.frauds}</div>
          <div className="stat-label">Frauds Detected</div>
        </div>
        <div className="stat-block">
          <div className="stat-value">{fraudRate}%</div>
          <div className="stat-label">Fraud Rate</div>
        </div>
      </div>

      {/* Empty state */}
      {transactions.length === 0 && (
        <div className="card" style={{ padding: '60px 32px', textAlign: 'center' }}>
          <div style={{ fontSize: 48, marginBottom: 16, opacity: 0.4 }}>📡</div>
          <div style={{ fontSize: 15, color: 'var(--text-secondary)', marginBottom: 8 }}>
            Waiting for transactions...
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            Transactions will appear here in real-time as they come in.
          </div>
        </div>
      )}

      {/* Transaction feed */}
      {transactions.length > 0 && (
        <div ref={listRef} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {transactions.map((tx) => {
            const amount = tx.amount ?? tx.amt ?? 0;
            const category = tx.category ?? 'misc_net';
            const emoji = CATEGORY_EMOJI[category] ?? '💳';
            const name = tx.name ?? 'Unknown';
            const merchant = tx.merchant ?? 'Unknown Merchant';
            const time = tx.timestamp ?? '';

            return (
              <div key={tx.id} className={`live-tx-card ${tx.is_fraud ? 'fraud' : 'safe'}`}>
                <div className="tx-avatar" style={{
                  background: tx.is_fraud ? 'rgba(255,51,85,0.1)' : 'rgba(0,230,118,0.08)',
                  border: `1px solid ${tx.is_fraud ? 'rgba(255,51,85,0.2)' : 'rgba(0,230,118,0.15)'}`,
                }}>
                  {emoji}
                </div>
                <div className="tx-info">
                  <div className="tx-name">{name}</div>
                  <div className="tx-meta">{merchant} · {category} · {time}</div>
                </div>
                {tx.probability !== undefined && (
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'right', flexShrink: 0 }}>
                    <div style={{ fontWeight: 700, color: tx.is_fraud ? 'var(--fraud-red)' : 'var(--text-muted)' }}>
                      {(tx.probability * 100).toFixed(0)}%
                    </div>
                    <div>confidence</div>
                  </div>
                )}
                <div className="tx-amount">${amount.toFixed(2)}</div>
                <span className={`badge ${tx.is_fraud ? 'badge-fraud' : 'badge-safe'}`} style={{ flexShrink: 0 }}>
                  {tx.is_fraud ? '⚠ FRAUD' : '✓ SAFE'}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
