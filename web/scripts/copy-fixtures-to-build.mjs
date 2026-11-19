#!/usr/bin/env node
// Copies the fixture dataset into build/data/, mimicking what the Pages workflow does
// with the real data bundle. Used by the Playwright smoke test and local Lighthouse runs.
import { cpSync, existsSync, rmSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import path from 'node:path';

const web = path.resolve(import.meta.dirname, '..');
const src = path.join(web, 'fixtures', 'data');
const dest = path.join(web, 'build', 'data');

if (!existsSync(path.join(src, 'manifest.json'))) {
	execFileSync(process.execPath, [path.join(web, 'scripts', 'make-fixture-data.mjs')], {
		stdio: 'inherit'
	});
}
if (!existsSync(path.join(web, 'build'))) {
	console.error('build/ does not exist; run `npm run build` first');
	process.exit(1);
}
rmSync(dest, { recursive: true, force: true });
cpSync(src, dest, { recursive: true });
console.log(`copied fixtures → ${path.relative(web, dest)}`);
