/**
 * States and provinces (contract v1.6 proposal, format `wx-admin1-v1`, see docs/admin1.md).
 *
 * Three files, loaded lazily and only when the manifest lists them:
 *  - `admin1/index.json`        one row per region with the headline numbers (rankings, search, labels);
 *  - `admin1/boundaries.json`   simplified GeoJSON outlines, `feature.id` = row in the index;
 *  - `admin1/c/{country}.json`  everything for one country's regions, loaded when a region opens.
 *
 * Every value can be `null`; `flags` says why. Rows and fields are read by name, so additive
 * fields are fine.
 */

export type RegionFlag =
	'admin0' | 'low_res' | 'nearest_cell' | 'no_land' | 'all_glacier' | (string & {});

/** The `admin1` block of manifest.json. */
export interface Admin1Ref {
	available: boolean;
	format: string;
	index: string;
	boundaries: string;
	/** Path template with `{country}`. */
	country: string;
	data_version?: string;
	build_hash?: string;
}

export interface RegionRow {
	/** Row number in the index, and the `id` of the matching boundary feature. */
	num: number;
	/** ISO 3166-2 code or a fallback (`DE-BY`). */
	id: string;
	name: string;
	/** ISO 3166-1 alpha-3, the key of `regions.json` and of `countries`. */
	country: string;
	lon: number;
	lat: number;
	area_km2: number | null;
	flags: RegionFlag[];
	p_full: number | null;
	p_then: number | null;
	p_now: number | null;
	/** p_now − p_then, percentage points. */
	change: number | null;
	/** pp per decade over the full period. */
	trend: number | null;
	/** Mann–Kendall p of the regional series. */
	trend_p: number | null;
	/** Population-weighted p_now (places of 15,000+). */
	p_now_pop: number | null;
	p_then_raw: number | null;
	p_now_raw: number | null;
	/** Median projected probability per warming level ("1.5" → 21.0), calibrated threshold. */
	gwl: Record<string, number | null>;
}

export interface Admin1Index {
	format: string;
	contract: string;
	data_version: string;
	/** Threshold and definition the row values are for (the defaults). */
	threshold: string;
	definition: string;
	windows: { p_full: string; p_then: string; p_now: string };
	/** trend_p below this counts as significant. */
	trend_alpha: number;
	rows: RegionRow[];
	countries: Record<string, { name: string; regions: number }>;
	/** Plain-language text for every flag. */
	flags: Record<string, string>;
	attribution: string;
}

export interface RegionStats {
	/** Per window, in the order of the country file's `windows`. */
	p: (number | null)[];
	p_pop: (number | null)[];
	/** % of the area with p ≥ 50 %, per window. */
	share50: (number | null)[];
	p5: (number | null)[];
	p95: (number | null)[];
	change: number | null;
	change_pop: number | null;
	trend: number | null;
	trend_p: number | null;
	/** % of the area that was white, per year from `years[0]`. */
	series: (number | null)[];
}

export interface RegionProjection {
	baseline: number | null;
	/** Per warming level, in the order of the country file's `projections.gwls`. */
	p10: (number | null)[];
	p50: (number | null)[];
	p90: (number | null)[];
	change: (number | null)[];
	agree: boolean[];
	n_models: number;
	p50_pop: (number | null)[];
}

export interface RegionDetail {
	id: string;
	name: string;
	name_local: string;
	/** "State", "Province", … */
	type: string;
	flags: RegionFlag[];
	lon: number;
	lat: number;
	/** west, south, east, north */
	bbox: [number, number, number, number] | null;
	area_km2: number | null;
	land_km2: number | null;
	/** Land cells used, as a sum of cell fractions. */
	cells: number | null;
	glacier_pct: number | null;
	/** min, area-weighted mean, max (m). */
	elev_m: [number, number, number] | null;
	places: number;
	places_pop: number;
	/** threshold id → definition id → statistics. */
	stats: Record<string, Record<string, RegionStats>>;
	proj: RegionProjection | null;
}

export interface CountryProjections {
	threshold: string;
	definition: string;
	gwls: number[];
	baseline_window: string;
	models: string[];
}

export interface CountryFile {
	country: string;
	country_name: string;
	years: [number, number];
	thresholds: string[];
	definitions: string[];
	windows: string[];
	windows_then_now: string[];
	trend_alpha: number;
	spread_share_pct: number;
	projections: CountryProjections | null;
	regions: RegionDetail[];
}

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const str = (v: unknown, d = ''): string => (typeof v === 'string' ? v : d);
const strs = (v: unknown): string[] =>
	Array.isArray(v) ? v.filter((s) => typeof s === 'string') : [];
const nums = (v: unknown): (number | null)[] => (Array.isArray(v) ? v.map(num) : []);

export class Admin1Error extends Error {
	constructor(message: string) {
		super(`admin1: ${message}`);
		this.name = 'Admin1Error';
	}
}

