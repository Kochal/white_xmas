import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { checkBuild } from './check-build.mjs';

const dirs = [];
afterEach(() => {
	for (const d of dirs.splice(0)) rmSync(d, { recursive: true, force: true });
});

/** Writes a fake build: files maps a relative path to its content. */
function build(files) {
	const dir = mkdtempSync(path.join(tmpdir(), 'check-build-'));
	dirs.push(dir);
	for (const [rel, content] of Object.entries(files)) {
		const full = path.join(dir, rel);
		mkdirSync(path.dirname(full), { recursive: true });
		writeFileSync(full, content);
	}
	return dir;
}

const page = (site, extra = '') => `<!doctype html><head>
<link rel="canonical" href="${site}/about/" />
<meta property="og:url" content="${site}/about/" />
<meta property="og:image" content="${site}/og-image.png" />
<meta name="twitter:image" content="${site}/og-image.png" />
</head><body>${extra}</body>`;

describe('checkBuild', () => {
	it('accepts a clean root build for a custom domain', () => {
		const site = 'https://snowatchristmas.com';
		const dir = build({
			'index.html': page(
				site,
				'<a href="/about/">about</a> <a href="https://github.com/Kochal/white_xmas">repo</a>'
			),
			'_app/immutable/a.js': 'fetch("/data/manifest.json")'
		});
		expect(checkBuild({ dir, base: '', siteUrl: site })).toEqual([]);
	});

	it('flags a hard-coded /white_xmas in a root build, but not the repo link', () => {
		const site = 'https://snowatchristmas.com';
		const dir = build({
			'index.html': page(site),
			'_app/immutable/a.js':
				'const u="/white_xmas/data/x"; const r="https://github.com/Kochal/white_xmas";'
		});
		const problems = checkBuild({ dir, base: '', siteUrl: site });
		expect(problems).toHaveLength(1);
		expect(problems[0]).toContain('a.js');
		expect(problems[0]).toContain('/white_xmas/data/x');
	});

	it('flags a github.io URL when the site URL is a custom domain', () => {
		const site = 'https://snowatchristmas.com';
		const dir = build({
			'index.html': page(site),
			'_app/immutable/a.js': 'const s="https://kochal.github.io/white_xmas"'
		});
		const problems = checkBuild({ dir, base: '', siteUrl: site });
		expect(problems.some((p) => p.includes('kochal.github.io'))).toBe(true);
	});

	it('flags canonical and og tags that are not on the site URL', () => {
		const dir = build({ 'index.html': page('https://kochal.github.io/white_xmas') });
		const problems = checkBuild({ dir, base: '', siteUrl: 'https://snowatchristmas.com' });
		expect(problems.filter((p) => p.includes('not under the site URL'))).toHaveLength(4);
	});

	it('accepts a github.io build under its base and flags links outside it', () => {
		const site = 'https://kochal.github.io/white_xmas';
		const ok = build({ 'index.html': page(site, '<a href="/white_xmas/about/">x</a>') });
		expect(checkBuild({ dir: ok, base: '/white_xmas', siteUrl: site })).toEqual([]);
		const bad = build({ 'index.html': page(site, '<a href="/about/">x</a>') });
		expect(checkBuild({ dir: bad, base: '/white_xmas', siteUrl: site })).toEqual([
			expect.stringContaining('root-absolute URL outside base')
		]);
	});

	it('ignores the data tree and reports an empty build', () => {
		const site = 'https://snowatchristmas.com';
		const dir = build({ 'index.html': page(site), 'data/manifest.json': '{"u":"/white_xmas/"}' });
		expect(checkBuild({ dir, base: '', siteUrl: site })).toEqual([]);
		const empty = build({ 'data/x.json': '{}' });
		expect(checkBuild({ dir: empty, base: '' })).toEqual([
			expect.stringContaining('no text files')
		]);
	});
});
