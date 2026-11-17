import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["node_modules", "src/api/schema.d.ts"] },
  js.configs.recommended,
  ...tseslint.configs.strict,
  reactHooks.configs.flat.recommended,
  {
    languageOptions: { globals: globals.browser },
    rules: {
      // Text reaches the page only as React text nodes, never as raw HTML.
      "no-restricted-syntax": [
        "error",
        {
          selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
          message: "Render text as React text nodes; raw HTML is not allowed.",
        },
        {
          selector: "MemberExpression[property.name=/^(innerHTML|outerHTML)$/]",
          message: "Render text as React text nodes; raw HTML is not allowed.",
        },
      ],
    },
  },
  {
    // Components reach the server only through src/api.
    files: ["src/**/*.{ts,tsx}"],
    ignores: ["src/api/**"],
    rules: {
      "no-restricted-globals": [
        "error",
        { name: "fetch", message: "Call the server through src/api/client." },
      ],
    },
  },
);
