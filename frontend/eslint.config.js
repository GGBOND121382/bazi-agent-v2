import js from '@eslint/js'
import tsParser from '@typescript-eslint/parser'
import tsPlugin from '@typescript-eslint/eslint-plugin'
import vue from 'eslint-plugin-vue'

const globals = {
  window: 'readonly', document: 'readonly', crypto: 'readonly', fetch: 'readonly',
  localStorage: 'readonly', sessionStorage: 'readonly', EventSource: 'readonly',
  MessageEvent: 'readonly', setTimeout: 'readonly', clearTimeout: 'readonly',
  URL: 'readonly', HTMLSelectElement: 'readonly', process: 'readonly', __dirname: 'readonly',
}

const sharedRules = {
  'no-unused-vars': 'off',
  '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
}

export default [
  { ignores: ['dist/**', 'node_modules/**', 'test-results/**', 'playwright-report/**'] },
  { ...js.configs.recommended, files: ['**/*.{js,mjs,cjs}'] },
  ...vue.configs['flat/recommended'],
  {
    files: ['**/*.ts'],
    languageOptions: { parser: tsParser, parserOptions: { ecmaVersion: 'latest', sourceType: 'module' }, globals },
    plugins: { '@typescript-eslint': tsPlugin },
    rules: sharedRules,
  },
  {
    files: ['**/*.vue'],
    languageOptions: { parserOptions: { parser: tsParser }, globals },
    plugins: { '@typescript-eslint': tsPlugin },
    rules: {
      ...sharedRules,
      'vue/multi-word-component-names': 'off',
      'vue/max-attributes-per-line': 'off',
      'vue/html-self-closing': 'off',
      'vue/singleline-html-element-content-newline': 'off',
      'vue/multiline-html-element-content-newline': 'off',
      'vue/attributes-order': 'off',
    },
  },
]
