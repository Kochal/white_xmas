import { describe, expect, it } from 'vitest';
import { PlaceSearcher, fold, loadPlaces, parsePlaces, searchPlaces } from './places';
import { loadRegions, parseRegions } from './regions';
import { tQuantile } from './stats';

const V1 = {
	fields: [
		'name',
		'ascii',
		'country',
		'admin1',
		'lat',
		'lon',
		'pop',
		'p_full',
		'p_then',
		'p_now',
		'trend'
	],
	definition: 'christmas_day',
	windows: { p_full: '1950_2025', p_then: '1961_1990', p_now: '1996_2025' },
	rows: [
		['Munich', 'Munich', 'DE', 'Bavaria', 48.14, 11.58, 1488202, 38.2, 46.7, 31.0, -3.1],
		[
			'Münster',
			'Munster',
			'DE',
			'North Rhine-Westphalia',
			51.96,
			7.63,
			270184,
			12.0,
			15.0,
			8.0,
			null
		],
		['Munich', 'Munich', 'US', 'North Dakota', 48.67, -98.83, 15200, 80.0, 82.0, 79.0, null],
		['Muncie', 'Muncie', 'US', 'Indiana', 40.19, -85.39, 67000, 20.0, 22.0, 18.0, null],
		['Zürich', 'Zurich', 'CH', 'Zurich', 47.37, 8.55, 341730, 20.0, 25.0, 15.0, -2.0]
	]
};

// v1.1: optional "alt" after "admin1"
const V11 = {
	...V1,
	fields: [
		'name',
		'ascii',
		'country',
		'admin1',
		'alt',
		'lat',
		'lon',
		'pop',
		'p_full',
		'p_then',
		'p_now',
		'trend'
	],
	rows: [
		[
			'Munich',
			'Munich',
			'DE',
			'Bavaria',
			'München|Monaco di Baviera',
			48.14,
			11.58,
			1488202,
			38.2,
			46.7,
			31.0,
			-3.1
		],
		[
			'Cologne',
			'Cologne',
			'DE',
			'North Rhine-Westphalia',
			'Köln|Colonia',
			50.93,
			6.95,
			963395,
			10.0,
			12.0,
			8.0,
			null
		],
		['Prague', 'Prague', 'CZ', 'Prague', '', 50.09, 14.42, 1165581, 20.0, 25.0, 15.0, null]
	]
};

describe('parsePlaces', () => {
	it('maps rows to objects by the field list, without alt (contract v1)', () => {
		const places = parsePlaces(V1);
		expect(places).toHaveLength(5);
		expect(places[0]).toMatchObject({
			name: 'Munich',
			country: 'DE',
			admin1: 'Bavaria',
			alt: [],
			lat: 48.14,
			lon: 11.58,
			pop: 1488202,
			p_full: 38.2,
			p_then: 46.7,
			p_now: 31.0,
			trend: -3.1
		});
		expect(places[1].trend).toBeNull();
	});

	it('reads the optional alt field (contract v1.1) and splits it on |', () => {
		const places = parsePlaces(V11);
		expect(places[0].alt).toEqual(['München', 'Monaco di Baviera']);
		expect(places[0].lat).toBe(48.14);
		expect(places[2].alt).toEqual([]);
	});

	it('rejects a file without the required fields', () => {
		expect(() => parsePlaces({ fields: ['name'], rows: [] })).toThrow(/lat/);
	});
});

describe('fold', () => {
	it('lower-cases and strips diacritics', () => {
		expect(fold('Zürich')).toBe('zurich');
		expect(fold('  São  Paulo ')).toBe('sao paulo');
		expect(fold('Łódź')).toBe('lodz');
	});
});

