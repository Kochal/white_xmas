/**
 * Point tiles: per-cell yearly snow history (`wx-points-v1`) and projections
 * (`wx-proj-v1`), web data contract § Point tiles.
 */

export const NODATA = 255;
/** Stored value meaning "at least 254 cm". */
export const CAPPED = 254;

export class PointTileError extends Error {
	constructor(message: string) {
		super(message);
		this.name = 'PointTileError';
	}
}

export interface PointTile {
	firstYear: number;
	nYears: number;
	nx: number;
	ny: number;
	nDays: number;
	/** uint8[ny][nx][nYears][nDays] */
	body: Uint8Array;
	/** bit k = cell k (row-major) is in the glacier mask */
	glacier: Uint8Array;
}

export interface CellHistory {
	years: number[];
	firstYear: number;
	nDays: number;
	/** uint8[nYears][nDays], whole cm, 254 = ≥ 254, 255 = nodata */
	values: Uint8Array;
	ocean: boolean;
	glacier: boolean;
	/** Depth in cm for Dec 24, 25, 26 of a year; null where there is no data. */
	depth(year: number): (number | null)[];
	/** True when any day of the year is stored as "≥ 254 cm". */
	capped(year: number): boolean;
}

const HEADER = 16;

function magic(bytes: Uint8Array): string {
	return String.fromCharCode(bytes[0], bytes[1], bytes[2], bytes[3]);
}

export function decodePointTile(bytes: Uint8Array): PointTile {
	if (bytes.length < HEADER || magic(bytes) !== 'WXP1')
		throw new PointTileError('not a wx-points-v1 tile (expected magic "WXP1")');
	const v = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
	const firstYear = v.getUint16(4, true);
	const nYears = v.getUint16(6, true);
	const nx = v.getUint16(8, true);
	const ny = v.getUint16(10, true);
	const nDays = v.getUint8(12);
	const bodyLen = nx * ny * nYears * nDays;
	const maskLen = Math.ceil((nx * ny) / 8);
	if (bytes.length < HEADER + bodyLen + maskLen)
		throw new PointTileError(
			`point tile truncated: ${bytes.length} bytes, expected ${HEADER + bodyLen + maskLen}`
		);
	return {
		firstYear,
		nYears,
		nx,
		ny,
		nDays,
		body: bytes.subarray(HEADER, HEADER + bodyLen),
		glacier: bytes.subarray(HEADER + bodyLen, HEADER + bodyLen + maskLen)
	};
}

/** History of the cell at column `ci`, row `cj` (from the tile's north-west corner). */
export function cellHistory(tile: PointTile, ci: number, cj: number): CellHistory {
	const k = cj * tile.nx + ci;
	const stride = tile.nYears * tile.nDays;
	const values = tile.body.subarray(k * stride, (k + 1) * stride);
	const ocean = values.every((x) => x === NODATA);
	const glacier = ((tile.glacier[k >> 3] >> (k & 7)) & 1) === 1;
	const years = Array.from({ length: tile.nYears }, (_, y) => tile.firstYear + y);
	const slice = (year: number) => {
		const y = year - tile.firstYear;
		if (y < 0 || y >= tile.nYears) return null;
		return values.subarray(y * tile.nDays, (y + 1) * tile.nDays);
	};
	return {
		years,
		firstYear: tile.firstYear,
		nDays: tile.nDays,
		values,
		ocean,
		glacier,
		depth(year) {
			const s = slice(year);
			if (!s) return Array.from({ length: tile.nDays }, () => null);
			return Array.from(s, (x) => (x === NODATA ? null : x));
		},
		capped(year) {
			const s = slice(year);
			return !!s && s.some((x) => x === CAPPED);
		}
	};
}

/** Gunzips when the bytes start with the gzip magic; returns them unchanged otherwise. */
export async function maybeGunzip(bytes: Uint8Array): Promise<Uint8Array> {
	if (bytes.length < 2 || bytes[0] !== 0x1f || bytes[1] !== 0x8b) return bytes;
	const stream = new Blob([bytes as BlobPart])
		.stream()
		.pipeThrough(new DecompressionStream('gzip'));
	return new Uint8Array(await new Response(stream).arrayBuffer());
}

