import twilioService from './twilioService'
import { normalizeGuideLang } from './guideLang'

const FLOW_PATHS = {
  find: '/find-food',
  share: '/share-food',
  claim: '/claim-food',
  request: '/request-food',
}

const SMS_COPY = {
  en: (url) => `DoGoods: Follow this link for step-by-step help: ${url}`,
  es: (url) => `DoGoods: Siga este enlace para ayuda paso a paso: ${url}`,
  fr: (url) => `DoGoods : Suivez ce lien pour une aide étape par étape : ${url}`,
  vi: (url) => `DoGoods: Mở liên kết này để được hướng dẫn từng bước: ${url}`,
  zh: (url) => `DoGoods：点击此链接获取分步帮助：${url}`,
}

function appOrigin() {
  if (typeof window !== 'undefined' && window.location?.origin) {
    return window.location.origin
  }
  return 'https://dogoods.store'
}

/**
 * Send a short SMS with a deep link to a guided flow.
 * Requires SMS opt-in on the user's account.
 *
 * @param {{ phone: string, flow?: 'find'|'share'|'claim'|'request', lang?: string }} opts
 */
export async function sendGuideLinkSms({ phone, flow = 'find', lang = 'en' }) {
  if (!phone) throw new Error('Phone number is required for SMS guide links')

  const guideLang = normalizeGuideLang(lang)
  const basePath = FLOW_PATHS[flow] || FLOW_PATHS.find
  const url = `${appOrigin()}${basePath}?guide=1&lang=${guideLang}`
  const copyFn = SMS_COPY[guideLang] || SMS_COPY.en
  const message = copyFn(url)

  return twilioService.sendSMS({
    to: phone,
    message,
    type: 'notification',
  })
}

export default { sendGuideLinkSms }
