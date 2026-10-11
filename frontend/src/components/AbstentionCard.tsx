import React from 'react';
import { ShieldAlert } from 'lucide-react';

interface AbstentionCardProps {
  message?: string;
}

export const AbstentionCard: React.FC<AbstentionCardProps> = ({ message }) => {
  return (
    <div
      style={{
        marginTop: '10px',
        padding: '14px 16px',
        background: 'rgba(244, 63, 94, 0.08)',
        border: '1px solid var(--accent-rose)',
        borderRadius: 'var(--radius-md)',
        color: '#FECDD3',
        boxShadow: '0 4px 16px rgba(244, 63, 94, 0.08)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
        <ShieldAlert size={18} color="var(--accent-rose)" />
        <span
          style={{
            fontWeight: 700,
            fontSize: '13px',
            color: 'var(--accent-rose)',
            letterSpacing: '0.3px',
            textTransform: 'uppercase',
          }}
        >
          Topic Not Discussed in Transcripts
        </span>
      </div>
      <p style={{ fontSize: '13px', lineHeight: '1.6', color: '#F1F5F9', margin: 0 }}>
        {message ||
          "Based on our search across all ingested Lenny's Podcast episodes, neither Lenny nor his guests discussed this topic. To prevent ungrounded hallucinations, the assistant declines to answer."}
      </p>
      <div
        style={{
          marginTop: '8px',
          fontSize: '11px',
          color: '#FDA4AF',
          fontStyle: 'italic',
        }}
      >
        Guardrail policy: Grounded-only intelligence strictly enforced.
      </div>
    </div>
  );
};
