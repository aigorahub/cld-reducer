import { defineConfig } from "vitest/config";

// Solves are synchronous WebAssembly calls. Child processes keep the test runner
// responsive when a solve takes long.
export default defineConfig({
  test: { include: ["test/**/*.test.ts"], testTimeout: 120_000, pool: "forks" },
});
