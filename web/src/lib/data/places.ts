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

// --- search ---------------------------------------------------------------------------------

const SPECIAL: Record<string, string> = {
	ł: 'l',
	ø: 'o',
	đ: 'd',
	ß: 'ss',
	æ: 'ae',
	œ: 'oe',
	ı: 'i'
};

/** Lower-case, strip diacritics, collapse whitespace. */
export function fold(s: string): string {
	return s
		.toLowerCase()
		.normalize('NFD')
		.replace(/[̀-ͯ]/g, '')
		.replace(/[łøđßæœı]/g, (c) => SPECIAL[c])
		.replace(/\s+/g, ' ')
		.trim();
}

interface Indexed {
	place: Place;
	names: { folded: string; original: string }[];
	country: string;
}

const indexCache = new WeakMap<Place[], Indexed[]>();

function index(places: Place[]): Indexed[] {
	let idx = indexCache.get(places);
	if (!idx) {
		idx = places.map((place) => {
			const originals = [place.name, place.ascii, ...place.alt];
			const seen = new Set<string>();
			const names = [];
			for (const original of originals) {
				const folded = fold(original);
				if (folded && !seen.has(folded)) {
					seen.add(folded);
					names.push({ folded, original });
				}
			}
			return { place, names, country: place.country.toLowerCase() };
		});
		indexCache.set(places, idx);
	}
	return idx;
}

/** Damerau–Levenshtein (optimal string alignment) distance, capped for speed. */
function editDistance(a: string, b: string, max: number): number {
	if (Math.abs(a.length - b.length) > max) return max + 1;
	const d: number[][] = Array.from({ length: a.length + 1 }, (_, i) => [i]);
	for (let j = 1; j <= b.length; j++) d[0][j] = j;
	for (let i = 1; i <= a.length; i++) {
		let rowMin = Infinity;
		for (let j = 1; j <= b.length; j++) {
			const cost = a[i - 1] === b[j - 1] ? 0 : 1;
			d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost);
			if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1])
				d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
			rowMin = Math.min(rowMin, d[i][j]);
		}
		if (rowMin > max) return max + 1;
	}
	return d[a.length][b.length];
}

function scoreName(name: string, q: string): number {
	if (name === q) return 100;
	if (name.startsWith(q)) return 80 - Math.min(10, name.length - q.length) * 0.5;
	if (name.split(/[\s\-']/).some((w) => w.startsWith(q))) return 60;
	if (q.length >= 3 && name.includes(q)) return 45;
	if (q.length >= 4) {
		const max = q.length >= 7 ? 2 : 1;
		const dist = editDistance(q, name.slice(0, q.length + 1), max);
		const distFull = editDistance(q, name, max);
		const best = Math.min(dist, distFull);
		if (best <= max) return 35 - best * 8;
	}
	return 0;
}

export interface SearchHit {
	place: Place;
	score: number;
	/** The name that matched (may be an alternate name). */
	matched: string;
}

/**
 * Client-side fuzzy search over name, ascii name and alternate names. A trailing
 * ", XX" (or " XX") country code boosts places in that country. Ties go to bigger places.
 */
export function searchPlaces(places: Place[], query: string, limit = 8): SearchHit[] {
	let q = fold(query);
	if (!q) return [];
	let country: string | null = null;
	const m = /^(.*?)[,\s]+([a-z]{2})$/.exec(q);
	if (m && m[1].length >= 2) {
		country = m[2];
		q = m[1].trim();
	}
	const hits: SearchHit[] = [];
	for (const entry of index(places)) {
		let best = 0;
		let matched = entry.place.name;
		for (const n of entry.names) {
			const s = scoreName(n.folded, q);
			if (s > best) {
				best = s;
				matched = n.original;
			}
		}
		if (best <= 0) continue;
		if (country && entry.country === country) best += 30;
		// population as a gentle tie-breaker (log scale, at most +8)
		const score = best + Math.min(8, Math.log10(Math.max(1, entry.place.pop)) - 4);
		hits.push({ place: entry.place, score, matched });
	}
	hits.sort((a, b) => b.score - a.score);
	return hits.slice(0, limit);
}
