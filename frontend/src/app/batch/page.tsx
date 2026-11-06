import FileUploader from '@/components/FileUploader';

export default function BatchPage() {
  return (
    <div style={{ maxWidth: 1000, margin: '0 auto' }}>
      <div style={{ marginBottom: 32 }}>
        <h1 className="section-title">
          <span style={{
            width: 42,
            height: 42,
            borderRadius: 12,
            background: 'rgba(30,144,255,0.1)',
            border: '1px solid rgba(30,144,255,0.25)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 20,
            color: 'var(--accent-blue)',
            flexShrink: 0,
          }}>⊞</span>
          Batch Analysis
        </h1>
        <p className="section-subtitle">
          Upload a CSV file containing multiple transactions for bulk analysis.
        </p>
      </div>

      <FileUploader />
    </div>
  );
}
