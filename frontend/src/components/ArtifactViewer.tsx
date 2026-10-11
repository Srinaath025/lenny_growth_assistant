import React, { useState, useEffect } from 'react';
import {
  X,
  Copy,
  Check,
  Download,
  Eye,
  Code2,
  ShieldCheck,
  FileText,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
  Layers,
  Sparkles,
} from 'lucide-react';
import { ArtifactDetailResponse, ArtifactSummary, SessionDetailResponse } from '../types';
import { buildSandboxDocument, artifactLabel, SANDBOX_ATTR } from '../lib/artifactSandbox.js';
import { fetchSession } from '../api';

interface ArtifactViewerProps {
  artifact: ArtifactDetailResponse | null;
  artifacts?: ArtifactSummary[];
  sessionId?: string | null;
  onSelectArtifact?: (id: string) => void;
  onClose: () => void;
}

export const ArtifactViewer: React.FC<ArtifactViewerProps> = ({
  artifact,
  artifacts = [],
  sessionId,
  onSelectArtifact,
  onClose,
}) => {
  const [activeTab, setActiveTab] = useState<'preview' | 'code'>('preview');
  const [copied, setCopied] = useState(false);
  const [internalArtifacts, setInternalArtifacts] = useState<ArtifactSummary[]>(artifacts);

  // Sync or fetch artifacts from session whenever artifact or sessionId changes
  useEffect(() => {
    if (artifacts && artifacts.length > 0) {
      setInternalArtifacts(artifacts);
    } else if (sessionId) {
      fetchSession(sessionId)
        .then((s: SessionDetailResponse) => {
          if (s.artifacts && s.artifacts.length > 0) {
            setInternalArtifacts(s.artifacts);
          }
        })
        .catch(console.warn);
    }
  }, [artifacts, sessionId, artifact?.id]);

  if (!artifact) return null;

  const effectiveArtifacts = internalArtifacts.length > 0 ? internalArtifacts : artifacts;

  const handleCopy = () => {
    navigator.clipboard.writeText(artifact.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const extension = artifact.artifact_type.includes('html') ? 'html' : 'md';
    const blob = new Blob([artifact.content], {
      type: extension === 'html' ? 'text/html' : 'text/markdown',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${artifact.title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}.${extension}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const currentIndex = effectiveArtifacts.findIndex((a) => a.id === artifact.id);

  return (
    <aside className="artifact-drawer" aria-label="Artifact Viewer">
      {/* Drawer Header */}
      <div
        style={{
          padding: '14px 16px',
          borderBottom: '1px solid #35313F',
          background: 'rgba(23, 21, 32, 0.95)',
          backdropFilter: 'blur(12px)',
          display: 'flex',
          flexDirection: 'column',
          gap: '10px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <FileText size={18} color="#D7FF5F" />
            <span style={{ fontWeight: 600, fontSize: '14px', color: '#F5F2EA' }}>
              Artifact Viewer
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <button
              onClick={handleCopy}
              className="btn-ghost"
              title="Copy code"
              style={{ fontSize: '12px' }}
            >
              {copied ? <Check size={15} color="var(--accent-emerald)" /> : <Copy size={15} />}
            </button>
            <button
              onClick={handleDownload}
              className="btn-ghost"
              title="Download file"
              style={{ fontSize: '12px' }}
            >
              <Download size={15} />
            </button>
            <button
              onClick={onClose}
              className="btn-ghost"
              title="Close drawer"
              style={{ fontSize: '12px', marginLeft: '4px' }}
            >
              <X size={17} />
            </button>
          </div>
        </div>

        {/* Multi-Artifact Switcher Strip */}
        {effectiveArtifacts.length > 0 && (
          <div
            style={{
              background: '#1B1924',
              border: '1px solid #35313F',
              borderRadius: 'var(--radius-sm)',
              padding: '8px 10px',
              display: 'flex',
              flexDirection: 'column',
              gap: '6px',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                fontSize: '11px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '5px', fontWeight: 600, color: 'var(--text-secondary)' }}>
                <Layers size={13} color="#D7FF5F" />
                <span>Session Artifacts ({effectiveArtifacts.length})</span>
              </div>
              {effectiveArtifacts.length > 1 && currentIndex !== -1 && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <button
                    onClick={() => currentIndex > 0 && onSelectArtifact?.(effectiveArtifacts[currentIndex - 1].id)}
                    disabled={currentIndex <= 0}
                    className="btn-ghost"
                    style={{
                      padding: '2px 6px',
                      fontSize: '11px',
                      opacity: currentIndex <= 0 ? 0.35 : 1,
                      cursor: currentIndex <= 0 ? 'not-allowed' : 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '2px',
                    }}
                    title="Previous artifact"
                  >
                    <ChevronLeft size={13} />
                    <span>Prev</span>
                  </button>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)', padding: '0 2px' }}>
                    {currentIndex + 1} of {effectiveArtifacts.length}
                  </span>
                  <button
                    onClick={() => currentIndex < effectiveArtifacts.length - 1 && onSelectArtifact?.(effectiveArtifacts[currentIndex + 1].id)}
                    disabled={currentIndex >= effectiveArtifacts.length - 1}
                    className="btn-ghost"
                    style={{
                      padding: '2px 6px',
                      fontSize: '11px',
                      opacity: currentIndex >= effectiveArtifacts.length - 1 ? 0.35 : 1,
                      cursor: currentIndex >= effectiveArtifacts.length - 1 ? 'not-allowed' : 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '2px',
                    }}
                    title="Next artifact"
                  >
                    <span>Next</span>
                    <ChevronRight size={13} />
                  </button>
                </div>
              )}
            </div>

            {/* List of artifact pills */}
            <div
              style={{
                display: 'flex',
                gap: '6px',
                overflowX: 'auto',
                paddingBottom: '2px',
                scrollbarWidth: 'thin',
              }}
            >
              {effectiveArtifacts.map((art, idx) => {
                const isCurrent = art.id === artifact.id;
                const isHtml = art.artifact_type.includes('html');
                const label = isHtml ? 'Interactive HTML' : 'Markdown Draft';
                return (
                  <button
                    key={art.id}
                    onClick={() => onSelectArtifact?.(art.id)}
                    style={{
                      flexShrink: 0,
                      padding: '5px 9px',
                      borderRadius: '5px',
                      border: isCurrent
                        ? '1px solid #D7FF5F'
                        : '1px solid #35313F',
                      background: isCurrent
                        ? 'rgba(215, 255, 95, 0.15)'
                        : '#171520',
                      color: isCurrent ? '#F5F2EA' : 'var(--text-secondary)',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      fontSize: '11px',
                      fontWeight: isCurrent ? 600 : 500,
                      transition: 'all var(--transition-fast)',
                      maxWidth: '240px',
                    }}
                    title={`${art.title} (${art.artifact_type})`}
                  >
                    {isHtml ? (
                      <Code2 size={12} color={isCurrent ? '#D7FF5F' : 'var(--accent-blue)'} />
                    ) : (
                      <FileText size={12} color={isCurrent ? '#D7FF5F' : 'var(--accent-emerald)'} />
                    )}
                    <span
                      style={{
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {label} {effectiveArtifacts.length > 2 ? `(#${idx + 1})` : ''}
                    </span>
                    {art.word_count > 0 && (
                      <span
                        style={{
                          fontSize: '9px',
                          color: isCurrent ? '#D7FF5F' : 'var(--text-muted)',
                          fontFamily: 'var(--font-mono)',
                          background: 'rgba(0,0,0,0.3)',
                          padding: '1px 4px',
                          borderRadius: '3px',
                        }}
                      >
                        {art.word_count}w
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Title & Metadata Badges */}
        <div>
          <h2
            style={{
              fontSize: '15px',
              fontWeight: 600,
              color: '#F5F2EA',
              margin: '0 0 6px 0',
              lineHeight: '1.3',
            }}
          >
            {artifact.title}
          </h2>

          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '6px' }}>
            <span
              style={{
                fontSize: '11px',
                fontWeight: 600,
                background: 'rgba(215, 255, 95, 0.12)',
                color: '#D7FF5F',
                padding: '2px 8px',
                borderRadius: '4px',
                border: '1px solid rgba(215, 255, 95, 0.3)',
              }}
            >
              {artifactLabel(artifact)}
            </span>

            {artifact.word_count > 0 && (
              <span
                style={{
                  fontSize: '11px',
                  fontFamily: 'var(--font-mono)',
                  color: 'var(--text-secondary)',
                  background: '#1B1924',
                  border: '1px solid #35313F',
                  padding: '2px 8px',
                  borderRadius: '4px',
                }}
              >
                {artifact.word_count} words
              </span>
            )}

            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                fontSize: '11px',
                color: 'var(--accent-emerald)',
                background: 'rgba(74, 222, 128, 0.08)',
                padding: '2px 6px',
                borderRadius: '4px',
                border: '1px solid rgba(74, 222, 128, 0.2)',
              }}
              title="Rendered in a fully sandboxed iframe: no scripts, no same-origin, no network"
            >
              <ShieldCheck size={12} />
              <span>Isolated Sandbox</span>
            </div>
          </div>
        </div>

        {/* Tab Controls */}
        <div
          style={{
            display: 'flex',
            background: '#1B1924',
            padding: '3px',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid #35313F',
          }}
        >
          <button
            onClick={() => setActiveTab('preview')}
            style={{
              flex: 1,
              padding: '6px 12px',
              fontSize: '12px',
              fontWeight: 600,
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              background: activeTab === 'preview' ? '#262232' : 'transparent',
              color: activeTab === 'preview' ? '#D7FF5F' : 'var(--text-muted)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
              transition: 'all var(--transition-fast)',
            }}
          >
            <Eye size={13} color={activeTab === 'preview' ? '#D7FF5F' : 'currentColor'} />
            <span>Rendered Preview</span>
          </button>
          <button
            onClick={() => setActiveTab('code')}
            style={{
              flex: 1,
              padding: '6px 12px',
              fontSize: '12px',
              fontWeight: 600,
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              background: activeTab === 'code' ? '#262232' : 'transparent',
              color: activeTab === 'code' ? '#D7FF5F' : 'var(--text-muted)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
              transition: 'all var(--transition-fast)',
            }}
          >
            <Code2 size={13} color={activeTab === 'code' ? '#D7FF5F' : 'currentColor'} />
            <span>Source</span>
          </button>
        </div>
      </div>

      {/* Security Isolation Notice Pill */}
      <div
        style={{
          background: 'rgba(17, 16, 24, 0.95)',
          padding: '6px 16px',
          borderBottom: '1px solid #35313F',
          fontSize: '11px',
          color: 'var(--text-muted)',
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
        }}
      >
        <span style={{ color: '#D7FF5F' }}>●</span>
        <span>
          Sandbox Policy: <code>sandbox=""</code> — blocks scripts, forms, popups, same-origin access and all network requests (CSP <code>default-src 'none'</code>). Allows static HTML + inline CSS + data: images.
        </span>
      </div>

      {/* Content Area */}
      <div style={{ flex: 1, overflow: 'hidden', position: 'relative', background: '#111018' }}>
        {activeTab === 'preview' ? (
          <iframe
            title={artifact.title}
            srcDoc={buildSandboxDocument(artifact.content, artifact.artifact_type)}
            sandbox={SANDBOX_ATTR}
            style={{
              width: '100%',
              height: '100%',
              border: 'none',
              background: '#111018',
            }}
          />
        ) : (
          <pre
            style={{
              margin: 0,
              padding: '16px',
              height: '100%',
              overflow: 'auto',
              fontFamily: 'var(--font-mono)',
              fontSize: '12px',
              lineHeight: '1.6',
              color: '#F5F2EA',
              background: '#111018',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}
          >
            {artifact.content}
          </pre>
        )}
      </div>
    </aside>
  );
};
