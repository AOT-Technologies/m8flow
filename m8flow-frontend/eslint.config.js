import js from "@eslint/js";
import tsParser from "@typescript-eslint/parser";
import tsPlugin from "@typescript-eslint/eslint-plugin";
import globals from "globals";

export default [
  {
    ignores: ["dist/**", "node_modules/**"],
    linterOptions: {
      noInlineConfig: true,
      reportUnusedInlineConfigs: "off",
    },
  },
  {
    files: ["src/**/*.{ts,tsx}", "vite.config.ts"],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaVersion: "latest",
        sourceType: "module",
        ecmaFeatures: {
          jsx: true,
        },
      },
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    plugins: {
      "@typescript-eslint": tsPlugin,
    },
    rules: {
      ...js.configs.recommended.rules,
      "no-undef": "off",
      "no-unused-vars": "off",
      "@typescript-eslint/no-unused-vars": "off",
    },
  },
];
