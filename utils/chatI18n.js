/**
 * Chat panel UI strings — en, es, fr, vi, zh.
 */
import { normalizeGuideLang } from './guideLang'
import { GUIDE_LANGUAGE_LABELS } from './accessibilityStorage'

export const CHAT_UI_LANGUAGES = ['en', 'es', 'fr', 'vi', 'zh']
export const CHAT_LANGUAGE_LABELS = GUIDE_LANGUAGE_LABELS

const WELCOME_CATEGORIES = {
  en: [
    { key: 'guide', icon: 'fa-compass', accent: 'amber', title: 'Not sure?', blurb: 'I’ll walk you through it', prompts: ['I\'m not sure what to do — help me', 'How does DoGoods work?'] },
    { key: 'find', icon: 'fa-magnifying-glass-location', accent: 'emerald', title: 'Find food', blurb: 'I’ll ask how you want help', prompts: ['I want to find food', 'Find free food near me'] },
    { key: 'share', icon: 'fa-hand-holding-heart', accent: 'fuchsia', title: 'Share food', blurb: 'I’ll ask how you want help', prompts: ['I want to share food', 'Share extra food from my address'] },
    { key: 'request', icon: 'fa-clipboard-list', accent: 'sky', title: 'Request food', blurb: 'I’ll ask how you want help', prompts: ['I want to request food', 'Request food that isn’t listed yet'] },
    { key: 'manage', icon: 'fa-list-check', accent: 'cyan', title: 'Manage activity', blurb: 'Pickups, claims, impact', prompts: ['What are my upcoming pickups?', 'Show my impact stats'] },
  ],
  es: [
    { key: 'guide', icon: 'fa-compass', accent: 'amber', title: '¿No estás seguro?', blurb: 'Te guío paso a paso', prompts: ['No sé qué hacer — ayúdame', '¿Cómo funciona DoGoods?'] },
    { key: 'find', icon: 'fa-magnifying-glass-location', accent: 'emerald', title: 'Buscar comida', blurb: 'Te pregunto cómo ayudar', prompts: ['Quiero buscar comida', 'Buscar comida gratis cerca'] },
    { key: 'share', icon: 'fa-hand-holding-heart', accent: 'fuchsia', title: 'Compartir comida', blurb: 'Te pregunto cómo ayudar', prompts: ['Quiero compartir comida', 'Compartir comida extra desde mi dirección'] },
    { key: 'request', icon: 'fa-clipboard-list', accent: 'sky', title: 'Solicitar comida', blurb: 'Te pregunto cómo ayudar', prompts: ['Quiero solicitar comida', 'Solicitar comida que aún no está listada'] },
    { key: 'manage', icon: 'fa-list-check', accent: 'cyan', title: 'Mi actividad', blurb: 'Recogidas, reclamos, impacto', prompts: ['¿Cuáles son mis próximas recogidas?', 'Muestra mis estadísticas de impacto'] },
  ],
  fr: [
    { key: 'guide', icon: 'fa-compass', accent: 'amber', title: 'Pas sûr ?', blurb: 'Je vous guide pas à pas', prompts: ['Je ne sais pas quoi faire — aidez-moi', 'Comment fonctionne DoGoods ?'] },
    { key: 'find', icon: 'fa-magnifying-glass-location', accent: 'emerald', title: 'Trouver de la nourriture', blurb: 'Je vous demande comment aider', prompts: ['Je veux trouver de la nourriture', 'Trouver de la nourriture gratuite près de moi'] },
    { key: 'share', icon: 'fa-hand-holding-heart', accent: 'fuchsia', title: 'Partager de la nourriture', blurb: 'Je vous demande comment aider', prompts: ['Je veux partager de la nourriture', 'Partager de la nourriture depuis mon adresse'] },
    { key: 'request', icon: 'fa-clipboard-list', accent: 'sky', title: 'Demander de la nourriture', blurb: 'Je vous demande comment aider', prompts: ['Je veux demander de la nourriture', 'Demander une nourriture non listée'] },
    { key: 'manage', icon: 'fa-list-check', accent: 'cyan', title: 'Mon activité', blurb: 'Retraits, réclamations, impact', prompts: ['Quels sont mes prochains retraits ?', 'Afficher mes statistiques d\'impact'] },
  ],
  vi: [
    { key: 'guide', icon: 'fa-compass', accent: 'amber', title: 'Không chắc?', blurb: 'Tôi hướng dẫn từng bước', prompts: ['Tôi không biết phải làm gì — giúp tôi', 'DoGoods hoạt động thế nào?'] },
    { key: 'find', icon: 'fa-magnifying-glass-location', accent: 'emerald', title: 'Tìm thực phẩm', blurb: 'Tôi hỏi bạn muốn giúp thế nào', prompts: ['Tôi muốn tìm thực phẩm', 'Tìm thực phẩm miễn phí gần tôi'] },
    { key: 'share', icon: 'fa-hand-holding-heart', accent: 'fuchsia', title: 'Chia sẻ thực phẩm', blurb: 'Tôi hỏi bạn muốn giúp thế nào', prompts: ['Tôi muốn chia sẻ thực phẩm', 'Chia sẻ thực phẩm thừa từ địa chỉ của tôi'] },
    { key: 'request', icon: 'fa-clipboard-list', accent: 'sky', title: 'Yêu cầu thực phẩm', blurb: 'Tôi hỏi bạn muốn giúp thế nào', prompts: ['Tôi muốn yêu cầu thực phẩm', 'Yêu cầu thực phẩm chưa có trong danh sách'] },
    { key: 'manage', icon: 'fa-list-check', accent: 'cyan', title: 'Hoạt động của tôi', blurb: 'Nhận hàng, yêu cầu, tác động', prompts: ['Lịch nhận hàng sắp tới của tôi?', 'Xem thống kê tác động của tôi'] },
  ],
  zh: [
    { key: 'guide', icon: 'fa-compass', accent: 'amber', title: '不确定？', blurb: '我会一步步引导您', prompts: ['我不确定该做什么 — 请帮助我', 'DoGoods 如何运作？'] },
    { key: 'find', icon: 'fa-magnifying-glass-location', accent: 'emerald', title: '找食物', blurb: '我会询问您需要什么帮助', prompts: ['我想找食物', '在我附近找免费食物'] },
    { key: 'share', icon: 'fa-hand-holding-heart', accent: 'fuchsia', title: '分享食物', blurb: '我会询问您需要什么帮助', prompts: ['我想分享食物', '从我的地址分享多余食物'] },
    { key: 'request', icon: 'fa-clipboard-list', accent: 'sky', title: '请求食物', blurb: '我会询问您需要什么帮助', prompts: ['我想请求食物', '请求尚未列出的食物'] },
    { key: 'manage', icon: 'fa-list-check', accent: 'cyan', title: '我的活动', blurb: '取货、认领、影响', prompts: ['我即将取货的有哪些？', '显示我的影响统计'] },
  ],
}

