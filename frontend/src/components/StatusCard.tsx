'use client';

interface StatusCardProps {
  isFraud: boolean;
  probability?: number;
  message?: string;
}

export default function StatusCard({ isFraud, probability, message }: StatusCardProps) {
  return (
    <div className={`result-card ${isFraud ? 'fraud' : 'safe'}`}>
      <span className="result-icon">{isFraud ? '🚨' : '✅'}</span>
      <div className={`result-title ${isFraud ? 'fraud' : 'safe'}`}>
        {isFraud ? 'Fraudulent Transaction' : 'Legitimate Transaction'}
      </div>
      {probability !== undefined && (
        <div style={{ marginTop: 12 }}>
          <div style={{
            fontSize: 11,
            textTransform: 'uppercase',
            letterSpacing: '0.1em',
            color: 'var(--text-muted)',
            marginBottom: 8,
          }}>
            Fraud Probability
          </div>
          <div style={{ position: 'relative', height: 6, background: 'rgba(255,255,255,0.06)', borderRadius: 3, overflow: 'hidden' }}>
            <div style={{
              position: 'absolute',
              left: 0,
              top: 0,
              height: '100%',
              width: `${(probability * 100).toFixed(1)}%`,
              background: isFraud
                ? 'linear-gradient(90deg, #ff3355, #ff6b35)'
                : 'linear-gradient(90deg, #00e676, #1de9b6)',
              borderRadius: 3,
              transition: 'width 0.8s ease',
            }} />
          </div>
          <div style={{ fontSize: 20, fontWeight: 800, marginTop: 8, fontFamily: 'var(--font-display)', color: isFraud ? 'var(--fraud-red)' : 'var(--safe-green)' }}>
            {(probability * 100).toFixed(1)}%
          </div>
        </div>
      )}
      <p className="result-message">
        {message || (isFraud
          ? 'This transaction has been flagged as potentially fraudulent.'
          : 'This transaction appears to be safe.'
        )}
      </p>
    </div>
  );
}
