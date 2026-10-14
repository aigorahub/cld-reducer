// The path of Chrome, for the browser test.

import { existsSync } from "node:fs";

export function findChrome() {
  const chrome = [
    process.env.CHROME_PATH,
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  ].find((p) => p && existsSync(p));
  if (!chrome) {
    console.error("Chrome was not found. Set CHROME_PATH.");
    process.exit(1);
  }
  return chrome;
}
