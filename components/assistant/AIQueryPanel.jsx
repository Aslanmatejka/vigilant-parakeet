import React from 'react';
import PropTypes from 'prop-types';
import { useAuthContext } from '../../utils/AuthContext';
import aiChatService from '../../utils/services/aiChatService';
import { AIThinkingPanel } from '../common/AIThinking.jsx';

const SUGGESTIONS = [
    'How many active claims do I have?',
    'Show my listings that expire this week',
    'Find vegan produce nearby',
    'What is my impact summary?',
];

const ADMIN_SUGGESTIONS = [
    'How many recipients are signed up?',
    'List the 5 most recent pending claims',
    'Show recent failed broadcasts',
];

/**
 * Natural-language Q&A panel.
 *
 * Sends the question to /api/ai/query, which uses OpenAI function-calling to
 * map the question to a whitelist of safe, parameterized Supabase tools, then
 * returns a grounded natural-language answer plus a tool-call trace.
 */
export default function AIQueryPanel({ className = '' }) {
    const { user, isAuthenticated, isAdmin } = useAuthContext();

    const [question, setQuestion] = React.useState('');
    const [loading, setLoading] = React.useState(false);
    const [error, setError] = React.useState(null);
    const [errorMeta, setErrorMeta] = React.useState(null);
    const [result, setResult] = React.useState(null);
    const [showTrace, setShowTrace] = React.useState(false);

    const submit = async (q) => {
        const value = (q ?? question).trim();
        if (!value) return;
        if (!isAuthenticated || !user?.id) {
            setError('Please sign in to ask questions about your data.');
            setErrorMeta(null);
            return;
        }
        setLoading(true);
        setError(null);
        setErrorMeta(null);
        try {
            const res = await aiChatService.askQuery(user.id, value);
            setResult(res);
        } catch (err) {
            setError(err?.message || 'Query failed.');
            setErrorMeta(err?.aiError || null);
            setResult(null);
        } finally {
            setLoading(false);
        }
    };

    const handleSubmit = (e) => {
        e.preventDefault();
        submit();
    };

    const suggestions = isAdmin
        ? [...SUGGESTIONS, ...ADMIN_SUGGESTIONS]
        : SUGGESTIONS;

    return (
        <section
            className={`bg-white rounded-2xl shadow-md border border-gray-100 overflow-hidden ${className}`}
            aria-label="Natural language query"
        >
            <header className="px-5 py-3 border-b border-gray-100 bg-gradient-to-r from-indigo-50 to-white">
                <div className="flex items-center gap-2 text-gray-800">
                    <i className="fas fa-database text-indigo-600" aria-hidden="true" />
                    <h2 className="text-sm font-semibold">Ask about your data</h2>
                    <span className="ml-2 text-xs text-gray-500">
                        function-calling · read-only
                    </span>
                </div>
            </header>

            <div className="px-5 py-4 space-y-3">
                <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-2">
                    <input
                        type="text"
                        value={question}
                        onChange={(e) => setQuestion(e.target.value)}
                        placeholder='e.g. "How many pickups do I have this week?"'
                        className="flex-1 rounded-md border border-gray-200 px-3 py-2 text-sm focus:border-indigo-500 focus:ring focus:ring-indigo-100"
                        disabled={loading}
                        maxLength={500}
                    />
                    <button
                        type="submit"
                        disabled={loading || !question.trim()}
                        className="inline-flex items-center justify-center gap-2 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:bg-gray-300"
                    >
                        <i className={`fas ${loading ? 'fa-spinner animate-spin' : 'fa-paper-plane'}`} aria-hidden="true" />
                        {loading ? 'Thinking…' : 'Ask'}
                    </button>
                </form>

                <div className="flex flex-wrap gap-2">
                    {suggestions.map((s) => (
                        <button
                            key={s}
                            type="button"
                            onClick={() => { setQuestion(s); submit(s); }}
                            disabled={loading}
                            className="rounded-full bg-gray-100 hover:bg-indigo-50 hover:text-indigo-700 px-3 py-1 text-[11px] text-gray-700 transition"
                        >
                            {s}
                        </button>
                    ))}
                </div>

                {error && (
                    <div className="rounded-md border border-red-100 bg-red-50 px-3 py-2 text-xs text-red-700">
                        <p>{error}</p>
                        {errorMeta?.code && (
                            <p className="mt-1 text-[10px] text-red-500">
                                {errorMeta.code}
                                {errorMeta.requestId ? ` · ${errorMeta.requestId.slice(0, 8)}` : ''}
                            </p>
                        )}
                        {(errorMeta?.retryable ?? true) && (
                            <button
                                type="button"
                                onClick={() => submit()}
                                disabled={loading || !question.trim()}
                                className="mt-2 inline-flex items-center gap-1 rounded-md bg-red-600 px-2.5 py-1 text-[11px] font-medium text-white hover:bg-red-700 disabled:opacity-50"
                            >
                                <i className={`fas fa-${loading ? 'spinner fa-spin' : 'redo'}`} aria-hidden="true" />
                                Retry
                            </button>
                        )}
                    </div>
                )}
                {!isAuthenticated && (
                    <p className="text-xs text-gray-500">Sign in to query your data.</p>
                )}

                {loading && (
                    <AIThinkingPanel
                        title="Querying your data"
                        stages={[
                            { icon: 'magnifying-glass', label: 'Parsing your question' },
                            { icon: 'database', label: 'Selecting safe tools' },
                            { icon: 'bolt', label: 'Running secure query' },
                            { icon: 'wand-magic-sparkles', label: 'Composing answer' },
                        ]}
                    />
                )}

                {result && (
                    <article className="rounded-lg border border-indigo-100 bg-indigo-50/40 p-4">
                        <p className="text-xs uppercase tracking-wide text-indigo-600 font-semibold mb-1">
                            Answer
                        </p>
                        <div className="text-sm text-gray-800 whitespace-pre-wrap">
                            {result.answer || 'No answer.'}
                        </div>

                        {result.toolTrace?.length > 0 && (
                            <div className="mt-3 border-t border-indigo-100 pt-2">
                                <button
                                    type="button"
                                    onClick={() => setShowTrace((v) => !v)}
                                    className="text-[11px] text-indigo-700 hover:underline inline-flex items-center gap-1"
                                    aria-expanded={showTrace}
                                >
                                    <i className={`fas fa-chevron-${showTrace ? 'up' : 'down'}`} aria-hidden="true" />
                                    {showTrace ? 'Hide' : 'Show'} {result.toolTrace.length} tool call{result.toolTrace.length === 1 ? '' : 's'}
                                </button>

                                {showTrace && (
                                    <ul className="mt-2 space-y-2">
                                        {result.toolTrace.map((t, idx) => (
                                            <li
                                                key={idx}
                                                className="rounded-md bg-white ring-1 ring-gray-100 p-2 text-[11px] text-gray-700"
                                            >
                                                <div className="flex items-center gap-2">
                                                    <span className="rounded bg-indigo-100 px-1.5 py-0.5 font-mono text-indigo-700">
                                                        {t.tool}
                                                    </span>
                                                    {t.arguments && Object.keys(t.arguments).length > 0 && (
                                                        <code className="truncate text-gray-500">
                                                            {JSON.stringify(t.arguments)}
                                                        </code>
                                                    )}
                                                </div>
                                                {t.result_preview && (
                                                    <pre className="mt-1 whitespace-pre-wrap break-words text-gray-600">
                                                        {t.result_preview}
                                                    </pre>
                                                )}
                                            </li>
                                        ))}
                                    </ul>
                                )}
                            </div>
                        )}
                    </article>
                )}
            </div>
        </section>
    );
}

AIQueryPanel.propTypes = {
    className: PropTypes.string,
};
