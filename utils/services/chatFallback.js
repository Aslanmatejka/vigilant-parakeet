/**
 * Chat Fallback Responder (offline self-healing for the chat surface)
 * --------------------------------------------------------------------
 * Deterministic, keyword-routed responses used when the AI backend is
 * unreachable. Keeps the assistant useful and feels natural instead of
 * repeating the same "I'm reconnecting" line forever.
 *
 * No external calls. Pure JS.
 */

// ---- Conversational routes (checked in order) -----------------------------

const ROUTES = [
    // Greetings
    {
        match: /^\s*(hi|hey|hello|yo|hola|sup|good\s*(morning|afternoon|evening))\b/i,
        replies: [
            "Hey! I'm Nouri. What are you in the mood to do — find food, share some, or check your pickups?",
            "Hi there! I can help you find food, share what you have, or jump into your dashboard. What sounds good?",
            "Hello! Tell me what you're after — finding food, sharing food, recipes, or your activity?",
        ],
        suggestions: ['Find food', 'Share food', 'Open dashboard'],
    },
    // Thanks
    {
        match: /\b(thanks|thank\s*you|thx|ty|appreciate|cheers)\b/i,
        replies: [
            "Anytime! Let me know if you want to find food, share some, or check your dashboard.",
            "You're welcome! Want me to point you to recipes or your latest pickups?",
        ],
        suggestions: ['Find food', 'See recipes', 'Open dashboard'],
    },
    // Identity / capability
    {
        match: /\b(who\s*are\s*you|what\s*are\s*you|your\s*name|what\s*can\s*you\s*do|how\s*can\s*you\s*help|help\s*me)\b/i,
        replies: [
            "I'm Nouri, your DoGoods assistant. I can help you find food nearby, share what you have, check pickups, browse recipes, or open your impact stats. Where shall we start?",
            "I'm Nouri — I help with finding food, sharing food, claims & pickups, recipes, and your community impact. What would you like to do?",
        ],
        suggestions: ['Find food', 'Share food', 'See recipes'],
    },
    // Yes / no — keep the convo moving instead of dead-ending
    {
        match: /^\s*(yes|yeah|yep|sure|ok|okay|sounds\s*good)\s*\.?\s*$/i,
        replies: [
            "Great — tell me a bit more. Are you looking to find food, share food, or check your dashboard?",
            "Awesome. What direction — finding food, sharing food, or recipes?",
        ],
        suggestions: ['Find food', 'Share food', 'Open dashboard'],
    },
    {
        match: /^\s*(no|nope|nah|not\s*really)\s*\.?\s*$/i,
        replies: [
            "No problem. If you change your mind, I can find food, share food, or open your dashboard.",
            "All good. Want to browse recipes or check your impact instead?",
        ],
        suggestions: ['See recipes', 'View impact', 'Find food'],
    },

    // Action routes
    {
        match: /\b(find|near\s*me|where|browse|available)\b.*\b(food|meal|donation|listing)\b|\bfind food\b/i,
        replies: [
            "Sure — you can browse food available near you on the Find Food page.",
            "Got it. The Find Food page shows everything available near you right now.",
        ],
        suggestions: ['Find food near me', 'Open my dashboard', 'See recipes'],
        action: { label: 'Find food', href: '/find' },
    },
    {
        match: /\b(share|donate|give|post|list)\b.*\b(food|meal|surplus|leftover)\b|\bshare food\b|\bdonate food\b/i,
        replies: [
            "Nice — open the Share Food form to post your listing.",
            "Awesome. Head to Share Food and I'll get your listing up for the community.",
        ],
        suggestions: ['Share food', 'My listings', 'Donation schedules'],
        action: { label: 'Share food', href: '/share' },
    },
    {
        match: /\b(claim|pickup|pick\s*up|receive|my\s*orders)\b/i,
        replies: [
            "Your active claims and pickups live on your dashboard.",
            "You can see all your pickups on the dashboard.",
        ],
        suggestions: ['Open dashboard', 'Find food', 'View claims'],
        action: { label: 'Open dashboard', href: '/dashboard' },
    },
    {
        match: /\b(recipe|cook|meal\s*idea|what\s*can\s*i\s*make)\b/i,
        replies: [
            "Browse the recipes library — there's plenty to choose from.",
            "Open Recipes for community-tested ideas.",
        ],
        suggestions: ['See recipes', 'Find food', 'How it works'],
        action: { label: 'Browse recipes', href: '/recipes' },
    },
    {
        match: /\b(store|storage|keep|fridge|freezer|preserve|shelf\s*life)\b/i,
        replies: [
            "Rule of thumb: cooked food keeps 3–4 days in the fridge, up to 3 months in the freezer. The Recipes page has detailed tips.",
        ],
        suggestions: ['Browse recipes', 'Find food', 'How it works'],
        action: { label: 'Recipes & tips', href: '/recipes' },
    },
    {
        match: /\b(impact|stat|metric|how\s*much|how\s*many|meals\s*saved|co2)\b/i,
        replies: [
            "Your impact stats live on your profile — meals shared, claims fulfilled, and community reach.",
        ],
        suggestions: ['Open profile', 'Open dashboard', 'Find food'],
        action: { label: 'View my impact', href: '/profile' },
    },
    {
        match: /\b(community|group|local|neighbour|neighborhood)\b/i,
        replies: [
            "The Community page lists local groups and partners.",
        ],
        suggestions: ['Open community', 'Find food', 'Share food'],
        action: { label: 'Open community', href: '/community' },
    },
    {
        match: /\b(profile|setting|account|update|edit)\b/i,
        replies: [
            "You can update your profile and preferences in Settings.",
        ],
        suggestions: ['Open settings', 'Open profile', 'Open dashboard'],
        action: { label: 'Open settings', href: '/settings' },
    },
    {
        match: /\b(how\s*does|how\s*do|guide|tutorial|getting\s*started)\b/i,
        replies: [
            "The How It Works guide walks through claiming and donating step by step.",
        ],
        suggestions: ['How it works', 'Find food', 'Share food'],
        action: { label: 'How it works', href: '/how-it-works' },
    },
    {
        match: /\b(contact|support|admin|report\s*(an?\s*)?issue)\b/i,
        replies: [
            "The Contact page connects you straight to the team.",
        ],
        suggestions: ['Contact us', 'Open dashboard', 'Help'],
        action: { label: 'Contact us', href: '/contact' },
    },
]