const SUGGESTIONS = {
  en: [
    'What food is available near me?', 'What food is available within 5 miles?', 'Show me food listings nearby',
    'What are my upcoming pickups?', 'What are my recent claims?', 'Cancel my pickup', 'Show my dashboard',
    'Show my impact stats', 'How many meals have I shared?', 'Can you suggest a recipe from available food?',
    'Give me a recipe for leftovers', 'How do I store fresh produce?', 'I want to share some food',
    'How do I post a food listing?', 'What distribution events are coming up?', 'Find a distribution center near me',
    'Route me to the nearest pickup', 'How does DoGoods work?', 'How do I verify my account?',
    'Update my profile address', 'Switch to Spanish', 'Open the map', 'Find food expiring soon', 'Show urgent listings',
  ],
  es: [
    '¿Qué comida hay disponible cerca de mí?', '¿Qué comida hay a menos de 5 millas?', 'Muéstrame las publicaciones cercanas',
    '¿Cuáles son mis próximas recogidas?', '¿Cuáles son mis reclamos recientes?', 'Cancela mi recogida', 'Muestra mi panel',
    'Muestra mis estadísticas de impacto', '¿Cuántas comidas he compartido?', '¿Puedes sugerirme una receta con comida disponible?',
    'Dame una receta para sobras', '¿Cómo guardo productos frescos?', 'Quiero compartir comida', '¿Cómo publico una donación?',
    '¿Qué eventos de distribución hay próximamente?', 'Encuentra un centro de distribución cerca', 'Llévame a la recogida más cercana',
    '¿Cómo funciona DoGoods?', '¿Cómo verifico mi cuenta?', 'Actualiza la dirección de mi perfil', 'Cambia a inglés',
    'Abre el mapa', 'Comida que vence pronto', 'Muestra publicaciones urgentes',
  ],
  fr: [
    'Quelle nourriture est disponible près de moi ?', 'Quels sont mes prochains retraits ?', 'Afficher mes statistiques d\'impact',
    'Je veux partager de la nourriture', 'Comment fonctionne DoGoods ?', 'Trouver la nourriture qui expire bientôt',
  ],
  vi: [
    'Thực phẩm nào có gần tôi?', 'Lịch nhận hàng sắp tới của tôi?', 'Xem thống kê tác động của tôi',
    'Tôi muốn chia sẻ thực phẩm', 'DoGoods hoạt động thế nào?', 'Tìm thực phẩm sắp hết hạn',
  ],
  zh: [
    '我附近有什么食物？', '我即将取货有哪些？', '显示我的影响统计',
    '我想分享食物', 'DoGoods 如何运作？', '查找即将过期的食物',
  ],
}

