import React, { useState, useRef, useEffect } from 'react';
import {
  Send,
  Square,
  Sparkles,
  ArrowRight,
  TrendingUp,
  Target,
  Zap,
} from 'lucide-react';
import { MessageItem } from '../types';
import { ChatMessage } from './ChatMessage';

interface ChatViewProps {
  messages: MessageItem[];
  isStreaming: boolean;
  streamingMessage: string;
  onSendMessage: (text: string) => void;
  onStopStreaming?: () => void;
  onOpenEssayModal: () => void;
  onOpenArtifact?: (artifactId?: string) => void;
}

const PROMPT_STARTERS = [
  {
    icon: <Target size={14} color="#D7FF5F" />,
    text: 'How does Shreyas Doshi differentiate between high-agency PMs and good execution?',
  },
  {
    icon: <Sparkles size={14} color="#7DD3FC" />,
    text: 'Draft a Ship 30 for 30 essay on Product-Led Sales based on Pete Kazanjy’s playbook.',
  },
  {
    icon: <TrendingUp size={14} color="#4ADE80" />,
    text: 'What are Elena Verna’s rules for when B2B companies should launch self-serve pricing?',
  },
  {
    icon: <Sparkles size={14} color="#D7FF5F" />,
    text: 'Create an HTML card summarizing the retention loop advice from the transcripts.',
  },
  {
    icon: <Zap size={14} color="#D7FF5F" />,
    text: 'Explain the Cold Start Problem and atomic networks using Andrew Chen’s framework.',
  },
];