// Rotating default replies so the user never sees the same line twice
// in a row. Friendly and short — no "I'm reconnecting" repetition.
const DEFAULT_REPLIES = [
    "I'm not sure I caught that — do you want to find food, share food, or check your dashboard?",
    "Could you say a bit more? I can help with finding food, sharing food, recipes, or your activity.",
    "Tell me what you're after — finding food, sharing food, recipes, or your impact?",
    "Happy to help — are you looking to find food, share food, or open your dashboard?",
]

const DEFAULT_SUGGESTIONS = ['Find food', 'Share food', 'See recipes']
const DEFAULT_ACTION = { label: 'Open dashboard', href: '/dashboard' }

// Module-level rotation cursor so consecutive defaults don't repeat verbatim.
let _defaultCursor = 0
const _pickDefault = () => {
    const reply = DEFAULT_REPLIES[_defaultCursor % DEFAULT_REPLIES.length]
    _defaultCursor += 1
    return reply
}

// Stable per-message variant pick (so a given input always gets the
// same reply during the session — no flicker on re-renders).
const _pickVariant = (replies, message) => {
    if (!Array.isArray(replies) || replies.length === 0) return ''
    if (replies.length === 1) return replies[0]
    let hash = 0
    const src = String(message || '')
    for (let i = 0; i < src.length; i++) hash = (hash * 31 + src.charCodeAt(i)) | 0
    return replies[Math.abs(hash) % replies.length]
}

/**
 * Return a deterministic chat response without contacting the backend.
 * Always succeeds — even nonsense input gets a friendly, non-repetitive reply.
 *
 * @param {string} message - the user's message
 * @returns {{ response, lang, audioUrl, conversationId, toolResults, suggestions, action, degraded, source, error }}
 */
export function buildChatFallback(message) {
    const raw = (message || '').trim()
    let chosenText = null
    let suggestions = DEFAULT_SUGGESTIONS
    let action = DEFAULT_ACTION

    if (raw) {
        for (const route of ROUTES) {
            if (route.match.test(raw)) {
                chosenText = _pickVariant(route.replies, raw)
                suggestions = route.suggestions || DEFAULT_SUGGESTIONS
                action = route.action || null
                break
            }
        }
    }

    if (!chosenText) {
        chosenText = _pickDefault()
    }

    return {
        response: chosenText,
        lang: 'en',
        audioUrl: null,
        conversationId: null,
        toolResults: [],
        suggestions,
        action,
        degraded: true,
        source: 'local',
        error: null,
    }
}
