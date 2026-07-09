module.exports = {
  env: {
    browser: true,
    es2021: true,
    node: true,
  },
  extends: [
    'eslint:recommended',
    'plugin:react/recommended',
    'prettier',
  ],
  parserOptions: {
    ecmaFeatures: {
      jsx: true,
    },
    ecmaVersion: 12,
    sourceType: 'module',
  },
  plugins: ['react', 'react-hooks'],
  rules: {
    'react/react-in-jsx-scope': 'off',
    'react/prop-types': 'off',
    // Apostrophes/quotes in JSX copy are common; warn instead of fail CI.
    'react/no-unescaped-entities': 'warn',
    'react-hooks/rules-of-hooks': 'error',
    'react-hooks/exhaustive-deps': 'warn',
    // Keep unused-vars as warn so CI stays green while the large JSX
    // surface is cleaned up incrementally; hooks/rules remain hard errors.
    'no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
    'no-empty': ['error', { allowEmptyCatch: true }],
    'no-useless-catch': 'warn',
  },
  settings: {
    react: {
      version: 'detect',
    },
  },
  overrides: [
    {
      files: ['**/__tests__/**', '**/*.{test,spec}.{js,jsx}', 'tests/**/*.{js,jsx}'],
      env: {
        jest: true,
      },
    },
  ],
  ignorePatterns: [
    'dist/',
    'build/',
    'node_modules/',
    'coverage/',
    '.netlify/',
    'uploads/',
    'backend/',
    'scripts/',
    'mcp-server/',
  ],
};
