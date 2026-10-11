import {
  HealthResponse,
  SessionSummary,
  SessionDetailResponse,
  ChatRequest,
  EssayRequest,
  EssayResponse,
  ArtifactDetailResponse,
  CitationItem,
} from './types';

const API_BASE = '/api';

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) {
    throw new Error(`Failed to fetch health status: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function fetchSessions(): Promise<SessionSummary[]> {
  const res = await fetch(`${API_BASE}/sessions`);
  if (!res.ok) {
    throw new Error(`Failed to fetch sessions: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function createSession(
  title: string = 'New Growth Session',
  model_provider: string = 'ollama',
  model_name: string = 'llama3.2:3b'
): Promise<SessionSummary> {
  const res = await fetch(`${API_BASE}/sessions`, {
    method: 'POST',
    headers: JSON_HEADERS(),
    body: JSON.stringify({ title, model_provider, model_name }),
  });
  if (!res.ok) {
    throw new Error(`Failed to create session: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function fetchSession(sessionId: string): Promise<SessionDetailResponse> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch session ${sessionId}: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function updateSession(
  sessionId: string,
  updates: { title?: string; model_provider?: string; model_name?: string }
): Promise<SessionSummary> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}`, {
    method: 'PATCH',
    headers: JSON_HEADERS(),
    body: JSON.stringify(updates),
  });
  if (!res.ok) {
    throw new Error(`Failed to update session: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function deleteSession(sessionId: string): Promise<{ deleted: boolean; id: string }> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    throw new Error(`Failed to delete session: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function generateEssay(req: EssayRequest): Promise<EssayResponse> {
  const res = await fetch(`${API_BASE}/essay`, {
    method: 'POST',
    headers: JSON_HEADERS(),
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(describeError(errorBody, `Failed to generate essay: ${res.status}`));
  }
  return res.json();
}

export async function fetchArtifact(artifactId: string): Promise<ArtifactDetailResponse> {
  const res = await fetch(`${API_BASE}/artifacts/${artifactId}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch artifact ${artifactId}: ${res.status}`);
  }
  return res.json();
}

export function getRawArtifactUrl(artifactId: string): string {
  return `${API_BASE}/artifacts/${artifactId}/raw`;
}

const CLIENT_ID_KEY = 'lenny_client_id';
function clientId(): string {
  try {
    let id = localStorage.getItem(CLIENT_ID_KEY);
    if (!id) {
      id = (crypto.randomUUID?.() ?? `c-${Date.now()}-${Math.random().toString(36).slice(2)}`);
      localStorage.setItem(CLIENT_ID_KEY, id);
    }
    return id;
  } catch {
    return 'anonymous';
  }
}
const JSON_HEADERS = () => ({ 'Content-Type': 'application/json', 'X-Client-Id': clientId() });

/** Reads the structured error contract {error:{code,message,hint,request_id}} (falls back to FastAPI `detail`). */
export function describeError(body: any, fallback: string): string {
  const e = body?.error;
  if (e?.message) return `${e.message}${e.hint ? ` — ${e.hint}` : ''}${e.request_id ? ` (ref ${e.request_id})` : ''}`;
  return body?.detail || fallback;
}

export interface StreamChatCallbacks {
  onStatus?: (text: string) => void;
  onArtifact?: (artifactId: string, intent: string) => void;
  onToken: (token: string) => void;
  onComplete: (data: {
    message_id: string;
    session_id: string;
    role: string;
    content: string;
    is_abstention: boolean;
    citations: CitationItem[];
    duration_seconds: number;
  }) => void;
  onError: (error: string) => void;
}

export async function streamChat(
  req: ChatRequest,
  callbacks: StreamChatCallbacks,
  signal?: AbortSignal
): Promise<void> {
  const response = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: JSON_HEADERS(),
    body: JSON.stringify({ ...req, stream: true }),
    signal,
  });

  if (!response.ok) {
    const errText = await response.text();
    let parsedBody: any = null;
    try { parsedBody = JSON.parse(errText); } catch { /* not JSON */ }
    callbacks.onError(describeError(parsedBody, `Chat request failed (${response.status}): ${errText}`));
    return;
  }

  if (!response.body) {
    callbacks.onError('ReadableStream not supported by browser.');
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      // Keep unfinished line in buffer
      buffer = lines.pop() || '';

      let currentEvent = '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) {
          currentEvent = '';
          continue;
        }

        if (trimmed.startsWith('event: ')) {
          currentEvent = trimmed.slice(7).trim();
        } else if (trimmed.startsWith('data: ')) {
          const dataStr = trimmed.slice(6).trim();

          if (currentEvent === 'token') {
            try {
              const parsed = JSON.parse(dataStr);
              callbacks.onToken(parsed.text || '');
            } catch {
              callbacks.onToken(dataStr);
            }
          } else if (currentEvent === 'status') {
            try { callbacks.onStatus?.(JSON.parse(dataStr).text || ''); } catch { /* ignore */ }
          } else if (currentEvent === 'artifact') {
            try { const a = JSON.parse(dataStr); callbacks.onArtifact?.(a.artifact_id, a.intent); } catch { /* ignore */ }
          } else if (currentEvent === 'complete') {
            try {
              const parsed = JSON.parse(dataStr);
              callbacks.onComplete(parsed);
            } catch (e) {
              console.error('Failed to parse SSE complete payload', e);
            }
          } else if (currentEvent === 'error') {
            try {
              const parsed = JSON.parse(dataStr);
              callbacks.onError(describeError({ error: { message: parsed.error, hint: parsed.hint, request_id: parsed.request_id } }, 'Unknown error'));
            } catch {
              callbacks.onError(dataStr);
            }
          } else if (currentEvent === 'done' || dataStr === '[DONE]') {
            return;
          }
        }
      }
    }
  } catch (err: unknown) {
    if (signal?.aborted) {
      console.log('Stream cancelled by user');
      return;
    }
    const message = err instanceof Error ? err.message : String(err);
    callbacks.onError(message);
  }
}