const UI = {
  greeting: {
    en: (n) => (n ? `Hi, ${n}!` : 'Hi there!'),
    es: (n) => (n ? `¡Hola, ${n}!` : '¡Hola!'),
    fr: (n) => (n ? `Bonjour, ${n} !` : 'Bonjour !'),
    vi: (n) => (n ? `Xin chào, ${n}!` : 'Xin chào!'),
    zh: (n) => (n ? `你好，${n}！` : '你好！'),
  },
  welcomeSubtitle: {
    en: 'Tap a suggestion below, a card, or type — I’ll ask whether to do it for you or guide you step by step.',
    es: 'Elige una sugerencia abajo, una tarjeta, o escribe — te pregunto si lo hago yo o te guío paso a paso.',
    fr: 'Choisissez une suggestion, une carte ou écrivez — je demande si je le fais pour vous ou si je vous guide.',
    vi: 'Chạm gợi ý, thẻ hoặc gõ — tôi hỏi bạn muốn tôi làm giúp hay hướng dẫn từng bước.',
    zh: '点击建议、卡片或输入 — 我会问是您来做还是一步步引导您。',
  },
  today: { en: 'Today', es: 'Hoy', fr: 'Aujourd\'hui', vi: 'Hôm nay', zh: '今天' },
  yesterday: { en: 'Yesterday', es: 'Ayer', fr: 'Hier', vi: 'Hôm qua', zh: '昨天' },
  jumpLatest: { en: 'Jump to latest', es: 'Ir al final', fr: 'Aller au plus récent', vi: 'Đến mới nhất', zh: '跳到最新' },
  latest: { en: 'Latest', es: 'Más reciente', fr: 'Récent', vi: 'Mới nhất', zh: '最新' },
  onlineTone: { en: (tone) => `Online · ${tone} tone`, es: (tone) => `En línea · tono ${tone}`, fr: (tone) => `En ligne · ton ${tone}`, vi: (tone) => `Trực tuyến · giọng ${tone}`, zh: (tone) => `在线 · ${tone} 语气` },
  signInForFeatures: { en: 'Sign in for full features', es: 'Inicia sesión para más funciones', fr: 'Connectez-vous pour plus de fonctions', vi: 'Đăng nhập để dùng đầy đủ', zh: '登录以使用完整功能' },
  chatLanguage: { en: 'Chat language', es: 'Idioma del chat', fr: 'Langue du chat', vi: 'Ngôn ngữ trò chuyện', zh: '聊天语言' },
  conversationTone: { en: 'Conversation tone', es: 'Tono de conversación', fr: 'Ton de conversation', vi: 'Giọng điệu trò chuyện', zh: '对话语气' },
  messagePlaceholder: { en: 'Message Nouri…', es: 'Pregunta lo que quieras…', fr: 'Écrivez à Nouri…', vi: 'Nhắn cho Nouri…', zh: '给 Nouri 发消息…' },
  photoCaptionPlaceholder: { en: 'Add a caption (optional)…', es: 'Añade un mensaje (opcional)…', fr: 'Ajoutez une légende (optionnel)…', vi: 'Thêm chú thích (tùy chọn)…', zh: '添加说明（可选）…' },
  retry: { en: 'Retry', es: 'Reintentar', fr: 'Réessayer', vi: 'Thử lại', zh: '重试' },
  copy: { en: 'Copy', es: 'Copiar', fr: 'Copier', vi: 'Sao chép', zh: '复制' },
  copied: { en: 'Copied', es: 'Copiado', fr: 'Copié', vi: 'Đã sao chép', zh: '已复制' },
  regenerate: { en: 'Regenerate', es: 'Regenerar', fr: 'Régénérer', vi: 'Tạo lại', zh: '重新生成' },
  voice: { en: 'Voice', es: 'Voz', fr: 'Voix', vi: 'Giọng nói', zh: '语音' },
  signInRequired: {
    en: 'You need to sign in to chat with me. Please log in or create an account and try again.',
    es: 'Necesitas iniciar sesión para hablar conmigo. Crea una cuenta o inicia sesión y vuelve a intentarlo.',
    fr: 'Vous devez vous connecter pour discuter avec moi. Connectez-vous ou créez un compte.',
    vi: 'Bạn cần đăng nhập để trò chuyện với tôi. Vui lòng đăng nhập hoặc tạo tài khoản.',
    zh: '您需要登录才能与我聊天。请登录或创建账户后重试。',
  },
}

