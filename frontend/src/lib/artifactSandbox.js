// Pure helpers for the Artifact Viewer (kept framework-free so they can be unit-tested with `node --test`).
//
// Isolation layers applied to every artifact (see architecture.md section "Artifact security"):
//   1. The <iframe> has sandbox="" -> no scripts, no same-origin, no forms, no popups, no top navigation.
//   2. A Content-Security-Policy <meta> is injected as the FIRST thing in the document ->
//      no network of any kind (no remote images/fonts/styles/fetch), only inline CSS and data: images.
//   3. Markdown is rendered by an escape-first renderer (all HTML in the source is neutralised).
//   (The backend additionally sanitizes generated HTML with an allow-list before storing it.)

export const ARTIFACT_CSP =
  "default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; base-uri 'none'; form-action 'none'";

export const SANDBOX_ATTR = '';

const BASE_STYLE = `
body{font-family:Georgia,'Times New Roman',serif;line-height:1.75;font-size:16px;max-width:760px;margin:0 auto;padding:28px 24px;background:#111018;color:#F5F2EA}
h1,h2,h3,h4{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;color:#FFFFFF;line-height:1.25;margin:1.4em 0 .5em}
h1{font-size:28px}h2{font-size:22px;border-bottom:1px solid #35313F;padding-bottom:6px}h3{font-size:18px;color:#D7FF5F}
a{color:#D7FF5F}strong{color:#FFFFFF}blockquote{border-left:3px solid #D7FF5F;margin:1em 0;padding-left:1em;color:#A6A1B2;font-style:italic}
code{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:14px;background:#1B1924;padding:2px 6px;border-radius:4px;color:#D7FF5F}
pre{background:#1B1924;padding:12px 14px;border-radius:8px;overflow:auto;border:1px solid #35313F}pre code{background:none;padding:0}
hr{border:0;border-top:1px solid #35313F;margin:1.5em 0}li{margin-bottom:6px}
`;

export function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function inline(raw) {
  let s = escapeHtml(raw);
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<em>$2</em>');
  // Links: only http(s) targets survive; the sandbox prevents navigation anyway (shown as text + URL on hover).
  s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (_m, label, url) => `<a href="${url}" rel="noreferrer noopener">${label}</a>`);
  return s;
}

/** Escape-first Markdown -> HTML (headings, lists, quotes, code fences, rules, bold/italic/code/links). */
export function renderMarkdown(md) {
  const lines = String(md ?? '').replace(/\r\n/g, '\n').split('\n');
  const out = [];
  let i = 0;
  let para = [];
  const flush = () => {
    if (para.length) {
      out.push(`<p>${inline(para.join(' '))}</p>`);
      para = [];
    }
  };
  while (i < lines.length) {
    const line = lines[i];
    if (/^```/.test(line)) {
      flush();
      const buf = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]);
      i++;
      out.push(`<pre><code>${escapeHtml(buf.join('\n'))}</code></pre>`);
      continue;
    }
    const h = /^(#{1,6})\s+(.*)$/.exec(line);
    if (h) {
      flush();
      out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`);
      i++;
      continue;
    }
    if (/^\s*([-*_])\1{2,}\s*$/.test(line)) {
      flush();
      out.push('<hr>');
      i++;
      continue;
    }
    if (/^>\s?/.test(line)) {
      flush();
      const buf = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) buf.push(lines[i++].replace(/^>\s?/, ''));
      out.push(`<blockquote>${inline(buf.join(' '))}</blockquote>`);
      continue;
    }
    const ul = /^\s*[-*+]\s+/.test(line);
    const ol = /^\s*\d+[.)]\s+/.test(line);
    if (ul || ol) {
      flush();
      const re = ul ? /^\s*[-*+]\s+/ : /^\s*\d+[.)]\s+/;
      const items = [];
      while (i < lines.length && re.test(lines[i])) items.push(`<li>${inline(lines[i++].replace(re, ''))}</li>`);
      out.push(`<${ul ? 'ul' : 'ol'}>${items.join('')}</${ul ? 'ul' : 'ol'}>`);
      continue;
    }
    if (!line.trim()) {
      flush();
      i++;
      continue;
    }
    para.push(line.trim());
    i++;
  }
  flush();
  return out.join('\n');
}

const CSP_META = `<meta http-equiv="Content-Security-Policy" content="${ARTIFACT_CSP}">`;

/**
 * Builds the srcdoc for the sandboxed iframe. The CSP meta is placed FIRST (before any artifact
 * content) so nothing in the artifact can load a resource before the policy is in force.
 */
export function buildSandboxDocument(content, artifactType) {
  const isMarkdown = String(artifactType || '').toLowerCase().includes('markdown') || artifactType === 'md';
  let body;
  if (isMarkdown) {
    body = `<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>${BASE_STYLE}</style></head><body>${renderMarkdown(content)}</body></html>`;
  } else {
    body = String(content ?? '').replace(/^\s*<!doctype[^>]*>/i, '');
    if (!/<html[\s>]/i.test(body)) {
      body = `<html lang="en"><head><meta charset="UTF-8"><style>${BASE_STYLE}</style></head><body>${body}</body></html>`;
    }
  }
  return `<!DOCTYPE html>${CSP_META}${body}`;
}

/** Human label for the viewer badge. */
export function artifactLabel(artifact) {
  const type = String(artifact?.artifact_type || '').toLowerCase();
  const title = String(artifact?.title || '');
  if (type === 'markdown') return 'Markdown';
  if (/essay|ship 30/i.test(title) || (type === 'html' && (artifact?.word_count || 0) >= 900)) return 'Ship 30 for 30';
  return 'HTML / CSS';
}
