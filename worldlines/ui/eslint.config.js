import js from '@eslint/js'
import globals from 'globals'
import tseslint from 'typescript-eslint'

// 1.0 界面(app/)是纯浏览器脚本,由 app/build.mjs 拼进单页;这里只 lint TypeScript(Playwright 用例与配置)。
export default tseslint.config(
  { ignores: ['dist', 'dist-local', 'test-results', 'playwright-report'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: { ...globals.browser, ...globals.node },
    },
  },
  // 用例要伸进页面全局(window.MAPW 等)和引擎 JSON,any 在这里是常态
  { files: ['e2e/**', 'e2e-legacy/**'], rules: { '@typescript-eslint/no-explicit-any': 'off' } },
)
