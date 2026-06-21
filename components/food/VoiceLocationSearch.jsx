import React from 'react';
import PropTypes from 'prop-types';
import { useNavigate } from 'react-router-dom';
import aiChatService from '../../utils/services/aiChatService';
import { transcribeAudio } from '../../utils/openaiVoice';
import { useEffectiveLocation } from '../../utils/hooks/useLocation';
import { useAuthContext } from '../../utils/AuthContext';
import { AIThinkingPanel } from '../common/AIThinking.jsx';

const URGENCY_BADGE = {
    critical: 'bg-red-100 text-red-700 ring-red-200',
    expired: 'bg-red-100 text-red-700 ring-red-200',
    high: 'bg-amber-100 text-amber-700 ring-amber-200',
    medium: 'bg-yellow-50 text-yellow-700 ring-yellow-200',
    normal: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
};

const URGENCY_LABEL = {
    critical: 'Critical',
    expired: 'Expired',
    high: 'High urgency',
    medium: 'Soon',
    normal: 'Plenty of time',
};

const QUICK_SEARCHES = [
    { label: 'Vegan nearby', query: 'vegan food nearby' },
    { label: 'Expiring soon', query: 'food expiring soon nearby' },
    { label: 'Fresh produce', query: 'fresh produce nearby' },
    { label: 'Prepared meals', query: 'prepared meals nearby' },
    { label: 'Gluten-free', query: 'gluten-free food nearby' },
];

const RADIUS_OPTIONS = [5, 10, 25, 50, 100];

const MAX_RECORD_MS = 30000;
const SILENCE_MS = 1500;

function WaveformBars({ level = 0, active = false, bars = 5 }) {
    return (
        <div className="vls-waveform" aria-hidden="true">
            {Array.from({ length: bars }).map((_, i) => {
                const phase = (i / bars) * Math.PI;
                const scale = active
                    ? 0.25 + level * 0.75 * (0.6 + 0.4 * Math.sin(phase + level * 6))
                    : 0.2;
                return (
                    <span
                        key={i}
                        className="vls-waveform-bar"
                        style={{ transform: `scaleY(${Math.min(1, Math.max(0.15, scale))})` }}
                    />
                );
            })}
        </div>
    );
}

/**
 * GPS + voice food search panel.
 *
 *   tap mic  → record  → /api/ai/transcribe → /api/ai/voice-search
 *                                          ↘ also accepts typed queries
 *
 * Results are ranked by combined urgency + distance score and clickable.
 */
