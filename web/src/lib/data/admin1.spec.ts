import { describe, expect, it } from 'vitest';
import {
	countryPath,
	parseAdmin1Index,
	parseAdmin1Ref,
	parseBoundaries,
	parseCountryFile,
	rowsById
} from './admin1';
import { DataSource } from './source';
import { parseManifest } from './manifest';

const INDEX = {
	format: 'wx-admin1-v1',
	contract: '1.6',
	data_version: 'sample',
	threshold: 'calibrated',
	definition: 'christmas_day',
	windows: { p_full: '1950_2025', p_then: '1961_1990', p_now: '1996_2025' },
	trend_alpha: 0.1,
	fields: [
		'id',
		'name',
		'country',
		'lon',
		'lat',
		'area_km2',
		'flags',
		'p_full',
		'p_then',
		'p_now',
		'change',
		'trend',
		'trend_p',
		'p_now_pop',
		'p_then_raw',
		'p_now_raw',
		'p_gwl1.5',
		'p_gwl2.0',
		'p_gwl3.0'
	],
	rows: [
		[
			'DE-BY',
			'Bavaria',
			'DEU',
			11.3,
			48.9,
			70550,
			[],
			33,
			41,
			26,
			-15,
			-2.3,
			0.012,
			21.4,
			70,
			61,
			21,
			18,
			11
		],
		[
			'CNM',
			'Buffer zone',
			'CNM',
			33.9,
			35,
			341,
			['admin0', 'no_land'],
			null,
			null,
			null,
			null,
			null,
			null,
			null,
			null,
			null,
			null,
			null,
			null
		]
	],
	countries: { DEU: { name: 'Germany', regions: 16 }, CNM: { name: 'Buffer zone', regions: 1 } },
	flags: { low_res: 'few cells' },
	attribution: 'Borders: Natural Earth.'
};

describe('admin1 index', () => {
	it('reads rows by field name, numbers them like the boundary features, and keeps nulls', () => {
		const idx = parseAdmin1Index(INDEX);
		expect(idx.rows).toHaveLength(2);
		expect(idx.rows[0]).toMatchObject({
			num: 0,
			id: 'DE-BY',
			name: 'Bavaria',
			country: 'DEU',
			area_km2: 70550,
			flags: [],
			p_now: 26,
			change: -15,
			trend_p: 0.012,
			p_now_pop: 21.4,
			p_now_raw: 61,
			gwl: { '1.5': 21, '2.0': 18, '3.0': 11 }
		});
		expect(idx.rows[1]).toMatchObject({ num: 1, p_now: null, flags: ['admin0', 'no_land'] });
		expect(idx.trend_alpha).toBe(0.1);
		expect(idx.countries.DEU).toEqual({ name: 'Germany', regions: 16 });
		expect(idx.windows.p_now).toBe('1996_2025');
		expect(rowsById(idx.rows).get('CNM')?.num).toBe(1);
	});

	it('copes with missing optional fields (older or leaner exports)', () => {
		const idx = parseAdmin1Index({
			fields: ['id', 'name', 'country', 'lon', 'lat'],
			rows: [['X-1', 'X', 'XXX', 1, 2]]
		});
		expect(idx.rows[0]).toMatchObject({ p_now: null, flags: [], gwl: {}, area_km2: null });
		expect(idx.trend_alpha).toBe(0.1);
	});

	it('rejects a file that is not an index', () => {
		expect(() => parseAdmin1Index({ fields: ['id'], rows: [] })).toThrow(/required field "name"/);
		expect(() => parseAdmin1Index({ rows: [] })).toThrow(/"fields" and "rows"/);
		expect(() => parseAdmin1Index(null)).toThrow(/not a JSON object/);
	});
});

describe('manifest admin1 block', () => {
	const ref = {
		available: true,
		format: 'wx-admin1-v1',
		index: 'admin1/index.json',
		boundaries: 'admin1/boundaries.json',
		country: 'admin1/c/{country}.json'
	};

	it('is accepted only when available and complete', () => {
		expect(parseAdmin1Ref(ref)?.country).toBe('admin1/c/{country}.json');
		expect(parseAdmin1Ref({ ...ref, available: false })).toBeUndefined();
		expect(parseAdmin1Ref({ ...ref, index: undefined })).toBeUndefined();
		expect(parseAdmin1Ref({ ...ref, country: 'admin1/c/all.json' })).toBeUndefined();
		expect(parseAdmin1Ref(undefined)).toBeUndefined();
	});

	it('validates the country key before it goes into a URL', () => {
		const r = parseAdmin1Ref(ref)!;
		expect(countryPath(r, 'DEU')).toBe('admin1/c/DEU.json');
		expect(() => countryPath(r, '../manifest')).toThrow(/bad country key/);
		expect(() => countryPath(r, '')).toThrow(/bad country key/);
	});
});

