// Checks that a finished build in build/ matches the base path and site URL it was built for.
// Used by scripts/check-build.mjs (CLI, run in CI) and unit-tested in check-build.spec.mjs.
import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';

const TEXT_EXT = new Set(['.html', '.js', '.mjs', '.css', '.json', '.txt', '.xml', '.webmanifest']);

/** The base path the site was deployed under before the custom domain (see docs/custom-domain.md). */
export const LEGACY_BASE = '/white_xmas';

/** The github.io host the site was served from before the custom domain. */
export const LEGACY_HOST = 'kochal.github.io';

/** Repo links such as https://github.com/Kochal/white_xmas legitimately contain "/white_xmas". */
const REPO_LINK = /github\.com\/[^/\s"'<>]+\/white_xmas/gi;

/** Yields every text file under dir, skipping the data tree (it arrives at deploy time). */
function* walk(dir, skip) {
	for (const entry of readdirSync(dir, { withFileTypes: true })) {
		const full = path.join(dir, entry.name);
		if (entry.isDirectory()) {
			if (skip.has(full)) continue;
			yield* walk(full, skip);
		} else if (TEXT_EXT.has(path.extname(entry.name).toLowerCase())) {
			yield full;
		}
	}
}

/** Origin (scheme and host) of an absolute URL, or null. */
function originOf(url) {
	try {
		return new URL(url).origin;
	} catch {
		return null;
	}
}

/** Where `needle` occurs in `text`, as short snippets for the error message. */
function snippets(text, needle) {
	const out = [];
	let i = text.indexOf(needle);
	while (i !== -1 && out.length < 3) {
		out.push(text.slice(Math.max(0, i - 25), i + needle.length + 25).replace(/\s+/g, ' '));
		i = text.indexOf(needle, i + needle.length);
	}
	return out;
}

/**
 * @param {{ dir: string, base?: string, siteUrl?: string }} options
 *   base: the BASE_PATH the build was made with ('' for a root deployment);
 *   siteUrl: the PUBLIC_SITE_URL it was made with (absolute, no trailing slash).
 * @returns {string[]} problems; empty when the build is consistent
 */
export function checkBuild({ dir, base = '', siteUrl }) {
	base = base.replace(/\/$/, '');
	const problems = [];
	const skip = new Set([path.join(dir, 'data')]);
	const siteOrigin = siteUrl ? originOf(siteUrl) : null;
	const siteHost = siteOrigin ? new URL(siteOrigin).hostname : null;
	// A custom domain: no URL on the old github.io host may remain anywhere (it would bypass the
	// domain). Other github.io links, such as a library's docs, are fine.
	const forbidLegacyHost = !!siteHost && !siteHost.endsWith('.github.io');

	let files = 0;
	let pages = 0;
	for (const file of walk(dir, skip)) {
		files++;
		const rel = path.relative(dir, file).split(path.sep).join('/');
		const text = readFileSync(file, 'utf8');
		const withoutRepoLinks = text.replace(REPO_LINK, '');

		// 1. a root build must not carry the old base path in any asset or link
		if (base === '' && withoutRepoLinks.includes(LEGACY_BASE)) {
			for (const s of snippets(withoutRepoLinks, LEGACY_BASE))
				problems.push(`${rel}: hard-coded "${LEGACY_BASE}": …${s}…`);
		}

		// 2. a custom-domain build must not point at the old github.io host
		if (forbidLegacyHost && text.toLowerCase().includes(LEGACY_HOST)) {
			problems.push(`${rel}: absolute URL on ${LEGACY_HOST} with site URL ${siteUrl}`);
		}

		// 3a. in a base-path build the scripts must not build root-absolute data or asset URLs
		//     (a string literal starting "/data/" or "/_app/" would escape the base)
		if (base !== '' && !rel.endsWith('.html')) {
			const m = /["'`]\/(?:data|_app)\//.exec(text);
			if (m) problems.push(`${rel}: root-absolute URL in a base-path build: …${m[0]}…`);
		}

		if (!rel.endsWith('.html')) continue;
		pages++;

		// 3b. root-absolute links in a base-path build must stay under the base
		if (base !== '') {
			for (const m of text.matchAll(/\b(?:href|src)="(\/(?!\/)[^"]*)"/g)) {
				const url = m[1];
				if (url !== base && !url.startsWith(`${base}/`) && !url.startsWith(`${base}?`))
					problems.push(`${rel}: root-absolute URL outside base "${base}": ${url}`);
			}
		}

		// 4. social/canonical tags must be absolute URLs on the site URL (the 404.html fallback
		//    is a bare app shell without them)
		if (siteUrl && rel !== '404.html') {
			const tags = {
				'link rel=canonical': /<link[^>]*rel="canonical"[^>]*href="([^"]*)"/i,
				'og:url': /<meta[^>]*property="og:url"[^>]*content="([^"]*)"/i,
				'og:image': /<meta[^>]*property="og:image"[^>]*content="([^"]*)"/i,
				'twitter:image': /<meta[^>]*name="twitter:image"[^>]*content="([^"]*)"/i
			};
			for (const [name, re] of Object.entries(tags)) {
				const m = re.exec(text);
				if (!m) problems.push(`${rel}: missing ${name} tag`);
				else if (m[1] !== siteUrl && !m[1].startsWith(`${siteUrl}/`))
					problems.push(`${rel}: ${name} "${m[1]}" is not under the site URL ${siteUrl}`);
			}
		}
	}
	if (files === 0) problems.push(`no text files found in ${dir} (did the build run?)`);
	else if (pages === 0) problems.push(`no HTML pages found in ${dir}`);
	return problems;
}
