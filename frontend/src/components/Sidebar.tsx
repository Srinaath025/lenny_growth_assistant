import React, { useState } from 'react';
import {
  Plus,
  MessageSquare,
  Trash2,
  Edit2,
  Check,
  X,
  Search,
} from 'lucide-react';
import { SessionSummary, HealthResponse } from '../types';
import { ModelSelector } from './ModelSelector';

interface SidebarProps {
  sessions: SessionSummary[];
  activeSessionId: string | null;
  currentProvider: string;
  currentModel: string;
  health: HealthResponse | null;
  isOpen: boolean;
  onSelectSession: (id: string) => void;
  onCreateSession: () => void;
  onUpdateSessionTitle: (id: string, newTitle: string) => void;
  onDeleteSession: (id: string) => void;
  onSelectModel: (provider: string, model: string) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  sessions,
  activeSessionId,
  currentProvider,
  currentModel,
  health,
  isOpen,
  onSelectSession,
  onCreateSession,
  onUpdateSessionTitle,
  onDeleteSession,
  onSelectModel,
}) => {
  const [search, setSearch] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');

  const filteredSessions = sessions.filter((s) =>
    s.title.toLowerCase().includes(search.toLowerCase())
  );

  const startEditing = (s: SessionSummary, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(s.id);
    setEditTitle(s.title);
  };

  const saveEditing = (id: string, e: React.MouseEvent | React.FormEvent) => {
    e.stopPropagation();
    if (editTitle.trim()) {
      onUpdateSessionTitle(id, editTitle.trim());
    }
    setEditingId(null);
  };

  const cancelEditing = (e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(null);
  };

  const handleDelete = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirm('Delete this conversation session? All messages and citations will be removed.')) {
      onDeleteSession(id);
    }
  };

  return (
    <aside className={`sidebar-pane ${isOpen ? 'open' : ''}`} aria-label="Session Sidebar">
      {/* Top Action: New Session */}
      <div style={{ padding: '14px 12px 10px 12px' }}>
        <button
          onClick={onCreateSession}
          className="btn-primary"
          style={{
            width: '100%',
            justifyContent: 'center',
            padding: '9px 12px',
            fontSize: '13px',
          }}
        >
          <Plus size={16} />
          <span>New Session</span>
          <span
            style={{
              fontSize: '10px',
              opacity: 0.8,
              marginLeft: 'auto',
              fontFamily: 'var(--font-mono)',
            }}
          >
            Ctrl+N
          </span>
        </button>

        {/* Filter Input */}
        {sessions.length > 4 && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              marginTop: '10px',
              padding: '6px 8px',
              background: 'var(--bg-tertiary)',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border-subtle)',
            }}
          >
            <Search size={13} color="var(--text-muted)" />
            <input
              type="text"
              placeholder="Search conversations..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{
                width: '100%',
                background: 'transparent',
                border: 'none',
                outline: 'none',
                fontSize: '12px',
                color: 'var(--text-primary)',
              }}
            />
          </div>
        )}
      </div>

      {/* Session List Feed */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '0 8px 12px 8px',
          display: 'flex',
          flexDirection: 'column',
          gap: '3px',
        }}
      >
        <div
          style={{
            fontSize: '10px',
            fontWeight: 700,
            textTransform: 'uppercase',
            letterSpacing: '0.8px',
            color: 'var(--text-muted)',
            padding: '6px 8px 4px 8px',
          }}
        >
          Conversations ({sessions.length})
        </div>

        {filteredSessions.length === 0 ? (
          <div
            style={{
              padding: '24px 12px',
              textAlign: 'center',
              color: 'var(--text-muted)',
              fontSize: '12px',
            }}
          >
            {search ? 'No matching sessions found.' : 'No sessions yet. Click "New Session" to start!'}
          </div>
        ) : (
          filteredSessions.map((s) => {
            const isActive = s.id === activeSessionId;
            const isEditing = s.id === editingId;

            return (
              <div
                key={s.id}
                onClick={() => onSelectSession(s.id)}
                style={{
                  position: 'relative',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '8px 10px',
                  borderRadius: 'var(--radius-sm)',
                  cursor: 'pointer',
                  background: isActive ? '#1B1924' : 'transparent',
                  border: isActive ? '1px solid #D7FF5F' : '1px solid transparent',
                  boxShadow: isActive ? '0 0 12px rgba(215, 255, 95, 0.08)' : 'none',
                  color: isActive ? '#F5F2EA' : 'var(--text-secondary)',
                  transition: 'all var(--transition-fast)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0, flex: 1 }}>
                  <MessageSquare
                    size={14}
                    color={isActive ? '#D7FF5F' : 'var(--text-muted)'}
                    style={{ flexShrink: 0 }}
                  />

                  {isEditing ? (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px', flex: 1 }}>
                      <input
                        type="text"
                        autoFocus
                        value={editTitle}
                        onChange={(e) => setEditTitle(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') saveEditing(s.id, e);
                          if (e.key === 'Escape') setEditingId(null);
                        }}
                        style={{
                          width: '100%',
                          background: '#111018',
                          border: '1px solid #D7FF5F',
                          borderRadius: '3px',
                          color: '#F5F2EA',
                          fontSize: '12px',
                          padding: '2px 4px',
                        }}
                      />
                      <button
                        onClick={(e) => saveEditing(s.id, e)}
                        className="btn-ghost"
                        style={{ padding: '2px' }}
                      >
                        <Check size={12} color="var(--accent-emerald)" />
                      </button>
                      <button
                        onClick={cancelEditing}
                        className="btn-ghost"
                        style={{ padding: '2px' }}
                      >
                        <X size={12} color="var(--accent-rose)" />
                      </button>
                    </div>
                  ) : (
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div
                        style={{
                          fontSize: '12.5px',
                          fontWeight: isActive ? 600 : 400,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {s.title}
                      </div>
                      <div style={{ fontSize: '10.5px', color: 'var(--text-muted)' }}>
                        {s.message_count} {s.message_count === 1 ? 'msg' : 'msgs'}
                      </div>
                    </div>
                  )}
                </div>

                {/* Inline Action Icons */}
                {!isEditing && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '2px', marginLeft: '6px' }}>
                    <button
                      onClick={(e) => startEditing(s, e)}
                      className="btn-ghost"
                      title="Rename"
                      style={{ padding: '3px' }}
                    >
                      <Edit2 size={12} />
                    </button>
                    <button
                      onClick={(e) => handleDelete(s.id, e)}
                      className="btn-ghost"
                      title="Delete"
                      style={{ padding: '3px' }}
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Docked Model Selector at Bottom */}
      <ModelSelector
        currentProvider={currentProvider}
        currentModel={currentModel}
        health={health}
        onSelect={onSelectModel}
      />
    </aside>
  );
};