/** The manifest's `admin1` block, or undefined unless it lists a usable dataset. */
export function parseAdmin1Ref(raw: unknown): Admin1Ref | undefined {
	if (!isObj(raw) || raw.available !== true) return undefined;
	if (typeof raw.index !== 'string' || typeof raw.boundaries !== 'string') return undefined;
	if (typeof raw.country !== 'string' || !raw.country.includes('{country}')) return undefined;
	return {
		available: true,
		format: str(raw.format, 'wx-admin1-v1'),
		index: raw.index,
		boundaries: raw.boundaries,
		country: raw.country,
		data_version: typeof raw.data_version === 'string' ? raw.data_version : undefined,
		build_hash: typeof raw.build_hash === 'string' ? raw.build_hash : undefined
	};
}

export function parseAdmin1Index(raw: unknown): Admin1Index {
	if (!isObj(raw)) throw new Admin1Error('index: not a JSON object');
	if (!Array.isArray(raw.fields) || !Array.isArray(raw.rows))
		throw new Admin1Error('index: "fields" and "rows" must be lists');
	const idx = new Map<string, number>((raw.fields as string[]).map((f, i) => [f, i]));
	for (const f of ['id', 'name', 'country', 'lon', 'lat'])
		if (!idx.has(f)) throw new Admin1Error(`index: required field "${f}" is missing`);
	const gwlFields = [...idx.keys()].filter((f) => /^p_gwl\d/.test(f));
	const rows: RegionRow[] = (raw.rows as unknown[][]).map((row, k) => {
		const get = (f: string): unknown => (idx.has(f) ? row[idx.get(f)!] : undefined);
		const gwl: Record<string, number | null> = {};
		for (const f of gwlFields) gwl[f.slice('p_gwl'.length)] = num(get(f));
		return {
			num: k,
			id: str(get('id')),
			name: str(get('name')),
			country: str(get('country')),
			lon: num(get('lon')) ?? 0,
			lat: num(get('lat')) ?? 0,
			area_km2: num(get('area_km2')),
			flags: strs(get('flags')),
			p_full: num(get('p_full')),
			p_then: num(get('p_then')),
			p_now: num(get('p_now')),
			change: num(get('change')),
			trend: num(get('trend')),
			trend_p: num(get('trend_p')),
			p_now_pop: num(get('p_now_pop')),
			p_then_raw: num(get('p_then_raw')),
			p_now_raw: num(get('p_now_raw')),
			gwl
		};
	});
	const w = isObj(raw.windows) ? raw.windows : {};
	const countries: Admin1Index['countries'] = {};
	if (isObj(raw.countries))
		for (const [k, v] of Object.entries(raw.countries))
			if (isObj(v)) countries[k] = { name: str(v.name, k), regions: num(v.regions) ?? 0 };
	const flags: Record<string, string> = {};
	if (isObj(raw.flags))
		for (const [k, v] of Object.entries(raw.flags)) if (typeof v === 'string') flags[k] = v;
	return {
		format: str(raw.format),
		contract: str(raw.contract),
		data_version: str(raw.data_version),
		threshold: str(raw.threshold, 'calibrated'),
		definition: str(raw.definition, 'christmas_day'),
		windows: {
			p_full: str(w.p_full, '1950_2025'),
			p_then: str(w.p_then, '1961_1990'),
			p_now: str(w.p_now, '1996_2025')
		},
		trend_alpha: num(raw.trend_alpha) ?? 0.1,
		rows,
		countries,
		flags,
		attribution: str(raw.attribution)
	};
}

function parseStats(raw: unknown): RegionStats | null {
	if (!isObj(raw)) return null;
	return {
		p: nums(raw.p),
		p_pop: nums(raw.p_pop),
		share50: nums(raw.share50),
		p5: nums(raw.p5),
		p95: nums(raw.p95),
		change: num(raw.change),
		change_pop: num(raw.change_pop),
		trend: num(raw.trend),
		trend_p: num(raw.trend_p),
		series: nums(raw.series)
	};
}

function parseProjection(raw: unknown): RegionProjection | null {
	if (!isObj(raw)) return null;
	return {
		baseline: num(raw.baseline),
		p10: nums(raw.p10),
		p50: nums(raw.p50),
		p90: nums(raw.p90),
		change: nums(raw.change),
		agree: Array.isArray(raw.agree) ? raw.agree.map((a) => a === true) : [],
		n_models: num(raw.n_models) ?? 0,
		p50_pop: nums(raw.p50_pop)
	};
}

