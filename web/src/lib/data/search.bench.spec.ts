import { describe, expect, it } from 'vitest';
import type { Place } from './places';
import { PlaceSearcher } from './search';

/** ~34k pseudo-random places with 0–4 alternate names, like GeoNames cities15000. */
function generatePlaces(n: number): Place[] {
	const syl = [
		'ka',
		'mun',
		'ber',
		'lin',
		'ham',
		'burg',
		'ich',
		'sta',
		'dt',
		'ro',
		'ma',
		'pa',
		'ris',
		'new',
		'york',
		'to',
		'ron',
		'chi',
		'ca',
		'go',
		'vi',
		'en',
		'na',
		'osl',
		'zu',
		'rich',
		'gra',
		'nad',
		'el',
		'san',
		'jo',
		'se',
		'por',
		'to',
		'li',
		'ma',
		'que',
		'bec',
		'an',
		'ger'
	];
	let seed = 42;
	const rnd = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
	const word = () => {
		let w = '';
		const k = 2 + Math.floor(rnd() * 3);
		for (let i = 0; i < k; i++) w += syl[Math.floor(rnd() * syl.length)];
		return w[0].toUpperCase() + w.slice(1);
	};
	const places: Place[] = [];
	for (let i = 0; i < n; i++) {
		const name = rnd() < 0.15 ? `${word()} ${word()}` : word();
		const alt = Array.from({ length: Math.floor(rnd() * 5) }, word);
		places.push({
			name,
			ascii: name,
			country: 'XX',
			admin1: '',
			alt,
			lat: 0,
			lon: 0,
			pop: 15000 + Math.floor(rnd() * 1e6),
			p_full: null,
			p_then: null,
			p_now: null,
			trend: null
		});
	}
	places.push({
		...places[0],
		name: 'Munich',
		ascii: 'Munich',
		alt: ['München', 'Monaco di Baviera'],
		pop: 1.5e6
	});
	return places;
}

/** Every prefix of `word`, as typed one key at a time. */
const keystrokes = (word: string) => Array.from(word, (_, i) => word.slice(0, i + 1));

describe('search performance on a 34k-place list', () => {
	const places = generatePlaces(34_000);

	it('answers each keystroke within the budget (15 ms desktop target)', () => {
		const t0 = performance.now();
		const searcher = new PlaceSearcher(places);
		const indexMs = performance.now() - t0;

		const times: number[] = [];
		const run = (word: string) => {
			for (const q of keystrokes(word)) {
				const t = performance.now();
				searcher.search(q);
				times.push(performance.now() - t);
			}
		};
		// warm up the JIT, then measure typing sessions incl. typos and misses
		run('munich');
		times.length = 0;
		for (const w of ['munich', 'muenchen', 'muncih', 'new york', 'xqztvw', 'san jose', 'zurich'])
			run(w);
		times.sort((a, b) => a - b);
		const median = times[Math.floor(times.length / 2)];
		const p95 = times[Math.floor(times.length * 0.95)];
		const worst = times[times.length - 1];
		console.info(
			`search 34k: index ${indexMs.toFixed(0)} ms; per keystroke median ${median.toFixed(2)} ms, p95 ${p95.toFixed(2)} ms, max ${worst.toFixed(2)} ms`
		);
		// shared CI runners are slower and noisier than a desktop
		const budget = process.env.CI ? 40 : 15;
		expect(p95).toBeLessThan(budget);
		expect(searcher.search('München')[0].place.name).toBe('Munich');
		expect(searcher.search('Muncih')[0].place.name).toBe('Munich');
	});
});
