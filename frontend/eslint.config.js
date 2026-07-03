import tseslint from 'typescript-eslint'
import reactHooks from 'eslint-plugin-react-hooks'

export default tseslint.config(
  { ignores: ['dist/', 'node_modules/'] },
  ...tseslint.configs.recommended,
  {
    files: ['src/**/*.{ts,tsx}'],
    plugins: { 'react-hooks': reactHooks },
    rules: {
      'react-hooks/rules-of-hooks': 'error',
      // Known deferred debt: several effects intentionally under-declare deps
      // (documented inline). Keep visible as warnings, not errors.
      'react-hooks/exhaustive-deps': 'warn',
    },
  },
)
