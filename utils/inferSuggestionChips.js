/**
 * Client-side chip inference — safety net when backend suggestions are empty
 * or stale. Keep in sync with backend/ai/ai_engine.generate_quick_replies.
 */

function norm(text) {
  return String(text || '')
    .toLowerCase()
    .replace(/[-_/]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function chip(label, message = label, extra = {}) {
  return { label, message: message || label, ...extra }
}

function isPostSuccessResponse(raw) {
  const t = norm(raw)
  if (!t) return false
  const text = String(raw || '')
  if (text.includes('?') || text.includes('¿')) {
    if (/(should|shall|want me|would you|which community|which school|list under|go under|ready to post)/.test(t)) {
      return false
    }
  }
  if (/listing is live|successfully posted|posted!|posted your|all set|is now live|went live|are shared|is shared|awaiting admin approval|anything else you want to share|ya est[aá] publicado/.test(t)) {
    return true
  }
  if (/(listed under|posted under)/.test(t) && /(your|done|all set|live|shared|posted|successfully|awaiting|approval|anything else)/.test(t)) {
    return true
  }
  return false
}

/**
 * Infer up to 6 contextual chips from the latest assistant reply.
 * Returns [] when nothing safe matches (empty > wrong).
 */
export function inferChipsFromResponse(responseText, language = 'en') {
  const raw = String(responseText || '')
  const t = norm(raw)
  if (!t) return []
  const es = language === 'es'
    || raw.includes('¿')
    || /\b(qué|cómo|cuándo|dónde|comida|hazlo|gu[ií]ame)\b/i.test(raw)

  // GUIDED (header or headerless open-page tutorial)
  const guidedTutorial = (
    /\bguided\b|\bguiado\b/.test(t)
    || (
      /(open the share|open share food|open the find|open find food|open the request|tap share food|tap find food|look at the top|main menu|top menu|please open the)/.test(t)
      && /(say done|let me know when|when you see|next step|see the form|together)/.test(t)
    )
    || /(baby step|look at the blue|look at the green|tap the box|type your name)/.test(t)
  )
  if (guidedTutorial) {
    if (/donor type|tipo de donante/.test(t)) {
      return es
        ? [chip('Individual/Familia'), chip('Organización'), chip('Listo', 'listo')]
        : [chip('Individual/Family'), chip('Organization'), chip('Done', 'done')]
    }
    if (/photo|picture|foto|imagen/.test(t)) {
      return es
        ? [chip('Adjuntar foto'), chip('Listo', 'listo')]
        : [chip("I'll add a photo"), chip('Done', 'done')]
    }
    const base = es
      ? [chip('Listo', 'listo'), chip('Siguiente', 'siguiente'), chip('¿Ayuda?', 'Necesito ayuda con este paso')]
      : [chip('Done', 'done'), chip("What's next?", "what's next"), chip('Need help', 'I need help with this step')]
    if (/(open the share|open share|open the find|open find|open the request|tap share|tap find|main menu|top menu|see the form)/.test(t)) {
      const see = es
        ? chip('Ya veo el formulario', 'listo — ya veo el formulario')
        : chip('I see the form', 'done — I see the form')
      return [see, ...base]
    }
    return base
  }

  // Assistance fork — Share/Request use form label; Find uses Open Find Food.
  // Require a real mode-choice ask (both options), not a hands-on ack that
  // merely says "I'll handle everything for you in chat…".
  const forkAsk = (
    (
      (
        /do it for me|handle everything|handle the whole|hazlo por|here in chat/.test(t)
        && /guide me|walk you through|paso a paso|gu[ií]ame|open the form|open find food|open request food/.test(t)
      )
      || (/would you like me to handle|would you rather|how would you like|like to proceed/.test(t)
        && /shar|donat|find food|request|search|nearby|posting/.test(t))
    )
    && /(or |want me|would you|prefer|options|three)/.test(t)
  ) && !/(say done|let me know when|when you see|next step together|i see the form)/.test(t)
  if (forkAsk) {
    let path = typeof window !== 'undefined' ? String(window.location?.pathname || '') : ''
    const pagePath = path.toLowerCase()
    let goal = 'share'
    if (/find food|buscar comida|search nearby|near you|handle the search/.test(t)
      && !/share food|compartir|donate|posting/.test(t)) {
      goal = 'find'
    } else if (/request food|solicitar/.test(t) && !/share food|compartir|donate|posting/.test(t)) {
      goal = 'request'
    } else if (/\/find|near-me/.test(pagePath) && !/\/share|\/request/.test(pagePath)) {
      goal = 'find'
    } else if (/\/request/.test(pagePath)) {
      goal = 'request'
    }

    const mode = es
      ? [chip('Hazlo por mí'), chip('Guíame paso a paso')]
      : [chip('Do it for me'), chip('Guide me step by step')]

    if (goal === 'find') {
      const nav = pagePath.includes('near-me') ? '/near-me' : '/find'
      const open = es
        ? chip('Abrir Buscar comida', 'Abrir Buscar comida', { action: 'navigate', path: nav, href: nav })
        : chip('Open Find Food', 'Open Find Food', { action: 'navigate', path: nav, href: nav })
      return [open, ...mode]
    }
    if (goal === 'request') {
      const open = es
        ? chip('Abrir Solicitar comida', 'Abrir Solicitar comida', { action: 'navigate', path: '/request', href: '/request' })
        : chip('Open Request Food', 'Open Request Food', { action: 'navigate', path: '/request', href: '/request' })
      return [open, ...mode]
    }
    const open = es
      ? chip('Abrir el formulario', 'Abrir el formulario', { action: 'navigate', path: '/share', href: '/share' })
      : chip('Open the form', 'Open the form', { action: 'navigate', path: '/share', href: '/share' })
    return [open, ...mode]
  }

  // Photo — required; never offer skip / later / without.
  // Skip when the turn is really a post confirm or success summary.
  if (/photo|picture|foto|imagen/.test(t)
    && /required|please|need|upload|attach|add a|send a photo|before post|so we can post|snap|skip the photo|without a photo/.test(t)
    && !/ready to post|shall i post|want me to post|photos received|got your photo|with your photos|with photo|look right|looks right|does this look/.test(t)) {
    return es
      ? [chip('Adjuntar foto')]
      : [chip('Attach a photo')]
  }

  // Success / anything else — before community / post chips
  if (isPostSuccessResponse(raw)) {
    return es
      ? [chip('Compartir otra cosa'), chip('Buscar comida'), chip('Eso es todo')]
      : [chip('Share something else'), chip('Find food near me'), chip("That's all for now")]
  }

  // Success / anything else (legacy patterns)
  if (/listing is live|are shared|is shared|posted!|successfully posted|share another|anything else you want to share|you're all set|claimed successfully/.test(t)) {
    return es
      ? [chip('Compartir otra cosa'), chip('Buscar comida'), chip('Eso es todo')]
      : [chip('Share something else'), chip('Find food near me'), chip("That's all for now")]
  }

  // Donor type / name
  if (/donor type|individual\/family|individual \/ family|tipo de donante/.test(t)) {
    return es
      ? [chip('Individual/Familia'), chip('Organización')]
      : [chip('Individual/Family'), chip('Organization')]
  }
  if (/your name|donor name|name \/ organization|name\/organization|name or organization/.test(t)) {
    return es
      ? [chip('Usar mi nombre de perfil'), chip('Es una organización')]
      : [chip('Use my profile name'), chip("It's an organization")]
  }

  // Address / where pickup — before community / post confirm.
  if (/where should|what address|profile address|does that look good|pickup address|dirección/.test(t)) {
    return es
      ? [chip('Usar mi dirección guardada'), chip('Es otra dirección'), chip('No tengo una')]
      : [chip('Use my saved address'), chip('Use a different address'), chip("I don't have one saved")]
  }

  // Community confirm / pick — BEFORE post confirm so
  // "want me to post this to your community" is not treated as publish.
  // Require a real community cue so address / look-right recaps do not match.
  if (!isPostSuccessResponse(raw)
    && /community|school|warehouse|linked to|list under|listed under|use that one|comunidad|escuela|district/.test(t)
    && /which community|which school|list under|listed under|community should|for the community|post (this |it )?(under|to)|go under|school district|your community|use that one|linked to|profile is linked|profile is connected|profile is set|comunidad|escuela|publicar bajo|bajo qu[eé]/.test(t)
    && (/(\?|¿|should|shall|want me|would you|use that one)/.test(t))
    && !/ready to post|shall i post|looks? right|does this look|sound good to post|go ahead and share/.test(t)) {
    const nameMatch = String(responseText || '').match(
      /(?:linked to|connected to|listed under|list under|use|under|—|-)\s*([A-Z][A-Za-z0-9 &.'/-]{2,48}?)(?:\s+for\s+the\s+community)?(?:\s*,|\s*\?|\s*$|[.!,])/,
    )
    const endMatch = String(responseText || '').match(
      /,\s*([A-Z][A-Za-z][A-Za-z0-9 &.'/-]{1,48}?)\s*\?\s*$/,
    )
    const suggested = ((nameMatch && nameMatch[1]) || (endMatch && endMatch[1]) || '').trim()
    if (suggested && !/^(the|this|that|your|a|an)$/i.test(suggested)) {
      return es
        ? [chip(suggested.slice(0, 48)), chip('Otra comunidad')]
        : [chip(suggested.slice(0, 48)), chip('Different one')]
    }
    return es
      ? [chip('Usar la de mi perfil'), chip('Otra comunidad')]
      : [chip('Use my profile community'), chip('Different one')]
  }

  // Post / claim confirms
  if (/ready to post|want me to post|shall i post|publish it|post it|say yes if|publish now|sound good to post|looks? right|does this look|go ahead and share|shall i go ahead/.test(t)
    && !(/your community|list under|linked to|use that one|for the community/.test(t)
      && !/ready to post|shall i post|looks? right|sound good to post|go ahead and share/.test(t))) {
    const photoEvidence = /photos received|got your photo|with your photos|with photo|with a photo|photo attached|foto adjunta|fotos recibidas|con tus fotos|image:|https?:\/\//.test(t)
    const photoNudge = !photoEvidence
      && /ready to post|ready to publish|shall i post|should i post|want me to post/.test(t)
      && !/looks? right|does this look|sound good|go ahead and share|your community|list under|linked to/.test(t)
    if (photoNudge) {
      return es ? [chip('Adjuntar foto')] : [chip('Attach a photo')]
    }
    return es
      ? [chip('Sí, publícalo'), chip('Espera, edítalo'), chip('Cancelar')]
      : [chip('Yes, post it'), chip('Wait, edit it'), chip('Cancel')]
  }
  if (/ready to claim these|claim these|claim both/.test(t)) {
    return es
      ? [chip('Sí, reclamar todos'), chip('Cambiar cantidades'), chip('Cancelar')]
      : [chip('Yes, claim these'), chip('Change amounts'), chip('Cancel')]
  }
  if (/shall i claim|claim this listing|claim it for you|claim #/.test(t)) {
    return es
      ? [chip('Sí, reclámalo'), chip('No, gracias'), chip('Cancelar')]
      : [chip('Yes, claim it'), chip('No thanks'), chip('Cancel')]
  }

  // Allergens — before food/qty/expiry so mixed "best by… any allergens?" wins.
  if (
    /allerg|alérgen|alergia|dietary restriction|restricciones diet/.test(t)
    || (
      (t.match(/\b(nuts|dairy|eggs|wheat|soy|shellfish|gluten|peanut|sesame|fish|frutos secos|l[aá]cteos|huevos|trigo)\b/g) || []).length >= 2
      && /(any |contain|should i|note|know about|does this|do these|dietary|allerg|\?|¿)/.test(t)
    )
    || (
      /(nuts|dairy|eggs|wheat|soy|shellfish|gluten|frutos secos|lácteos)/.test(t)
      && /(any |contain|should i|note|know about|dietary|allerg)/.test(t)
    )
  ) {
    return es
      ? [chip('Sin alérgenos'), chip('Solo gluten'), chip('Lácteos'), chip('Frutos secos')]
      : [chip('No allergens'), chip('Just gluten'), chip('Dairy'), chip('Nuts')]
  }

  // Food ask / looking for — BEFORE bare qty so hands-on
  // "What food … and how much?" gets food+qty examples, not 1/3/5/10.
  const foodAsk = /what food|food name|what would you like to share|what would you like to donate|what are you sharing|what are you donating|what do you have|tell me what you have|tell me what you've got|what kind of food|tell me the food|qué comida|qué quieres compartir|qué vas a (donar|compartir)/.test(t)
  const qtyAsk = /how much|how many|cuántos|cuántas|cuánto|cuánta/.test(t)
  const combinedFoodQty = (
    (foodAsk && qtyAsk)
    || /food name and|roughly how much|food and how much|tell me what you have|tell me what you've got|qué y cuánto|qué comida y cuánto/.test(t)
  )
  if (combinedFoodQty) {
    return es
      ? [chip('5 manzanas'), chip('2 panes'), chip('Verduras — 1 caja'), chip('Huevos — 1 docena')]
      : [chip('5 apples'), chip('2 loaves of bread'), chip('Vegetables — 1 box'), chip('Eggs — 1 dozen')]
  }
  if (foodAsk || /what are you looking for|what do you need|qué buscas|qué necesitas/.test(t)) {
    return es
      ? [chip('Pan'), chip('Frutas'), chip('Verduras'), chip('Comida preparada')]
      : [chip('Bread'), chip('Fruit'), chip('Vegetables'), chip('Prepared meal')]
  }

  // Qty (after food is known — e.g. "How many slices are you sharing?")
  if (/how many of the|how many would you like|how many do you want/.test(t)) {
    return es
      ? [chip('1'), chip('2'), chip('3'), chip('Todos')]
      : [chip('1'), chip('2'), chip('3'), chip('All of them')]
  }
  if (qtyAsk) {
    return [chip('1'), chip('3'), chip('5'), chip('10')]
  }

  // Search pick
  if (/which number|options above|1, 2, or 3|closest options|here'?s what'?s|near you/.test(t)
    && (/which|pick|number|options|closest|cerca/.test(t))) {
    return es
      ? [chip('1'), chip('2'), chip('3'), chip('El más cercano')]
      : [chip('1'), chip('2'), chip('3'), chip('The closest one')]
  }

  // Help menu
  if (/what can you do|try first|how does this work|not sure|where do i start/.test(t)) {
    return es
      ? [chip('Buscar comida gratis'), chip('Compartir comida extra'), chip('Solicitar comida')]
      : [chip('Find free food'), chip('Share extra food'), chip('Request food')]
  }

  // Description — before photo/expiry so "add a short description" gets
  // description chips even without a question mark. Do not use allergen
  // or best-by chips here — those collide with other Do-it-for-me steps.
  if (
    /short description|add a description|describe the food|describe it|description for recipients|one-sentence description|one sentence about|few words about|tell me more about the food|tell me a bit about|tell me a bit more about|how would you describe|should know about the food|people should know|anything else about the food|note for recipients|descripci[oó]n corta|descripci[oó]n para|describe la comida/.test(t)
  ) {
    return es
      ? [chip('Sigue sellado'), chip('Casero, refrigerado'), chip('Sobras variadas')]
      : [chip('Still sealed'), chip('Homemade, refrigerated'), chip('Assorted leftovers')]
  }

  // Pickup window
  if (/when can|pickup window|what time|cuándo pueden/.test(t)) {
    return es
      ? [chip('Hoy 5–8pm'), chip('Mañana'), chip('Próximas 24h'), chip('Cuando sea')]
      : [chip('Today 5–8pm'), chip('Tomorrow morning'), chip('Next 24h'), chip('Whenever')]
  }

  // Good-until / expiry — only when actively asking, never on allergen turns
  // or acknowledgements that merely repeat a chosen date.
  const allergenAsk = /allerg|alérgen|alergia|dietary restriction/.test(t)
  const expiryCue = /best by|best-by|good until|good for|use by|expir|vence|caduc|how long is it good|how long will it (keep|stay)|stay fresh|fecha de venc|when does it expire|best before/.test(t)
  const expiryAck = /got it|noted|i'?ll use|set to|set as|confirmed|listed as|using tomorrow|anotado/.test(t)
  const expiryReAsk = /change|different date|another date|update the|wrong date|want a different|\?|¿|when does|when is|how long/.test(t)
  if (
    expiryCue
    && !allergenAsk
    && !/what food|donating|sharing|fresh apples|fresh bread/.test(t)
    && !(expiryAck && !expiryReAsk)
  ) {
    return es
      ? [chip('Mañana'), chip('En 2 días'), chip('En 3 días'), chip('En un mes')]
      : [chip('Tomorrow'), chip('In 2 days'), chip('In 3 days'), chip('In a month')]
  }

  // Remind
  if (/remind you|remind me|recuerde|recordarte/.test(t)) {
    return es
      ? [chip('Sí, recuérdame'), chip('No, gracias')]
      : [chip('Yes, remind me'), chip('No thanks')]
  }

  return []
}
