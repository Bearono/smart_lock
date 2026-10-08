import vue from 'eslint-plugin-vue'

export default [
  { ignores: ['dist/**', 'node_modules/**'] },
  ...vue.configs['flat/essential'],
  {
    files: ['**/*.{js,mjs,cjs,vue}'],
    languageOptions: { ecmaVersion: 'latest' },
    rules: { 'no-unused-vars': 'error' }
  }
]
