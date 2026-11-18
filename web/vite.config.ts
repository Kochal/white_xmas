import { defineConfig, type Plugin } from 'vitest/config';
import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import { existsSync, statSync } from 'node:fs';
import { sendFile } from './scripts/lib/send-file.mjs';
import path from 'node:path';

/**
 * Base path the site is served from. Empty for local development, `/white_xmas`
 * on GitHub Pages (set by `.github/workflows/pages.yml`).
 */
const base = (process.env.BASE_PATH ?? '').replace(/\/$/, '') as '' | `/${string}`;

/** URL prefix the dev server uses to serve the fixture dataset (see README). */
const FIXTURE_URL_PREFIX = '/__fixtures/data';

/**
 * Serves `web/fixtures/data/` (written by `npm run fixtures`) at
 * `${base}/__fixtures/data/` in `vite dev`, with HTTP range support for PMTiles.
 * The fixtures are never copied into `static/`, so they can't leak into a build.
 */
function serveFixtures(): Plugin {
	const root = path.resolve(import.meta.dirname, 'fixtures/data');
	const prefix = `${base}${FIXTURE_URL_PREFIX}/`;
	return {
		name: 'whitexmas-serve-fixtures',
		apply: 'serve',
		configureServer(server) {
			server.middlewares.use((req, res, next) => {
				const url = req.url?.split('?')[0] ?? '';
				if (!url.startsWith(prefix)) return next();
				const file = path.resolve(root, decodeURIComponent(url.slice(prefix.length)));
				if (!file.startsWith(root) || !existsSync(file) || !statSync(file).isFile()) {
					res.statusCode = 404;
					res.end('fixture not found (run `npm run fixtures`)');
					return;
				}
				sendFile(req, res, file);
			});
		}
	};
}

export default defineConfig({
	plugins: [
		serveFixtures(),
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			adapter: adapter({ fallback: '404.html' }),
			paths: { base },
			prerender: {
				// The data tree arrives at deploy time (pages.yml), so links into it can't be
				// crawled during the build.
				handleHttpError: ({ path, message }) => {
					if (path.startsWith(`${base}/data/`)) return;
					throw new Error(message);
				}
			}
		})
	],
	define: { __BASE_PATH__: JSON.stringify(base) },
	server: { port: Number(process.env.PANE_PORT ?? 5173) },
	test: {
		expect: { requireAssertions: true },
		projects: [
			{
				extends: './vite.config.ts',
				test: {
					name: 'server',
					environment: 'node',
					include: ['src/**/*.{test,spec}.{js,ts}', 'scripts/**/*.{test,spec}.{js,mjs}'],
					exclude: ['src/**/*.svelte.{test,spec}.{js,ts}']
				}
			}
		]
	}
});
