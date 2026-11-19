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
	/** The name that matched: the English name, or the local one ("Bayern"). */
	matched: string;
	countryName: string;
}

interface Entry {
	row: RegionRow;
	/** folded English and local names, deduplicated */
	names: string[];
	originals: string[];
	/** " word word" with separators as spaces, for word-prefix tests */
	spaced: string[];
	country: string;
	areaBonus: number;
}

const entries = new WeakMap<RegionRow[], Entry[]>();

const spaced = (s: string) => ' ' + s.replace(/[-'’.,]/g, ' ');

function build(rows: RegionRow[], countries: Record<string, { name: string }>): Entry[] {
	return rows.map((row) => {
		const names: string[] = [];
		const originals: string[] = [];
		for (const original of [row.name, row.name_local]) {
			const f = fold(original);
			if (f && !names.includes(f)) {
				names.push(f);
				originals.push(original);
			}
		}
		return {
			row,
			names,
			originals,
			spaced: names.map(spaced),
			country: spaced(fold(countries[row.country]?.name ?? '')),
			// size as a gentle tie-breaker, at most +6
			areaBonus: Math.min(6, Math.max(0, Math.log10(Math.max(1, row.area_km2 ?? 1)) - 1.5))
		};
	});
}

const wordStarts = (hay: string, token: string) => hay.includes(' ' + token);

/** Same scale as the place search: exact 100, prefix ≈ 80, word prefix 60, substring 45. */
function scoreName(name: string, sp: string, q: string): number {
	if (name === q) return 100;
	if (name.startsWith(q)) return 80 - Math.min(10, name.length - q.length) * 0.5;
	if (wordStarts(sp, q)) return 60;
	if (q.length >= 3 && name.includes(q)) return 45;
	return 0;
}

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
		let matched = e.originals[0] ?? e.row.name;
		for (let t = 0; t < e.names.length; t++) {
			const sc = scoreName(e.names[t], e.spaced[t], q);
			if (sc > score) {
				score = sc;
				matched = e.originals[t];
			}
		}
		if (score === 0 && tokens.length > 1) {
			// "ontario canada": every word starts a word of a name or of the country
			for (let t = 0; t < e.names.length && score === 0; t++) {
				const hay = e.spaced[t] + e.country;
				if (tokens.every((w) => wordStarts(hay, w))) {
					score = 50;
					matched = e.originals[t];
				}
			}
		}
		if (score > 0)
			hits.push({
				row: e.row,
				score: score + e.areaBonus,
				matched,
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
