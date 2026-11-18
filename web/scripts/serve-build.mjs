#!/usr/bin/env node
// Serves build/ the way GitHub Pages does: under BASE_PATH, index.html for directories,
// a redirect to add the trailing slash, 404.html for unknown paths, and range requests.
// Usage: node scripts/serve-build.mjs [port]
import { createServer } from 'node:http';
import { existsSync, statSync } from 'node:fs';
import path from 'node:path';
import { sendFile } from './lib/send-file.mjs';

const root = path.resolve(import.meta.dirname, '..', 'build');
const base = (process.env.BASE_PATH ?? '').replace(/\/$/, '');
const port = Number(process.argv[2] ?? process.env.PORT ?? 4173);

const isFile = (p) => existsSync(p) && statSync(p).isFile();

createServer((req, res) => {
	const url = new URL(req.url ?? '/', 'http://localhost');
	let pathname = decodeURIComponent(url.pathname);
	if (base && !pathname.startsWith(base)) {
		res.writeHead(302, { Location: `${base}/` }).end();
		return;
	}
	pathname = pathname.slice(base.length) || '/';
	const file = path.resolve(root, '.' + pathname);
	if (!file.startsWith(root)) {
		res.writeHead(403).end();
		return;
	}
	const immutable = pathname.startsWith('/_app/immutable/');
	const cacheControl = immutable ? 'public, max-age=31536000, immutable' : 'public, max-age=600';
	if (isFile(file)) return sendFile(req, res, file, { cacheControl });
	if (existsSync(file) && statSync(file).isDirectory()) {
		if (!pathname.endsWith('/')) {
			res.writeHead(301, { Location: `${base}${pathname}/${url.search}` }).end();
			return;
		}
		if (isFile(path.join(file, 'index.html')))
			return sendFile(req, res, path.join(file, 'index.html'), { cacheControl });
	}
	if (isFile(file + '.html')) return sendFile(req, res, file + '.html', { cacheControl });
	const notFound = path.join(root, '404.html');
	if (isFile(notFound)) return sendFile(req, res, notFound, { status: 404 });
	res.writeHead(404).end('not found');
}).listen(port, () => console.log(`serving build/ at http://localhost:${port}${base}/`));
