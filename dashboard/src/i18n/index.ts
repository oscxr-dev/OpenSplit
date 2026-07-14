import i18n from 'i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import { initReactI18next } from 'react-i18next';
import type { Locale } from 'date-fns';
import { enUS, es as esLocale } from 'date-fns/locale';
import en from './locales/en.json';
import es from './locales/es.json';

/** localStorage key the language choice persists under (explicit user choice
 *  wins over the browser language on the next visit). */
export const LANGUAGE_STORAGE_KEY = 'opensplit-language';

export const SUPPORTED_LANGUAGES = ['en', 'es'] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

// Resources are bundled inline, so init completes synchronously and i18n.t is
// safe to call from plain modules (lib helpers) right after this import.
void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      es: { translation: es },
    },
    fallbackLng: 'en',
    supportedLngs: [...SUPPORTED_LANGUAGES],
    load: 'languageOnly',
    detection: {
      order: ['localStorage', 'navigator'],
      lookupLocalStorage: LANGUAGE_STORAGE_KEY,
      caches: ['localStorage'],
    },
    interpolation: { escapeValue: false }, // React already escapes
    nsSeparator: false, // single namespace; keys (and pass-through text) may contain ':'
    returnNull: false,
  });

/** date-fns locale matching the active UI language (prose like "5 minutes
 *  ago"); sat/fiat number formatting is intentionally left unchanged. */
export function dateFnsLocale(): Locale {
  return i18n.language?.startsWith('es') ? esLocale : enUS;
}

export default i18n;
