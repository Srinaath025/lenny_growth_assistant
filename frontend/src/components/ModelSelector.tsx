import React, { useState } from 'react';
import { Cpu, Lock, CheckCircle2, AlertCircle, Info } from 'lucide-react';
import { HealthResponse } from '../types';

interface ModelSelectorProps {
  currentProvider: string;
  currentModel: string;
  health: HealthResponse | null;
  onSelect: (provider: string, model: string) => void;
}

export const ModelSelector: React.FC<ModelSelectorProps> = ({
  currentProvider,
  currentModel,
  health,
  onSelect,
}) => {
  const [showTooltip, setShowTooltip] = useState(false);

  const ollamaOk = health?.ollama.available ?? false;
  const cloudOk = health?.cloud.available ?? false;

  const isCloudProvider = currentProvider === 'anthropic' || currentProvider === 'gemini';

  const handleCloudClick = () => {
    if (!cloudOk) {
      setShowTooltip(true);
      setTimeout(() => setShowTooltip(false), 5000);
      return;
    }
    const prov = health?.cloud.provider || 'gemini';
    const mod = health?.cloud.model || (prov === 'gemini' ? 'gemini-2.5-flash' : 'claude-sonnet-5-5');
    onSelect(prov, mod);
  };

  const handleOllamaClick = () => {
    onSelect('ollama', health?.ollama.model || 'llama3.2:3b');
  };

  return (
    <div
      style={{
        padding: '12px',
        borderTop: '1px solid var(--border-subtle)',
        background: 'var(--bg-secondary)',
      }}
    >
      <div
        style={{
          fontSize: '11px',
          fontWeight: 600,
          textTransform: 'uppercase',
          letterSpacing: '0.8px',
          color: 'var(--text-muted)',
          marginBottom: '8px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <span>Model Provider</span>
        <span style={{ fontSize: '10px', color: '#D7FF5F', fontWeight: 600 }}>Dual-Layer</span>
      </div>

      <div role="radiogroup" aria-label="Model provider" style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        {/* Local Ollama Option (Default & Active) */}
        <div
          role="radio" aria-checked={currentProvider === 'ollama'} tabIndex={0} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleOllamaClick(); } }}
          onClick={handleOllamaClick}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '8px 10px',
            borderRadius: 'var(--radius-sm)',
            cursor: 'pointer',
            border:
              currentProvider === 'ollama'
                ? '1px solid var(--accent-emerald)'
                : '1px solid var(--border-subtle)',
            background:
              currentProvider === 'ollama'
                ? 'rgba(74, 222, 128, 0.08)'
                : 'rgba(27, 25, 36, 0.6)',
            transition: 'all var(--transition-fast)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div
              style={{
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                backgroundColor: ollamaOk ? 'var(--accent-emerald)' : 'var(--accent-rose)',
                boxShadow: ollamaOk ? '0 0 8px rgba(74, 222, 128, 0.6)' : 'none',
              }}
              className={ollamaOk ? 'animate-pulse-dot' : ''}
            />
            <div>
              <div
                style={{
                  fontSize: '12.5px',
                  fontWeight: 600,
                  color: currentProvider === 'ollama' ? '#F5F2EA' : 'var(--text-primary)',
                }}
              >
                Local Ollama
              </div>
              <div style={{ fontSize: '10.5px', color: 'var(--text-muted)' }}>
                {health?.ollama.model || 'llama3.2:3b'} (On-Device)
              </div>
            </div>
          </div>

          {currentProvider === 'ollama' && (
            <CheckCircle2 size={14} color="var(--accent-emerald)" />
          )}
        </div>

        {/* Cloud Anthropic Option */}
        <div
          role="radio" aria-checked={currentProvider === 'anthropic'} tabIndex={0} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleCloudClick(); } }}
          onClick={handleCloudClick}
          style={{
            position: 'relative',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '8px 10px',
            borderRadius: 'var(--radius-sm)',
            cursor: cloudOk ? 'pointer' : 'not-allowed',
            border:
              isCloudProvider
                ? '1px solid #D7FF5F'
                : '1px solid var(--border-subtle)',
            background:
              isCloudProvider
                ? 'rgba(215, 255, 95, 0.08)'
                : 'rgba(27, 25, 36, 0.4)',
            opacity: cloudOk ? 1 : 0.65,
            transition: 'all var(--transition-fast)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {cloudOk ? (
              <Cpu size={14} color="#D7FF5F" />
            ) : (
              <Lock size={14} color="var(--text-disabled)" />
            )}
            <div>
              <div
                style={{
                  fontSize: '12.5px',
                  fontWeight: 500,
                  color: cloudOk ? '#F5F2EA' : 'var(--text-disabled)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
              >
                <span>{health?.cloud.provider === 'gemini' ? 'Google Gemini' : 'Cloud LLM'}</span>
                {!cloudOk && (
                  <span
                    style={{
                      fontSize: '9px',
                      background: 'var(--border-prominent)',
                      padding: '1px 4px',
                      borderRadius: '3px',
                      color: 'var(--text-muted)',
                    }}
                  >
                    NO KEY
                  </span>
                )}
              </div>
              <div style={{ fontSize: '10.5px', color: 'var(--text-disabled)' }}>
                {cloudOk
                  ? (health?.cloud.provider === 'gemini' ? 'Google AI Studio Live (Fast)' : 'Anthropic API Live')
                  : 'Add GEMINI_API_KEY in .env'}
              </div>
            </div>
          </div>

          {isCloudProvider && cloudOk && (
            <CheckCircle2 size={14} color="#D7FF5F" />
          )}
        </div>

        {/* Informative Tooltip Banner when cloud is disabled and clicked */}
        {showTooltip && (
          <div
            style={{
              marginTop: '4px',
              padding: '8px 10px',
              background: 'rgba(215, 255, 95, 0.1)',
              border: '1px solid #D7FF5F',
              borderRadius: 'var(--radius-sm)',
              fontSize: '11px',
              color: '#F5F2EA',
              lineHeight: '1.4',
              display: 'flex',
              gap: '6px',
            }}
          >
            <Info size={14} style={{ flexShrink: 0, marginTop: '2px', color: '#D7FF5F' }} />
            <span>
              Cloud inference is disabled because <code>GEMINI_API_KEY</code> is not set in <code>.env</code>. Local Ollama mode is fully active for all queries.
            </span>
          </div>
        )}
      </div>
    </div>
  );
};
