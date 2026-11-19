/**
 * `places.json` (contract § places.json, v1.1): searchable places with precomputed
 * values for the default definition. Rows are read by field name, so the optional
 * `alt` field (v1.1) and any future additive fields are handled.
 */

export interface Place {
	name: string;
	ascii: string;
	country: string;
	admin1: string;
	/** Alternate names (local-language names, exonyms); empty when absent. */
	alt: string[];
	lat: number;
	lon: number;
	pop: number;
	p_full: number | null;
	p_then: number | null;
	p_now: number | null;
	/** pp per decade over the full window; null when not significant at p < 0.1. */
	trend: number | null;
}

export interface PlacesMeta {
	definition: string;
	windows: { p_full: string; p_then: string; p_now: string };
}

const REQUIRED = ['name', 'lat', 'lon'] as const;

type RawPlaces = { fields?: unknown; rows?: unknown; [k: string]: unknown };

const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const str = (v: unknown): string => (typeof v === 'string' ? v : '');

export function parsePlaces(raw: RawPlaces): Place[] {
	if (!Array.isArray(raw.fields) || !Array.isArray(raw.rows))
		throw new Error('places.json: "fields" and "rows" must be lists');
	const idx = new Map<string, number>((raw.fields as string[]).map((f, i) => [f, i]));
	for (const f of REQUIRED)
		if (!idx.has(f)) throw new Error(`places.json: required field "${f}" is missing`);
	const get = (row: unknown[], f: string) => (idx.has(f) ? row[idx.get(f)!] : undefined);
	return (raw.rows as unknown[][]).map((row) => {
		const name = str(get(row, 'name'));
		const alt = str(get(row, 'alt'))
			.split('|')
			.map((s) => s.trim())
			.filter(Boolean);
		return {
			name,
			ascii: str(get(row, 'ascii')) || name,
			country: str(get(row, 'country')),
			admin1: str(get(row, 'admin1')),
			alt,
			lat: num(get(row, 'lat')) ?? 0,
			lon: num(get(row, 'lon')) ?? 0,
			pop: num(get(row, 'pop')) ?? 0,
			p_full: num(get(row, 'p_full')),
			p_then: num(get(row, 'p_then')),
			p_now: num(get(row, 'p_now')),
			trend: num(get(row, 'trend'))
		};
	});
}

export function parsePlacesMeta(raw: Partial<PlacesMeta>): PlacesMeta {
	return {
		definition: raw.definition ?? 'christmas_day',
		windows: raw.windows ?? { p_full: '1950_2025', p_then: '1961_1990', p_now: '1996_2025' }
	};
}

export async function fetchPlacesFile(
	dataBase: string,
	path: string,
	fetchFn: typeof fetch = fetch
): Promise<{ places: Place[]; meta: PlacesMeta }> {
	const url = `${dataBase}/${path}`;
	const res = await fetchFn(url);
	if (!res.ok) throw new Error(`could not load ${url} (HTTP ${res.status})`);
	const raw = await res.json();
	return { places: parsePlaces(raw), meta: parsePlacesMeta(raw) };
}

export async function loadPlaces(
	dataBase: string,
	path: string,
	fetchFn: typeof fetch = fetch
): Promise<Place[]> {
	return (await fetchPlacesFile(dataBase, path, fetchFn)).places;
}

// Search lives in search.ts; re-exported here for convenience.
export { fold, PlaceSearcher, searchPlaces, warmSearch, type SearchHit } from './search';