async function fetchBytes(url: string, fetchFn: typeof fetch): Promise<Uint8Array> {
	const res = await fetchFn(url);
	if (!res.ok) throw new PointTileError(`could not load ${url} (HTTP ${res.status})`);
	return maybeGunzip(new Uint8Array(await res.arrayBuffer()));
}

export async function fetchPointTile(
	dataBase: string,
	key: string,
	fetchFn: typeof fetch = fetch
): Promise<PointTile> {
	return decodePointTile(await fetchBytes(`${dataBase}/points/${key}.bin.gz`, fetchFn));
}

/** `points/index.json` */
export interface PointIndex {
	format: string;
	tile_deg: number;
	years: [number, number];
	tiles: string[];
}

export async function fetchPointIndex(
	dataBase: string,
	indexPath: string,
	fetchFn: typeof fetch = fetch
): Promise<PointIndex> {
	const url = `${dataBase}/${indexPath}`;
	const res = await fetchFn(url);
	if (!res.ok) throw new PointTileError(`could not load ${url} (HTTP ${res.status})`);
	const raw = (await res.json()) as PointIndex;
	if (!Array.isArray(raw.tiles)) throw new PointTileError(`${url}: "tiles" must be a list`);
	return raw;
}

// --- projections (wx-proj-v1) -------------------------------------------------------------

export interface ProjTile {
	nLevels: number;
	nStats: number;
	nx: number;
	ny: number;
	/** uint8[ny][nx][nLevels][nStats] */
	body: Uint8Array;
	/** one bitmask per level */
	agreement: Uint8Array[];
}

export interface ProjectedProbability {
	p10: number;
	median: number;
	p90: number;
	/** At least two thirds of the models agree on the sign of the change. */
	agree: boolean;
}

export function decodeProjTile(bytes: Uint8Array): ProjTile {
	if (bytes.length < HEADER || magic(bytes) !== 'WXQ1')
		throw new PointTileError('not a wx-proj-v1 tile (expected magic "WXQ1")');
	const v = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
	const nLevels = v.getUint8(4);
	const nStats = v.getUint8(5);
	const nx = v.getUint16(6, true);
	const ny = v.getUint16(8, true);
	const bodyLen = nx * ny * nLevels * nStats;
	const maskLen = Math.ceil((nx * ny) / 8);
	if (bytes.length < HEADER + bodyLen + nLevels * maskLen)
		throw new PointTileError('projection tile truncated');
	const agreement = Array.from({ length: nLevels }, (_, l) => {
		const o = HEADER + bodyLen + l * maskLen;
		return bytes.subarray(o, o + maskLen);
	});
	return { nLevels, nStats, nx, ny, body: bytes.subarray(HEADER, HEADER + bodyLen), agreement };
}

/** Projected probabilities per warming level (manifest order), or null for an ocean/nodata cell. */
export function cellProjection(
	tile: ProjTile,
	ci: number,
	cj: number
): ProjectedProbability[] | null {
	const k = cj * tile.nx + ci;
	const out: ProjectedProbability[] = [];
	for (let l = 0; l < tile.nLevels; l++) {
		const o = (k * tile.nLevels + l) * tile.nStats;
		const [p10, median, p90] = tile.body.subarray(o, o + 3);
		if (median === NODATA) return null;
		out.push({ p10, median, p90, agree: ((tile.agreement[l][k >> 3] >> (k & 7)) & 1) === 1 });
	}
	return out;
}

export async function fetchProjTile(
	dataBase: string,
	pathTemplate: string,
	tx: number,
	ty: number,
	fetchFn: typeof fetch = fetch
): Promise<ProjTile> {
	const rel = pathTemplate.replace('{tx}', String(tx)).replace('{ty}', String(ty));
	return decodeProjTile(await fetchBytes(`${dataBase}/${rel}`, fetchFn));
}
