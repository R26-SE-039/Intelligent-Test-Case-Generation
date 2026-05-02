#!/usr/bin/env node

/**
 * Lint script for backend files
 * Cross-platform wrapper for ruff execution in backend venv
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

const backendDir = path.join(rootDir, "backend");
const pythonExe = path.join(
  backendDir,
  process.platform === "win32" ? ".venv\\Scripts\\python.exe" : ".venv/bin/python",
);

// Check if backend directory exists
if (!fs.existsSync(backendDir)) {
  console.error("Backend directory not found at", backendDir);
  process.exit(1);
}

// Check if venv exists
if (!fs.existsSync(pythonExe)) {
  console.error("Backend venv Python not found at", pythonExe);
  process.exit(1);
}

try {
  // Run ruff check --fix
  console.log("Running ruff check --fix...");
  execSync(`"${pythonExe}" -m ruff check --fix "${backendDir}"`, {
    cwd: rootDir,
    stdio: "inherit",
    shell: true,
  });

  // Run ruff format
  console.log("Running ruff format...");
  execSync(`"${pythonExe}" -m ruff format "${backendDir}"`, {
    cwd: rootDir,
    stdio: "inherit",
    shell: true,
  });
} catch (error) {
  process.exit(error.status || 1);
}
