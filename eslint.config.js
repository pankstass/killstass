// v1.9: frontend linter (ESLint 9 flat config). Run: npm run lint (see docs/19-v1.9.md).
import js from "@eslint/js";
import globals from "globals";

export default [
  { ignores: ["node_modules/**", "tools/**", "docs/**"] },
  js.configs.recommended,
  {
    files: ["web/**/*.js"],
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: "module",
      globals: { ...globals.browser },
    },
    rules: {
      "no-unused-vars": ["error", { args: "none", caughtErrors: "none" }],
      "no-empty": ["error", { allowEmptyCatch: true }],
      "prefer-const": "error",
      "no-var": "error",
      eqeqeq: ["error", "smart"],
      "no-implicit-globals": "error",
      "no-restricted-globals": ["error", "event", "name", "status", "length"],
      "no-eval": "error",
      "no-implied-eval": "error",
      "no-new-func": "error",
      "no-script-url": "error",
    },
  },
  // v1.10: the service worker is a classic script with its own global scope.
  {
    files: ["web/sw.js"],
    languageOptions: {
      sourceType: "script",
      globals: { ...globals.serviceworker },
    },
    rules: { "no-implicit-globals": "off" },
  },
  {
    files: ["tests/e2e/**/*.mjs", "eslint.config.js"],
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: "module",
      globals: { ...globals.node, ...globals.browser },
    },
  },
];
