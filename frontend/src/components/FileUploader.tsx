'use client';

import { useState, useRef, DragEvent } from 'react';
import { predictBatch, BatchResponse } from '@/services/api';

export default function FileUploader() {
  const [file, setFile] = useState<File | null>(null);
  const [dragover, setDragover] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BatchResponse | null>(null);
  const [preview, setPreview] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = (f: File) => {
    if (!f.name.endsWith('.csv')) {
      setError('Please upload a CSV file.');
      return;
    }
    setFile(f);
    setError(null);
    setResult(null);

    // Parse preview
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result as string;
      const lines = text.trim().split('\n');
      const headers = lines[0].split(',').map(h => h.trim().replace(/"/g, ''));
      const rows = lines.slice(1, 6).map(line => {
        const vals = line.split(',').map(v => v.trim().replace(/"/g, ''));
        return Object.fromEntries(headers.map((h, i) => [h, vals[i] ?? '']));
      });
      setPreview(rows.length > 0 ? [{ __headers: headers }, ...rows] : []);
    };
    reader.readAsText(f);
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragover(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  };

  const handleProcess = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const res = await predictBatch(file);
      setResult(res);
    } catch (e: any) {
      setError(e.message || 'Processing failed');
    } finally {
      setLoading(false);
    }
  };

  const headers = preview[0]?.__headers as string[] | undefined;
  const rows = preview.slice(1);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24, maxWidth: 1000, margin: '0 auto' }}>
      {/* Drop zone */}
      <div
        className={`drop-zone ${dragover ? 'dragover' : ''}`}
        onDrop={onDrop}
        onDragOver={(e) => { e.preventDefault(); setDragover(true); }}
        onDragLeave={() => setDragover(false)}
        onClick={() => inputRef.current?.click()}
      >
        <div className="drop-zone-icon">📤</div>
        <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 6 }}>
          Drag and drop file here
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          Limit 200MB per file • CSV
        </div>
        <input
          ref={inputRef}
          type="file"
          accept=".csv"
          style={{ display: 'none' }}
          onChange={e => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
        />
      </div>

      {/* File info */}
      {file && (
        <div className="alert alert-info" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span>📄</span>
          <span style={{ flex: 1 }}>
            <strong>{file.name}</strong> — {(file.size / 1024).toFixed(1)} KB
          </span>
          <span style={{ color: 'var(--safe-green)', fontWeight: 700 }}>
            ✓ File uploaded successfully. Click below to process.
          </span>
          <button
            style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 18 }}
            onClick={() => { setFile(null); setPreview([]); setResult(null); }}
          >×</button>
        </div>
      )}

      {/* Preview table */}
      {headers && rows.length > 0 && (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', fontSize: 12, color: 'var(--text-muted)', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
            Preview (first 5 rows)
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  {headers.map(h => <th key={h}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr key={i}>
                    {headers.map(h => <td key={h}>{row[h]}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Process button */}
      {file && (
        <button className="btn-primary" onClick={handleProcess} disabled={loading} style={{ alignSelf: 'flex-start' }}>
          {loading ? <span className="spinner" /> : null}
          {loading ? 'Processing...' : 'Process Batch'}
        </button>
      )}

      {/* Error */}
      {error && (
        <div className="alert alert-error">⚠ {error}</div>
      )}

      {/* Results */}
      {result && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div className="alert alert-success">✓ Processing Complete!</div>

          {/* Stats */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
            <div className="stat-block">
              <div className="stat-value">{result.total}</div>
              <div className="stat-label">Total Transactions</div>
            </div>
            <div className="stat-block">
              <div className="stat-value" style={{ color: 'var(--fraud-red)', WebkitTextFillColor: 'var(--fraud-red)' }}>
                {result.frauds_detected}
              </div>
              <div className="stat-label">Frauds Detected</div>
            </div>
            <div className="stat-block">
              <div className="stat-value">
                {((result.frauds_detected / result.total) * 100).toFixed(1)}%
              </div>
              <div className="stat-label">Fraud Rate</div>
            </div>
          </div>

          {/* Download */}
          {result.csv_url && (
            <a href={result.csv_url} download="fraud_results.csv" className="btn-secondary" style={{ alignSelf: 'flex-start', textDecoration: 'none' }}>
              ⬇ Download Results CSV
            </a>
          )}

          {/* Results table */}
          {result.results && result.results.length > 0 && (
            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
              <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: 14, fontFamily: 'var(--font-display)', fontWeight: 700 }}>Results Preview</span>
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  Frauds Detected: <strong style={{ color: 'var(--fraud-red)' }}>{result.frauds_detected} / {result.total}</strong>
                </span>
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Prediction</th>
                      {result.results[0]?.probability !== undefined && <th>Probability</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {result.results.slice(0, 10).map((r) => (
                      <tr key={r.index}>
                        <td>{r.index}</td>
                        <td className={`predict-cell ${r.is_fraud ? 'fraud-cell' : 'safe-cell'}`}>
                          <span className={`badge ${r.is_fraud ? 'badge-fraud' : 'badge-safe'}`}>
                            {r.is_fraud ? '⚠ FRAUD' : '✓ SAFE'}
                          </span>
                        </td>
                        {r.probability !== undefined && (
                          <td>{(r.probability * 100).toFixed(1)}%</td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