const TONE_LABELS = {
  en: { warm: 'Warm', professional: 'Professional', casual: 'Casual', empathetic: 'Empathetic' },
  es: { warm: 'Cálido', professional: 'Profesional', casual: 'Informal', empathetic: 'Empático' },
  fr: { warm: 'Chaleureux', professional: 'Professionnel', casual: 'Décontracté', empathetic: 'Empathique' },
  vi: { warm: 'Ấm áp', professional: 'Chuyên nghiệp', casual: 'Thân mật', empathetic: 'Đồng cảm' },
  zh: { warm: '温暖', professional: '专业', casual: '随意', empathetic: '共情' },
}

const ERROR_MESSAGES = {
  timeout: {
    en: 'My response took too long. Please try again in a moment.',
    es: 'Mi respuesta tardó demasiado. Intenta de nuevo en un momento.',
    fr: 'Ma réponse a pris trop de temps. Réessayez dans un instant.',
    vi: 'Phản hồi mất quá nhiều thời gian. Vui lòng thử lại.',
    zh: '响应时间过长。请稍后再试。',
  },
  rate_limit: {
    en: "I'm getting a lot of requests right now. Please try again in a few seconds.",
    es: 'Estoy recibiendo muchas solicitudes ahora mismo. Intenta de nuevo en unos segundos.',
    fr: 'Je reçois beaucoup de demandes. Réessayez dans quelques secondes.',
    vi: 'Hiện có quá nhiều yêu cầu. Vui lòng thử lại sau vài giây.',
    zh: '当前请求较多。请几秒后重试。',
  },
  model_unavailable: {
    en: 'My AI model is temporarily unavailable. Please try again.',
    es: 'Mi modelo de IA no está disponible temporalmente. Vuelve a intentarlo.',
    fr: 'Mon modèle IA est temporairement indisponible. Réessayez.',
    vi: 'Mô hình AI tạm thời không khả dụng. Vui lòng thử lại.',
    zh: 'AI 模型暂时不可用。请重试。',
  },
  circuit_open: {
    en: "I'm recovering from a hiccup. Please try again in a few seconds.",
    es: 'Estoy recuperándome de un problema. Intenta de nuevo en unos segundos.',
    fr: 'Je me remets d\'un problème. Réessayez dans quelques secondes.',
    vi: 'Tôi đang khắc phục sự cố. Vui lòng thử lại sau vài giây.',
    zh: '正在恢复中。请几秒后重试。',
  },
  auth: {
    en: "There's an authentication issue. Please contact support if this keeps happening.",
    es: 'Hay un problema con mi autenticación. Contacta a soporte si esto continúa.',
    fr: 'Problème d\'authentification. Contactez le support si cela continue.',
    vi: 'Có lỗi xác thực. Liên hệ hỗ trợ nếu vẫn tiếp diễn.',
    zh: '身份验证出现问题。若持续发生请联系支持。',
  },
  invalid_input: {
    en: "I couldn't process that request. Please try rephrasing it.",
    es: 'No pude procesar esa solicitud. Intenta reformularla.',
    fr: 'Je n\'ai pas pu traiter cette demande. Reformulez-la.',
    vi: 'Tôi không xử lý được yêu cầu đó. Hãy diễn đạt lại.',
    zh: '无法处理该请求。请换一种说法。',
  },
  internal: {
    en: "I'm having a little trouble right now. Please try again.",
    es: 'Estoy teniendo un pequeño problema. ¿Puedes intentar de nuevo?',
    fr: 'J\'ai un petit problème. Veuillez réessayer.',
    vi: 'Tôi gặp chút trục trặc. Vui lòng thử lại.',
    zh: '我遇到了一点问题。请重试。',
  },
  network: {
    en: 'Cannot reach the AI server. Start the backend with npm run dev:backend (or npm run dev:full), then retry.',
    es: 'No puedo conectar con el servidor de IA. Inicia el backend con npm run dev:backend (o npm run dev:full) e inténtalo de nuevo.',
    fr: 'Impossible de joindre le serveur IA. Lancez le backend avec npm run dev:backend (ou npm run dev:full), puis réessayez.',
    vi: 'Không kết nối được máy chủ AI. Chạy npm run dev:backend (hoặc npm run dev:full) rồi thử lại.',
    zh: '无法连接 AI 服务器。请运行 npm run dev:backend（或 npm run dev:full）后重试。',
  },
}

