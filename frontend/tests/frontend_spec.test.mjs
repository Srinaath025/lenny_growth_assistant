import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const srcDir = path.resolve(__dirname, '../src');

test('Security Verification: ArtifactViewer uses the fully-sandboxed iframe (no scripts, no same-origin) + injected CSP', async () => {
  const content = fs.readFileSync(path.join(srcDir, 'components', 'ArtifactViewer.tsx'), 'utf8');
  assert.ok(/<iframe/.test(content), 'iframe must exist');
  assert.ok(/sandbox=\{SANDBOX_ATTR\}/.test(content), 'iframe must take its sandbox value from the audited constant');
  assert.ok(!/allow-same-origin|allow-scripts|allow-popups|allow-top-navigation/.test(content), 'no sandbox escape tokens in the viewer');
  const lib = await import('../src/lib/artifactSandbox.js');
  assert.equal(lib.SANDBOX_ATTR, '', 'sandbox attribute must be empty (maximum isolation)');
});

test('Sandbox document: CSP meta is injected FIRST and forbids network + scripts', async () => {
  const { buildSandboxDocument, ARTIFACT_CSP } = await import('../src/lib/artifactSandbox.js');
  const doc = buildSandboxDocument('<!DOCTYPE html><html><head><title>x</title></head><body><img src="https://evil.example/x.png"><script>alert(1)</script></body></html>', 'html');
  assert.ok(doc.startsWith('<!DOCTYPE html><meta http-equiv="Content-Security-Policy"'));
  assert.ok(doc.indexOf('Content-Security-Policy') < doc.indexOf('evil.example'));
  assert.match(ARTIFACT_CSP, /default-src 'none'/);
  assert.ok(!/script-src/.test(ARTIFACT_CSP) && !/connect-src/.test(ARTIFACT_CSP));
});

test('Markdown renderer neutralises HTML injection', async () => {
  const { renderMarkdown } = await import('../src/lib/artifactSandbox.js');
  const out = renderMarkdown('# Title <script>alert(1)</script>\n\n- item <img src=x onerror=alert(1)>\n\n[x](javascript:alert(1)) **b**');
  assert.ok(!/<script|<img/i.test(out));
  assert.ok(!/href="javascript:/i.test(out));
  assert.ok(/<h1>/.test(out) && /<li>/.test(out) && /<strong>b<\/strong>/.test(out));
});

test('Design Tokens: index.css includes full Impeccable Tinted Obsidian tokens', () => {
  const cssPath = path.join(srcDir, 'index.css');
  assert.ok(fs.existsSync(cssPath), 'index.css must exist');

  const css = fs.readFileSync(cssPath, 'utf8');

  // Tinted Obsidian tokens
  assert.match(css, /--bg-primary:\s*#0C0D0E/i, 'Must define --bg-primary obsidian canvas');
  assert.match(css, /--bg-secondary:\s*#141618/i, 'Must define --bg-secondary');
  assert.match(css, /--accent-amber:\s*#F59E0B/i, 'Must define --accent-amber');
  assert.match(css, /--accent-blue:\s*#38BDF8/i, 'Must define --accent-blue');
  assert.match(css, /--accent-emerald:\s*#10B981/i, 'Must define --accent-emerald');
  assert.match(css, /--accent-rose:\s*#F43F5E/i, 'Must define --accent-rose');

  // Typography tokens
  assert.match(css, /--font-serif:\s*'Newsreader'/i, 'Must define Newsreader serif font');
  assert.match(css, /--font-sans:\s*'Inter'/i, 'Must define Inter sans font');
  assert.match(css, /--font-mono:\s*'JetBrains Mono'/i, 'Must define JetBrains Mono font');
});

test('ModelSelector: Defaults to Local Ollama and gracefully disables Cloud Claude', () => {
  const modelSelPath = path.join(srcDir, 'components', 'ModelSelector.tsx');
  assert.ok(fs.existsSync(modelSelPath), 'ModelSelector.tsx must exist');

  const content = fs.readFileSync(modelSelPath, 'utf8');

  // Local Ollama default & pulsing dot
  assert.match(content, /Local Ollama/, 'Must include Local Ollama option');
  assert.match(content, /animate-pulse-dot/, 'Must show active pulsing status dot');

  // Cloud Claude disabled state & lock icon
  assert.match(content, /Cloud Claude/, 'Must include Cloud Claude option');
  assert.match(content, /ANTHROPIC_API_KEY/, 'Must explain ANTHROPIC_API_KEY requirement');
  assert.match(content, /Lock/, 'Must render lock icon when cloud key is absent');
});

test('ModelSelector: Unlocks and enables Cloud Claude when cloud.available is true', () => {
  const modelSelPath = path.join(srcDir, 'components', 'ModelSelector.tsx');
  const content = fs.readFileSync(modelSelPath, 'utf8');

  // Verify dynamic switching logic
  assert.match(content, /onSelect\('anthropic'/i, 'Must allow selecting Anthropic when cloudOk is true');
  assert.match(content, /Anthropic API Live/i, 'Must show live status label when key is available');
});

test('API Client: Maps all required REST endpoints and handles SSE streaming events', () => {
  const apiPath = path.join(srcDir, 'api.ts');
  assert.ok(fs.existsSync(apiPath), 'api.ts must exist');

  const content = fs.readFileSync(apiPath, 'utf8');

  // Check required endpoints
  assert.ok(content.includes('/health'), 'Must call /health');
  assert.ok(content.includes('/sessions'), 'Must call /sessions');
  assert.ok(content.includes('/chat'), 'Must call /chat');
  assert.ok(content.includes('/essay'), 'Must call /essay');
  assert.ok(content.includes('/artifacts/'), 'Must call /artifacts');

  // Check SSE event parsing
  assert.match(content, /currentEvent === 'token'/, 'Must handle token event');
  assert.match(content, /currentEvent === 'complete'/, 'Must handle complete event');
  assert.match(content, /currentEvent === 'error'/, 'Must handle error event');
  assert.match(content, /currentEvent === 'done'/, 'Must handle done event');
});

test('EssayModal: Encodes Ship 30 for 30 4A Framework', () => {
  const essayModalPath = path.join(srcDir, 'components', 'EssayModal.tsx');
  assert.ok(fs.existsSync(essayModalPath), 'EssayModal.tsx must exist');

  const content = fs.readFileSync(essayModalPath, 'utf8');

  // Must reflect 4A framework
  assert.match(content, /Actionable/, 'Must include Actionable');
  assert.match(content, /Analytical/, 'Must include Analytical');
  assert.match(content, /Aspirational/, 'Must include Aspirational');
  assert.match(content, /Anthropological/, 'Must include Anthropological');
  assert.match(content, /1,250/, 'Must mention target 1,250 words');
});

test('AbstentionCard: Protects against hallucination with rose-tinted guardrail styling', () => {
  const cardPath = path.join(srcDir, 'components', 'AbstentionCard.tsx');
  assert.ok(fs.existsSync(cardPath), 'AbstentionCard.tsx must exist');

  const content = fs.readFileSync(cardPath, 'utf8');

  assert.match(content, /Topic Not Discussed in Transcripts/i, 'Must have clear guardrail heading');
  assert.match(content, /var\(--accent-rose\)/i, 'Must use rose accent border/color');
});