const country = {
	country: 'DEU',
	country_name: 'Germany',
	years: [1950, 2025],
	thresholds: ['calibrated', 'raw'],
	definitions: ['christmas_day'],
	windows: ['1950_2025', '1961_1990', '1996_2025'],
	windows_then_now: ['1961_1990', '1996_2025'],
	trend_alpha: 0.1,
	spread_share_pct: 50,
	projections: {
		threshold: 'calibrated',
		definition: 'christmas_day',
		gwls: [1.5, 2.0, 3.0],
		baseline_window: '1996_2025',
		models: ['A', 'B']
	},
	regions: [
		{
			id: 'DE-BY',
			name: 'Bavaria',
			name_local: 'Bayern',
			type: 'State',
			flags: ['low_res'],
			lon: 11.3,
			lat: 48.9,
			bbox: [8.98, 47.27, 13.84, 50.56],
			area_km2: 70550,
			elev_m: [107, 512, 2341],
			places: 41,
			places_pop: 5_400_000,
			stats: {
				calibrated: {
					christmas_day: {
						p: [33, 41, 26],
						p_pop: [24, 30, 18],
						share50: [18, 30, 12],
						p5: [9, 13, 6],
						p95: [83, 90, 76],
						change: -15,
						change_pop: -12,
						trend: -2.3,
						trend_p: 0.012,
						series: [55, null, 12]
					}
				}
			},
			proj: {
				baseline: 26,
				p10: [16, 13, 8],
				p50: [21, 18, 11],
				p90: [27, 25, 19],
				change: [-5, -8, -15],
				agree: [true, true, false],
				n_models: 19,
				p50_pop: [14, 12, 7]
			}
		},
		{ id: 'bad' },
		'not an object'
	]
};

describe('admin1 country file', () => {
	it('parses regions, statistics and projections', () => {
		const c = parseCountryFile(country);
		expect(c.country_name).toBe('Germany');
		expect(c.years).toEqual([1950, 2025]);
		expect(c.windows_then_now).toEqual(['1961_1990', '1996_2025']);
		expect(c.projections?.gwls).toEqual([1.5, 2, 3]);
		const r = c.regions.find((x) => x.id === 'DE-BY')!;
		expect(r.name_local).toBe('Bayern');
		expect(r.bbox).toEqual([8.98, 47.27, 13.84, 50.56]);
		expect(r.stats.calibrated.christmas_day.series).toEqual([55, null, 12]);
		expect(r.proj?.agree).toEqual([true, true, false]);
	});

	it('drops entries that are not regions and fills missing blocks with null', () => {
		const c = parseCountryFile({ ...country, projections: null });
		expect(c.projections).toBeNull();
		expect(c.regions.map((r) => r.id)).toEqual(['DE-BY', 'bad']);
		const bare = c.regions.find((r) => r.id === 'bad')!;
		expect(bare).toMatchObject({ bbox: null, elev_m: null, proj: null, stats: {}, places: 0 });
	});

	it('rejects a file without years or regions', () => {
		expect(() => parseCountryFile({ ...country, years: undefined })).toThrow(/years/);
		expect(() => parseCountryFile({ ...country, regions: undefined })).toThrow(/regions/);
	});
});

describe('admin1 boundaries', () => {
	it('accepts a FeatureCollection and nothing else', () => {
		expect(parseBoundaries({ type: 'FeatureCollection', features: [] }).features).toEqual([]);
		expect(() => parseBoundaries({ type: 'Feature' })).toThrow(/FeatureCollection/);
	});
});

describe('DataSource admin1 loaders', () => {
	const manifest = parseManifest({
		schema_version: 1,
		data_version: 't',
		built: '',
		build_hash: '',
		years: { first: 1950, last: 1951 },
		threshold_cm: 1,
		attribution: '',
		definitions: [{ id: 'christmas_day', label: 'x', short: 'x', description: 'x', default: true }],
		windows: [{ id: '1950_1951', label: 'x', start: 1950, end: 1951, kind: 'full' }],
		layers: [],
		colormaps: {},
		points: { index: 'points/index.json', tile_deg: 5, format: 'wx-points-v1' },
		places: 'places.json',
		regions: 'regions.json',
		admin1: {
			available: true,
			format: 'wx-admin1-v1',
			index: 'admin1/index.json',
			boundaries: 'admin1/boundaries.json',
			country: 'admin1/c/{country}.json'
		}
	});

	function server(files: Record<string, object>) {
		const requests: string[] = [];
		const fetchFn = (async (url: string) => {
			requests.push(url);
			const f = files[url];
			return f ? new Response(JSON.stringify(f)) : new Response('', { status: 404 });
		}) as typeof fetch;
		return { requests, fetchFn };
	}

	it('fetches nothing until asked, then once per file (lazy)', async () => {
		const { requests, fetchFn } = server({
			'/d/admin1/index.json': INDEX,
			'/d/admin1/c/DEU.json': country
		});
		const ds = new DataSource('/d', manifest, fetchFn);
		expect(ds.hasAdmin1).toBe(true);
		expect(requests).toEqual([]);
		await Promise.all([ds.admin1Index(), ds.admin1Index()]);
		await ds.admin1Country('DEU');
		await ds.admin1Country('DEU');
		expect(requests).toEqual(['/d/admin1/index.json', '/d/admin1/c/DEU.json']);
	});

	it('retries after a failed load', async () => {
		const files: Record<string, object> = {};
		const { requests, fetchFn } = server(files);
		const ds = new DataSource('/d', manifest, fetchFn);
		await expect(ds.admin1Index()).rejects.toThrow(/HTTP 404/);
		files['/d/admin1/index.json'] = INDEX;
		expect((await ds.admin1Index()).rows).toHaveLength(2);
		expect(requests).toHaveLength(2);
	});

	it('is absent when the manifest has no admin1 block', async () => {
		const bare = parseManifest({ ...JSON.parse(JSON.stringify(manifest)), admin1: undefined });
		const ds = new DataSource('/d', bare, server({}).fetchFn);
		expect(ds.hasAdmin1).toBe(false);
		await expect(ds.admin1Index()).rejects.toThrow(/not in this dataset/);
	});
});
