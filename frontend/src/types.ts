export interface OllamaHealth {
  available: boolean;
  url: string;
  model: string;
  error?: string | null;
}

export interface CloudHealth {
  available: boolean;
  provider: string;
  key_configured: boolean;
  model?: string;
}

export interface DatabaseHealth {
  connected: boolean;
  total_chunks: number;
}

export interface HealthResponse {
  status: 'healthy' | 'degraded' | 'unhealthy';
  version?: string;
  ingestion?: { state: string; detail?: string };
  ollama: OllamaHealth;
  cloud: CloudHealth;
  database: DatabaseHealth;
}

export interface SessionSummary {
  id: string;
  title: string;
  model_provider: string;
  model_name: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface CitationItem {
  id?: string;
  episode_title: string;
  guest_name: string;
  youtube_url: string;
  timestamp_seconds?: number | null;
  quote_text: string;
}

export interface MessageItem {
  id: string;
  session_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  is_abstention: boolean;
  created_at: string;
  citations: CitationItem[];
}

export interface ArtifactSummary {
  id: string;
  session_id?: string | null;
  message_id?: string | null;
  title: string;
  artifact_type: string;
  word_count: number;
  created_at: string;
}

export interface ArtifactDetailResponse {
  id: string;
  session_id?: string | null;
  message_id?: string | null;
  title: string;
  artifact_type: string;
  content: string;
  word_count: number;
  created_at: string;
}

export interface SessionDetailResponse {
  id: string;
  title: string;
  model_provider: string;
  model_name: string;
  created_at: string;
  updated_at: string;
  messages: MessageItem[];
  artifacts: ArtifactSummary[];
}

export interface ChatRequest {
  session_id: string;
  message: string;
  model_provider?: string;
  model_name?: string;
  stream?: boolean;
}

export interface ChatResponse {
  message_id: string;
  session_id: string;
  role: string;
  content: string;
  is_abstention: boolean;
  citations: CitationItem[];
  duration_seconds: number;
}

export interface EssayRequest {
  topic: string;
  session_id?: string | null;
  guest_filter?: string | null;
  model_provider?: string;
}

export interface EssayResponse {
  artifact_id: string;
  session_id?: string | null;
  title: string;
  subtitle: string;
  topic: string;
  word_count: number;
  is_valid_word_count: boolean;
  has_all_4a_sections: boolean;
  guest_attributions: string[];
  citations: CitationItem[];
  markdown_content: string;
  html_content: string;
  created_at: string;
}
