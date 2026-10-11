import React, { useState } from 'react';
import { X, Sparkles, BookOpen, CheckCircle, Loader2 } from 'lucide-react';
import { generateEssay } from '../api';
import { EssayResponse } from '../types';

interface EssayModalProps {
  isOpen: boolean;
  sessionId?: string | null;
  onClose: () => void;
  onSuccess: (essay: EssayResponse) => void;
  currentProvider?: string;
}

export const EssayModal: React.FC<EssayModalProps> = ({
  isOpen,
  sessionId,
  onClose,
  onSuccess,
  currentProvider = 'ollama',
}) => {
  const [topic, setTopic] = useState('');
  const [guestFilter, setGuestFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!topic.trim()) return;

    setLoading(true);
    setError(null);
    setCurrentStep(1);

    // Simulated progress steps for user feedback during multi-phase generation
    const timer1 = setTimeout(() => setCurrentStep(2), 2500);
    const timer2 = setTimeout(() => setCurrentStep(3), 6000);

    try {
      const result = await generateEssay({
        topic: topic.trim(),
        session_id: sessionId || null,
        guest_filter: guestFilter.trim() || null,
        model_provider: currentProvider,
      });
      clearTimeout(timer1);
      clearTimeout(timer2);
      setCurrentStep(4);
      setTimeout(() => {
        onSuccess(result);
        onClose();
        setTopic('');
        setGuestFilter('');
        setLoading(false);
        setCurrentStep(0);
      }, 600);
    } catch (err: unknown) {
      clearTimeout(timer1);
      clearTimeout(timer2);
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      setLoading(false);
      setCurrentStep(0);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.75)',
        backdropFilter: 'blur(6px)',
        zIndex: 50,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '16px',
      }}
    >
      <div
        className="card-base"
        style={{
          width: '100%',
          maxWidth: '560px',
          background: '#1B1924',
          border: '1px solid #35313F',
          padding: '24px',
          boxShadow: '0 20px 50px rgba(0,0,0,0.7)',
          borderRadius: 'var(--radius-lg)',
        }}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: '16px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: '36px',
                height: '36px',
                borderRadius: '8px',
                background: 'rgba(215, 255, 95, 0.12)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#D7FF5F',
              }}
            >
              <BookOpen size={20} />
            </div>
            <div>
              <h2 style={{ fontSize: '16px', fontWeight: 700, color: '#F5F2EA', margin: 0 }}>
                Ship 30 for 30 Essay Skill
              </h2>
              <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                4A Framework (~1,250 Words) • 2-Year Test • Traceable Citations
              </div>
            </div>
          </div>

          <button onClick={onClose} disabled={loading} className="btn-ghost">
            <X size={18} />
          </button>
        </div>

        {/* Framework Badges */}
        <div
          style={{
            display: 'flex',
            gap: '6px',
            marginBottom: '20px',
            padding: '10px 12px',
            background: '#111018',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid #35313F',
          }}
        >
          {['Actionable', 'Analytical', 'Aspirational', 'Anthropological'].map((pill, i) => (
            <span
              key={i}
              style={{
                fontSize: '11px',
                fontWeight: 600,
                color: '#D7FF5F',
                background: 'rgba(215, 255, 95, 0.08)',
                padding: '2px 8px',
                borderRadius: '4px',
                border: '1px solid rgba(215, 255, 95, 0.18)',
              }}
            >
              {pill}
            </span>
          ))}
        </div>

        {/* Generation Form */}
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: '14px' }}>
            <label
              style={{
                display: 'block',
                fontSize: '12px',
                fontWeight: 600,
                marginBottom: '6px',
                color: '#F5F2EA',
              }}
            >
              Essay Topic or Core Hypothesis *
            </label>
            <input
              type="text"
              required
              disabled={loading}
              placeholder="e.g. Why Retention Is The Only Growth Metric That Truly Matters"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              style={{
                width: '100%',
                padding: '10px 12px',
                background: '#111018',
                border: '1px solid #35313F',
                borderRadius: 'var(--radius-sm)',
                color: '#F5F2EA',
                fontSize: '13.5px',
                outline: 'none',
              }}
            />
          </div>

          <div style={{ marginBottom: '20px' }}>
            <label
              style={{
                display: 'block',
                fontSize: '12px',
                fontWeight: 600,
                marginBottom: '6px',
                color: 'var(--text-secondary)',
              }}
            >
              Optional Guest Filter (Focus on specific wisdom)
            </label>
            <input
              type="text"
              disabled={loading}
              placeholder="e.g. Brian Balfour, Elena Verna, Shreyas Doshi"
              value={guestFilter}
              onChange={(e) => setGuestFilter(e.target.value)}
              style={{
                width: '100%',
                padding: '8px 12px',
                background: '#111018',
                border: '1px solid #35313F',
                borderRadius: 'var(--radius-sm)',
                color: '#F5F2EA',
                fontSize: '13px',
                outline: 'none',
              }}
            />
          </div>

          {/* Stepper Status when loading */}
          {loading && (
            <div
              style={{
                padding: '14px',
                background: '#111018',
                borderRadius: 'var(--radius-sm)',
                marginBottom: '16px',
                border: '1px solid #35313F',
              }}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '12px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  {currentStep >= 1 ? (
                    <CheckCircle size={14} color="var(--accent-emerald)" />
                  ) : (
                    <Loader2 size={14} className="animate-spin" />
                  )}
                  <span style={{ color: currentStep >= 1 ? 'var(--text-primary)' : 'var(--text-muted)' }}>
                    Searching & indexing transcript knowledge base...
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  {currentStep >= 2 ? (
                    <CheckCircle size={14} color="var(--accent-emerald)" />
                  ) : (
                    <span style={{ width: '14px', textAlign: 'center', color: 'var(--text-disabled)' }}>•</span>
                  )}
                  <span style={{ color: currentStep >= 2 ? 'var(--text-primary)' : 'var(--text-muted)' }}>
                    Synthesizing 4A structural outline & evidence claims...
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  {currentStep >= 3 ? (
                    <CheckCircle size={14} color="var(--accent-emerald)" />
                  ) : (
                    <span style={{ width: '14px', textAlign: 'center', color: 'var(--text-disabled)' }}>•</span>
                  )}
                  <span style={{ color: currentStep >= 3 ? 'var(--text-primary)' : 'var(--text-muted)' }}>
                    Generating 4A editorial essay & interactive HTML artifact...
                  </span>
                </div>
                {currentStep >= 3 && (
                  <div style={{ fontSize: '11.5px', color: '#D7FF5F', marginLeft: '22px', marginTop: '2px' }}>
                    {currentProvider === 'ollama'
                      ? '⏳ On-device CPU inference active (~60-90s). The 4A essay artifact will open automatically when completed.'
                      : '⚡ Cloud model inference active (~15-30s)...'}
                  </div>
                )}
              </div>
            </div>
          )}

          {error && (
            <div
              style={{
                padding: '10px 12px',
                background: 'var(--accent-rose-glow)',
                border: '1px solid var(--accent-rose)',
                borderRadius: 'var(--radius-sm)',
                color: '#FECDD3',
                fontSize: '12.5px',
                marginBottom: '16px',
              }}
            >
              {error}
            </div>
          )}

          {/* Action Buttons */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
            <button
              type="button"
              disabled={loading}
              onClick={onClose}
              className="btn-secondary"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || !topic.trim()}
              className="btn-primary"
            >
              {loading ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  <span>Synthesizing Essay...</span>
                </>
              ) : (
                <>
                  <Sparkles size={14} />
                  <span>Generate Ship 30 Essay</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
