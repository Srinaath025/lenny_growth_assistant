import React from 'react';
import {
  Mic,
  Database,
  Cpu,
  Layers,
  Sparkles,
  Menu,
} from 'lucide-react';
import { HealthResponse } from '../types';

interface HeaderProps {
  sessionTitle: string;
  health: HealthResponse | null;
  artifactCount: number;
  isArtifactDrawerOpen: boolean;
  onToggleDrawer: () => void;
  onToggleSidebar: () => void;
  onOpenEssayModal: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  sessionTitle,
  health,
  artifactCount,
  isArtifactDrawerOpen,
  onToggleDrawer,
  onToggleSidebar,
  onOpenEssayModal,
}) => {
  const ollamaOk = health?.ollama.available ?? false;
  const dbOk = health?.database.connected ?? false;
  const cloudOk = health?.cloud.available ?? false;

  return (
    <header className="app-header">
      {/* Left Branding */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <button
          onClick={onToggleSidebar}
          className="btn-ghost"
          style={{ display: 'none' }}
          id="btn-toggle-sidebar"
        >
          <Menu size={18} />
        </button>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div
            style={{
              width: '32px',
              height: '32px',
              borderRadius: '8px',
              background: 'linear-gradient(135deg, #D7FF5F, #A3E635)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#111018',
              boxShadow: '0 2px 10px rgba(215, 255, 95, 0.25)',
            }}
          >
            <Mic size={18} />
          </div>

          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ fontWeight: 700, fontSize: '14px', letterSpacing: '-0.2px', color: '#F5F2EA' }}>
                The Lenny Growth Assistant
              </span>
              <span
                style={{
                  fontSize: '10px',
                  fontFamily: 'var(--font-mono)',
                  background: 'rgba(215, 255, 95, 0.12)',
                  color: '#D7FF5F',
                  padding: '1px 5px',
                  borderRadius: '3px',
                  fontWeight: 600,
                }}
              >
                v1.0
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Center Session Title */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          maxWidth: '380px',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          color: 'var(--text-secondary)',
          fontSize: '13px',
          background: '#1B1924',
          padding: '4px 12px',
          borderRadius: '20px',
          border: '1px solid #35313F',
        }}
      >
        <span style={{ color: 'var(--text-muted)', marginRight: '6px' }}>Session:</span>
        <span style={{ color: '#F5F2EA', fontWeight: 500 }}>{sessionTitle}</span>
      </div>

      {/* Right Telemetry & Actions */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        {/* Telemetry Status Indicators */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            background: '#1B1924',
            padding: '3px 8px',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid #35313F',
          }}
        >
          {/* Database Health Pill */}
          <div
            title={`PostgreSQL: ${dbOk ? 'Connected' : 'Disconnected'} (${health?.database.total_chunks || 0} transcript chunks indexed)`}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              fontSize: '11px',
              color: dbOk ? 'var(--text-secondary)' : 'var(--accent-rose)',
            }}
          >
            <Database size={12} color={dbOk ? 'var(--accent-blue)' : 'var(--accent-rose)'} />
            <span style={{ fontFamily: 'var(--font-mono)' }}>
              {health?.database.total_chunks ? `${health.database.total_chunks} chunks` : 'DB Live'}
            </span>
          </div>

          <span style={{ color: 'var(--border-prominent)' }}>|</span>

          {/* Ollama Health Pill */}
          <div
            title={`Local Ollama: ${ollamaOk ? 'Daemon Ready' : 'Daemon Unreachable'}`}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '5px',
              fontSize: '11px',
              color: ollamaOk ? 'var(--accent-emerald)' : 'var(--accent-rose)',
            }}
          >
            <span
              style={{
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                backgroundColor: ollamaOk ? 'var(--accent-emerald)' : 'var(--accent-rose)',
              }}
              className={ollamaOk ? 'animate-pulse-dot' : ''}
            />
            <span style={{ fontWeight: 500 }}>
              {ollamaOk ? 'Ollama Ready' : 'Ollama Offline'}
            </span>
          </div>

          <span style={{ color: 'var(--border-prominent)' }}>|</span>

          {/* Cloud Health Pill */}
          <div
            title={cloudOk ? `${health?.cloud.provider === 'gemini' ? 'Google Gemini' : 'Anthropic Claude'} Active` : 'Cloud Key Not Configured (Local Ollama Active)'}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              fontSize: '11px',
              color: cloudOk ? '#D7FF5F' : 'var(--text-disabled)',
            }}
          >
            <Cpu size={12} />
            <span>{cloudOk ? (health?.cloud.provider === 'gemini' ? 'Gemini Live' : 'Claude Live') : 'Cloud Locked'}</span>
          </div>
        </div>

        {/* Quick Action: Draft Essay */}
        <button
          onClick={onOpenEssayModal}
          className="btn-secondary"
          style={{ fontSize: '12px', padding: '6px 10px', borderColor: 'rgba(215, 255, 95, 0.3)' }}
        >
          <Sparkles size={13} color="#D7FF5F" />
          <span>Draft Essay</span>
        </button>

        {/* Artifact Drawer Toggle */}
        <button
          onClick={onToggleDrawer}
          className="btn-secondary"
          style={{
            fontSize: '12px',
            padding: '6px 12px',
            background: isArtifactDrawerOpen ? 'rgba(215, 255, 95, 0.12)' : '#1B1924',
            borderColor: isArtifactDrawerOpen ? '#D7FF5F' : '#35313F',
            color: isArtifactDrawerOpen ? '#D7FF5F' : 'var(--text-primary)',
          }}
        >
          <Layers size={13} />
          <span>Artifacts</span>
          {artifactCount > 0 && (
            <span
              style={{
                fontSize: '10px',
                background: '#D7FF5F',
                color: '#111018',
                padding: '0 5px',
                borderRadius: '999px',
                fontWeight: 700,
                marginLeft: '4px',
              }}
            >
              {artifactCount}
            </span>
          )}
        </button>
      </div>
    </header>
  );
};
