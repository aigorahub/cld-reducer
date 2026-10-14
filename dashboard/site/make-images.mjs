// Make the images of the hosted page from favicon.svg and og.html: og.png
// (the link preview card, 1200 x 630), apple-touch-icon.png, and favicon.ico.
// The images are committed, because Chrome draws the text of the card with
// the fonts of the computer. Needs Chrome: set CHROME_PATH, or install it in
// the usual place.
//
//   npm run images

import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { chromium } from "playwright-core";
import { findChrome } from "../chrome.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const icon = readFileSync(join(here, "favicon.svg"), "utf8");
const tile = icon.match(/<rect[^>]*fill="([^"]+)"/)[1];

// An .ico file that holds PNG images: a 6-byte header, a 16-byte entry for
// each image, and then the images.
function ico(images) {
  const header = Buffer.alloc(6 + 16 * images.length);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(images.length, 4);
  let offset = header.length;
  images.forEach(([size, png], i) => {
    const entry = 6 + 16 * i;
    header.writeUInt8(size, entry);
    header.writeUInt8(size, entry + 1);
    header.writeUInt16LE(1, entry + 4);
    header.writeUInt16LE(32, entry + 6);
    header.writeUInt32LE(png.length, entry + 8);
    header.writeUInt32LE(offset, entry + 12);
    offset += png.length;
  });
  return Buffer.concat([header, ...images.map(([, png]) => png)]);
}

const browser = await chromium.launch({ executablePath: findChrome(), headless: true });
try {
  const card = await browser.newPage({ viewport: { width: 1200, height: 630 } });
  await card.goto(pathToFileURL(join(here, "og.html")).href);
  await card.screenshot({ path: join(here, "og.png") });

  // The icon as a PNG of a size in pixels. Without a background, the corners are transparent.
  const iconPng = async (size, background) => {
    const page = await browser.newPage({ viewport: { width: size, height: size } });
    await page.setContent(`<style>html, body { margin: 0; background: ${background ?? "transparent"}; }
      svg { display: block; width: ${size}px; height: ${size}px; }</style>${icon}`);
    const png = await page.screenshot({ omitBackground: !background });
    await page.close();
    return png;
  };

  // iOS rounds the corners of the icon, so the color of the tile fills the square.
  writeFileSync(join(here, "apple-touch-icon.png"), await iconPng(180, tile));
  const sizes = [16, 32, 48];
  writeFileSync(join(here, "favicon.ico"), ico(await Promise.all(sizes.map(async (s) => [s, await iconPng(s)]))));
} finally {
  await browser.close();
}
console.log("og.png, apple-touch-icon.png, favicon.ico");
