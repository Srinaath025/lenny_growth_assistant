import React from 'react';
import { ExternalLink, Play, Quote } from 'lucide-react';
import { CitationItem } from '../types';

interface CitationCardProps {
  citation: CitationItem;
  index: number;
}

export const CitationCard: React.FC<CitationCardProps> = ({ citation, index }) => {
  const formatTimestamp = (seconds?: number | null) => {
    if (seconds === null || seconds === undefined) return null;
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const tsStr = formatTimestamp(citation.timestamp_seconds);

  // Derive guest initials for avatar badge
  const initials = citation.guest_name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((n) => n[0].toUpperCase())
    .join('');

  return (
    <div
      className="card-base"
      style={{
        background: '#1B1924',
        border: '1px solid #35313F',
        borderLeft: '3px solid #D7FF5F',
        marginTop: '8px',
        borderRadius: 'var(--radius-md)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div
            style={{
              width: '24px',
              height: '24px',
              borderRadius: '50%',
              background: 'linear-gradient(135deg, #262232, #35313F)',
              color: '#D7FF5F',
              border: '1px solid #35313F',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '10px',
              fontWeight: 700,
              letterSpacing: '0.5px',
            }}
          >
            {initials || 'L'}
          </div>
          <div>
            <div style={{ fontSize: '12px', fontWeight: 600, color: '#F5F2EA' }}>
              {citation.guest_name}
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
              {citation.episode_title}
            </div>
          </div>
        </div>

        {citation.youtube_url && (
          <a
            href={citation.youtube_url}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-secondary"
            style={{
              fontSize: '11px',
              padding: '4px 8px',
              textDecoration: 'none',
              color: '#D7FF5F',
              borderColor: 'rgba(215, 255, 95, 0.35)',
              background: 'rgba(215, 255, 95, 0.08)',
            }}
          >
            <Play size={11} fill="currentColor" />
            <span>{tsStr ? `Watch (${tsStr})` : 'Watch on YouTube'}</span>
            <ExternalLink size={10} style={{ marginLeft: '2px', opacity: 0.7 }} />
          </a>
        )}
      </div>

      <div
        style={{
          display: 'flex',
          gap: '8px',
          fontStyle: 'italic',
          color: 'var(--text-secondary)',
          fontSize: '12.5px',
          lineHeight: '1.5',
          background: 'rgba(17, 16, 24, 0.6)',
          border: '1px solid rgba(53, 49, 63, 0.4)',
          padding: '8px 10px',
          borderRadius: 'var(--radius-sm)',
        }}
      >
        <Quote size={13} style={{ flexShrink: 0, marginTop: '2px', color: '#D7FF5F' }} />
        <span>"{citation.quote_text}"</span>
      </div>
    </div>
  );
};
