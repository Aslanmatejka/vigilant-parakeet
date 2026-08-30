import React from 'react'
import Card from '../common/Card'
import { useNouriGuide } from '../../utils/NouriGuideContext'
import { useAuthContext } from '../../utils/AuthContext'
import {
  GUIDE_LANGUAGE_LABELS,
  SUPPORTED_GUIDE_LANGUAGES,
} from '../../utils/accessibilityStorage'
import { sendGuideLinkSms } from '../../utils/smsGuideService'
import { toast } from 'react-toastify'

function ToggleRow({ id, label, description, checked, onChange }) {
  return (
    <div className="flex items-start justify-between gap-4 py-3 border-b border-gray-100 last:border-b-0">
      <div className="flex-1 min-w-0">
        <label htmlFor={id} className="block text-sm font-medium text-gray-900">
          {label}
        </label>
        {description && (
          <p id={`${id}-desc`} className="mt-0.5 text-xs text-gray-500">
            {description}
          </p>
        )}
      </div>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        aria-describedby={description ? `${id}-desc` : undefined}
        onClick={() => onChange(!checked)}
        className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2CABE3] ${
          checked ? 'bg-[#2CABE3]' : 'bg-gray-200'
        }`}
      >
        <span
          className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition ${
            checked ? 'translate-x-5' : 'translate-x-0'
          }`}
          aria-hidden="true"
        />
        <span className="sr-only">{label}</span>
      </button>
    </div>
  )
}

export default function AccessibilitySettings() {
  const { settings, updateSetting, resetSettings } = useNouriGuide()
  const { user } = useAuthContext()
  const [smsSending, setSmsSending] = React.useState(false)

  const handleSmsToggle = async (enabled) => {
    updateSetting('smsGuideEnabled', enabled)
    if (!enabled || !user?.phone) return

    setSmsSending(true)
    try {
      await sendGuideLinkSms({
        phone: user.phone,
        flow: 'find',
        lang: settings.preferredLanguage,
      })
      toast.success('Guide link sent by text message.')
    } catch (err) {
      toast.warn(err?.message || 'Could not send SMS. Check phone and SMS opt-in in your profile.')
      updateSetting('smsGuideEnabled', false)
    } finally {
      setSmsSending(false)
    }
  }

  return (
    <Card>
      <div className="p-6">
        <h2 className="text-xl font-semibold mb-1">Accessibility</h2>
        <p className="text-sm text-gray-600 mb-4">
          Customize display, motion, and how Nouri speaks. Settings save on this device and sync to your account when signed in.
        </p>

        <div className="mb-4">
          <label htmlFor="a11y-preferred-language" className="block text-sm font-medium text-gray-900 mb-1">
            Preferred language
          </label>
          <p id="a11y-preferred-language-desc" className="text-xs text-gray-500 mb-2">
            Nouri will try to respond in this language in chat and guided steps.
          </p>
          <select
            id="a11y-preferred-language"
            aria-describedby="a11y-preferred-language-desc"
            value={settings.preferredLanguage}
            onChange={(e) => updateSetting('preferredLanguage', e.target.value)}
            className="block w-full max-w-xs rounded-md border border-gray-300 px-3 py-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2CABE3]"
          >
            {SUPPORTED_GUIDE_LANGUAGES.map((code) => (
              <option key={code} value={code}>{GUIDE_LANGUAGE_LABELS[code]}</option>
            ))}
          </select>
        </div>

        <div className="divide-y divide-gray-100">
          <ToggleRow
            id="a11y-large-text"
            label="Large text"
            description="Increases text size across the app."
            checked={settings.largeText}
            onChange={(v) => updateSetting('largeText', v)}
          />
          <ToggleRow
            id="a11y-high-contrast"
            label="High contrast"
            description="Stronger text and focus outlines for easier reading."
            checked={settings.highContrast}
            onChange={(v) => updateSetting('highContrast', v)}
          />
          <ToggleRow
            id="a11y-reduce-motion"
            label="Reduce motion"
            description="Minimizes animations and smooth scrolling."
            checked={settings.reduceMotion}
            onChange={(v) => updateSetting('reduceMotion', v)}
          />
          <ToggleRow
            id="a11y-captions"
            label="Always show captions"
            description="Shows a text bar whenever Nouri speaks in chat or on forms."
            checked={settings.alwaysShowCaptions}
            onChange={(v) => updateSetting('alwaysShowCaptions', v)}
          />
          <ToggleRow
            id="a11y-form-voice"
            label="Form voice guide"
            description={
              settings.preferTextOverVoice
                ? 'Turn off "Prefer text over voice" above to enable spoken form hints.'
                : 'Nouri reads form field hints aloud when you focus a field. Text hints still appear when this is off.'
            }
            checked={settings.formVoiceGuideEnabled}
            onChange={(v) => updateSetting('formVoiceGuideEnabled', v)}
          />
          <ToggleRow
            id="a11y-prefer-text"
            label="Prefer text over voice"
            description="Nouri shows instructions as text instead of playing audio automatically."
            checked={settings.preferTextOverVoice}
            onChange={(v) => updateSetting('preferTextOverVoice', v)}
          />
          <ToggleRow
            id="a11y-simple-language"
            label="Simple language"
            description="Uses clearer spacing; Nouri will favor shorter phrases when this is on."
            checked={settings.simpleLanguage}
            onChange={(v) => updateSetting('simpleLanguage', v)}
          />
          <ToggleRow
            id="a11y-easy-mode"
            label="Easy mode"
            description="Shows one form section at a time with a progress bar and larger controls."
            checked={settings.easyMode}
            onChange={(v) => updateSetting('easyMode', v)}
          />
          <ToggleRow
            id="a11y-list-first-find"
            label="List-first Find Food"
            description="Shows food listings first; map is optional (better for screen readers)."
            checked={settings.listFirstFind}
            onChange={(v) => updateSetting('listFirstFind', v)}
          />
          <ToggleRow
            id="a11y-screen-reader"
            label="Screen reader optimized"
            description="Clearer labels and fewer visual-only cues in Nouri replies."
            checked={settings.screenReaderOptimized}
            onChange={(v) => updateSetting('screenReaderOptimized', v)}
          />
          <ToggleRow
            id="a11y-sms-guide"
            label="SMS step-by-step links"
            description={
              user?.phone
                ? 'Text me deep links to guided flows (requires SMS opt-in on your profile).'
                : 'Add a phone number in your profile to receive guided flow links by text.'
            }
            checked={settings.smsGuideEnabled}
            onChange={handleSmsToggle}
          />
          {smsSending && (
            <p className="text-xs text-gray-500 py-2" role="status">Sending guide link…</p>
          )}
        </div>

        <div className="mt-4 flex justify-end">
          <button
            type="button"
            onClick={resetSettings}
            className="text-sm text-gray-600 hover:text-gray-900 underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2CABE3]"
          >
            Reset accessibility settings
          </button>
        </div>
      </div>
    </Card>
  )
}
