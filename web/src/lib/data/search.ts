/**
 * Client-side place search over name, ascii name and alternate names (contract v1.1).
 * Built for the real list (~34k GeoNames places, up to 7 names each) on a phone:
 *  - cheap passes first (exact, prefix, word prefix, substring); the fuzzy pass runs only
 *    when they find fewer than `limit` places;
 *  - the fuzzy pass prunes by length and first letters, and reuses one DP buffer;
 *  - when the query grows by typing, only the previous candidates are rescanned.
 */
import type { Place } from './places';

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

interface Entry {
	place: Place;
	/** folded names, deduplicated */
	names: string[];
	/** same names with word separators as spaces and a leading space, for word-prefix tests */
	spaced: string[];
	originals: string[];
	country: string;
	popBonus: number;
}

export interface SearchHit {
	place: Place;
	score: number;
	/** The name that matched (may be an alternate name). */
	matched: string;
}

function buildEntries(places: Place[]): Entry[] {
	return places.map((place) => {
		const names: string[] = [];
		const originals: string[] = [];
		for (const original of [place.name, place.ascii, ...place.alt]) {
			const f = fold(original);
			if (f && !names.includes(f)) {
				names.push(f);
				originals.push(original);
			}
		}
		return {
			place,
			names,
			spaced: names.map((n) => ' ' + n.replace(/[-'’]/g, ' ')),
			originals,
			country: place.country.toLowerCase(),
			// population as a gentle tie-breaker (log scale, at most +8)
			popBonus: Math.min(8, Math.log10(Math.max(1, place.pop)) - 4)
		};
	});
}

/** Fuzzy tolerance: one edit for short queries, two from 7 characters. */
const maxEdits = (len: number) => (len >= 7 ? 2 : 1);

/**
 * Smallest optimal-string-alignment distance between `q` and any prefix of `name`
 * ("q is a fuzzy prefix of name"), or `max + 1` when it exceeds `max`. Uses `buf`
 * (three rolling rows) instead of allocating.
 */
function fuzzyPrefixDistance(q: string, name: string, max: number, buf: Int32Array): number {
	const L = q.length;
	const n = Math.min(name.length, L + max);
	const W = n + 1;
	// rows: r0 = i-2, r1 = i-1, r2 = i (offsets into buf)
	let r0 = 0;
	let r1 = W;
	let r2 = 2 * W;
	for (let j = 0; j <= n; j++) buf[r1 + j] = j;
	for (let i = 1; i <= L; i++) {
		buf[r2] = i;
		let rowMin = i;
		const qc = q.charCodeAt(i - 1);
		for (let j = 1; j <= n; j++) {
			const nc = name.charCodeAt(j - 1);
			let v = Math.min(buf[r1 + j] + 1, buf[r2 + j - 1] + 1, buf[r1 + j - 1] + (qc === nc ? 0 : 1));
			if (i > 1 && j > 1 && qc === name.charCodeAt(j - 2) && q.charCodeAt(i - 2) === nc)
				v = Math.min(v, buf[r0 + j - 2] + 1);
			buf[r2 + j] = v;
			if (v < rowMin) rowMin = v;
		}
		if (rowMin > max) return max + 1;
		const t = r0;
		r0 = r1;
		r1 = r2;
		r2 = t;
	}
	// after the loop, r1 holds the last row
	let best = max + 1;
	for (let j = Math.max(0, L - max); j <= n; j++) if (buf[r1 + j] < best) best = buf[r1 + j];
	return best;
}

interface Previous {
	q: string;
	country: string | null;
	/** entries where some name contains q */
	cheap: Int32Array;
	/** entries within the fuzzy tolerance, when the fuzzy pass scanned every entry */
	fuzzy: Int32Array | null;
	fuzzyMax: number;
}

export class PlaceSearcher {
	readonly #entries: Entry[];
	#all: Int32Array;
	#buf = new Int32Array(3 * 64);
	#prev: Previous | null = null;

	constructor(places: Place[]) {
		this.#entries = buildEntries(places);
		this.#all = Int32Array.from(this.#entries, (_, k) => k);
	}

	search(query: string, limit = 8): SearchHit[] {
		let q = fold(query);
		if (!q) return [];
		let country: string | null = null;
		const m = /^(.*?)[,\s]+([a-z]{2})$/.exec(q);
		if (m && m[1].length >= 2) {
			country = m[2];
			q = m[1].trim();
		}
		const prev =
			this.#prev && this.#prev.country === country && q.startsWith(this.#prev.q)
				? this.#prev
				: null;

		const entries = this.#entries;
		const scores = new Map<number, { score: number; matched: string }>();
		const cheap: number[] = [];
		const L = q.length;
		const wordQ = ' ' + q;

		// pass 1: exact, prefix, word prefix, substring
		for (const k of prev ? prev.cheap : this.#all) {
			const e = entries[k];
			let best = 0;
			let matched = '';
			let contains = false;
			for (let t = 0; t < e.names.length; t++) {
				const name = e.names[t];
				if (!name.includes(q)) continue;
				contains = true;
				let s: number;
				if (name === q) s = 100;
				else if (name.startsWith(q)) s = 80 - Math.min(10, name.length - L) * 0.5;
				else if (e.spaced[t].includes(wordQ)) s = 60;
				else if (L >= 3) s = 45;
				else s = 0;
				if (s > best) {
					best = s;
					matched = e.originals[t];
				}
			}
			if (!contains) continue;
			cheap.push(k);
			if (best > 0) scores.set(k, { score: best, matched });
		}

		// pass 2: typo tolerance, only when the cheap passes found too few
		let fuzzy: Int32Array | null = null;
		const max = maxEdits(L);
		if (L >= 4 && scores.size < limit) {
			const pool = prev?.fuzzy && prev.fuzzyMax === max ? prev.fuzzy : this.#all;
			if (this.#buf.length < 3 * (L + max + 2)) this.#buf = new Int32Array(3 * (L + max + 2));
			const c0 = q.charCodeAt(0);
			const c1 = q.charCodeAt(1);
			const found: number[] = [];
			for (const k of pool) {
				const e = entries[k];
				let bestDist = max + 1;
				let matched = '';
				for (let t = 0; t < e.names.length; t++) {
					const name = e.names[t];
					if (name.length < L - max) continue;
					const n0 = name.charCodeAt(0);
					const n1 = name.charCodeAt(1);
					// typos rarely hit the first letter twice: keep names that share the first
					// or second letter with the query, or swap the first two
					if (n0 !== c0 && n1 !== c1 && !(n0 === c1 && n1 === c0)) continue;
					const d = fuzzyPrefixDistance(q, name, max, this.#buf);
					if (d < bestDist) {
						bestDist = d;
						matched = e.originals[t];
					}
				}
				if (bestDist > max) continue;
				found.push(k);
				const s = 35 - bestDist * 8;
				if (!scores.has(k) || scores.get(k)!.score < s) scores.set(k, { score: s, matched });
			}
			fuzzy = Int32Array.from(found);
		}

		this.#prev = { q, country, cheap: Int32Array.from(cheap), fuzzy, fuzzyMax: max };

		const hits: SearchHit[] = [];
		for (const [k, { score, matched }] of scores) {
			const e = entries[k];
			const boost = country && e.country === country ? 30 : 0;
			hits.push({ place: e.place, score: score + boost + e.popBonus, matched });
		}
		hits.sort((a, b) => b.score - a.score);
		return hits.slice(0, limit);
	}
}

const searchers = new WeakMap<Place[], PlaceSearcher>();

/**
 * Search `places` (see {@link PlaceSearcher}). A trailing ", XX" (or " XX") country code
 * boosts places in that country. Ties go to bigger places.
 */
export function searchPlaces(places: Place[], query: string, limit = 8): SearchHit[] {
	let s = searchers.get(places);
	if (!s) {
		s = new PlaceSearcher(places);
		searchers.set(places, s);
	}
	return s.search(query, limit);
}
