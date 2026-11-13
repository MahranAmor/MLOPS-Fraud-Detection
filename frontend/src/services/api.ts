// services/api.ts
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// ============================================================================
// Types
// ============================================================================

export interface PredictRequest {
  trans_date_trans_time: string;
  amt: number;
  lat: number;
  long: number;
  merch_lat: number;
  merch_long: number;
  category: string;
  gender: string;
  state: string;
  job: string;
  dob: string;
}

export interface PredictionResponse {
  is_fraud: boolean;
  probability?: number;
}

export interface BatchResponse {
  total: number;
  frauds_detected: number;
  results?: Array<{
    index: number;
    is_fraud: boolean;
    probability?: number;
  }>;
  csv_url?: string;
}

// ============================================================================
// API Functions
// ============================================================================

/**
 * Single transaction prediction
 */
export async function predictTransaction(data: PredictRequest): Promise<PredictionResponse> {
  const response = await fetch(`${API_BASE_URL}/predict`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Prediction failed: ${errorText}`);
  }

  const result = await response.json();
  
  // Convertir la réponse backend vers le format attendu
  return {
    is_fraud: result.predictions[0] === 1,
    probability: result.probabilities ? result.probabilities[0] : undefined,
  };
}

/**
 * Batch CSV prediction
 */
export async function predictBatch(file: File): Promise<BatchResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${API_BASE_URL}/predictCSV`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`CSV prediction failed: ${errorText}`);
  }

  // Le backend retourne directement un CSV
  // On va télécharger le fichier et extraire les stats
  const blob = await response.blob();
  const text = await blob.text();
  const lines = text.trim().split('\n');
  const headers = lines[0].split(',');
  const predictIndex = headers.findIndex(h => h === 'predict');
  
  let frauds = 0;
  const results: Array<{ index: number; is_fraud: boolean }> = [];
  
  lines.slice(1).forEach((line, i) => {
    const values = line.split(',');
    const prediction = parseInt(values[predictIndex]) === 1;
    if (prediction) frauds++;
    results.push({ index: i + 1, is_fraud: prediction });
  });

  // Créer une URL pour télécharger le CSV
  const csvBlob = new Blob([text], { type: 'text/csv' });
  const csv_url = URL.createObjectURL(csvBlob);

  return {
    total: lines.length - 1,
    frauds_detected: frauds,
    results,
    csv_url,
  };
}

/**
 * Health check
 */
export async function checkHealth() {
  const response = await fetch(`${API_BASE_URL}/health`);
  return response.json();
}

/**
 * Get model info
 */
export async function getModelInfo() {
  const response = await fetch(`${API_BASE_URL}/model-info`);
  return response.json();
}
/**
 * Live stream : flux Server-Sent Events de l'API (GET /stream), une entrée par
 * prédiction faite via /predict. EventSource se reconnecte tout seul après une
 * coupure. Renvoie null si le navigateur ne connaît pas EventSource (rendu serveur).
 */
export function createLiveStream(
  onMessage: (data: any) => void,
  onError: (error: Event) => void
): EventSource | null {
  if (typeof window === 'undefined' || typeof EventSource === 'undefined') return null;
  const es = new EventSource(`${API_BASE_URL}/stream`);
  es.onmessage = (event) => {
    try {
      onMessage(JSON.parse(event.data));
    } catch {
      // message illisible : ignoré
    }
  };
  es.onerror = onError;
  return es;
}