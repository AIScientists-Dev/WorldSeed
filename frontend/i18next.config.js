/** @type {import('i18next-cli').UserConfig} */
export default {
  locales: ['en', 'zh', 'ja', 'ko', 'es', 'fr', 'de'],
  extract: {
    input: ['src/**/*.{ts,tsx}'],
    exclude: ['src/components/ui/**'],
    output: 'src/locales/{{language}}/{{namespace}}.json',
    primaryLanguage: 'en',
    defaultNS: 'common',
    keySeparator: '.',
  },
}
