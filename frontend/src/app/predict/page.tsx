import PredictionForm from '@/components/PredictionForm';

export default function PredictPage() {
  return (
    <div style={{ maxWidth: 1000, margin: '0 auto' }}>
      <div style={{ marginBottom: 32 }}>
        <h1 className="section-title">
          <span style={{
            width: 42,
            height: 42,
            borderRadius: 12,
            background: 'rgba(0,212,255,0.1)',
            border: '1px solid rgba(0,212,255,0.25)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 20,
            color: 'var(--accent-cyan)',
            flexShrink: 0,
          }}>⬡</span>
          Analyze Transaction
        </h1>
        <p className="section-subtitle">
          Enter transaction details below to check for fraud probability.
        </p>
      </div>

      <PredictionForm />
    </div>
  );
}
