module.exports = {
  root: true,
  env: { browser: true, es2022: true },
  extends: [
    'eslint:recommended',
    'plugin:react/recommended',
    'plugin:react/jsx-runtime',
    'plugin:react-hooks/recommended',
  ],
  parserOptions: { ecmaVersion: 'latest', sourceType: 'module', ecmaFeatures: { jsx: true } },
  settings: { react: { version: '18' } },
  plugins: ['react', 'react-hooks'],
  rules: {
    'react/prop-types': 'off',
  },
  ignorePatterns: ['dist', 'node_modules'],
}
