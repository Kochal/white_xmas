/**
 * Search over states and provinces (name, plus the country's name as extra words), so
 * "bavaria", "tyr" or "ontario canada" find regions next to the place search's results.
 * The score scale matches `search.ts` (exact 100, prefix ≈ 80, word prefix 60, substring 45),
 * so both result lists can be merged.
 */
import type { RegionRow } from './admin1';
import { fold, type SearchHit } from './search';

export interface RegionHit {
	row: RegionRow;
	score: number;
	countryName: string;
}

interface Entry {
	row: RegionRow;
	name: string;
	/** " word word" with separators as spaces, for word-prefix tests */
	spaced: string;
	country: string;
	areaBonus: number;
}

const entries = new WeakMap<RegionRow[], Entry[]>();

const spaced = (s: string) => ' ' + s.replace(/[-'’.,]/g, ' ');

function build(rows: RegionRow[], countries: Record<string, { name: string }>): Entry[] {
	return rows.map((row) => {
		const name = fold(row.name);
		return {
			row,
			name,
			spaced: spaced(name),
			country: spaced(fold(countries[row.country]?.name ?? '')),
			// size as a gentle tie-breaker, at most +6
			areaBonus: Math.min(6, Math.max(0, Math.log10(Math.max(1, row.area_km2 ?? 1)) - 1.5))
		};
	});
}

const wordStarts = (hay: string, token: string) => hay.includes(' ' + token);

export function searchRegions(
	rows: RegionRow[],
	countries: Record<string, { name: string }>,
	query: string,
	limit = 4
): RegionHit[] {
	const q = fold(query);
	if (q.length < 2) return [];
	let list = entries.get(rows);
	if (!list) {
		list = build(rows, countries);
		entries.set(rows, list);
	}
	const tokens = q.split(' ');
	const hits: RegionHit[] = [];
	for (const e of list) {
		let score = 0;
		if (e.name === q) score = 100;
		else if (e.name.startsWith(q)) score = 80 - Math.min(10, e.name.length - q.length) * 0.5;
		else if (wordStarts(e.spaced, q)) score = 60;
		else if (q.length >= 3 && e.name.includes(q)) score = 45;
		else if (tokens.length > 1) {
			// "ontario canada": every word starts a word of the region or of its country
			const hay = e.spaced + e.country;
			if (tokens.every((t) => wordStarts(hay, t))) score = 50;
		}
		if (score > 0)
			hits.push({
				row: e.row,
				score: score + e.areaBonus,
				countryName: countries[e.row.country]?.name ?? ''
			});
	}
	hits.sort((a, b) => b.score - a.score || a.row.name.localeCompare(b.row.name, 'en'));
	return hits.slice(0, limit);
}

export type MergedHit =
	| { kind: 'place'; hit: SearchHit; score: number }
	| { kind: 'region'; hit: RegionHit; score: number };

/**
 * One result list for the search box: by score, but with room for at least `minRegions`
 * regions when there are that many matches, so a state isn't hidden behind eight
 * villages of the same name.
 */
export function mergeHits(
	places: SearchHit[],
	regions: RegionHit[],
	limit: number,
	minRegions = 2
): MergedHit[] {
	const all: MergedHit[] = [
		...places.map((hit) => ({ kind: 'place' as const, hit, score: hit.score })),
		...regions.map((hit) => ({ kind: 'region' as const, hit, score: hit.score }))
	].sort((a, b) => b.score - a.score);
	const top = all.slice(0, limit);
	const have = top.filter((h) => h.kind === 'region').length;
	const want = Math.min(minRegions, regions.length);
	if (have >= want) return top;
	// swap the weakest places for the best regions that missed the cut
	const missing = all
		.slice(limit)
		.filter((h) => h.kind === 'region')
		.slice(0, want - have);
	const keep = top.slice(0, limit - missing.length);
	return [...keep, ...missing].sort((a, b) => b.score - a.score);
}
