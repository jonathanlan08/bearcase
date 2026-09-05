import { defineConfig, devices } from "@playwright/test";

const API = "cd ../api && uv run bearcase serve --port 8000";
const WEB = "npm run dev -- --port 3000";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  use: { baseURL: "http://localhost:3000", trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }, { name: "mobile", use: { ...devices["Pixel 7"] } }],
  webServer: [
    { command: API, url: "http://localhost:8000/api/health", reuseExistingServer: !process.env.CI, timeout: 120_000, env: { BEARCASE_DATABASE_URL: "sqlite:///./data/e2e.db", BEARCASE_STORAGE_LOCAL_DIR: "./data/e2e-storage", BEARCASE_JOB_RUNNER: "thread" } },
    { command: WEB, url: "http://localhost:3000", reuseExistingServer: !process.env.CI, timeout: 180_000 },
  ],
});
