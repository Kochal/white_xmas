import { describe, expect, it } from 'vitest';
import {
	PointTileError,
	cellHistory,
	cellProjection,
	decodePointTile,
	decodeProjTile,
	fetchPointTile,
	maybeGunzip
} from './points';

/**
 * A 2 × 2-cell, 3-year, 3-day wx-points-v1 tile built byte by byte from the contract:
 * header (16) · body uint8[ny][nx][years][days] · glacier bitmask (ceil(4/8) = 1 byte).
 */
function tinyPointTile(): Uint8Array {
	// prettier-ignore
	return new Uint8Array([
		0x57, 0x58, 0x50, 0x31, // "WXP1"
		0x9e, 0x07,             // first_year = 1950 (0x079e), little-endian
		0x03, 0x00,             // n_years = 3
		0x02, 0x00,             // n_cells_x = 2
		0x02, 0x00,             // n_cells_y = 2
		0x03,                   // n_days = 3
		0x00, 0x00, 0x00,       // reserved
		// cell (row 0, col 0): NW
		0, 5, 7,     12, 0, 0,     255, 255, 255,
		// cell (row 0, col 1): NE, all ocean
		255, 255, 255, 255, 255, 255, 255, 255, 255,
		// cell (row 1, col 0): SW
		1, 1, 1,     254, 254, 254, 0, 0, 0,
		// cell (row 1, col 1): SE, glacier
		200, 201, 202, 203, 204, 205, 206, 207, 208,
		0b00001000              // glacier bit 3 = cell (1, 1)
	]);
}

async function gzip(bytes: Uint8Array): Promise<Uint8Array> {
	const stream = new Blob([bytes as BlobPart]).stream().pipeThrough(new CompressionStream('gzip'));
	return new Uint8Array(await new Response(stream).arrayBuffer());
}

describe('decodePointTile (wx-points-v1)', () => {
	it('reads the header', () => {
		const t = decodePointTile(tinyPointTile());
		expect(t).toMatchObject({ firstYear: 1950, nYears: 3, nx: 2, ny: 2, nDays: 3 });
	});

	it('returns each cell history in year order with the days Dec 24, 25, 26', () => {
		const t = decodePointTile(tinyPointTile());
		const nw = cellHistory(t, 0, 0);
		expect(nw.ocean).toBe(false);
		expect(nw.glacier).toBe(false);
		expect(nw.years).toEqual([1950, 1951, 1952]);
		expect(nw.depth(1950)).toEqual([0, 5, 7]);
		expect(nw.depth(1951)).toEqual([12, 0, 0]);
		expect(nw.depth(1952)).toEqual([null, null, null]);
	});

	it('flags all-nodata cells as ocean and reads the glacier bit', () => {
		const t = decodePointTile(tinyPointTile());
		expect(cellHistory(t, 1, 0).ocean).toBe(true);
		const se = cellHistory(t, 1, 1);
		expect(se.glacier).toBe(true);
		expect(se.depth(1952)).toEqual([206, 207, 208]);
	});

	it('keeps 254 as the "at least 254 cm" value', () => {
		const sw = cellHistory(decodePointTile(tinyPointTile()), 0, 1);
		expect(sw.depth(1951)).toEqual([254, 254, 254]);
		expect(sw.capped(1951)).toBe(true);
		expect(sw.capped(1950)).toBe(false);
	});

	it('returns null depths for years outside the tile', () => {
		const nw = cellHistory(decodePointTile(tinyPointTile()), 0, 0);
		expect(nw.depth(1949)).toEqual([null, null, null]);
	});

	it('rejects a wrong magic and a truncated body', () => {
		const bad = tinyPointTile();
		bad[3] = 0x32;
		expect(() => decodePointTile(bad)).toThrow(PointTileError);
		expect(() => decodePointTile(tinyPointTile().subarray(0, 30))).toThrow(/truncated/);
	});
});

describe('maybeGunzip', () => {
	it('decompresses gzip and passes raw tiles through (servers may decode .gz already)', async () => {
		const raw = tinyPointTile();
		expect(await maybeGunzip(await gzip(raw))).toEqual(raw);
		expect(await maybeGunzip(raw)).toEqual(raw);
	});
});

describe('fetchPointTile', () => {
	it('fetches points/<tx>_<ty>.bin.gz and decodes it', async () => {
		const body = await gzip(tinyPointTile());
		const seen: string[] = [];
		const fetchFn = (async (url: string) => {
			seen.push(url);
			return new Response(body as BodyInit);
		}) as typeof fetch;
		const t = await fetchPointTile('/data', '38_8', fetchFn);
		expect(seen).toEqual(['/data/points/38_8.bin.gz']);
		expect(t.nYears).toBe(3);
	});

	it('fails with the HTTP status for a missing tile', async () => {
		const fetchFn = (async () => new Response('', { status: 404 })) as unknown as typeof fetch;
		await expect(fetchPointTile('/data', '1_1', fetchFn)).rejects.toThrow(/404/);
	});
});

/** wx-proj-v1: 2 × 1 cells, 2 warming levels, 3 stats (p10, median, p90), agreement bitmask per level. */
function tinyProjTile(): Uint8Array {
	// prettier-ignore
	return new Uint8Array([
		0x57, 0x58, 0x51, 0x31, // "WXQ1"
		0x02,                   // n_levels
		0x03,                   // n_stats
		0x02, 0x00,             // n_cells_x = 2
		0x01, 0x00,             // n_cells_y = 1
		0, 0, 0, 0, 0, 0,       // reserved
		// cell 0: level 0 then level 1
		20, 30, 40,   10, 18, 25,
		// cell 1: ocean
		255, 255, 255, 255, 255, 255,
		0b00000001,             // level 0: cell 0 agrees
		0b00000000              // level 1: nobody agrees
	]);
}

describe('decodeProjTile (wx-proj-v1)', () => {
	it('reads p10, median and p90 per warming level and the agreement flags', () => {
		const t = decodeProjTile(tinyProjTile());
		expect(t).toMatchObject({ nLevels: 2, nStats: 3, nx: 2, ny: 1 });
		expect(cellProjection(t, 0, 0)).toEqual([
			{ p10: 20, median: 30, p90: 40, agree: true },
			{ p10: 10, median: 18, p90: 25, agree: false }
		]);
		expect(cellProjection(t, 1, 0)).toBeNull();
	});

	it('rejects a points tile passed as a projection tile', () => {
		expect(() => decodeProjTile(tinyPointTile())).toThrow(/WXQ1/);
	});
});