export default function VoiceLocationSearch({
    className = '',
    defaultRadiusKm = 25,
    onResultSelect = null,
    embedded = false,
}) {
    const { user, isAuthenticated } = useAuthContext();
    const navigate = useNavigate();
    const { location, error: locationError, enableLocation, refreshLocation } = useEffectiveLocation();

    const [typedQuery, setTypedQuery] = React.useState('');
    const [radiusKm, setRadiusKm] = React.useState(defaultRadiusKm);
    const [isRecording, setIsRecording] = React.useState(false);
    const [isSearching, setIsSearching] = React.useState(false);
    const [recordingError, setRecordingError] = React.useState(null);
    const [searchResult, setSearchResult] = React.useState(null);
    const [lastError, setLastError] = React.useState(null);
    const [lastErrorMeta, setLastErrorMeta] = React.useState(null);
    const [audioLevel, setAudioLevel] = React.useState(0);

    const mediaRecorderRef = React.useRef(null);
    const chunksRef = React.useRef([]);
    const streamRef = React.useRef(null);
    const silenceTimerRef = React.useRef(null);
    const maxDurationTimerRef = React.useRef(null);
    const rafRef = React.useRef(null);

    const stopRecording = React.useCallback(() => {
        if (rafRef.current) {
            cancelAnimationFrame(rafRef.current);
            rafRef.current = null;
        }
        try {
            if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
                mediaRecorderRef.current.stop();
            }
        } catch (_err) { /* noop */ }
        if (streamRef.current) {
            streamRef.current.getTracks().forEach(t => t.stop());
            streamRef.current = null;
        }
        if (silenceTimerRef.current) {
            clearTimeout(silenceTimerRef.current);
            silenceTimerRef.current = null;
        }
        if (maxDurationTimerRef.current) {
            clearTimeout(maxDurationTimerRef.current);
            maxDurationTimerRef.current = null;
        }
        setIsRecording(false);
        setAudioLevel(0);
    }, []);

    React.useEffect(() => () => stopRecording(), [stopRecording]);

    const runSearch = React.useCallback(async (transcript) => {
        const cleaned = (transcript || '').trim();
        if (!cleaned) {
            setLastError('Please say or type what you are looking for.');
            return;
        }
        if (!user?.id) {
            setLastError('Sign in to use voice search.');
            return;
        }
        setLastError(null);
        setLastErrorMeta(null);
        setRecordingError(null);
        setIsSearching(true);
        try {
            const result = await aiChatService.voiceSearch(user.id, {
                transcript: cleaned,
                latitude: location?.latitude ?? null,
                longitude: location?.longitude ?? null,
                maxDistanceKm: Number(radiusKm) || defaultRadiusKm,
                limit: 8,
            });
            setSearchResult(result);
        } catch (err) {
            setLastError(err?.message || 'Search failed. Try again.');
            setLastErrorMeta(err?.aiError || null);
            setSearchResult(null);
        } finally {
            setIsSearching(false);
        }
    }, [user?.id, location, radiusKm, defaultRadiusKm]);

    const handleAudioBlob = React.useCallback(async (blob) => {
        if (!blob || blob.size < 2000) {
            setRecordingError("Didn't catch that — try speaking a bit longer.");
            return;
        }
        setRecordingError(null);
        setIsSearching(true);
        try {
            const transcript = await transcribeAudio(blob);
            if (!transcript || !transcript.trim()) {
                setRecordingError("Couldn't understand the audio. Try again.");
                setIsSearching(false);
                return;
            }
            setTypedQuery(transcript);
            await runSearch(transcript);
        } catch (err) {
            setRecordingError(err?.message || 'Transcription failed.');
            setIsSearching(false);
        }
    }, [runSearch]);

    const startRecording = async () => {
        if (isRecording) return;
        setRecordingError(null);
        setLastError(null);
        if (!navigator.mediaDevices?.getUserMedia) {
            setRecordingError('Microphone not supported in this browser.');
            return;
        }
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            streamRef.current = stream;
            const recorder = new MediaRecorder(stream);
            chunksRef.current = [];
            recorder.ondataavailable = (evt) => {
                if (evt.data && evt.data.size > 0) chunksRef.current.push(evt.data);
            };
            recorder.onstop = () => {
                const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' });
                chunksRef.current = [];
                handleAudioBlob(blob);
            };
            recorder.start();
            mediaRecorderRef.current = recorder;
            setIsRecording(true);

            maxDurationTimerRef.current = setTimeout(stopRecording, MAX_RECORD_MS);

            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            if (AudioCtx) {
                const audioCtx = new AudioCtx();
                const source = audioCtx.createMediaStreamSource(stream);
                const analyser = audioCtx.createAnalyser();
                analyser.fftSize = 1024;
                source.connect(analyser);
                const data = new Uint8Array(analyser.frequencyBinCount);
                let silentSince = null;
                const tick = () => {
                    if (!streamRef.current) {
                        try { audioCtx.close(); } catch (_e) { /* noop */ }
                        return;
                    }
                    analyser.getByteTimeDomainData(data);
                    let max = 0;
                    for (let i = 0; i < data.length; i++) {
                        const v = Math.abs(data[i] - 128);
                        if (v > max) max = v;
                    }
                    setAudioLevel(Math.min(1, max / 32));

                    if (max < 5) {
                        if (!silentSince) silentSince = Date.now();
                        else if (Date.now() - silentSince > SILENCE_MS) {
                            stopRecording();
                            try { audioCtx.close(); } catch (_e) { /* noop */ }
                            return;
                        }
                    } else {
                        silentSince = null;
                    }
                    rafRef.current = requestAnimationFrame(tick);
                };
                rafRef.current = requestAnimationFrame(tick);
            }
        } catch (err) {
            setRecordingError(err?.message || 'Microphone permission denied.');
            stopRecording();
        }
    };

    const onSubmit = (evt) => {
        evt.preventDefault();
        runSearch(typedQuery);
    };

    const applyQuickSearch = (query) => {
        setTypedQuery(query);
        runSearch(query);
    };

    const openListing = (id, result = null) => {
        if (!id) return;
        if (typeof onResultSelect === 'function') {
            onResultSelect(id, result);
            return;
        }
        navigate(`/find?listing=${encodeURIComponent(id)}`);
    };

    const hasLocation = !!(location?.latitude && location?.longitude);
    const busy = isSearching && !isRecording;
    const micDisabled = busy || !isAuthenticated;

    const statusLine = isRecording
        ? 'Listening… tap the mic when you\'re done'
        : isSearching
            ? 'Finding food that matches your request'
            : 'Tap the mic and describe what you need';

    return (
        <section
            className={`vls-card relative overflow-hidden ${
                embedded
                    ? ''
                    : 'rounded-2xl shadow-md border border-gray-100/80'
            } ${className}`}
            aria-label="Voice and location food search"
        >
            {!embedded && (
                <header className="relative z-10 flex items-center justify-between gap-3 px-5 py-3.5 border-b border-white/60 bg-white/50 backdrop-blur-sm">
                    <div className="min-w-0">
                        <div className="flex items-center gap-2 text-gray-900">
                            <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-[#2CABE3]/15 text-[#2CABE3]">
                                <i className="fas fa-microphone-lines text-sm" aria-hidden="true" />
                            </span>
                            <div>
                                <h2 className="text-sm font-semibold leading-tight">Search with your voice</h2>
                                <p className="text-[11px] text-gray-500 mt-0.5">Speak naturally — we rank by urgency &amp; distance</p>
                            </div>
                        </div>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                        {hasLocation ? (
                            <>
                                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-medium text-emerald-700 ring-1 ring-emerald-200/80">
                                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" aria-hidden="true" />
                                    GPS on
                                </span>
                                <button
                                    type="button"
                                    onClick={refreshLocation}
                                    className="inline-flex h-8 w-8 items-center justify-center rounded-full text-gray-500 hover:bg-white hover:text-[#2CABE3] transition"
                                    aria-label="Refresh location"
                                >
                                    <i className="fas fa-rotate text-xs" aria-hidden="true" />
                                </button>
                            </>
                        ) : (
                            <button
                                type="button"
                                onClick={enableLocation}
                                className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2.5 py-1 text-[11px] font-medium text-amber-800 ring-1 ring-amber-200 hover:bg-amber-100 transition"
                            >
                                <i className="fas fa-location-crosshairs" aria-hidden="true" />
                                Enable GPS
                            </button>
                        )}
                    </div>
                </header>
            )}

            <div className="relative z-10 px-4 sm:px-5 py-4 sm:py-5 space-y-4">
                {!isAuthenticated && (
                    <div className="flex items-start gap-3 rounded-xl border border-amber-200/80 bg-amber-50/90 px-3.5 py-3 text-sm text-amber-900">
                        <i className="fas fa-user-lock mt-0.5 text-amber-600" aria-hidden="true" />
                        <div className="flex-1 min-w-0">
                            <p className="font-medium">Sign in to search with your voice</p>
                            <p className="text-xs text-amber-800/80 mt-0.5">We use your account to rank listings near you.</p>
                        </div>
                        <button
                            type="button"
                            onClick={() => navigate('/login')}
                            className="shrink-0 inline-flex items-center gap-1.5 rounded-full bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-700"
                        >
                            Log in
                        </button>
                    </div>
                )}

                {embedded && (
                    <div className="flex flex-wrap items-center justify-center gap-2">
                        {hasLocation ? (
                            <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700 ring-1 ring-emerald-200/80">
                                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" aria-hidden="true" />
                                Using your location
                            </span>
                        ) : (
                            <button
                                type="button"
                                onClick={enableLocation}
                                className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-3 py-1 text-xs font-medium text-amber-800 ring-1 ring-amber-200 hover:bg-amber-100"
                            >
                                <i className="fas fa-location-crosshairs" aria-hidden="true" />
                                Use my location for nearby results
                            </button>
                        )}
                    </div>
                )}

                {/* Hero mic */}
                <div className="vls-mic-zone">
                    <div className="vls-mic-orb-wrap">
                        {isRecording && (
                            <>
                                <span className="vls-mic-ring animate-voice-ring-1" aria-hidden="true" />
                                <span className="vls-mic-ring animate-voice-ring-2" aria-hidden="true" />
                                <span
                                    className="vls-mic-ring"
                                    style={{ transform: `scale(${1 + audioLevel * 0.35})`, opacity: 0.5 + audioLevel * 0.4 }}
                                    aria-hidden="true"
                                />
                            </>
                        )}
                        <button
                            type="button"
                            onClick={isRecording ? stopRecording : startRecording}
                            disabled={micDisabled}
                            className={`vls-mic-orb ${isRecording ? 'vls-mic-orb--recording' : ''}`}
                            style={isRecording ? { transform: `scale(${1 + audioLevel * 0.06})` } : undefined}
                            aria-pressed={isRecording}
                            aria-label={isRecording ? 'Stop recording' : 'Start voice search'}
                        >
                            <i className={`fas ${isRecording ? 'fa-stop' : 'fa-microphone'}`} aria-hidden="true" />
                        </button>
                    </div>

                    <WaveformBars level={audioLevel} active={isRecording} />

                    <p className="text-base font-semibold text-gray-900 text-center">{statusLine}</p>
                    {!isRecording && !isSearching && (
                        <p className="text-xs text-gray-500 text-center max-w-xs">
                            Try a Quick Search below, or speak naturally — e.g. &ldquo;vegan meals expiring soon&rdquo;.
                        </p>
                    )}
                    {isRecording && (
                        <p className="text-xs text-gray-500 text-center max-w-xs">
                            Pause briefly when finished — we&rsquo;ll stop automatically.
                        </p>
                    )}
                </div>

                {/* Radius */}
                <div className="space-y-1.5">
                    <p className="text-xs font-medium text-gray-600 px-0.5">Search within</p>
                    <div className="flex flex-wrap gap-1.5" role="group" aria-label="Search radius">
                        {RADIUS_OPTIONS.map((km) => (
                            <button
                                key={km}
                                type="button"
                                disabled={isRecording || busy}
                                onClick={() => setRadiusKm(km)}
                                className={`vls-radius-pill ${radiusKm === km ? 'vls-radius-pill--active' : ''}`}
                                aria-pressed={radiusKm === km}
                            >
                                {km} km
                            </button>
                        ))}
                    </div>
                </div>

                {/* Quick searches */}
                <div className="space-y-1.5">
                    <p className="text-xs font-medium text-gray-600 px-0.5">Quick searches</p>
                    <div className="flex flex-wrap gap-1.5">
                        {QUICK_SEARCHES.map(({ label, query }) => (
                            <button
                                key={label}
                                type="button"
                                disabled={busy || isRecording || !isAuthenticated}
                                onClick={() => applyQuickSearch(query)}
                                className="vls-chip"
                            >
                                <i className="fas fa-bolt text-[9px] text-[#2CABE3]" aria-hidden="true" />
                                {label}
                            </button>
                        ))}
                    </div>
                </div>

                {/* Typed fallback */}
                <form onSubmit={onSubmit} className="space-y-1.5">
                    <label htmlFor="vls-query" className="text-xs font-medium text-gray-600 px-0.5 block">
                        Or type your search
                    </label>
                    <div className="flex flex-col sm:flex-row gap-2">
                        <div className="relative flex-1">
                            <i className="fas fa-keyboard absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-xs pointer-events-none" aria-hidden="true" />
                            <input
                                id="vls-query"
                                type="text"
                                value={typedQuery}
                                onChange={(e) => setTypedQuery(e.target.value)}
                                placeholder='e.g. dairy-free snacks nearby'
                                className="w-full rounded-xl border border-gray-200 bg-white/90 pl-9 pr-3 py-2.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-[#2CABE3]/35 focus:border-[#2CABE3]/50"
                                disabled={isRecording}
                            />
                        </div>
                        <button
                            type="submit"
                            disabled={busy || !typedQuery.trim() || !isAuthenticated}
                            className="inline-flex items-center justify-center gap-2 rounded-xl bg-gray-900 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-black disabled:bg-gray-300 disabled:cursor-not-allowed transition"
                        >
                            <i className={`fas ${busy ? 'fa-spinner fa-spin' : 'fa-magnifying-glass'}`} aria-hidden="true" />
                            {busy ? 'Searching…' : 'Search'}
                        </button>
                    </div>
                </form>

                {/* Errors */}
                {(recordingError || locationError || lastError) && (
                    <div className="rounded-xl border border-red-100 bg-red-50/90 px-3.5 py-3 text-sm text-red-800" role="alert">
                        <div className="flex items-start gap-2">
                            <i className="fas fa-circle-exclamation mt-0.5 text-red-500 shrink-0" aria-hidden="true" />
                            <div className="min-w-0 flex-1">
                                <p>{recordingError || lastError || locationError}</p>
                                {lastErrorMeta?.code && (
                                    <p className="mt-1 text-[10px] text-red-600/80">
                                        {lastErrorMeta.code}
                                        {lastErrorMeta.requestId ? ` · ${lastErrorMeta.requestId.slice(0, 8)}` : ''}
                                    </p>
                                )}
                                {lastError && (lastErrorMeta?.retryable ?? true) && (
                                    <button
                                        type="button"
                                        onClick={() => runSearch(typedQuery)}
                                        disabled={busy || !typedQuery.trim()}
                                        className="mt-2 inline-flex items-center gap-1 rounded-lg bg-red-600 px-2.5 py-1 text-[11px] font-medium text-white hover:bg-red-700 disabled:opacity-50"
                                    >
                                        <i className={`fas fa-${busy ? 'spinner fa-spin' : 'redo'}`} aria-hidden="true" />
                                        Retry
                                    </button>
                                )}
                            </div>
                        </div>
                    </div>
                )}

                {!hasLocation && !locationError && isAuthenticated && (
                    <p className="text-xs text-gray-500 text-center">
                        <i className="fas fa-lightbulb text-amber-500 mr-1" aria-hidden="true" />
                        Enable GPS to sort results by how close they are to you.
                    </p>
                )}

                {isSearching && (
                    <AIThinkingPanel
                        title="Voice search"
                        stages={[
                            { icon: 'microphone-lines', label: 'Transcribing your voice' },
                            { icon: 'brain', label: 'Understanding your request' },
                            { icon: 'location-crosshairs', label: 'Scanning nearby food' },
                            { icon: 'ranking-star', label: 'Ranking by urgency & distance' },
                        ]}
                    />
                )}

                {searchResult && !isSearching && (
                    <div className="space-y-3 pt-1">
                        <div className="flex items-end justify-between gap-3 border-t border-gray-100 pt-4">
                            <div>
                                <p className="text-[11px] font-semibold uppercase tracking-wide text-[#2CABE3]">Results</p>
                                <p className="text-sm font-semibold text-gray-900 mt-0.5">{searchResult.headline}</p>
                            </div>
                            <span className="shrink-0 rounded-full bg-gray-100 px-2.5 py-1 text-[11px] font-medium text-gray-600">
                                {searchResult.totalMatched} match{searchResult.totalMatched === 1 ? '' : 'es'}
                            </span>
                        </div>

                        {searchResult.results.length === 0 ? (
                            <div className="rounded-xl border border-dashed border-gray-200 bg-white/60 px-4 py-8 text-center">
                                <span className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-gray-100 text-gray-400 mb-3">
                                    <i className="fas fa-search text-lg" aria-hidden="true" />
                                </span>
                                <p className="text-sm font-medium text-gray-700">No listings matched</p>
                                <p className="text-xs text-gray-500 mt-1 max-w-xs mx-auto">
                                    Widen your radius or try different words like “produce” or “expires today”.
                                </p>
                                <button
                                    type="button"
                                    onClick={() => setRadiusKm(Math.min(100, radiusKm * 2 || 50))}
                                    className="mt-3 inline-flex items-center gap-1 rounded-lg bg-[#2CABE3] px-3 py-1.5 text-xs font-medium text-white hover:opacity-90"
                                >
                                    <i className="fas fa-expand-arrows-alt" aria-hidden="true" />
                                    Widen to {Math.min(100, radiusKm * 2 || 50)} km
                                </button>
                            </div>
                        ) : (
                            <ul className="space-y-2.5">
                                {searchResult.results.map((r, idx) => {
                                    const badgeClass = URGENCY_BADGE[r.urgency_label] || URGENCY_BADGE.normal;
                                    const isTop = idx < 3;
                                    return (
                                        <li key={r.id}>
                                            <button
                                                type="button"
                                                onClick={() => openListing(r.id, r)}
                                                className="vls-result-card w-full text-left flex items-start gap-3 rounded-xl border border-gray-100 bg-white/90 p-3.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#2CABE3]/40"
                                            >
                                                <span className={`vls-result-rank ${isTop ? 'vls-result-rank--top' : ''}`}>
                                                    {idx + 1}
                                                </span>
                                                {r.image_url ? (
                                                    <img
                                                        src={r.image_url}
                                                        alt=""
                                                        className="h-14 w-14 flex-shrink-0 rounded-lg object-cover ring-1 ring-gray-100"
                                                    />
                                                ) : (
                                                    <span className="h-14 w-14 flex-shrink-0 rounded-lg bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center text-gray-400 ring-1 ring-gray-100">
                                                        <i className="fas fa-utensils" aria-hidden="true" />
                                                    </span>
                                                )}
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-start justify-between gap-2">
                                                        <h3 className="text-sm font-semibold text-gray-900 line-clamp-1">
                                                            {r.title || 'Untitled listing'}
                                                        </h3>
                                                        <span className={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ${badgeClass}`}>
                                                            {URGENCY_LABEL[r.urgency_label] || r.urgency_label}
                                                        </span>
                                                    </div>
                                                    <p className="mt-0.5 text-xs text-gray-500 line-clamp-2">
                                                        {r.description || r.location || 'No description'}
                                                    </p>
                                                    <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-gray-600">
                                                        {r.distance_km != null && (
                                                            <span className="inline-flex items-center gap-1 font-medium text-[#2CABE3]">
                                                                <i className="fas fa-route" aria-hidden="true" />
                                                                {r.distance_km} km away
                                                            </span>
                                                        )}
                                                        {r.hours_until_deadline != null && (
                                                            <span className="inline-flex items-center gap-1 text-amber-700">
                                                                <i className="fas fa-clock" aria-hidden="true" />
                                                                {r.hours_until_deadline < 1
                                                                    ? '<1h left'
                                                                    : `${Math.round(r.hours_until_deadline)}h left`}
                                                            </span>
                                                        )}
                                                        {r.quantity && (
                                                            <span>
                                                                <i className="fas fa-box-open mr-1 text-gray-400" aria-hidden="true" />
                                                                {r.quantity}{r.unit ? ` ${r.unit}` : ''}
                                                            </span>
                                                        )}
                                                    </div>
                                                </div>
                                                <i className="fas fa-chevron-right text-gray-300 text-xs mt-1 shrink-0" aria-hidden="true" />
                                            </button>
                                        </li>
                                    );
                                })}
                            </ul>
                        )}
                    </div>
                )}
            </div>
        </section>
    );
}

VoiceLocationSearch.propTypes = {
    className: PropTypes.string,
    defaultRadiusKm: PropTypes.number,
    onResultSelect: PropTypes.func,
    embedded: PropTypes.bool,
};
