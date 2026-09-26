import React, { useState, useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Sparkles,
  X,
  Minus,
  Maximize2,
  Send,
  Trash2,
  ShieldCheck,
  Table,
  ChevronRight,
  ExternalLink,
  Zap,
  Mic,
  MicOff,
  Volume2,
  VolumeX,
  Share2,
  ShoppingBag,
  Square,
} from 'lucide-react';
import api from '../../services/api';
import SkuExplainabilityModal from './SkuExplainabilityModal';
import MarkdownViewer from './MarkdownViewer';

export default function FloatingChatBot() {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [inputQuery, setInputQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [selectedSkuForModal, setSelectedSkuForModal] = useState(null);
  const [isListening, setIsListening] = useState(false);
  const [autoVoice, setAutoVoice] = useState(true);
  const [currentlySpeakingId, setCurrentlySpeakingId] = useState(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const recognitionRef = useRef(null);
  const location = useLocation();
  const navigate = useNavigate();

  // Route-based context hints
  const getContextPrompts = (path) => {
    if (path.includes('inventory')) {
      return [
        "Which items are currently below ROP?",
        "Which SKUs will stock out before Diwali?",
        "What's my total capital tied up in dead stock?",
      ];
    }
    if (path.includes('forecast')) {
      return [
        "Show me the top 10 SKUs by sales volume",
        "Which model is best?",
        "Demand for SKU 19512",
      ];
    }
    if (path.includes('procurement') || path.includes('purchase')) {
      return [
        "Show purchase orders",
        "Who are my suppliers?",
        "Which products should I buy now given prices are rising?",
      ];
    }
    if (path.includes('price') || path.includes('market')) {
      return [
        "Which products should I buy now given prices are rising?",
        "Show commodity price movers",
        "What's my total capital tied up in dead stock?",
      ];
    }
    // Default / Dashboard
    return [
      "SKU 476825 ka 30 units ka order create karo",
      "Dead stock par 20% discount laga do",
      "Dukaan me munafa kaise badhaye?",
      "Kitna paisa dead stock mein fasa hai?",
    ];
  };

  const contextPrompts = getContextPrompts(location.pathname);

  // If user navigates to the dedicated /assistant page, hide the floating widget to avoid redundancy
  const isAssistantPage = location.pathname === '/assistant';

  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
      inputRef.current?.focus();
    }
  }, [isOpen, messages]);

  // Pre-load and cache voices
  useEffect(() => {
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      const loadVoices = () => {
        window.speechSynthesis.getVoices();
      };
      loadVoices();
      window.speechSynthesis.onvoiceschanged = loadVoices;
    }
  }, []);

  // Initialize SpeechRecognition for Voice Chat
  useEffect(() => {
    const SpeechRecognition = typeof window !== 'undefined' && (window.SpeechRecognition || window.webkitSpeechRecognition);
    if (SpeechRecognition) {
      try {
        const recognition = new SpeechRecognition();
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.lang = 'hi-IN'; // Recognizes both Hindi & Indian English

        recognition.onstart = () => setIsListening(true);
        recognition.onend = () => setIsListening(false);
        recognition.onerror = () => setIsListening(false);
        recognition.onresult = (event) => {
          const transcript = event.results?.[0]?.[0]?.transcript;
          if (transcript) {
            setInputQuery(transcript);
            handleSend(transcript, true); // true = called from voice input
          }
        };
        recognitionRef.current = recognition;
      } catch (e) {
        console.warn('SpeechRecognition initialization error', e);
      }
    }
    return () => {
      if (typeof window !== 'undefined' && window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  const toggleListening = () => {
    if (!recognitionRef.current) {
      alert("Aapke browser me microphone speech recognition support nahi kar raha hai. Chrome ya Edge use karein.");
      return;
    }
    if (isListening) {
      recognitionRef.current.stop();
      setIsListening(false);
    } else {
      try {
        recognitionRef.current.start();
      } catch (e) {
        console.warn("Could not start speech recognition", e);
      }
    }
  };

  const cleanSpeechText = (text) => {
    if (!text) return '';
    return text
      .replace(/[*#_`~]/g, '') // remove markdown symbols
      .replace(/[\u{1F300}-\u{1F9FF}\u{2600}-\u{27BF}\u{1F600}-\u{1F64F}\u{1F680}-\u{1F6FF}]/gu, '') // remove emojis
      .replace(/₹\s*/g, 'rupaye ')
      .replace(/\$\s*/g, 'dollar ')
      .replace(/\s+/g, ' ')
      .trim();
  };

  const speakText = (text, id, lang = 'hi') => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) return;
    if (currentlySpeakingId === id) {
      window.speechSynthesis.cancel();
      setCurrentlySpeakingId(null);
      return;
    }
    window.speechSynthesis.cancel();
    const clean = cleanSpeechText(text);
    if (!clean) return;

    const utterance = new SpeechSynthesisUtterance(clean);
    utterance.rate = 1.0;
    utterance.pitch = 1.0;

    const voices = window.speechSynthesis.getVoices() || [];
    const isHindi = lang === 'hi' || /[\u0900-\u097F]/.test(text) || /hai|hain|karo|bik|saman|dukaan|paisa|kisko|reorder/i.test(text);

    let chosenVoice = null;
    if (isHindi) {
      chosenVoice = voices.find(v => 
        v.lang === 'hi-IN' || 
        v.lang.startsWith('hi') || 
        /hindi|swara|madhur|kalpana|hemant/i.test(v.name)
      );
      if (!chosenVoice) {
        chosenVoice = voices.find(v => 
          v.lang === 'en-IN' || 
          /india|neerja|ravi|prabhat|heera/i.test(v.name)
        );
      }
      utterance.lang = chosenVoice?.lang || 'hi-IN';
    } else {
      chosenVoice = voices.find(v => v.lang.startsWith('en')) || voices[0];
      utterance.lang = chosenVoice?.lang || 'en-US';
    }

    if (chosenVoice) {
      utterance.voice = chosenVoice;
    }

    utterance.onstart = () => setCurrentlySpeakingId(id);
    utterance.onend = () => setCurrentlySpeakingId(null);
    utterance.onerror = (e) => {
      console.warn("Speech synthesis error", e);
      setCurrentlySpeakingId(null);
    };
    window.speechSynthesis.speak(utterance);
  };

  const handleSend = async (customQuery, isFromVoice = false) => {
    const q = (customQuery || inputQuery).trim();
    if (!q || loading) return;

    setInputQuery('');
    const userMsg = { id: Date.now(), role: 'user', content: q, time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      const res = await api.post('/assistant/query', { query: q });
      const detectedLang = res.data?.detected_language || 'hi';
      const botMsg = {
        id: Date.now() + 1,
        role: 'assistant',
        status: res.data?.status,
        template: res.data?.template_name,
        content: res.data?.prose,
        table: res.data?.table,
        actionResult: res.data?.action_result,
        executionMs: res.data?.execution_ms,
        suggestedPrompts: res.data?.suggested_prompts,
        detectedLanguage: detectedLang,
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, botMsg]);

      // Auto-speak response if triggered by voice OR autoVoice is active
      if ((isFromVoice || autoVoice) && res.data?.prose) {
        speakText(res.data.prose, botMsg.id, detectedLang);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 1,
          role: 'assistant',
          status: 'error',
          content: "Sorry, I encountered an issue connecting to the decision intelligence engine. Please try asking again.",
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const clearChat = () => {
    setMessages([]);
    if (typeof window !== 'undefined' && window.speechSynthesis) {
      window.speechSynthesis.cancel();
      setCurrentlySpeakingId(null);
    }
  };

  if (isAssistantPage) return null;

  return (
    <>
      {/* Floating Toggle Button */}
      {!isOpen && (
        <div style={{ position: 'fixed', bottom: '24px', right: '24px', zIndex: 1000 }}>
          <button
            onClick={() => setIsOpen(true)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '10px 16px',
              backgroundColor: 'var(--accent-primary)',
              color: '#ffffff',
              borderRadius: 'var(--border-radius-pill)',
              border: '1px solid rgba(255, 255, 255, 0.2)',
              boxShadow: '0 4px 14px rgba(30, 64, 175, 0.35)',
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: '13px',
              transition: 'all 0.2s ease',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.transform = 'translateY(-2px)')}
            onMouseLeave={(e) => (e.currentTarget.style.transform = 'translateY(0)')}
            title="Open AI Decision Assistant"
          >
            <Sparkles size={16} color="#93c5fd" />
            <span>Ask Copilot</span>
            <span
              style={{
                display: 'inline-block',
                width: '7px',
                height: '7px',
                borderRadius: '50%',
                backgroundColor: '#22c55e',
                boxShadow: '0 0 6px #22c55e',
              }}
            />
          </button>
        </div>
      )}

      {/* Floating Drawer Modal */}
      {isOpen && (
        <div
          style={{
            position: 'fixed',
            bottom: '20px',
            right: '20px',
            width: '420px',
            maxWidth: 'calc(100vw - 32px)',
            height: '580px',
            maxHeight: 'calc(100vh - 40px)',
            backgroundColor: 'var(--bg-surface)',
            borderRadius: 'var(--border-radius-lg)',
            border: '1px solid var(--border-subtle)',
            boxShadow: 'var(--shadow-dropdown)',
            display: 'flex',
            flexDirection: 'column',
            zIndex: 1001,
            overflow: 'hidden',
          }}
        >
          {/* Header */}
          <div
            style={{
              padding: '12px 16px',
              backgroundColor: 'var(--accent-primary)',
              color: '#ffffff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div
                style={{
                  width: '28px',
                  height: '28px',
                  borderRadius: 'var(--border-radius-sm)',
                  backgroundColor: 'rgba(255, 255, 255, 0.15)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <Sparkles size={16} color="#bfdbfe" />
              </div>
              <div>
                <div style={{ fontSize: '13px', fontWeight: 700, lineHeight: 1.2 }}>
                  DemandIQ Copilot
                </div>
                <div style={{ fontSize: '10px', color: '#bfdbfe', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <ShieldCheck size={11} /> Zero-SQL Guarded Engine
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <button
                onClick={() => {
                  if (currentlySpeakingId) {
                    window.speechSynthesis?.cancel();
                    setCurrentlySpeakingId(null);
                  }
                  setAutoVoice((prev) => !prev);
                }}
                style={{
                  background: autoVoice ? '#059669' : 'rgba(255, 255, 255, 0.15)',
                  border: autoVoice ? '1px solid #34d399' : '1px solid rgba(255, 255, 255, 0.2)',
                  color: '#ffffff',
                  cursor: 'pointer',
                  padding: '4px 8px',
                  borderRadius: '20px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  fontSize: '10px',
                  fontWeight: 600,
                  boxShadow: autoVoice ? '0 0 8px rgba(16, 185, 129, 0.6)' : 'none',
                }}
                title={autoVoice ? "Awaaz (Voice) Response ON - Click to mute" : "Awaaz (Voice) Response OFF - Click to unmute"}
              >
                {autoVoice ? <Volume2 size={12} color="#ffffff" /> : <VolumeX size={12} color="#cbd5e1" />}
                <span>{autoVoice ? 'Awaaz ON' : 'Awaaz OFF'}</span>
              </button>
              {messages.length > 0 && (
                <button
                  onClick={clearChat}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: '#cbd5e1',
                    cursor: 'pointer',
                    padding: '4px',
                    borderRadius: '4px',
                  }}
                  title="Clear conversation"
                >
                  <Trash2 size={14} />
                </button>
              )}
              <button
                onClick={() => {
                  setIsOpen(false);
                  navigate('/assistant');
                }}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#cbd5e1',
                  cursor: 'pointer',
                  padding: '4px',
                  borderRadius: '4px',
                }}
                title="Expand to Full Studio"
              >
                <Maximize2 size={14} />
              </button>
              <button
                onClick={() => setIsOpen(false)}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#cbd5e1',
                  cursor: 'pointer',
                  padding: '4px',
                  borderRadius: '4px',
                }}
                title="Minimize Copilot"
              >
                <X size={16} />
              </button>
            </div>
          </div>

          {/* Context Banner */}
          <div
            style={{
              padding: '6px 14px',
              backgroundColor: 'var(--bg-surface-subtle)',
              borderBottom: '1px solid var(--border-subtle)',
              fontSize: '11px',
              color: 'var(--text-secondary)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <span>Live Supply Chain Decision Copilot</span>
            <span style={{ fontWeight: 600, color: 'var(--accent-primary)', fontSize: '10px' }}>
              Scope: Active Tenant
            </span>
          </div>

          {/* Messages Body */}
          <div
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: '14px',
              display: 'flex',
              flexDirection: 'column',
              gap: '12px',
              backgroundColor: 'var(--bg-main)',
            }}
          >
            {messages.length === 0 ? (
              <div style={{ padding: '8px 0', textAlign: 'center' }}>
                <div
                  style={{
                    width: '40px',
                    height: '40px',
                    margin: '0 auto 8px',
                    borderRadius: '50%',
                    backgroundColor: 'var(--accent-primary-subtle)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: 'var(--accent-primary)',
                  }}
                >
                  <Sparkles size={20} />
                </div>
                <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '4px' }}>
                  Ask anything about your supply chain
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '14px', lineHeight: 1.4 }}>
                  Verified parameterized answers computed over your live stock, forecasts, and orders.
                </div>

                {/* Quick Prompts */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', textAlign: 'left' }}>
                  <div style={{ fontSize: '10px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    Suggested for this screen:
                  </div>
                  {contextPrompts.map((p, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleSend(p)}
                      style={{
                        padding: '8px 10px',
                        backgroundColor: 'var(--bg-surface)',
                        border: '1px solid var(--border-subtle)',
                        borderRadius: 'var(--border-radius-md)',
                        fontSize: '11px',
                        color: 'var(--text-primary)',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        textAlign: 'left',
                        transition: 'border-color 0.15s ease',
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'var(--accent-primary)')}
                      onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'var(--border-subtle)')}
                    >
                      <span style={{ fontWeight: 500 }}>{p}</span>
                      <ChevronRight size={13} color="var(--text-muted)" />
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((m) => (
                <div
                  key={m.id}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: m.role === 'user' ? 'flex-end' : 'flex-start',
                  }}
                >
                  <div
                    style={{
                      maxWidth: '88%',
                      padding: '10px 12px',
                      borderRadius: 'var(--border-radius-lg)',
                      fontSize: '12px',
                      lineHeight: 1.5,
                      backgroundColor: m.role === 'user' ? 'var(--accent-primary)' : 'var(--bg-surface)',
                      color: m.role === 'user' ? '#ffffff' : 'var(--text-primary)',
                      border: m.role === 'user' ? 'none' : '1px solid var(--border-subtle)',
                      boxShadow: 'var(--shadow-sm)',
                    }}
                  >
                    {/* Bot header */}
                    {m.role === 'assistant' && m.template && (
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          borderBottom: '1px solid var(--border-subtle)',
                          paddingBottom: '4px',
                          marginBottom: '6px',
                          fontSize: '10px',
                          color: 'var(--text-muted)',
                        }}
                      >
                        <span style={{ fontWeight: 600, color: 'var(--accent-primary)' }}>
                          {m.template}
                        </span>
                        {m.executionMs !== undefined && (
                          <span style={{ fontFamily: 'var(--font-mono)' }}>{m.executionMs}ms</span>
                        )}
                      </div>
                    )}

                    {/* Prose */}
                    {m.role === 'user' ? (
                      <div style={{ whiteSpace: 'pre-wrap' }}>{m.content}</div>
                    ) : (
                      <MarkdownViewer content={m.content} />
                    )}

                    {/* Mini Table Preview */}
                    {m.table && m.table.rows && m.table.rows.length > 0 && (
                      <div
                        style={{
                          marginTop: '8px',
                          backgroundColor: 'var(--bg-surface-subtle)',
                          borderRadius: 'var(--border-radius-sm)',
                          border: '1px solid var(--border-subtle)',
                          overflow: 'hidden',
                          fontSize: '10px',
                        }}
                      >
                        <div
                          style={{
                            padding: '4px 8px',
                            backgroundColor: 'var(--bg-surface)',
                            borderBottom: '1px solid var(--border-subtle)',
                            fontWeight: 600,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            color: 'var(--text-secondary)',
                          }}
                        >
                          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                            <Table size={12} color="var(--accent-primary)" />
                            {m.table.rows.length} records verified
                          </span>
                          <button
                            onClick={() => navigate('/assistant')}
                            style={{
                              background: 'none',
                              border: 'none',
                              color: 'var(--accent-primary)',
                              fontSize: '10px',
                              fontWeight: 600,
                              cursor: 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '2px',
                            }}
                          >
                            Full View <ExternalLink size={10} />
                          </button>
                        </div>
                        <div style={{ maxHeight: '120px', overflowY: 'auto' }}>
                          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                            <thead>
                              <tr style={{ backgroundColor: 'var(--bg-surface)', color: 'var(--text-muted)', borderBottom: '1px solid var(--border-subtle)' }}>
                                {m.table.columns.slice(0, 3).map((col) => (
                                  <th key={col} style={{ padding: '3px 6px', fontWeight: 600 }}>{col.replace(/_/g, ' ')}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {m.table.rows.slice(0, 4).map((r, rIdx) => (
                                <tr key={rIdx} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                                  {m.table.columns.slice(0, 3).map((col, cIdx) => (
                                    <td key={cIdx} style={{ padding: '3px 6px', fontFamily: 'var(--font-mono)' }}>
                                      {String(r[col] ?? '')}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}

                    {/* Unmapped pills */}
                    {m.suggestedPrompts && (
                      <div style={{ marginTop: '8px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        {m.suggestedPrompts.slice(0, 3).map((sp, idx) => (
                          <button
                            key={idx}
                            onClick={() => handleSend(sp)}
                            style={{
                              padding: '4px 8px',
                              backgroundColor: 'var(--accent-primary-subtle)',
                              border: '1px solid var(--accent-primary-border)',
                              borderRadius: '4px',
                              fontSize: '10px',
                              color: 'var(--accent-primary-text)',
                              cursor: 'pointer',
                              textAlign: 'left',
                              fontWeight: 500,
                            }}
                          >
                            {sp}
                          </button>
                        ))}
                      </div>
                    )}

                    {/* Autonomous Action Live Execution Banner */}
                    {m.actionResult && (
                      <div
                        style={{
                          marginTop: '8px',
                          padding: '8px 10px',
                          borderRadius: '6px',
                          backgroundColor: 'rgba(16, 185, 129, 0.12)',
                          border: '1px solid rgba(16, 185, 129, 0.4)',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '6px',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', fontWeight: 700, color: '#10b981' }}>
                          <Zap size={13} fill="#10b981" />
                          {m.actionResult.action_type === 'PO_CREATED' ? (
                            <span>⚡ Live PO Generated in DB: {m.actionResult.po_number}</span>
                          ) : (
                            <span>⚡ Live Clearance Discount Applied ({Math.round((m.actionResult.discount_pct || 0.20) * 100)}%)</span>
                          )}
                        </div>

                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '2px' }}>
                          {m.actionResult.action_type === 'PO_CREATED' ? (
                            <button
                              onClick={() => {
                                setIsOpen(false);
                                navigate('/purchase-orders');
                              }}
                              style={{
                                backgroundColor: '#10b981',
                                color: '#ffffff',
                                border: 'none',
                                borderRadius: '4px',
                                padding: '4px 10px',
                                fontSize: '10px',
                                fontWeight: 600,
                                cursor: 'pointer',
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '4px',
                              }}
                            >
                              <ShoppingBag size={11} />
                              <span>View PO in Orders</span>
                            </button>
                          ) : (
                            <button
                              onClick={() => {
                                setIsOpen(false);
                                navigate('/inventory/dead-stock');
                              }}
                              style={{
                                backgroundColor: '#0284c7',
                                color: '#ffffff',
                                border: 'none',
                                borderRadius: '4px',
                                padding: '4px 10px',
                                fontSize: '10px',
                                fontWeight: 600,
                                cursor: 'pointer',
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '4px',
                              }}
                            >
                              <Table size={11} />
                              <span>View Dead Stock</span>
                            </button>
                          )}

                          {m.actionResult.whatsapp_text && (
                            <button
                              onClick={() => {
                                window.open(`https://wa.me/?text=${encodeURIComponent(m.actionResult.whatsapp_text)}`, '_blank');
                              }}
                              style={{
                                backgroundColor: '#25D366',
                                color: '#ffffff',
                                border: 'none',
                                borderRadius: '4px',
                                padding: '4px 10px',
                                fontSize: '10px',
                                fontWeight: 600,
                                cursor: 'pointer',
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '4px',
                              }}
                            >
                              <Share2 size={11} />
                              <span>WhatsApp Order Slip</span>
                            </button>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Bot Voice & Decision Action Bar */}
                    {m.role === 'assistant' && (
                      <div
                        style={{
                          marginTop: '8px',
                          paddingTop: '6px',
                          borderTop: '1px solid var(--border-subtle)',
                          display: 'flex',
                          flexWrap: 'wrap',
                          alignItems: 'center',
                          gap: '6px',
                        }}
                      >
                        {/* Listen Voice Button */}
                        <button
                          onClick={() => speakText(m.content, m.id, m.detectedLanguage || 'hi')}
                          style={{
                            background: currentlySpeakingId === m.id ? '#ef4444' : 'var(--bg-main)',
                            color: currentlySpeakingId === m.id ? '#ffffff' : 'var(--text-secondary)',
                            border: '1px solid var(--border-subtle)',
                            borderRadius: '4px',
                            padding: '3px 8px',
                            fontSize: '10px',
                            fontWeight: 600,
                            cursor: 'pointer',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px',
                            transition: 'all 0.2s',
                          }}
                          title={currentlySpeakingId === m.id ? "Awaaz roko (Stop voice)" : "Jawab suniye (Listen in Hindi/English)"}
                        >
                          {currentlySpeakingId === m.id ? <Square size={10} /> : <Volume2 size={10} />}
                          <span>{currentlySpeakingId === m.id ? 'Awaaz Roko (Stop)' : 'Suniye (Listen)'}</span>
                        </button>

                        {/* Decision 1: Create Purchase Order (if not already a PO action) */}
                        {!m.actionResult && (
                          <button
                            onClick={() => {
                              setIsOpen(false);
                              navigate('/purchase-orders');
                            }}
                            style={{
                              backgroundColor: '#10b981',
                              color: '#ffffff',
                              border: 'none',
                              borderRadius: '4px',
                              padding: '3px 8px',
                              fontSize: '10px',
                              fontWeight: 600,
                              cursor: 'pointer',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '4px',
                              boxShadow: '0 1px 2px rgba(16, 185, 129, 0.2)',
                            }}
                            title="Generate a real Purchase Order for this item"
                          >
                            <ShoppingBag size={11} />
                            <span>Order Bhejo (PO)</span>
                          </button>
                        )}

                        {/* Decision 2: Share to WhatsApp (if not already having custom WhatsApp button) */}
                        {!m.actionResult?.whatsapp_text && (
                          <button
                            onClick={() => {
                              const waText = `Namaste Ji,\n\n*DemandIQ Decision Assistant Alert:*\n${m.content?.replace(/[*#_`]/g, '').slice(0, 200)}...\n\nKripya reorder check karein. Dhanyawad!`;
                              window.open(`https://wa.me/?text=${encodeURIComponent(waText)}`, '_blank');
                            }}
                            style={{
                              backgroundColor: '#25D366',
                              color: '#ffffff',
                              border: 'none',
                              borderRadius: '4px',
                              padding: '3px 8px',
                              fontSize: '10px',
                              fontWeight: 600,
                              cursor: 'pointer',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '4px',
                            }}
                            title="Send alert / reorder directly to supplier via WhatsApp"
                          >
                            <Share2 size={11} />
                            <span>WhatsApp</span>
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                  <span style={{ fontSize: '9px', color: 'var(--text-muted)', marginTop: '2px', padding: '0 4px' }}>
                    {m.time}
                  </span>
                </div>
              ))
            )}

            {loading && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 12px', backgroundColor: 'var(--bg-surface)', borderRadius: 'var(--border-radius-md)', border: '1px solid var(--border-subtle)', width: 'fit-content', fontSize: '11px', color: 'var(--text-secondary)' }}>
                <span style={{ display: 'inline-block', width: '12px', height: '12px', border: '2px solid var(--border-subtle)', borderTopColor: 'var(--accent-primary)', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
                <span>Computing verified decision intelligence...</span>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input Bar */}
          <div
            style={{
              padding: '10px 14px',
              backgroundColor: 'var(--bg-surface)',
              borderTop: '1px solid var(--border-subtle)',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <input
              ref={inputRef}
              type="text"
              value={inputQuery}
              onChange={(e) => setInputQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
              placeholder={isListening ? "Sun rahe hain... (Speak now)..." : "Puchiye ya Mic daba kar boliye..."}
              style={{
                flex: 1,
                padding: '8px 12px',
                borderRadius: 'var(--border-radius-md)',
                border: isListening ? '1px solid #ef4444' : '1px solid var(--border-subtle)',
                fontSize: '12px',
                outline: 'none',
                backgroundColor: isListening ? '#fef2f2' : 'var(--bg-main)',
                color: 'var(--text-primary)',
              }}
            />

            {/* Mic Speech-to-Text Button */}
            <button
              onClick={toggleListening}
              type="button"
              style={{
                padding: '8px 10px',
                backgroundColor: isListening ? '#ef4444' : 'var(--bg-main)',
                color: isListening ? '#ffffff' : 'var(--text-secondary)',
                border: isListening ? 'none' : '1px solid var(--border-subtle)',
                borderRadius: 'var(--border-radius-md)',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'all 0.2s',
                boxShadow: isListening ? '0 0 10px rgba(239, 68, 68, 0.5)' : 'none',
              }}
              title={isListening ? "Listening... click to stop" : "Bolkar sawal puchiye (Click to speak in Hindi/English)"}
            >
              {isListening ? <MicOff size={14} /> : <Mic size={14} />}
            </button>

            <button
              onClick={() => handleSend()}
              disabled={!inputQuery.trim() || loading}
              style={{
                padding: '8px 14px',
                backgroundColor: 'var(--accent-primary)',
                color: '#ffffff',
                border: 'none',
                borderRadius: 'var(--border-radius-md)',
                cursor: !inputQuery.trim() || loading ? 'not-allowed' : 'pointer',
                opacity: !inputQuery.trim() || loading ? 0.6 : 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
              title="Send message"
            >
              <Send size={14} />
            </button>
          </div>
        </div>
      )}

      {/* Sku Explainability Modal */}
      {selectedSkuForModal && (
        <SkuExplainabilityModal
          productId={selectedSkuForModal}
          onClose={() => setSelectedSkuForModal(null)}
        />
      )}
    </>
  );
}
