/**
 * ESLint flat config.
 *
 * Next 16 removed `next lint`, and `next build` no longer lints, so linting is its
 * own npm script. `eslint-config-next` ships native flat-config arrays, so they are
 * spread directly rather than shimmed through FlatCompat.
 */
import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

const config = [
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "next-env.d.ts",
      "src/lib/video/__fixtures__/**",
    ],
  },
  ...nextCoreWebVitals,
  ...nextTypescript,
  {
    rules: {
      // Media is served by the storage provider (local disk, or S3/CDN in
      // production), not by the Next image pipeline, so <img> is correct here.
      "@next/next/no-img-element": "off",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
    },
  },
];

export default config;
