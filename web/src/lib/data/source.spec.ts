import { describe, expect, it } from 'vitest';
import { DataSource } from './source';
import { parseManifest } from './manifest';

/** A full 50 × 50 wx-points-v1 tile, 2 years, all ocean except the cells given. */
function pointTile(land: Record<number, number[]>, glacierCells: number[] = []): Uint8Array {
	const nYears = 2;
	const header = [0x57, 0x58, 0x50, 0x31, 0x9e, 0x07, nYears, 0, 50, 0, 50, 0, 3, 0, 0, 0];
	const body = new Uint8Array(50 * 50 * nYears * 3).fill(255);
	for (const [k, values] of Object.entries(land)) body.set(values, Number(k) * nYears * 3);
	const mask = new Uint8Array(313);
	for (const k of glacierCells) mask[k >> 3] |= 1 << (k & 7);
	return new Uint8Array([...header, ...body, ...mask]);
}

const manifest = parseManifest({
	schema_version: 1,
	data_version: 't',
	built: '',
	build_hash: '',
	years: { first: 1950, last: 1951 },
	threshold_cm: 1,
	attribution: '',
	definitions: [{ id: 'christmas_day', label: 'x', short: 'x', description: 'x', default: true }],
	windows: [{ id: '1950_1951', label: 'x', start: 1950, end: 1951, kind: 'full' }],
	layers: [],
	colormaps: {},
	points: { index: 'points/index.json', tile_deg: 5, format: 'wx-points-v1' },
	places: 'places.json',
	regions: 'regions.json'
});

function server(files: Record<string, Uint8Array | object>) {
	const requests: string[] = [];
	const fetchFn = (async (url: string) => {
		requests.push(url);
		const f = files[url];
		if (!f) return new Response('', { status: 404 });
		return new Response(f instanceof Uint8Array ? (f as BodyInit) : JSON.stringify(f));
	}) as typeof fetch;
	return { fetchFn, requests };
}

// Munich: cell i = 1916, j = 419 → tile 38_8, ci = 16, cj = 19, k = 19·50 + 16 = 966
const MUNICH_K = 966;

describe('DataSource.lookup', () => {
	it('returns the history of the cell under a coordinate, fetching each tile once', async () => {
		const { fetchFn, requests } = server({
			'/d/points/index.json': {
				format: 'wx-points-v1',
				tile_deg: 5,
				years: [1950, 1951],
				tiles: ['38_8']
			},
			'/d/points/38_8.bin.gz': pointTile({ [MUNICH_K]: [0, 3, 0, 0, 0, 0] })
		});
		const ds = new DataSource('/d', manifest, fetchFn);
		const a = await ds.lookup(11.58, 48.14);
		expect(a.status).toBe('ok');
		expect(a.cell).toEqual({ i: 1916, j: 419 });
		expect(a.history!.depth(1950)).toEqual([0, 3, 0]);
		await ds.lookup(11.6, 48.1);
		expect(requests.filter((r) => r.endsWith('.bin.gz'))).toHaveLength(1);
	});

	it('does not fetch tiles the index does not list', async () => {
		const { fetchFn, requests } = server({
			'/d/points/index.json': {
				format: 'wx-points-v1',
				tile_deg: 5,
				years: [1950, 1951],
				tiles: []
			}
		});
		const r = await new DataSource('/d', manifest, fetchFn).lookup(-30, 40);
		expect(r.status).toBe('outside');
		expect(requests).toEqual(['/d/points/index.json']);
	});

	it('reports ocean, or moves to the nearest land cell within the radius when asked', async () => {
		const { fetchFn } = server({
			'/d/points/index.json': {
				format: 'wx-points-v1',
				tile_deg: 5,
				years: [1950, 1951],
				tiles: ['38_8']
			},
			// land two cells east of Munich's cell
			'/d/points/38_8.bin.gz': pointTile({ [MUNICH_K + 2]: [1, 1, 1, 0, 0, 0] })
		});
		const ds = new DataSource('/d', manifest, fetchFn);
		expect((await ds.lookup(11.58, 48.14)).status).toBe('ocean');
		const near = await ds.lookup(11.58, 48.14, { nearestLand: 2 });
		expect(near.status).toBe('ok');
		expect(near.moved).toBe(true);
		expect(near.cell).toEqual({ i: 1918, j: 419 });
	});
});
