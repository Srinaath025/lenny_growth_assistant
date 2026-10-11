import React, { useState, useEffect, useRef } from 'react';
import {
  fetchHealth,
  fetchSessions,
  createSession,
  fetchSession,
  updateSession,
  deleteSession,
  streamChat,
  fetchArtifact,
} from './api';
import {
  HealthResponse,
  SessionSummary,
  SessionDetailResponse,
  MessageItem,
  ArtifactDetailResponse,
  EssayResponse,
} from './types';
import { Header } from './components/Header';
import { Sidebar } from './components/Sidebar';
import { ChatView } from './components/ChatView';
import { ArtifactViewer } from './components/ArtifactViewer';
import { EssayModal } from './components/EssayModal';
import { AlertCircle, X } from 'lucide-react';

export const App: React.FC = () => {
  // App state
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [sessionDetail, setSessionDetail] = useState<SessionDetailResponse | null>(null);
  
  // Model selection
  const [currentProvider, setCurrentProvider] = useState<string>('ollama');
  const [currentModel, setCurrentModel] = useState<string>('llama3.2:3b');

  // Streaming state
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [streamingMessage, setStreamingMessage] = useState<string>('');
  const abortControllerRef = useRef<AbortController | null>(null);

  // Artifact drawer state
  const [activeArtifact, setActiveArtifact] = useState<ArtifactDetailResponse | null>(null);
  const [isArtifactDrawerOpen, setIsArtifactDrawerOpen] = useState<boolean>(false);

  // Modals & responsive state
  const [isEssayModalOpen, setIsEssayModalOpen] = useState<boolean>(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState<boolean>(false);
  const [errorToast, setErrorToast] = useState<string | null>(null);

  // 1. Initial Health and Sessions Load
  useEffect(() => {
    loadHealth();
    loadSessions(true);

    // Periodic health poll every 20 seconds
    const interval = setInterval(loadHealth, 20000);
    return () => clearInterval(interval);
  }, []);

  // 2. Global Keyboard Shortcuts (Ctrl+N for New Session)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
        e.preventDefault();
        handleCreateSession();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [currentProvider, currentModel]);

  const loadHealth = async () => {
    try {
      const h = await fetchHealth();
      setHealth(h);
    } catch (err) {
      console.warn('Health check failed:', err);
    }
  };

  const loadSessions = async (autoSelectFirst = false) => {
    try {
      const list = await fetchSessions();
      setSessions(list);
      if (autoSelectFirst && list.length > 0) {
        selectSession(list[0].id);
      } else if (list.length === 0) {
        // Create an initial session
        const fresh = await createSession('New Growth Session', currentProvider, currentModel);
        setSessions([fresh]);
        selectSession(fresh.id);
      }
    } catch (err) {
      console.error('Failed to load sessions:', err);
      setErrorToast('Could not connect to backend API. Please ensure FastAPI server is running.');
    }
  };

  const selectSession = async (id: string) => {
    setActiveSessionId(id);
    setIsSidebarOpen(false);
    try {
      const detail = await fetchSession(id);
      setSessionDetail(detail);
      setCurrentProvider(detail.model_provider || 'ollama');
      setCurrentModel(detail.model_name || 'llama3.2:3b');
      
      // Auto-load latest artifact if available
      if (detail.artifacts && detail.artifacts.length > 0) {
        const latestArt = detail.artifacts[detail.artifacts.length - 1];
        try {
          const artDetail = await fetchArtifact(latestArt.id);
          setActiveArtifact(artDetail);
        } catch (e) {
          console.warn('Could not load artifact detail', e);
        }
      } else {
        setActiveArtifact(null);
        setIsArtifactDrawerOpen(false);
      }
    } catch (err) {
      console.error('Failed to fetch session detail:', err);
      setErrorToast(`Failed to load session ${id}`);
    }
  };

  const handleCreateSession = async () => {
    try {
      const fresh = await createSession('New Growth Session', currentProvider, currentModel);
      setSessions((prev) => [fresh, ...prev]);
      selectSession(fresh.id);
    } catch (err) {
      console.error('Failed to create session:', err);
      setErrorToast('Failed to create new session');
    }
  };

  const handleUpdateSessionTitle = async (id: string, newTitle: string) => {
    try {
      const updated = await updateSession(id, { title: newTitle });
      setSessions((prev) => prev.map((s) => (s.id === id ? updated : s)));
      if (sessionDetail && sessionDetail.id === id) {
        setSessionDetail({ ...sessionDetail, title: newTitle });
      }
    } catch (err) {
      console.error('Failed to update title:', err);
      setErrorToast('Failed to rename session');
    }
  };

  const handleDeleteSession = async (id: string) => {
    try {
      await deleteSession(id);
      const remaining = sessions.filter((s) => s.id !== id);
      setSessions(remaining);
      if (activeSessionId === id) {
        if (remaining.length > 0) {
          selectSession(remaining[0].id);
        } else {
          handleCreateSession();
        }
      }
    } catch (err) {
      console.error('Failed to delete session:', err);
      setErrorToast('Failed to delete session');
    }
  };

  const handleSelectModel = async (provider: string, model: string) => {
    setCurrentProvider(provider);
    setCurrentModel(model);
    if (activeSessionId) {
      try {
        await updateSession(activeSessionId, { model_provider: provider, model_name: model });
      } catch (e) {
        console.warn('Failed to update session model preference:', e);
      }
    }
  };

  // 3. Chat Streaming Execution
  const handleSendMessage = async (text: string) => {
    if (!activeSessionId) return;

    // Immediately create optimistic user message for instant UI feedback
    const optimisticUserMsg: MessageItem = {
      id: `temp-${Date.now()}`,
      session_id: activeSessionId,
      role: 'user',
      content: text,
      is_abstention: false,
      created_at: new Date().toISOString(),
      citations: [],
    };

    setSessionDetail((prev) => {
      if (!prev) return null;
      return {
        ...prev,
        messages: [...prev.messages, optimisticUserMsg],
      };
    });

    setIsStreaming(true);
    setStreamingMessage('');

    const abortCtrl = new AbortController();
    abortControllerRef.current = abortCtrl;

    let fullAccumulated = '';

    await streamChat(
      {
        session_id: activeSessionId,
        message: text,
        model_provider: currentProvider,
        model_name: currentModel,
        stream: true,
      },
      {
        onStatus: (t) => { if (!fullAccumulated) setStreamingMessage(t); },
        onArtifact: async (artifactId) => {
          try {
            const art = await fetchArtifact(artifactId);
            setActiveArtifact(art);
            setIsArtifactDrawerOpen(true);
            if (activeSessionId) {
              const fresh = await fetchSession(activeSessionId);
              setSessionDetail(fresh);
            }
          } catch (e) {
            console.warn('Could not open generated artifact', e);
          }
        },
        onToken: (delta) => {
          fullAccumulated += delta;
          setStreamingMessage(fullAccumulated);
        },
        onComplete: async (data) => {
          setIsStreaming(false);
          setStreamingMessage('');

          try {
            const freshDetail = await fetchSession(data.session_id);
            setSessionDetail(freshDetail);
            if (freshDetail.artifacts && freshDetail.artifacts.length > 0) {
              const latest = freshDetail.artifacts[freshDetail.artifacts.length - 1];
              const art = await fetchArtifact(latest.id);
              setActiveArtifact(art);
            }
          } catch (e) {
            console.warn('Could not refresh session detail after stream', e);
            const completedMsg: MessageItem = {
              id: data.message_id,
              session_id: data.session_id,
              role: 'assistant',
              content: data.content,
              is_abstention: data.is_abstention,
              created_at: new Date().toISOString(),
              citations: data.citations || [],
            };
            setSessionDetail((prev) => {
              if (!prev) return null;
              return {
                ...prev,
                messages: [...prev.messages, completedMsg],
              };
            });
          }

          // Reload session list to get updated titles and message counts
          loadSessions(false);
        },
        onError: (err) => {
          setIsStreaming(false);
          setStreamingMessage('');
          setErrorToast(`Chat error: ${err}`);
        },
      },
      abortCtrl.signal
    );
  };

  const handleStopStreaming = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsStreaming(false);
    setStreamingMessage('');
  };

  // 4. Essay Generation Success Handler
  const handleEssaySuccess = async (essay: EssayResponse) => {
    // Reload active session to reflect new messages and artifacts
    if (activeSessionId) {
      await selectSession(activeSessionId);
    }
    // Fetch and display artifact in the sandboxed drawer
    if (essay.artifact_id) {
      try {
        const art = await fetchArtifact(essay.artifact_id);
        setActiveArtifact(art);
        setIsArtifactDrawerOpen(true);
      } catch (e) {
        console.warn('Failed to load newly created artifact', e);
      }
    }
    loadSessions(false);
  };

  const handleOpenArtifact = async (artifactId?: string) => {
    if (artifactId) {
      try {
        const art = await fetchArtifact(artifactId);
        setActiveArtifact(art);
        setIsArtifactDrawerOpen(true);
      } catch (e) {
        setErrorToast('Failed to load artifact');
      }
    } else if (activeArtifact) {
      setIsArtifactDrawerOpen(true);
    } else if (sessionDetail?.artifacts && sessionDetail.artifacts.length > 0) {
      const latest = sessionDetail.artifacts[sessionDetail.artifacts.length - 1];
      try {
        const art = await fetchArtifact(latest.id);
        setActiveArtifact(art);
        setIsArtifactDrawerOpen(true);
      } catch (e) {
        setErrorToast('Failed to load artifact');
      }
    }
  };

  return (
    <div className="app-layout">
      {/* Top Application Navigation & Telemetry */}
      <Header
        sessionTitle={sessionDetail?.title || 'Loading Session...'}
        health={health}
        artifactCount={sessionDetail?.artifacts?.length || 0}
        isArtifactDrawerOpen={isArtifactDrawerOpen}
        onToggleDrawer={async () => {
          if (!isArtifactDrawerOpen && activeSessionId) {
            try {
              const fresh = await fetchSession(activeSessionId);
              setSessionDetail(fresh);
              if (fresh.artifacts && fresh.artifacts.length > 0 && !activeArtifact) {
                const latest = fresh.artifacts[fresh.artifacts.length - 1];
                const art = await fetchArtifact(latest.id);
                setActiveArtifact(art);
              }
            } catch (e) {
              console.warn('Could not refresh artifacts on drawer open', e);
            }
          }
          setIsArtifactDrawerOpen((prev) => !prev);
        }}
        onToggleSidebar={() => setIsSidebarOpen((prev) => !prev)}
        onOpenEssayModal={() => setIsEssayModalOpen(true)}
      />

      {/* Main Workspace Stage */}
      <div className="app-body">
        {/* Left Session Sidebar */}
        <Sidebar
          sessions={sessions}
          activeSessionId={activeSessionId}
          currentProvider={currentProvider}
          currentModel={currentModel}
          health={health}
          isOpen={isSidebarOpen}
          onSelectSession={selectSession}
          onCreateSession={handleCreateSession}
          onUpdateSessionTitle={handleUpdateSessionTitle}
          onDeleteSession={handleDeleteSession}
          onSelectModel={handleSelectModel}
        />

        {/* Center Chat Experience */}
        <ChatView
          messages={sessionDetail?.messages || []}
          isStreaming={isStreaming}
          streamingMessage={streamingMessage}
          onSendMessage={handleSendMessage}
          onStopStreaming={handleStopStreaming}
          onOpenEssayModal={() => setIsEssayModalOpen(true)}
          onOpenArtifact={handleOpenArtifact}
        />

        {/* Right Artifact Drawer (Sandboxed) */}
        {isArtifactDrawerOpen && (
          <ArtifactViewer
            artifact={activeArtifact}
            artifacts={sessionDetail?.artifacts || []}
            sessionId={activeSessionId}
            onSelectArtifact={handleOpenArtifact}
            onClose={() => setIsArtifactDrawerOpen(false)}
          />
        )}
      </div>

      {/* Ship 30 for 30 Essay Modal */}
      <EssayModal
        isOpen={isEssayModalOpen}
        sessionId={activeSessionId}
        onClose={() => setIsEssayModalOpen(false)}
        onSuccess={handleEssaySuccess}
        currentProvider={currentProvider}
      />

      {/* Error Toast Notification */}
      {errorToast && (
        <div
          style={{
            position: 'fixed',
            bottom: '24px',
            right: '24px',
            background: '#1B1924',
            border: '1px solid var(--accent-rose)',
            boxShadow: '0 8px 30px rgba(0, 0, 0, 0.6)',
            borderRadius: 'var(--radius-md)',
            padding: '12px 16px',
            zIndex: 100,
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            maxWidth: '420px',
            color: '#FECDD3',
            fontSize: '13px',
          }}
        >
          <AlertCircle size={18} color="var(--accent-rose)" style={{ flexShrink: 0 }} />
          <span style={{ flex: 1 }}>{errorToast}</span>
          <button onClick={() => setErrorToast(null)} className="btn-ghost" style={{ padding: '2px' }}>
            <X size={14} />
          </button>
        </div>
      )}
    </div>
  );
};
