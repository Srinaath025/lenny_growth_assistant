export const ARTIFACT_CSP: string;
export const SANDBOX_ATTR: string;
export function escapeHtml(text: string): string;
export function renderMarkdown(md: string): string;
export function buildSandboxDocument(content: string, artifactType: string): string;
export function artifactLabel(artifact: { artifact_type?: string; title?: string; word_count?: number } | null | undefined): string;