const SWITCH_PROMPTS = {
  en: 'Hi, please speak in English',
  es: 'Hola, habla en español por favor',
  fr: 'Bonjour, parlez en français s\'il vous plaît',
  vi: 'Xin chào, hãy nói tiếng Việt nhé',
  zh: '你好，请用中文回复',
}

const DATE_LOCALE = { en: 'en-US', es: 'es-ES', fr: 'fr-FR', vi: 'vi-VN', zh: 'zh-CN' }

/** @param {string} lang */
export function chatLang(lang) {
  return normalizeGuideLang(lang)
}

/** @param {string} lang @param {string} key */
export function t(lang, key) {
  const l = chatLang(lang)
  const block = UI[key]
  if (!block) return ''
  return block[l] || block.en || ''
}

/** @param {string} lang @param {string} [userName] */
export function welcomeGreeting(lang, userName) {
  const l = chatLang(lang)
  const fn = UI.greeting[l] || UI.greeting.en
  return fn(userName)
}

/** @param {string} lang */
export function getWelcomeCategories(lang) {
  const l = chatLang(lang)
  return WELCOME_CATEGORIES[l] || WELCOME_CATEGORIES.en
}

/** @param {string} lang */
export function getSuggestions(lang) {
  const l = chatLang(lang)
  return SUGGESTIONS[l] || SUGGESTIONS.en
}

/** @param {string} lang */
export function getToneLabels(lang) {
  const l = chatLang(lang)
  return TONE_LABELS[l] || TONE_LABELS.en
}

/** @param {string} code @param {string} lang */
export function chatErrorMessage(code, lang) {
  const l = chatLang(lang)
  const block = ERROR_MESSAGES[code] || ERROR_MESSAGES.internal
  return block[l] || block.en
}

/** @param {string} lang */
export function languageSwitchPrompt(lang) {
  const l = chatLang(lang)
  return SWITCH_PROMPTS[l] || SWITCH_PROMPTS.en
}

/** @param {string} lang */
export function dateLocale(lang) {
  return DATE_LOCALE[chatLang(lang)] || 'en-US'
}

/** @param {string} lang @param {'today'|'yesterday'} key */
export function dateLabel(lang, key) {
  return t(lang, key)
}

/**
 * Pick initial chat UI language.
 * @param {object|null} user
 * @param {string|null|undefined} preferredLanguage
 */
export function pickInitialChatLanguage(user, preferredLanguage) {
  const fromSettings = normalizeGuideLang(preferredLanguage)
  if (fromSettings) {
    try {
      if (typeof sessionStorage !== 'undefined') {
        const cached = sessionStorage.getItem('dg.ai.lang')
        if (cached && CHAT_UI_LANGUAGES.includes(normalizeGuideLang(cached))) {
          return normalizeGuideLang(cached)
        }
      }
    } catch { /* private mode */ }
    if (fromSettings !== 'en') return fromSettings
  }
  try {
    if (typeof sessionStorage !== 'undefined') {
      const cached = sessionStorage.getItem('dg.ai.lang')
      if (cached && CHAT_UI_LANGUAGES.includes(normalizeGuideLang(cached))) {
        return normalizeGuideLang(cached)
      }
    }
  } catch { /* private mode */ }
  const pref = (user?.language || '').toString().toLowerCase()
  for (const code of CHAT_UI_LANGUAGES) {
    if (pref.startsWith(code)) return code
  }
  if (typeof navigator !== 'undefined') {
    const nav = (navigator.language || (navigator.languages && navigator.languages[0]) || '').toLowerCase()
    for (const code of CHAT_UI_LANGUAGES) {
      if (nav.startsWith(code)) return code
    }
  }
  return 'en'
}

/** @param {string} lang @param {string} toneLabel */
export function onlineToneLabel(lang, toneLabel) {
  const l = chatLang(lang)
  const fn = UI.onlineTone[l] || UI.onlineTone.en
  return fn(toneLabel)
}

/** @param {string} lang */
export function isValidChatLanguage(lang) {
  return CHAT_UI_LANGUAGES.includes(normalizeGuideLang(lang))
}
