import React, { useState } from 'react';
import { User, Sparkles, Copy, Check, FileText } from 'lucide-react';
import { MessageItem } from '../types';
import { CitationCard } from './CitationCard';
import { AbstentionCard } from './AbstentionCard';

interface ChatMessageProps {
  message: MessageItem;
  isStreaming?: boolean;
  onOpenArtifact?: (artifactId?: string) => void;
}

export const ChatMessage: React.FC<ChatMessageProps> = ({
  message,
  isStreaming,
  onOpenArtifact,
}) => {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === 'user';

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Simple markdown-style rendering for paragraphs, bullet points, and bold text
  const renderFormattedContent = (content: string) => {
    const lines = content.split('\n');
    return lines.map((line, idx) => {
      if (!line.trim()) {
        return <div key={idx} style={{ height: '8px' }} />;
      }

      // Check for bullet lines
      const isBullet = line.trim().startsWith('- ') || line.trim().startsWith('* ');
      const cleanLine = isBullet ? line.trim().substring(2) : line;

      // Parse bold segments **bold**
      const parts = cleanLine.split(/(\*\*[^*]+\*\*)/g);
      const parsedElements = parts.map((part, pIdx) => {
        if (part.startsWith('**') && part.endsWith('**')) {
          return (
            <strong key={pIdx} style={{ color: '#FFFFFF', fontWeight: 600 }}>
              {part.slice(2, -2)}
            </strong>
          );
        }
        return part;
      });

      if (isBullet) {
        return (
          <div
            key={idx}
            style={{
              display: 'flex',
              gap: '8px',
              paddingLeft: '12px',
              marginBottom: '4px',
              lineHeight: '1.6',
            }}
          >
            <span style={{ color: '#D7FF5F', fontSize: '13px' }}>•</span>
            <span style={{ flex: 1 }}>{parsedElements}</span>
          </div>
        );
      }

      return (
        <p key={idx} style={{ margin: '0 0 6px 0', lineHeight: '1.65' }}>
          {parsedElements}
        </p>
      );
    });
  };

  return (
    <div
      style={{
        display: 'flex',
        gap: '14px',
        padding: '16px 20px',
        background: isUser ? 'rgba(27, 25, 36, 0.45)' : 'transparent',
        borderBottom: '1px solid rgba(53, 49, 63, 0.5)',
        position: 'relative',
      }}
    >
      {/* Avatar Icon */}
      <div
        style={{
          width: '32px',
          height: '32px',
          borderRadius: '8px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
          background: isUser
            ? '#1B1924'
            : 'linear-gradient(135deg, #D7FF5F, #A3E635)',
          color: isUser ? 'var(--text-secondary)' : '#111018',
          border: '1px solid #35313F',
        }}
      >
        {isUser ? <User size={16} /> : <Sparkles size={16} />}
      </div>

      {/* Message Content Container */}
      <div style={{ flex: 1, minWidth: 0 }}>
        {/* Header line: Role and Timestamp */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: '6px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)' }}>
              {isUser ? 'You' : "Lenny's Growth Assistant"}
            </span>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
              {message.created_at ? new Date(message.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
            </span>
          </div>

          <button
            onClick={handleCopy}
            className="btn-ghost"
            title="Copy message text"
            style={{ padding: '3px 6px' }}
          >
            {copied ? <Check size={13} color="var(--accent-emerald)" /> : <Copy size={13} />}
          </button>
        </div>

        {/* Abstention Card OR Normal Content */}
        {message.is_abstention ? (
          <AbstentionCard message={message.content} />
        ) : (
          <div
            style={{
              fontSize: '13.5px',
              color: 'var(--text-primary)',
              wordBreak: 'break-word',
            }}
          >
            {renderFormattedContent(message.content)}
            {isStreaming && <span className="cursor-blinking" />}
          </div>
        )}

        {/* Verifiable Citations List */}
        {!message.is_abstention && message.citations && message.citations.length > 0 && (
          <div style={{ marginTop: '14px' }}>
            <div
              style={{
                fontSize: '11px',
                fontWeight: 600,
                textTransform: 'uppercase',
                letterSpacing: '0.6px',
                color: '#D7FF5F',
                marginBottom: '6px',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <span>Verifiable Episode Sources ({message.citations.length})</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {message.citations.map((c, i) => (
                <CitationCard key={c.id || i} citation={c} index={i} />
              ))}
            </div>
          </div>
        )}

        {/* Artifact Action Pill if message references generated artifact */}
        {(message.content.includes('interactive artifact') ||
          message.content.includes('available in the viewer') ||
          message.content.includes('Ship 30 for 30 growth essay')) &&
          onOpenArtifact && (
          <div style={{ marginTop: '12px' }}>
            <button
              onClick={() => onOpenArtifact()}
              className="btn-primary"
              style={{
                fontSize: '12px',
                padding: '6px 12px',
                background: 'rgba(215, 255, 95, 0.12)',
                color: '#D7FF5F',
                border: '1px solid #D7FF5F',
                fontWeight: 600,
              }}
            >
              <FileText size={14} color="#D7FF5F" />
              <span>Open in Artifact Viewer</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
