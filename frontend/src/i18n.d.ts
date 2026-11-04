import i18next from 'i18next'
import { initReactI18next, useTranslation } from 'react-i18next'

declare const i18next: i18next.i18nInstance
declare const initReactI18next: typeof initReactI18next
declare function useTranslation(): {
  t: typeof i18next.t
  i18n: i18next.i18nInstance
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  //: useTranslationReturn
}
