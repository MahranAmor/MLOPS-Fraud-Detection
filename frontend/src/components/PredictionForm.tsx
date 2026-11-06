'use client';

import { useState } from 'react';
import { predictTransaction, PredictRequest } from '@/services/api';
import StatusCard from './StatusCard';

const CATEGORIES = [
  'grocery_pos', 'gas_transport', 'home', 'shopping_net', 'entertainment',
  'food_dining', 'personal_care', 'health_fitness', 'shopping_pos', 'kids_pets',
  'misc_net', 'misc_pos', 'travel',
];

const US_STATES = [
  'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN',
  'IA','KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV',
  'NH','NJ','NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN',
  'TX','UT','VT','VA','WA','WV','WI','WY',
];

function NumberInput({ label, value, onChange, step = 1, decimals = 0 }: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  step?: number;
  decimals?: number;
}) {
  const fmt = (v: number) => decimals > 0 ? v.toFixed(decimals) : String(v);
  return (
    <div className="form-group">
      <label className="form-label">{label}</label>
      <div className="number-input-wrapper">
        <button className="number-btn" onClick={() => onChange(parseFloat((value - step).toFixed(decimals + 1)))}>−</button>
        <input
          type="number"
          value={fmt(value)}
          onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
          step={step}
        />
        <button className="number-btn" onClick={() => onChange(parseFloat((value + step).toFixed(decimals + 1)))}>+</button>
      </div>
    </div>
  );
}

const today = new Date().toISOString().slice(0, 10);
const nowTime = new Date().toTimeString().slice(0, 5);

export default function PredictionForm() {
  const [form, setForm] = useState<PredictRequest>({
    amt: 100,
    category: 'grocery_pos',
    gender: 'M',
    state: 'NY',
    job: 'Developer',
    lat: 40.7128,
    long: -74.006,
    merch_lat: 40.72,
    merch_long: -74.01,
    trans_date_trans_time: `${today} ${nowTime}:00`,
    dob: '1990-01-01',
  });

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ isFraud: boolean; probability?: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const set = (key: keyof PredictRequest, val: any) =>
    setForm(prev => ({ ...prev, [key]: val }));

  const handleSubmit = async () => {
    setLoading(true);
    setResult(null);
    setError(null);
    try {
      const res = await predictTransaction(form);
      setResult({ isFraud: res.is_fraud, probability: res.probability });
    } catch (e: any) {
      setError(e.message || 'Unknown error occurred');
    } finally {
      setLoading(false);
    }
  };

  const [transDate, transTime] = form.trans_date_trans_time.split(' ');

  return (
    <div className="card" style={{ padding: '32px', maxWidth: 900, margin: '0 auto' }}>
      <div className="form-grid">
        {/* Left column */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <NumberInput
            label="Amount ($)"
            value={form.amt}
            onChange={(v) => set('amt', Math.max(0, v))}
            step={10}
            decimals={2}
          />

          <div className="form-group">
            <label className="form-label">Category</label>
            <select className="form-select" value={form.category} onChange={e => set('category', e.target.value)}>
              {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">Gender</label>
            <select className="form-select" value={form.gender} onChange={e => set('gender', e.target.value)}>
              <option value="M">Male</option>
              <option value="F">Female</option>
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">State</label>
            <select className="form-select" value={form.state} onChange={e => set('state', e.target.value)}>
              {US_STATES.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">Job</label>
            <input className="form-input" type="text" value={form.job} onChange={e => set('job', e.target.value)} placeholder="e.g. Software Engineer" />
          </div>

          <div className="form-group">
            <label className="form-label">Date of Birth</label>
            <input className="form-input" type="date" value={form.dob} onChange={e => set('dob', e.target.value)} />
          </div>
        </div>

        {/* Right column */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div className="form-group">
            <label className="form-label">Transaction Date</label>
            <input className="form-input" type="date" value={transDate}
              onChange={e => set('trans_date_trans_time', `${e.target.value} ${transTime}:00`)} />
          </div>

          <div className="form-group">
            <label className="form-label">Transaction Time</label>
            <input className="form-input" type="time" value={transTime}
              onChange={e => set('trans_date_trans_time', `${transDate} ${e.target.value}:00`)} />
          </div>

          <div style={{ paddingTop: 4 }}>
            <div className="form-label" style={{ marginBottom: 16 }}>📍 Location Coordinates</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <NumberInput label="Lat" value={form.lat} onChange={v => set('lat', v)} step={0.01} decimals={4} />
              <NumberInput label="Long" value={form.long} onChange={v => set('long', v)} step={0.01} decimals={4} />
            </div>
          </div>

          <div>
            <div className="form-label" style={{ marginBottom: 16 }}>🏪 Merchant Coordinates</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <NumberInput label="Merch Lat" value={form.merch_lat} onChange={v => set('merch_lat', v)} step={0.01} decimals={4} />
              <NumberInput label="Merch Long" value={form.merch_long} onChange={v => set('merch_long', v)} step={0.01} decimals={4} />
            </div>
          </div>
        </div>
      </div>

      {/* Submit */}
      <div style={{ marginTop: 32 }}>
        <button className="btn-primary" onClick={handleSubmit} disabled={loading}>
          {loading ? <span className="spinner" /> : null}
          {loading ? 'Analyzing...' : 'Analyze Transaction'}
        </button>
      </div>

      {/* Result */}
      {error && (
        <div className="alert alert-error" style={{ marginTop: 24 }}>
          ⚠ {error}
        </div>
      )}
      {result && (
        <div style={{ marginTop: 24 }}>
          <StatusCard isFraud={result.isFraud} probability={result.probability} />
        </div>
      )}
    </div>
  );
}
