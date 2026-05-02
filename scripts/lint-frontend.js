#!/usr/bin/env node

/**
 * Lint script for frontend files
 * Cross-platform wrapper for ESLint execution in frontend directory
 */

const { execSync } = require("child_process");
const path = require("path");
const fs = require("fs");

// Find the project root by looking for package.json
let rootDir = __dirname;
while (rootDir !== path.dirname(rootDir)) {
  if (fs.existsSync(path.join(rootDir, "package.json"))) {
    const pkg = JSON.parse(
      fs.readFileSync(path.join(rootDir, "package.json"), "utf8"),
    );
    if (pkg.name === "intelligent-test-case-generation") {
      break;
    }
  }
  rootDir = path.dirname(rootDir);
}

const frontendDir = path.join(rootDir, "frontend");

// Check if frontend directory exists
if (!fs.existsSync(frontendDir)) {
  console.error("Frontend directory not found at", frontendDir);
  process.exit(1);
}

try {
  // Run eslint with passed arguments
  const cmd = `pnpm exec eslint . --fix --max-warnings=0 --no-error-on-unmatched-pattern`;
  execSync(cmd, {
    cwd: frontendDir,
    stdio: "inherit",
    shell: true,
  });
} catch (error) {
  process.exit(error.status || 1);
}
