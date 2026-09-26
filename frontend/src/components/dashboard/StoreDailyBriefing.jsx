import React, { useState, useEffect, useRef } from 'react';
import {
  Volume2,
  VolumeX,
  Play,
  Square,
  Sparkles,
  Share2,
  AlertTriangle,
  CheckCircle2,
  ArrowRight,
  TrendingUp,
} from 'lucide-react';
import api from '../../services/api';
import { useNavigate } from 'react-router-dom';

export default function StoreDailyBriefing() {
  const navigate = useNavigate();
  const [language, setLanguage] = useState('hinglish'); // 'hinglish' | 'hindi' | 'english'
  const [isPlaying, setIsPlaying] = useState(false);
  const [briefingData, setBriefingData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [playbackRate, setPlaybackRate] = useState(1.0);
  const [speechSupported, setSpeechSupported] = useState(true);

  // Check speech synthesis support on mount
  useEffect(() => {
    if (typeof window !== 'undefined' && !('speechSynthesis' in window)) {
      setSpeechSupported(false);
    }
  }, []);

  // Fetch daily briefing from backend
  useEffect(() => {
    let isMounted = true;
    const fetchBriefing = async () => {
      try {
        const res = await api.get('/assistant/daily-briefing');
        if (isMounted && res.data) {
          setBriefingData(res.data);
        }
      } catch (err) {
        console.warn('Using client-side fallback for daily briefing', err);
        if (isMounted) {
          setBriefingData({
            status: 'fallback',
            health_score: 86,
            total_units: 601760,
            critical_count: 3,
            urgent_items: [
              { product_id: '19512', name: 'Alphonso Mango 1kg', reorder_qty: 60, p_stockout: 0.88 },
              { product_id: '391306', name: 'Basmati Rice 5kg', reorder_qty: 40, p_stockout: 0.94 },
              { product_id: '12872', name: 'Cold Pressed Mustard Oil 1L', reorder_qty: 75, p_stockout: 0.72 },
            ],
            scripts: {
              hinglish:
                'Namaste! Aaj ki store summary: Aapki dukaan me lagbhag 6 Lakh units ki sale record hui hai. Alert: 3 zaroori items jaise Alphonso Mango, Basmati Rice aur Mustard Oil ka stock khatam hone ki kagar par hai. Bikri me nuksan se bachne ke liye naya order abhi supplier ko bhej dein. Aapka store health score 86 percent hai.',
              hindi:
                'नमस्ते! आज की दुकान की ताज़ा रिपोर्ट: आपकी दुकान में लगभग ६ लाख यूनिट्स की बिक्री दर्ज की गई है। ध्यान दें, ३ मुख्य सामान जैसे अल्फांसो आम, बासमती चावल और सरसों तेल का स्टॉक बहुत जल्द समाप्त होने वाला है। बिक्री में रुकावट से बचने के लिए तुरंत सप्लायर को ऑर्डर भेजें। आपकी दुकान का हेल्थ स्कोर ८६ प्रतिशत है।',
              english:
                "Hello! Here is today's store briefing: Total recorded sales reached 601,760 units. Warning: 3 critical items including Alphonso Mango, Basmati Rice, and Mustard Oil are nearing stockout. Place replenishment orders immediately to prevent lost revenue. Overall store health score is 86%.",
            },
            whatsapp_text:
              'Namaste Supplier Ji,\n\nDemandIQ Store Reorder List:\n- Alphonso Mango 1kg: 60 units (Urgent)\n- Basmati Rice 5kg: 40 units (Urgent)\n- Cold Pressed Mustard Oil 1L: 75 units (Urgent)\n\nKripya kal tak delivery karwa dein. Dhanyawad!',
          });
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    fetchBriefing();
    return () => {
      isMounted = false;
      if (typeof window !== 'undefined' && window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  // Voice speech handler
  const handleToggleVoice = () => {
    if (!speechSupported) {
      alert('Aapke browser me voice playback feature support nahi kar raha hai.');
      return;
    }

    if (isPlaying) {
      window.speechSynthesis.cancel();
      setIsPlaying(false);
      return;
    }

    const textToSpeak = briefingData?.scripts?.[language];
    if (!textToSpeak) return;

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(textToSpeak);
    utterance.rate = playbackRate;
    utterance.pitch = 1.0;

    // Pick matching voice
    const voices = window.speechSynthesis.getVoices();
    if (language === 'hindi') {
      const hiVoice = voices.find(
        (v) => v.lang.startsWith('hi') || v.name.toLowerCase().includes('hindi')
      );
      if (hiVoice) utterance.voice = hiVoice;
      utterance.lang = 'hi-IN';
    } else if (language === 'hinglish') {
      const inVoice = voices.find(
        (v) => v.lang.includes('IN') || v.lang.startsWith('hi')
      );
      if (inVoice) utterance.voice = inVoice;
      utterance.lang = 'en-IN';
    } else {
      const enVoice = voices.find((v) => v.lang.startsWith('en'));
      if (enVoice) utterance.voice = enVoice;
      utterance.lang = 'en-US';
    }

    utterance.onstart = () => setIsPlaying(true);
    utterance.onend = () => setIsPlaying(false);
    utterance.onerror = () => setIsPlaying(false);

    window.speechSynthesis.speak(utterance);
  };

  const handleLanguageChange = (newLang) => {
    if (isPlaying) {
      window.speechSynthesis.cancel();
      setIsPlaying(false);
    }
    setLanguage(newLang);
  };

  const handleWhatsAppShare = () => {
    const text = briefingData?.whatsapp_text || '';
    const url = `https://wa.me/?text=${encodeURIComponent(text)}`;
    window.open(url, '_blank');
  };

  const currentScript = briefingData?.scripts?.[language] || '';
  const healthScore = briefingData?.health_score || 85;

  return (
    <div
      style={{
        background: 'linear-gradient(135deg, rgba(238, 242, 255, 0.8) 0%, rgba(245, 243, 255, 0.9) 100%)',
        border: '1px solid rgba(99, 102, 241, 0.25)',
        borderRadius: '16px',
        padding: '20px 24px',
        marginBottom: '24px',
        boxShadow: '0 4px 20px -2px rgba(99, 102, 241, 0.08)',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Decorative top accent line */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          height: '4px',
          background: 'linear-gradient(90deg, #6366f1, #8b5cf6, #ec4899)',
        }}
      />

      {/* Top Header Row */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '12px',
          marginBottom: '16px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div
            style={{
              width: '36px',
              height: '36px',
              borderRadius: '10px',
              backgroundColor: '#4f46e5',
              color: '#ffffff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 2px 8px rgba(79, 70, 229, 0.3)',
            }}
          >
            <Volume2 size={18} />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 700, color: '#1e1b4b' }}>
                Dukaan Daily Audio Briefing
              </h3>
              <span
                style={{
                  fontSize: '11px',
                  fontWeight: 600,
                  backgroundColor: '#e0e7ff',
                  color: '#4338ca',
                  padding: '2px 8px',
                  borderRadius: '12px',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
              >
                <Sparkles size={11} /> AI Voice
              </span>
            </div>
            <p style={{ margin: '2px 0 0 0', fontSize: '13px', color: '#475569' }}>
              Non-tech store report — suniye ya padhiye aam bolchal ki bhasha me.
            </p>
          </div>
        </div>

        {/* Store Health Badge */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            backgroundColor: '#ffffff',
            padding: '6px 14px',
            borderRadius: '20px',
            border: '1px solid #e2e8f0',
            boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
          }}
        >
          <div
            style={{
              width: '10px',
              height: '10px',
              borderRadius: '50%',
              backgroundColor: healthScore >= 80 ? '#10b981' : '#f59e0b',
            }}
          />
          <span style={{ fontSize: '12px', color: '#64748b', fontWeight: 500 }}>Store Health:</span>
          <span style={{ fontSize: '13px', fontWeight: 700, color: '#0f172a' }}>
            {healthScore}/100
          </span>
        </div>
      </div>

      {/* Main Content Box */}
      <div
        style={{
          backgroundColor: '#ffffff',
          borderRadius: '12px',
          padding: '16px 20px',
          border: '1px solid #e0e7ff',
          display: 'flex',
          flexDirection: 'column',
          gap: '14px',
        }}
      >
        {/* Controls Bar */}
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px',
            borderBottom: '1px solid #f1f5f9',
            paddingBottom: '12px',
          }}
        >
          {/* Audio Action Button */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <button
              onClick={handleToggleVoice}
              disabled={loading}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '8px',
                backgroundColor: isPlaying ? '#ef4444' : '#4f46e5',
                color: '#ffffff',
                border: 'none',
                borderRadius: '8px',
                padding: '8px 18px',
                fontSize: '13px',
                fontWeight: 600,
                cursor: 'pointer',
                transition: 'all 0.2s',
                boxShadow: isPlaying
                  ? '0 2px 10px rgba(239, 68, 68, 0.4)'
                  : '0 2px 10px rgba(79, 70, 229, 0.3)',
              }}
            >
              {isPlaying ? (
                <>
                  <Square size={14} />
                  <span>Rukiye (Stop Audio)</span>
                </>
              ) : (
                <>
                  <Play size={14} />
                  <span>Suniye (Play Briefing)</span>
                </>
              )}
            </button>

            {/* Audio Wave Indicator when playing */}
            {isPlaying && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '3px',
                  height: '20px',
                }}
              >
                <span
                  style={{
                    width: '3px',
                    height: '14px',
                    backgroundColor: '#6366f1',
                    borderRadius: '2px',
                    animation: 'bounce 0.6s infinite alternate',
                  }}
                />
                <span
                  style={{
                    width: '3px',
                    height: '22px',
                    backgroundColor: '#8b5cf6',
                    borderRadius: '2px',
                    animation: 'bounce 0.8s infinite alternate',
                  }}
                />
                <span
                  style={{
                    width: '3px',
                    height: '10px',
                    backgroundColor: '#ec4899',
                    borderRadius: '2px',
                    animation: 'bounce 0.5s infinite alternate',
                  }}
                />
                <span
                  style={{
                    fontSize: '12px',
                    color: '#6366f1',
                    fontWeight: 600,
                    marginLeft: '4px',
                  }}
                >
                  Speaking...
                </span>
              </div>
            )}
          </div>

          {/* Language Selector Pills */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              backgroundColor: '#f8fafc',
              border: '1px solid #e2e8f0',
              borderRadius: '8px',
              padding: '2px',
            }}
          >
            {[
              { id: 'hinglish', label: '🇮🇳 Hinglish' },
              { id: 'hindi', label: '🇮🇳 हिंदी' },
              { id: 'english', label: '🇬🇧 English' },
            ].map((opt) => (
              <button
                key={opt.id}
                onClick={() => handleLanguageChange(opt.id)}
                style={{
                  border: 'none',
                  backgroundColor: language === opt.id ? '#ffffff' : 'transparent',
                  color: language === opt.id ? '#1e293b' : '#64748b',
                  fontWeight: language === opt.id ? 700 : 500,
                  fontSize: '12px',
                  padding: '5px 12px',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  boxShadow: language === opt.id ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
                  transition: 'all 0.15s ease',
                }}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {/* Text Transcript */}
        <div
          style={{
            backgroundColor: '#f8fafc',
            border: '1px solid #edf2f7',
            borderRadius: '8px',
            padding: '12px 16px',
            fontSize: '14px',
            lineHeight: '1.6',
            color: '#1e293b',
          }}
        >
          {loading ? (
            <div style={{ color: '#94a3b8' }}>Briefing load ho rahi hai...</div>
          ) : (
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
              <span style={{ fontSize: '16px' }}>💬</span>
              <p style={{ margin: 0, fontWeight: 500 }}>{currentScript}</p>
            </div>
          )}
        </div>

        {/* Bottom Action Cards */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
            gap: '12px',
            paddingTop: '4px',
          }}
        >
          {/* Card 1: 1-Click WhatsApp Order */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              backgroundColor: '#ecfdf5',
              border: '1px solid #a7f3d0',
              borderRadius: '8px',
              padding: '10px 14px',
            }}
          >
            <div>
              <div style={{ fontSize: '13px', fontWeight: 700, color: '#065f46' }}>
                Supplier Reorder List (WhatsApp)
              </div>
              <div style={{ fontSize: '11px', color: '#047857' }}>
                {briefingData?.critical_count || 3} items ka ready message bhejo
              </div>
            </div>
            <button
              onClick={handleWhatsAppShare}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                backgroundColor: '#10b981',
                color: '#ffffff',
                border: 'none',
                borderRadius: '6px',
                padding: '6px 12px',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer',
                boxShadow: '0 1px 3px rgba(16, 185, 129, 0.3)',
              }}
            >
              <Share2 size={12} />
              <span>WhatsApp par bhejo</span>
            </button>
          </div>

          {/* Card 2: Quick Jump to Inventory */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              backgroundColor: '#fffbeb',
              border: '1px solid #fde68a',
              borderRadius: '8px',
              padding: '10px 14px',
            }}
          >
            <div>
              <div style={{ fontSize: '13px', fontWeight: 700, color: '#92400e' }}>
                Naya Stock / Purchase Planning
              </div>
              <div style={{ fontSize: '11px', color: '#b45309' }}>
                September ke reorder levels check karein
              </div>
            </div>
            <button
              onClick={() => navigate('/inventory')}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                backgroundColor: '#f59e0b',
                color: '#ffffff',
                border: 'none',
                borderRadius: '6px',
                padding: '6px 12px',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              <span>Stock dekhein</span>
              <ArrowRight size={12} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
