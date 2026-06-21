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
        replies_es: [
            "¡Hola! Soy Nouri. ¿Qué te gustaría hacer — buscar comida, compartir o ver tus recogidas?",
            "¡Hola! Puedo ayudarte a buscar comida, compartir lo que tienes o abrir tu panel. ¿Por dónde empezamos?",
            "¡Hola! Cuéntame qué necesitas — buscar comida, compartir, recetas o tu actividad.",
        ],
        suggestions: ['Find food', 'Share food', 'Open dashboard'],
        suggestions_es: ['Buscar comida', 'Compartir comida', 'Abrir panel'],
    },
    // Thanks
    {
        match: /\b(thanks|thank\s*you|thx|ty|appreciate|cheers|gracias)\b/i,
        replies: [
            "Anytime! Let me know if you want to find food, share some, or check your dashboard.",
            "You're welcome! Want me to point you to recipes or your latest pickups?",
        ],
        replies_es: [
            "¡Cuando quieras! Avísame si quieres buscar comida, compartir o ver tu panel.",
            "¡De nada! ¿Te muestro recetas o tus últimas recogidas?",
        ],
        suggestions: ['Find food', 'See recipes', 'Open dashboard'],
        suggestions_es: ['Buscar comida', 'Ver recetas', 'Abrir panel'],
    },
    // Identity / capability
    {
        match: /\b(who\s*are\s*you|what\s*are\s*you|your\s*name|what\s*can\s*you\s*do|how\s*can\s*you\s*help|help\s*me|quién\s*eres|qué\s*haces|en\s*qué\s*puedes\s*ayudar)\b/i,
        replies: [
            "I'm Nouri, your DoGoods assistant. I can help you find food nearby, share what you have, check pickups, browse recipes, or open your impact stats. Where shall we start?",
            "I'm Nouri — I help with finding food, sharing food, claims & pickups, recipes, and your community impact. What would you like to do?",
        ],
        replies_es: [
            "Soy Nouri, tu asistente de DoGoods. Te ayudo a buscar comida cerca, compartir lo que tienes, revisar recogidas, ver recetas o abrir tus estadísticas de impacto. ¿Por dónde empezamos?",
            "Soy Nouri — te ayudo con búsqueda de comida, compartir, reclamos y recogidas, recetas y tu impacto en la comunidad. ¿Qué te gustaría hacer?",
        ],
        suggestions: ['Find food', 'Share food', 'See recipes'],
        suggestions_es: ['Buscar comida', 'Compartir comida', 'Ver recetas'],
    },
    // Yes / no — keep the convo moving instead of dead-ending
    {
        match: /^\s*(yes|yeah|yep|sure|ok|okay|sounds\s*good|sí|si|claro|vale|de\s*acuerdo)\s*\.?\s*$/i,
        replies: [
            "Great — tell me a bit more. Are you looking to find food, share food, or check your dashboard?",
            "Awesome. What direction — finding food, sharing food, or recipes?",
        ],
        replies_es: [
            "Genial — cuéntame un poco más. ¿Quieres buscar comida, compartir o ver tu panel?",
            "Perfecto. ¿En qué dirección — buscar comida, compartir o recetas?",
        ],
        suggestions: ['Find food', 'Share food', 'Open dashboard'],
        suggestions_es: ['Buscar comida', 'Compartir comida', 'Abrir panel'],
    },
    {
        match: /^\s*(no|nope|nah|not\s*really|para\s*nada)\s*\.?\s*$/i,
        replies: [
            "No problem. If you change your mind, I can find food, share food, or open your dashboard.",
            "All good. Want to browse recipes or check your impact instead?",
        ],
        replies_es: [
            "Sin problema. Si cambias de idea, puedo buscar comida, compartir o abrir tu panel.",
            "Tranquilo. ¿Prefieres ver recetas o revisar tu impacto?",
        ],
        suggestions: ['See recipes', 'View impact', 'Find food'],
        suggestions_es: ['Ver recetas', 'Ver impacto', 'Buscar comida'],
    },

    // Action routes
    {
        match: /\b(find|near\s*me|where|browse|available|buscar|encontrar|cerca\s*de\s*mí|disponible)\b.*\b(food|meal|donation|listing|comida|donaci[oó]n|publicaci[oó]n)\b|\bfind food\b|\bbuscar comida\b/i,
        replies: [
            "Sure — you can browse food available near you on the Find Food page.",
            "Got it. The Find Food page shows everything available near you right now.",
        ],
        replies_es: [
            "Claro — puedes ver la comida disponible cerca en la página Buscar Comida.",
            "Entendido. La página Buscar Comida muestra todo lo disponible cerca ahora mismo.",
        ],
        suggestions: ['Find food near me', 'Open my dashboard', 'See recipes'],
        suggestions_es: ['Buscar comida cerca', 'Abrir mi panel', 'Ver recetas'],
        action: { label: 'Find food', href: '/find' },
        action_es: { label: 'Buscar comida', href: '/find' },
    },
    {
        match: /\b(share|donate|give|post|list|compartir|donar|publicar|subir)\b.*\b(food|meal|surplus|leftover|comida|sobras|excedente)\b|\bshare food\b|\bdonate food\b|\bcompartir comida\b|\bdonar comida\b/i,
        replies: [
            "Nice — open the Share Food form to post your listing.",
            "Awesome. Head to Share Food and I'll get your listing up for the community.",
        ],
        replies_es: [
            "Genial — abre el formulario Compartir Comida para publicar tu listado.",
            "Perfecto. Ve a Compartir Comida y publicaré tu listado para la comunidad.",
        ],
        suggestions: ['Share food', 'My listings', 'Donation schedules'],
        suggestions_es: ['Compartir comida', 'Mis publicaciones', 'Calendario de donaciones'],
        action: { label: 'Share food', href: '/share' },
        action_es: { label: 'Compartir comida', href: '/share' },
    },
    {
        match: /\b(claim|pickup|pick\s*up|receive|my\s*orders|reclamo|reclamos|recogida|recogidas|recoger)\b/i,
        replies: [
            "Your active claims and pickups live on your dashboard.",
            "You can see all your pickups on the dashboard.",
        ],
        replies_es: [
            "Tus reclamos y recogidas activas están en tu panel.",
            "Puedes ver todas tus recogidas en el panel.",
        ],
        suggestions: ['Open dashboard', 'Find food', 'View claims'],
        suggestions_es: ['Abrir panel', 'Buscar comida', 'Ver reclamos'],
        action: { label: 'Open dashboard', href: '/dashboard' },
        action_es: { label: 'Abrir panel', href: '/dashboard' },
    },
    {
        match: /\b(recipe|cook|meal\s*idea|what\s*can\s*i\s*make|receta|recetas|cocinar|qué\s*puedo\s*cocinar)\b/i,
        replies: [
            "Browse the recipes library — there's plenty to choose from.",
            "Open Recipes for community-tested ideas.",
        ],
        replies_es: [
            "Explora la biblioteca de recetas — hay muchas para elegir.",
            "Abre Recetas para ideas probadas por la comunidad.",
        ],
        suggestions: ['See recipes', 'Find food', 'How it works'],
        suggestions_es: ['Ver recetas', 'Buscar comida', 'Cómo funciona'],
        action: { label: 'Browse recipes', href: '/recipes' },
        action_es: { label: 'Ver recetas', href: '/recipes' },
    },
    {
        match: /\b(store|storage|keep|fridge|freezer|preserve|shelf\s*life|guardar|almacenar|nevera|congelador|conservar)\b/i,
        replies: [
            "Rule of thumb: cooked food keeps 3–4 days in the fridge, up to 3 months in the freezer. The Recipes page has detailed tips.",
        ],
        replies_es: [
            "Regla general: la comida cocinada dura 3–4 días en la nevera y hasta 3 meses en el congelador. La página de Recetas tiene consejos detallados.",
        ],
        suggestions: ['Browse recipes', 'Find food', 'How it works'],
        suggestions_es: ['Ver recetas', 'Buscar comida', 'Cómo funciona'],
        action: { label: 'Recipes & tips', href: '/recipes' },
        action_es: { label: 'Recetas y consejos', href: '/recipes' },
    },
    {
        match: /\b(impact|stat|metric|how\s*much|how\s*many|meals\s*saved|co2|impacto|estad[ií]stica|cu[aá]nt[oa]s?|comidas\s*salvadas)\b/i,
        replies: [
            "Your impact stats live on your profile — meals shared, claims fulfilled, and community reach.",
        ],
        replies_es: [
            "Tus estadísticas de impacto están en tu perfil — comidas compartidas, reclamos completados y alcance comunitario.",
        ],
        suggestions: ['Open profile', 'Open dashboard', 'Find food'],
        suggestions_es: ['Abrir perfil', 'Abrir panel', 'Buscar comida'],
        action: { label: 'View my impact', href: '/profile' },
        action_es: { label: 'Ver mi impacto', href: '/profile' },
    },
    {
        match: /\b(community|group|local|neighbour|neighborhood|comunidad|grupo|vecindario|barrio)\b/i,
        replies: [
            "The Community page lists local groups and partners.",
        ],
        replies_es: [
            "La página de Comunidad muestra grupos y socios locales.",
        ],
        suggestions: ['Open community', 'Find food', 'Share food'],
        suggestions_es: ['Abrir comunidad', 'Buscar comida', 'Compartir comida'],
        action: { label: 'Open community', href: '/community' },
        action_es: { label: 'Abrir comunidad', href: '/community' },
    },
    {
        match: /\b(profile|setting|account|update|edit|perfil|ajustes|configuraci[oó]n|cuenta|actualizar|editar)\b/i,
        replies: [
            "You can update your profile and preferences in Settings.",
        ],
        replies_es: [
            "Puedes actualizar tu perfil y preferencias en Ajustes.",
        ],
        suggestions: ['Open settings', 'Open profile', 'Open dashboard'],
        suggestions_es: ['Abrir ajustes', 'Abrir perfil', 'Abrir panel'],
        action: { label: 'Open settings', href: '/settings' },
        action_es: { label: 'Abrir ajustes', href: '/settings' },
    },
    {
        match: /\b(how\s*does|how\s*do|guide|tutorial|getting\s*started|cómo\s*funciona|gu[ií]a|empezar)\b/i,
        replies: [
            "The How It Works guide walks through claiming and donating step by step.",
        ],
        replies_es: [
            "La guía Cómo Funciona te lleva paso a paso por reclamos y donaciones.",
        ],
        suggestions: ['How it works', 'Find food', 'Share food'],
        suggestions_es: ['Cómo funciona', 'Buscar comida', 'Compartir comida'],
        action: { label: 'How it works', href: '/how-it-works' },
        action_es: { label: 'Cómo funciona', href: '/how-it-works' },
    },
    {
        match: /\b(contact|support|admin|report\s*(an?\s*)?issue|contacto|contactar|soporte|reportar)\b/i,
        replies: [
            "The Contact page connects you straight to the team.",
        ],
        replies_es: [
            "La página de Contacto te conecta directamente con el equipo.",
        ],
        suggestions: ['Contact us', 'Open dashboard', 'Help'],
        suggestions_es: ['Contáctanos', 'Abrir panel', 'Ayuda'],
        action: { label: 'Contact us', href: '/contact' },
        action_es: { label: 'Contáctanos', href: '/contact' },
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
const DEFAULT_SUGGESTIONS_ES = ['Buscar comida', 'Compartir comida', 'Ver recetas']
const DEFAULT_ACTION = { label: 'Open dashboard', href: '/dashboard' }
const DEFAULT_ACTION_ES = { label: 'Abrir panel', href: '/dashboard' }

function _looksSpanish(text) {
    const raw = String(text || '')
    // Strong signals — punctuation or two+ accented characters — are
    // sufficient on their own; English doesn't use these.
    if (/[¿¡]/.test(raw)) return true
    if ((raw.match(/[áéíóúüñ]/gi) || []).length >= 2) return true
    // Weak signals — Spanish marker words. Use \b so 'donde' doesn't match
    // inside 'wondering', and require at least three hits to avoid false
    // positives on bilingual code-switched English input ("find me comida").
    const lower = raw.toLowerCase()
    const markers = [
        /\bhola\b/, /\bgracias\b/, /\bcomida\b/, /\bbuscar\b/, /\bquiero\b/,
        /\bnecesito\b/, /\bcómo\b/, /\bdonde\b/, /\bdónde\b/, /\bpor\s+favor\b/,
        /\bporque\b/, /\bqué\b/, /\bquién\b/, /\bcuándo\b/, /\bcuánto\b/,
    ]
    let hits = 0
    for (const re of markers) {
        if (re.test(lower)) hits += 1
        if (hits >= 3) return true
    }
    return false
}

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
    const isEs = _looksSpanish(raw)
    let chosenText = null
    let suggestions = isEs ? DEFAULT_SUGGESTIONS_ES : DEFAULT_SUGGESTIONS
    let action = isEs ? DEFAULT_ACTION_ES : DEFAULT_ACTION

    if (raw) {
        for (const route of ROUTES) {
            if (route.match.test(raw)) {
                // Prefer locale-specific reply/suggestions/action when present;
                // fall back to the EN strings so unmigrated routes still work.
                const replies = (isEs && route.replies_es) || route.replies
                const routeSuggestions = (isEs && route.suggestions_es) || route.suggestions
                const routeAction = (isEs && route.action_es) || route.action
                chosenText = _pickVariant(replies, raw)
                suggestions = routeSuggestions || (isEs ? DEFAULT_SUGGESTIONS_ES : DEFAULT_SUGGESTIONS)
                action = routeAction || null
                break
            }
        }
    }

    if (!chosenText) {
        chosenText = isEs
            ? 'No estoy seguro de haber entendido — ¿quieres buscar comida, compartir comida o ver tu panel?'
            : _pickDefault()
    }

    return {
        response: chosenText,
        lang: isEs ? 'es' : 'en',
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
