import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: [".next/**", "next-env.d.ts", "node_modules/**"] },
  js.configs.recommended,
  ...tseslint.configs.strict,
  {
    rules: {
      "@typescript-eslint/no-explicit-any": "error",
      "no-restricted-syntax": [
        "error",
        { selector: "ExportDefaultDeclaration", message: "Use named exports (CLAUDE.md §14)." },
      ],
    },
  },
  {
    // Next.js requires default exports for these file conventions.
    files: ["src/app/**/{page,layout,error,not-found,loading}.tsx", "*.config.{js,ts}"],
    rules: { "no-restricted-syntax": "off" },
  },
);
