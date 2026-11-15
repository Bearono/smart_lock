import vue from 'eslint-plugin-vue'
import tseslint from 'typescript-eslint'

export default [
  { ignores: ['dist/**', 'node_modules/**'] },
  {
    files: ['src/shared/**/*.{js,ts,vue}'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['**/features/**', '**/app/**'],
              message: 'Shared modules cannot depend on application or feature modules.'
            }
          ]
        }
      ]
    }
  },
  {
    files: ['src/features/**/*.{js,ts,vue}'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['**/app/**'],
              message: 'Features cannot depend on the application composition layer.'
            }
          ]
        }
      ]
    }
  },
  ...vue.configs['flat/essential'],
  {
    files: ['**/*.ts'],
    languageOptions: { parser: tseslint.parser },
    rules: { 'no-unused-vars': 'off', '@typescript-eslint/no-unused-vars': 'error' },
    plugins: { '@typescript-eslint': tseslint.plugin }
  },
  {
    files: ['**/*.vue'],
    languageOptions: { parserOptions: { parser: tseslint.parser } },
    rules: { 'no-unused-vars': 'off', '@typescript-eslint/no-unused-vars': 'error' },
    plugins: { '@typescript-eslint': tseslint.plugin }
  },
  {
    files: ['**/*.{js,mjs,cjs}'],
    languageOptions: { ecmaVersion: 'latest' },
    rules: { 'no-unused-vars': 'error' }
  }
]
