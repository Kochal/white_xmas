#!/usr/bin/env node
// Verifies a finished build matches the base path and site URL it was made for:
//   node scripts/check-build.mjs [--dir build] [--base ''] [--site-url https://snowatchristmas.com]
// Defaults to the BASE_PATH and PUBLIC_SITE_URL environment variables, like the build itself.
// A root build (empty base) must not contain "/white_xmas"; a build for a custom domain must
// not contain a kochal.github.io URL; a base-path build must not build root-absolute data or
// asset URLs; canonical/og tags must be on the site URL (required). Exits 1 on problems.
import path from 'node:path';
import { parseArgs } from 'node:util';
import { checkBuild } from './lib/check-build.mjs';

const { values } = parseArgs({
	options: {
		dir: { type: 'string', default: 'build' },
		base: { type: 'string' },
		'site-url': { type: 'string' }
	}
});

const dir = path.resolve(values.dir);
const base = values.base ?? process.env.BASE_PATH ?? '';
const siteUrl = (values['site-url'] ?? process.env.PUBLIC_SITE_URL ?? '').replace(/\/$/, '');

// Without a site URL the canonical and social tags would silently go unchecked.
if (!siteUrl) {
	console.error('build check failed: no site URL. Pass --site-url or set PUBLIC_SITE_URL.');
	process.exit(1);
}

const problems = checkBuild({ dir, base, siteUrl });
if (problems.length) {
	console.error(`build check failed (base '${base}', site URL '${siteUrl}'):`);
	for (const p of problems) console.error(`  - ${p}`);
	process.exit(1);
}
console.log(`build check ok: ${dir} (base '${base}', site URL '${siteUrl}')`);