describe('searchPlaces', () => {
	const v1 = parsePlaces(V1);
	const v11 = parsePlaces(V11);

	it('ranks exact names first, bigger places first among equals', () => {
		const hits = searchPlaces(v1, 'Munich');
		expect(hits.map((h) => `${h.place.name} ${h.place.country}`).slice(0, 2)).toEqual([
			'Munich DE',
			'Munich US'
		]);
	});

	it('matches prefixes, ignoring case and accents', () => {
		expect(searchPlaces(v1, 'zur')[0].place.name).toBe('Zürich');
		expect(searchPlaces(v1, 'münst')[0].place.name).toBe('Münster');
		expect(searchPlaces(v1, 'munst')[0].place.name).toBe('Münster');
	});

	it('tolerates a small typo', () => {
		expect(searchPlaces(v1, 'Muncih')[0].place.name).toBe('Munich');
	});

	it('matches "name, country" queries', () => {
		const hits = searchPlaces(v1, 'munich, us');
		expect(hits[0].place.country).toBe('US');
	});

	it('finds places by alternate names when alt is present', () => {
		expect(searchPlaces(v11, 'München')[0].place.name).toBe('Munich');
		expect(searchPlaces(v11, 'koln')[0].place.name).toBe('Cologne');
		expect(searchPlaces(v11, 'München')[0].matched).toBe('München');
	});

	it('returns nothing for an empty or hopeless query', () => {
		expect(searchPlaces(v1, '  ')).toEqual([]);
		expect(searchPlaces(v1, 'xyzzyq')).toEqual([]);
	});

	it('gives the same results when narrowing keystroke by keystroke as a fresh search', () => {
		const typing = new PlaceSearcher(v11);
		for (const word of ['muenchen', 'munich', 'koln', 'pragx', 'colonia, de']) {
			for (let i = 1; i <= word.length; i++) {
				const q = word.slice(0, i);
				const fresh = new PlaceSearcher(v11).search(q).map((h) => h.place.name);
				expect(
					typing.search(q).map((h) => h.place.name),
					q
				).toEqual(fresh);
			}
		}
	});

	it('lists no typo guesses next to an exact match', () => {
		const withJunk = parsePlaces({
			fields: ['name', 'ascii', 'country', 'admin1', 'alt', 'lat', 'lon', 'pop'],
			rows: [
				['Munich', 'Munich', 'DE', 'Bavaria', 'München', 48.1, 11.6, 1488202],
				['Naucalpan', 'Naucalpan', 'MX', 'México', 'Municipio Naucalpan', 19.5, -99.2, 834434]
			]
		});
		expect(searchPlaces(withJunk, 'Munich').map((h) => h.place.name)).toEqual(['Munich']);
		// without an exact match the typo tolerance still applies
		expect(searchPlaces(withJunk, 'Munick').map((h) => h.place.name)).toContain('Munich');
	});

	it('limits the number of hits', () => {
		expect(searchPlaces(v1, 'mun', 2)).toHaveLength(2);
	});
});

describe('loaders', () => {
	it('loadPlaces fetches the manifest-relative path', async () => {
		const seen: string[] = [];
		const fetchFn = (async (url: string) => {
			seen.push(url);
			return new Response(JSON.stringify(V1));
		}) as typeof fetch;
		expect(await loadPlaces('/data', 'places.json', fetchFn)).toHaveLength(5);
		expect(seen).toEqual(['/data/places.json']);
	});

	it('parseRegions maps rows by field names', () => {
		const regions = parseRegions({
			definition: 'christmas_day',
			fields: ['iso_a3', 'name', 'p_then', 'p_now', 'change'],
			rows: [['DEU', 'Germany', 21.4, 12.9, -8.5]]
		});
		expect(regions).toEqual([
			{ iso_a3: 'DEU', name: 'Germany', p_then: 21.4, p_now: 12.9, change: -8.5 }
		]);
	});

	it('loadRegions reports HTTP errors', async () => {
		const fetchFn = (async () => new Response('', { status: 500 })) as unknown as typeof fetch;
		await expect(loadRegions('/data', 'regions.json', fetchFn)).rejects.toThrow(/500/);
	});
});

describe('tQuantile', () => {
	it('matches textbook values', () => {
		expect(tQuantile(0.95, 10)).toBeCloseTo(1.8125, 3);
		expect(tQuantile(0.95, 74)).toBeCloseTo(1.6657, 3);
	});
});
