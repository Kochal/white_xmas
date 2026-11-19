/** `regions.json` (contract § regions.json): per-country statistics. */

export interface Region {
	iso_a3: string;
	name: string;
	p_then: number | null;
	p_now: number | null;
	change: number | null;
}

const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);

export function parseRegions(raw: {
	fields?: unknown;
	rows?: unknown;
	[k: string]: unknown;
}): Region[] {
	if (!Array.isArray(raw.fields) || !Array.isArray(raw.rows))
		throw new Error('regions.json: "fields" and "rows" must be lists');
	const idx = new Map<string, number>((raw.fields as string[]).map((f, i) => [f, i]));
	const get = (row: unknown[], f: string) => (idx.has(f) ? row[idx.get(f)!] : undefined);
	return (raw.rows as unknown[][]).map((row) => ({
		iso_a3: String(get(row, 'iso_a3') ?? ''),
		name: String(get(row, 'name') ?? ''),
		p_then: num(get(row, 'p_then')),
		p_now: num(get(row, 'p_now')),
		change: num(get(row, 'change'))
	}));
}

export async function loadRegions(
	dataBase: string,
	path: string,
	fetchFn: typeof fetch = fetch
): Promise<Region[]> {
	const url = `${dataBase}/${path}`;
	const res = await fetchFn(url);
	if (!res.ok) throw new Error(`could not load ${url} (HTTP ${res.status})`);
	return parseRegions(await res.json());
}