export const ChatView: React.FC<ChatViewProps> = ({
  messages,
  isStreaming,
  streamingMessage,
  onSendMessage,
  onStopStreaming,
  onOpenEssayModal,
  onOpenArtifact,
}) => {
  const [inputText, setInputText] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom when messages or streaming text updates
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingMessage]);

  const handleSend = () => {
    if (!inputText.trim() || isStreaming) return;
    onSendMessage(inputText.trim());
    setInputText('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputText(e.target.value);
    // Auto resize height up to 160px
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
    }
  };

  return (
    <main className="chat-stage" aria-label="Conversation Stage">
      {/* Scrollable Message Feed */}
      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
        {messages.length === 0 ? (
          /* Empty State: Editorial Welcoming Screen */
          <div
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '40px 24px',
              maxWidth: '760px',
              margin: '0 auto',
              textAlign: 'center',
            }}
          >
            <div
              style={{
                width: '48px',
                height: '48px',
                borderRadius: '12px',
                background: 'linear-gradient(135deg, #D7FF5F, #A3E635)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#111018',
                marginBottom: '16px',
                boxShadow: '0 4px 20px rgba(215, 255, 95, 0.25)',
              }}
            >
              <Sparkles size={24} />
            </div>

            <h1
              style={{
                fontFamily: 'var(--font-serif)',
                fontSize: '28px',
                fontWeight: 600,
                color: '#F5F2EA',
                marginBottom: '10px',
                letterSpacing: '-0.3px',
              }}
            >
              What growth framework would you like to explore today?
            </h1>

            <p
              style={{
                fontSize: '14px',
                color: 'var(--text-secondary)',
                lineHeight: '1.6',
                maxWidth: '560px',
                marginBottom: '32px',
              }}
            >
              Ask any product management or growth question strictly grounded in Lenny’s Podcast transcripts, with traceable YouTube timestamps and Ship 30 for 30 essay generation.
            </p>

            {/* Prompt Starter Chips Grid */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
                gap: '10px',
                width: '100%',
              }}
            >
              {PROMPT_STARTERS.map((starter, i) => (
                <div
                  key={i}
                  onClick={() => onSendMessage(starter.text)}
                  className="card-base"
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px',
                    padding: '12px 14px',
                    cursor: 'pointer',
                    textAlign: 'left',
                    background: 'var(--bg-secondary)',
                  }}
                >
                  <div style={{ flexShrink: 0 }}>{starter.icon}</div>
                  <div style={{ flex: 1, fontSize: '13px', color: 'var(--text-primary)' }}>
                    {starter.text}
                  </div>
                  <ArrowRight size={13} color="var(--text-muted)" style={{ flexShrink: 0 }} />
                </div>
              ))}
            </div>
          </div>
        ) : (
          /* Render History Messages */
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {messages.map((m) => (
              <ChatMessage
                key={m.id}
                message={m}
                onOpenArtifact={onOpenArtifact}
              />
            ))}

            {/* In-Flight Streaming Message */}
            {isStreaming && streamingMessage && (
              <ChatMessage
                message={{
                  id: 'streaming-temp',
                  session_id: 'active',
                  role: 'assistant',
                  content: streamingMessage,
                  is_abstention: false,
                  created_at: new Date().toISOString(),
                  citations: [],
                }}
                isStreaming={true}
              />
            )}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Action Bar */}
      <div
        style={{
          borderTop: '1px solid #35313F',
          background: 'rgba(17, 16, 24, 0.95)',
          backdropFilter: 'blur(12px)',
          padding: '12px 20px 16px 20px',
          maxWidth: '880px',
          width: '100%',
          margin: '0 auto',
        }}
      >
        {/* Quick Suggestion Chips */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
          <button
            onClick={onOpenEssayModal}
            className="btn-secondary"
            style={{
              fontSize: '11.5px',
              padding: '4px 10px',
              borderRadius: '999px',
              borderColor: 'rgba(215, 255, 95, 0.4)',
              background: 'rgba(215, 255, 95, 0.1)',
              color: '#D7FF5F',
              fontWeight: 500,
            }}
          >
            <Sparkles size={11} color="#D7FF5F" />
            <span>✍️ Draft Ship 30 Essay</span>
          </button>

          <button
            onClick={() => onSendMessage('What are Brian Balfour’s core principles of growth loops vs funnels?')}
            className="btn-secondary"
            style={{
              fontSize: '11.5px',
              padding: '4px 10px',
              borderRadius: '999px',
              background: '#1B1924',
              borderColor: '#35313F',
              color: 'var(--text-secondary)',
            }}
          >
            <span>🔄 Growth Loops</span>
          </button>

          <button
            onClick={() => onSendMessage('How should product managers balance high agency with team alignment according to Shreyas Doshi?')}
            className="btn-secondary"
            style={{
              fontSize: '11.5px',
              padding: '4px 10px',
              borderRadius: '999px',
              background: '#1B1924',
              borderColor: '#35313F',
              color: 'var(--text-secondary)',
            }}
          >
            <span>🎯 High-Agency PMs</span>
          </button>
        </div>

        {/* Text Input Container */}
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-end',
            gap: '10px',
            background: '#1B1924',
            border: '1px solid #35313F',
            borderRadius: 'var(--radius-md)',
            padding: '8px 12px',
            boxShadow: '0 4px 16px rgba(0, 0, 0, 0.4)',
            transition: 'border-color var(--transition-fast)',
          }}
        >
          <textarea
            ref={textareaRef}
            rows={1}
            value={inputText}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            placeholder="Ask Lenny Growth Assistant about product management, growth loops, PLG..."
            disabled={isStreaming}
            style={{
              flex: 1,
              background: 'transparent',
              border: 'none',
              outline: 'none',
              color: 'var(--text-primary)',
              fontSize: '13.5px',
              lineHeight: '1.5',
              resize: 'none',
              maxHeight: '160px',
              fontFamily: 'var(--font-sans)',
            }}
          />

          {isStreaming ? (
            <button
              onClick={onStopStreaming}
              className="btn-secondary"
              style={{
                padding: '6px 10px',
                color: 'var(--accent-rose)',
                borderColor: 'var(--accent-rose)',
              }}
              title="Stop streaming"
            >
              <Square size={13} fill="currentColor" />
              <span style={{ fontSize: '11.5px' }}>Stop</span>
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!inputText.trim()}
              className="btn-primary"
              style={{
                padding: '7px 12px',
                borderRadius: 'var(--radius-sm)',
              }}
              title="Send message"
            >
              <Send size={14} />
            </button>
          )}
        </div>

        {/* Footer Hint */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginTop: '6px',
            fontSize: '10.5px',
            color: 'var(--text-muted)',
          }}
        >
          <span>Strictly grounded in Lenny’s Podcast transcripts. Hallucinations guarded.</span>
          <span>Press Enter to send • Shift+Enter for new line</span>
        </div>
      </div>
    </main>
  );
};