function parseRegionDetail(raw: unknown): RegionDetail | null {
	if (!isObj(raw) || typeof raw.id !== 'string') return null;
	const stats: RegionDetail['stats'] = {};
	if (isObj(raw.stats))
		for (const [th, defs] of Object.entries(raw.stats)) {
			if (!isObj(defs)) continue;
			stats[th] = {};
			for (const [d, s] of Object.entries(defs)) {
				const parsed = parseStats(s);
				if (parsed) stats[th][d] = parsed;
			}
		}
	const bbox = Array.isArray(raw.bbox) && raw.bbox.length === 4 ? raw.bbox.map(num) : null;
	const elev = Array.isArray(raw.elev_m) && raw.elev_m.length === 3 ? raw.elev_m.map(num) : null;
	return {
		id: raw.id,
		name: str(raw.name),
		name_local: str(raw.name_local),
		type: str(raw.type),
		flags: strs(raw.flags),
		lon: num(raw.lon) ?? 0,
		lat: num(raw.lat) ?? 0,
		bbox: bbox && bbox.every((v) => v !== null) ? (bbox as RegionDetail['bbox']) : null,
		area_km2: num(raw.area_km2),
		land_km2: num(raw.land_km2),
		cells: num(raw.cells),
		glacier_pct: num(raw.glacier_pct),
		elev_m: elev && elev.every((v) => v !== null) ? (elev as RegionDetail['elev_m']) : null,
		places: num(raw.places) ?? 0,
		places_pop: num(raw.places_pop) ?? 0,
		stats,
		proj: parseProjection(raw.proj)
	};
}

export function parseCountryFile(raw: unknown): CountryFile {
	if (!isObj(raw)) throw new Admin1Error('country file: not a JSON object');
	if (!Array.isArray(raw.regions)) throw new Admin1Error('country file: "regions" must be a list');
	const years = Array.isArray(raw.years) && raw.years.length === 2 ? raw.years.map(num) : [];
	if (years.length !== 2 || years.some((y) => y === null))
		throw new Admin1Error('country file: "years" must be [first, last]');
	const p = isObj(raw.projections) ? raw.projections : null;
	const gwls = p ? nums(p.gwls).filter((g): g is number => g !== null) : [];
	return {
		country: str(raw.country),
		country_name: str(raw.country_name),
		years: years as [number, number],
		thresholds: strs(raw.thresholds),
		definitions: strs(raw.definitions),
		windows: strs(raw.windows),
		windows_then_now: strs(raw.windows_then_now),
		trend_alpha: num(raw.trend_alpha) ?? 0.1,
		spread_share_pct: num(raw.spread_share_pct) ?? 50,
		projections:
			p && gwls.length
				? {
						threshold: str(p.threshold, 'calibrated'),
						definition: str(p.definition, 'christmas_day'),
						gwls,
						baseline_window: str(p.baseline_window, '1996_2025'),
						models: strs(p.models)
					}
				: null,
		regions: (raw.regions as unknown[])
			.map(parseRegionDetail)
			.filter((r): r is RegionDetail => r !== null)
	};
}

/** Outlines as GeoJSON; only checks the shape MapLibre needs. */
export interface BoundaryCollection {
	type: 'FeatureCollection';
	features: { id: number; properties: { id: string; country: string }; geometry: unknown }[];
}

export function parseBoundaries(raw: unknown): BoundaryCollection {
	if (!isObj(raw) || raw.type !== 'FeatureCollection' || !Array.isArray(raw.features))
		throw new Admin1Error('boundaries: not a GeoJSON FeatureCollection');
	return raw as unknown as BoundaryCollection;
}

/** `admin1/c/{country}.json` for a country key; the key is validated, since it ends up in a URL. */
export function countryPath(ref: Admin1Ref, country: string): string {
	if (!/^[A-Za-z0-9_-]{1,12}$/.test(country)) throw new Admin1Error(`bad country key "${country}"`);
	return ref.country.replace('{country}', country);
}

async function getJson(url: string, fetchFn: typeof fetch): Promise<unknown> {
	const res = await fetchFn(url);
	if (!res.ok) throw new Admin1Error(`could not load ${url} (HTTP ${res.status})`);
	return res.json();
}

export async function loadAdmin1Index(
	dataBase: string,
	ref: Admin1Ref,
	fetchFn: typeof fetch = fetch
): Promise<Admin1Index> {
	return parseAdmin1Index(await getJson(`${dataBase}/${ref.index}`, fetchFn));
}

export async function loadBoundaries(
	dataBase: string,
	ref: Admin1Ref,
	fetchFn: typeof fetch = fetch
): Promise<BoundaryCollection> {
	return parseBoundaries(await getJson(`${dataBase}/${ref.boundaries}`, fetchFn));
}

export async function loadCountry(
	dataBase: string,
	ref: Admin1Ref,
	country: string,
	fetchFn: typeof fetch = fetch
): Promise<CountryFile> {
	return parseCountryFile(await getJson(`${dataBase}/${countryPath(ref, country)}`, fetchFn));
}

/** Rows by region id (`DE-BY`). */
export function rowsById(rows: RegionRow[]): Map<string, RegionRow> {
	return new Map(rows.map((r) => [r.id, r]));
}
