// Renders docs/methodology.md (written on the pipeline branch) at build time. Until that
// file exists, the page shows a short placeholder. Nothing here runs in the browser.
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { marked } from 'marked';
import type { PageServerLoad } from './$types';

export const prerender = true;

function methodologyPath(): string {
	if (process.env.METHODOLOGY_MD) return path.resolve(process.env.METHODOLOGY_MD);
	// the build runs from web/, the docs live at the repository root
	return path.resolve(process.cwd(), '..', 'docs', 'methodology.md');
}

export const load: PageServerLoad = () => {
	const file = methodologyPath();
	if (!existsSync(file)) return { html: null as string | null };
	const md = readFileSync(file, 'utf8');
	// The first-level heading becomes the page title; drop it from the body.
	const title = /^#\s+(.+)$/m.exec(md)?.[1]?.trim() ?? null;
	const body = title ? md.replace(/^#\s+.+$/m, '') : md;
	const html = (marked.parse(body, { async: false, gfm: true }) as string)
		// wide tables scroll inside their own box instead of widening the page on phones
		.replace(/<table>/g, '<div class="table-wrap"><table>')
		.replace(/<\/table>/g, '</table></div>');
	return { html, title };
};
