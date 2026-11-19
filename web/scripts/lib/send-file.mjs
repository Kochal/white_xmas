// Sends a static file with HTTP range support (PMTiles needs range requests).
import { createReadStream, statSync } from 'node:fs';
import { createGzip } from 'node:zlib';
import path from 'node:path';

/** @type {Record<string, string>} */
const MIME = {
	'.html': 'text/html; charset=utf-8',
	'.js': 'text/javascript',
	'.mjs': 'text/javascript',
	'.css': 'text/css',
	'.json': 'application/json',
	'.svg': 'image/svg+xml',
	'.png': 'image/png',
	'.webp': 'image/webp',
	'.ico': 'image/x-icon',
	'.txt': 'text/plain',
	'.webmanifest': 'application/manifest+json',
	'.gz': 'application/gzip',
	'.pmtiles': 'application/octet-stream'
};

/**
 * @param {import('node:http').IncomingMessage} req
 * @param {import('node:http').ServerResponse} res
 * @param {string} file absolute path to an existing file
 * @param {{status?: number, cacheControl?: string}} [opts]
 */
export function sendFile(req, res, file, opts = {}) {
	const size = statSync(file).size;
	res.setHeader('Content-Type', MIME[path.extname(file)] ?? 'application/octet-stream');
	res.setHeader('Accept-Ranges', 'bytes');
	res.setHeader('Cache-Control', opts.cacheControl ?? 'no-cache');
	const range = /^bytes=(\d+)-(\d*)$/.exec(req.headers.range ?? '');
	if (range && !opts.status) {
		const start = Number(range[1]);
		const end = range[2] ? Math.min(Number(range[2]), size - 1) : size - 1;
		if (start >= size) {
			res.statusCode = 416;
			res.setHeader('Content-Range', `bytes */${size}`);
			res.end();
			return;
		}
		res.statusCode = 206;
		res.setHeader('Content-Range', `bytes ${start}-${end}/${size}`);
		res.setHeader('Content-Length', String(end - start + 1));
		if (req.method === 'HEAD') return res.end();
		createReadStream(file, { start, end }).pipe(res);
		return;
	}
	res.statusCode = opts.status ?? 200;
	// Compress text like GitHub Pages does; binary data (gz, pmtiles, png) is sent as is.
	const compressible = /^(text\/|application\/(json|manifest\+json)|image\/svg)/.test(
		String(res.getHeader('Content-Type'))
	);
	if (compressible && /gzip/.test(String(req.headers['accept-encoding'] ?? ''))) {
		res.setHeader('Content-Encoding', 'gzip');
		res.setHeader('Vary', 'Accept-Encoding');
		if (req.method === 'HEAD') return res.end();
		createReadStream(file).pipe(createGzip()).pipe(res);
		return;
	}
	res.setHeader('Content-Length', String(size));
	if (req.method === 'HEAD') return res.end();
	createReadStream(file).pipe(res);
}
