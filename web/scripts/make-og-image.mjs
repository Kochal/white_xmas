#!/usr/bin/env node
// Renders the static social preview image (static/og-image.png, 1200 × 630) and the
// touch icon (static/apple-touch-icon.png, 180 × 180) with Playwright's Chromium.
// Run after changing the design: node scripts/make-og-image.mjs
import { chromium } from '@playwright/test';
import { readFileSync } from 'node:fs';
import path from 'node:path';

const web = path.resolve(import.meta.dirname, '..');
const favicon = readFileSync(path.join(web, 'src/lib/assets/favicon.svg'), 'utf8');

// An illustrative year strip: a decorative pattern, not data.
const cells = Array.from({ length: 76 }, (_, k) => {
	const white = Math.sin(k * 1.7) + Math.sin(k * 0.37) + 1.3 - k / 45 > 0.4;
	return `<i class="${white ? 'w' : 'g'}"></i>`;
}).join('');

const og = `<!doctype html><html><head><meta charset="utf-8"><style>
	* { box-sizing: border-box; margin: 0; }
	body { width: 1200px; height: 630px; font-family: 'Segoe UI', system-ui, sans-serif;
		background: radial-gradient(circle at 80% 10%, #2a5a9a 0, #0f2a52 55%, #0a1c38 100%); color: #f4f8fd;
		padding: 72px 80px; display: flex; flex-direction: column; }
	.brand { display: flex; align-items: center; gap: 18px; font-size: 30px; font-weight: 600; opacity: .9; }
	.brand svg { width: 52px; height: 52px; }
	h1 { margin-top: 56px; font-size: 76px; line-height: 1.05; font-weight: 750; letter-spacing: -1.5px; }
	p { margin-top: 24px; font-size: 32px; line-height: 1.35; color: #c9daf0; max-width: 900px; }
	.strip { margin-top: auto; display: flex; gap: 3px; height: 54px; }
	.strip i { flex: 1; border-radius: 3px; }
	.w { background: #f4f8fd; } .g { background: #5d8a5b; }
	.axis { display: flex; justify-content: space-between; margin-top: 10px; font-size: 22px; color: #9fb6d6; }
</style></head><body>
	<div class="brand">${favicon}<span>White Christmas</span></div>
	<h1>How likely is a white<br>Christmas where you live?</h1>
	<p>Snow on the ground at Christmas, every year since 1950, anywhere on Earth.</p>
	<div class="strip">${cells}</div>
	<div class="axis"><span>1950</span><span>white or green, year by year</span><span>2025</span></div>
</body></html>`;

const icon = `<!doctype html><html><head><style>*{margin:0}body{width:180px;height:180px}svg{width:180px;height:180px;display:block}</style></head><body>${favicon.replace('rx="14"', 'rx="0"')}</body></html>`;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1200, height: 630 } });
await page.setContent(og);
await page.screenshot({ path: path.join(web, 'static/og-image.png') });
await page.setViewportSize({ width: 180, height: 180 });
await page.setContent(icon);
await page.screenshot({ path: path.join(web, 'static/apple-touch-icon.png') });
await browser.close();
console.log('wrote static/og-image.png and static/apple-touch-icon.png');
