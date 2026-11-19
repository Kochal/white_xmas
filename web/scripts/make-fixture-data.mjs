#!/usr/bin/env node
// Writes a small, valid, obviously FAKE dataset in the web data contract format
// (manifest.json, tiles/*.pmtiles, points/, proj/, places.json, regions.json)
// to web/fixtures/data/. Usage: node scripts/make-fixture-data.mjs [--no-projections] [--no-admin1] [--out DIR]
import { cpSync, existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { gzipSync } from 'node:zlib';
import {
	FIRST_YEAR,
	LAST_YEAR,
	N_DAYS,
	N_YEARS,
	NODATA,
	fakeDepth,
	isFakeGlacier
} from './lib/fake-climate.mjs';
import { encodePng } from './lib/png.mjs';
import { TileType, writePmtiles } from './lib/pmtiles-writer.mjs';

const args = process.argv.slice(2);
const withProjections = !args.includes('--no-projections');
const withAdmin1 = !args.includes('--no-admin1');
const outIdx = args.indexOf('--out');
const OUT = path.resolve(
	outIdx >= 0 ? args[outIdx + 1] : path.join(import.meta.dirname, '..', 'fixtures', 'data')
);

const RES = 0.1;
const TC = 50; // cells per tile side
// contract v1.5: a station-calibrated default threshold and the raw ERA5-Land 1 cm view
const THRESHOLD = 5;
const RAW_THRESHOLD = 1;

// --- which 5° point tiles exist: central Europe and the North American Great Lakes
const TILES = [];
for (let tx = 37; tx <= 39; tx++) for (let ty = 6; ty <= 8; ty++) TILES.push([tx, ty]);
for (let tx = 18; tx <= 21; tx++) for (let ty = 8; ty <= 9; ty++) TILES.push([tx, ty]);
const TILE_KEYS = new Set(TILES.map(([tx, ty]) => `${tx}_${ty}`));
const BBOXES = [
	[5, 45, 20, 60],
	[-90, 40, -70, 50]
];

const cellLon = (i) => -180 + RES * i;
const cellLat = (j) => 90 - RES * j;

// --- build the cube: depth[tileKey] = Uint8Array(50·50·years·3)
console.log(`fixtures → ${OUT}`);
const cube = new Map();
const glacier = new Map();
for (const [tx, ty] of TILES) {
	const key = `${tx}_${ty}`;
	const body = new Uint8Array(TC * TC * N_YEARS * N_DAYS);
	const mask = new Uint8Array(Math.ceil((TC * TC) / 8));
	for (let cj = 0; cj < TC; cj++)
		for (let ci = 0; ci < TC; ci++) {
			const i = tx * TC + ci;
			const j = ty * TC + cj;
			const lon = cellLon(i);
			const lat = cellLat(j);
			const k = cj * TC + ci;
			if (isFakeGlacier(lon, lat)) mask[k >> 3] |= 1 << (k & 7);
			for (let y = 0; y < N_YEARS; y++)
				for (let d = 0; d < N_DAYS; d++)
					body[((k * N_YEARS + y) * N_DAYS + d) | 0] = fakeDepth(i, j, lon, lat, FIRST_YEAR + y, d);
		}
	cube.set(key, body);
	glacier.set(key, mask);
}

// --- derivations (deliberately simple; the site has its own, tested implementation)
const DEFINITIONS = {
	christmas_day: (d, th) => (d[1] === NODATA ? null : d[1] >= th),
	// as the pipeline: unknown when any needed day is missing
	all_three_days: (d, th) => (d.includes(NODATA) ? null : d.every((v) => v >= th)),
	any_day: (d, th) => (d.includes(NODATA) ? null : d.some((v) => v >= th))
};

function whiteSeries(key, k, def, th = THRESHOLD) {
	const body = cube.get(key);
	const out = [];
	for (let y = 0; y < N_YEARS; y++) {
		const o = (k * N_YEARS + y) * N_DAYS;
		out.push(DEFINITIONS[def]([body[o], body[o + 1], body[o + 2]], th));
	}
	return out;
}

function probability(series, start, end) {
	let n = 0;
	let w = 0;
	for (let y = start; y <= end; y++) {
		const s = series[y - FIRST_YEAR];
		if (s === null) continue;
		n++;
		if (s) w++;
	}
	// as the pipeline: at least 80 % of the window's years must have data
	return n === 0 || n < Math.ceil(0.8 * (end - start + 1)) ? NaN : (100 * w) / n;
}

/** Two-sided Mann–Kendall p for 0/1 data, ties corrected (the pipeline's test). */
function mannKendallP(ys) {
	const n = ys.length;
	let s = 0;
	for (let i = 0; i < n - 1; i++) for (let j = i + 1; j < n; j++) s += Math.sign(ys[j] - ys[i]);
	const ones = ys.filter((v) => v > 0).length;
	const zeros = n - ones;
	const tie = (t) => t * (t - 1) * (2 * t + 5);
	const v = (n * (n - 1) * (2 * n + 5) - tie(zeros) - tie(ones)) / 18;
	if (v <= 0) return 1;
	const z = Math.abs(s > 0 ? (s - 1) / Math.sqrt(v) : s < 0 ? (s + 1) / Math.sqrt(v) : 0);
	const x = z / Math.SQRT2;
	const t = 1 / (1 + 0.3275911 * x);
	return (
		t *
		(0.254829592 + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429)))) *
		Math.exp(-x * x)
	);
}

function trend(series) {
	const xs = [];
	const ys = [];
	series.forEach((s, idx) => {
		if (s !== null) {
			xs.push(FIRST_YEAR + idx);
			ys.push(s ? 100 : 0);
		}
	});
	const n = xs.length;
	const mx = xs.reduce((a, b) => a + b, 0) / n;
	const my = ys.reduce((a, b) => a + b, 0) / n;
	let sxx = 0;
	let sxy = 0;
	for (let t = 0; t < n; t++) {
		sxx += (xs[t] - mx) ** 2;
		sxy += (xs[t] - mx) * (ys[t] - my);
	}
	const slope = sxy / sxx;
	return { perDecade: slope * 10, significant: mannKendallP(ys.map((y) => y / 100)) < 0.1 };
}

const isOcean = (key, k) => {
	const body = cube.get(key);
	for (let t = 0; t < N_YEARS * N_DAYS; t++)
		if (body[k * N_YEARS * N_DAYS + t] !== NODATA) return false;
	return true;
};
const isGlacierCell = (key, k) => (glacier.get(key)[k >> 3] >> (k & 7)) & 1;

/** grid[tileKey] = { value: Float32Array(2500) (NaN = nodata), hatch: Uint8Array(2500) } */
function buildGrid(fn) {
	const grid = new Map();
	for (const key of TILE_KEYS) {
		const value = new Float32Array(TC * TC).fill(NaN);
		const hatch = new Uint8Array(TC * TC);
		for (let k = 0; k < TC * TC; k++) {
			if (isOcean(key, k)) continue;
			if (isGlacierCell(key, k)) {
				hatch[k] = 2; // glacier
				continue;
			}
			const r = fn(key, k);
			value[k] = r.value;
			hatch[k] = r.insignificant ? 1 : 0;
		}
		grid.set(key, { value, hatch });
	}
	return grid;
}

// --- windows
const windows = [
	{ id: '1950_2025', label: '1950–2025', start: 1950, end: 2025, kind: 'full' },
	{ id: '1961_1990', label: '1961–1990', start: 1961, end: 1990, kind: 'normal' },
	{ id: '1996_2025', label: '1996–2025', start: 1996, end: 2025, kind: 'normal' }
];
for (let end = LAST_YEAR; end - 9 >= FIRST_YEAR; end -= 10)
	windows.push({
		id: `${end - 9}_${end}`,
		label: `${end - 9}–${end}`,
		start: end - 9,
		end,
		kind: 'decade'
	});
const win = Object.fromEntries(windows.map((w) => [w.id, w]));

// --- colormaps: the same as the pipeline's (src/whitexmas/export/colors.py), so fixture
// legends look like the real ones. ColorBrewer YlGnBu and RdBu (red = fewer, blue = more).
const YLGNBU = [
	'#ffffd9',
	'#edf8b1',
	'#c7e9b4',
	'#7fcdbb',
	'#41b6c4',
	'#1d91c0',
	'#225ea8',
	'#253494',
	'#081d58'
];
const RDBU = [
	'#b2182b',
	'#d6604d',
	'#f4a582',
	'#fddbc7',
	'#f7f7f7',
	'#d1e5f0',
	'#92c5de',
	'#4393c3',
	'#2166ac'
];
const stops = (lo, hi, colours) =>
	colours.map((c, k) => [Math.round((lo + ((hi - lo) * k) / (colours.length - 1)) * 1e4) / 1e4, c]);
const colormaps = {
	probability: { unit: '%', domain: [0, 100], stops: stops(0, 100, YLGNBU) },
	change: { unit: 'pp', domain: [-50, 50], stops: stops(-50, 50, RDBU) },
	trend: { unit: 'pp/decade', domain: [-15, 15], stops: stops(-15, 15, RDBU) }
};

function hexToRgb(hex) {
	const n = parseInt(hex.slice(1), 16);
	return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function colour(cmap, v) {
	const stops = cmap.stops.map(([x, c]) => [x, hexToRgb(c)]);
	const x = Math.max(cmap.domain[0], Math.min(cmap.domain[1], v));
	for (let s = 1; s < stops.length; s++) {
		if (x <= stops[s][0]) {
			const [x0, c0] = stops[s - 1];
			const [x1, c1] = stops[s];
			const t = (x - x0) / (x1 - x0 || 1);
			return c0.map((c, ch) => Math.round(c + t * (c1[ch] - c)));
		}
	}
	return stops[stops.length - 1][1];
}

// --- raster tiles
function tileRange(z, [w, s, e, n]) {
	const N = 2 ** z;
	const xOf = (lon) => Math.floor(((lon + 180) / 360) * N);
	const yOf = (lat) => {
		const r = (lat * Math.PI) / 180;
		return Math.floor(((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2) * N);
	};
	return {
		x0: xOf(w),
		x1: Math.min(N - 1, xOf(e - 1e-9)),
		y0: yOf(n),
		y1: Math.min(N - 1, yOf(s))
	};
}

function renderTile(z, x, y, grid, cmap) {
	const size = 256;
	const rgba = new Uint8Array(size * size * 4);
	let any = false;
	const N = 2 ** z;
	for (let py = 0; py < size; py++) {
		const Y = (y + (py + 0.5) / size) / N;
		const lat = (Math.atan(Math.sinh(Math.PI * (1 - 2 * Y))) * 180) / Math.PI;
		const j = Math.round((90 - lat) / RES);
		for (let px = 0; px < size; px++) {
			const lon = ((x + (px + 0.5) / size) / N) * 360 - 180;
			const i = ((Math.round((lon + 180) / RES) % 3600) + 3600) % 3600;
			const tx = Math.floor(i / TC);
			const ty = Math.floor(j / TC);
			const g = grid.get(`${tx}_${ty}`);
			if (!g) continue;
			const k = (j - ty * TC) * TC + (i - tx * TC);
			const o = (py * size + px) * 4;
			const stripe = ((x * size + px + y * size + py) & 7) < 2;
			if (g.hatch[k] === 2) {
				const c = stripe ? [150, 150, 150] : [224, 224, 224]; // pipeline GLACIER_LINE / FILL
				rgba.set([...c, 255], o);
				any = true;
				continue;
			}
			const v = g.value[k];
			if (Number.isNaN(v)) continue;
			let c = colour(cmap, v);
			if (g.hatch[k] === 1 && stripe) c = [90, 90, 90]; // pipeline HATCH_LINE
			rgba.set([...c, 255], o);
			any = true;
		}
	}
	return any ? encodePng(size, size, rgba) : null;
}

function writeLayer(id, grid, cmapName) {
	const cmap = colormaps[cmapName];
	const tiles = [];
	for (let z = 0; z <= 6; z++) {
		const seen = new Set();
		for (const bbox of BBOXES) {
			const r = tileRange(z, bbox);
			for (let x = r.x0; x <= r.x1; x++)
				for (let y = r.y0; y <= r.y1; y++) {
					if (seen.has(`${x}/${y}`)) continue;
					seen.add(`${x}/${y}`);
					const png = renderTile(z, x, y, grid, cmap);
					if (png) tiles.push({ z, x, y, data: png });
				}
		}
	}
	const buf = writePmtiles({
		tiles,
		tileType: TileType.png,
		bounds: [-90, 40, 20, 60],
		metadata: { name: id, description: 'FIXTURE DATA — not real', colormap: cmapName }
	});
	writeFileSync(path.join(OUT, 'tiles', `${id}.pmtiles`), buf);
	console.log(`  tiles/${id}.pmtiles  ${tiles.length} tiles, ${(buf.length / 1024).toFixed(0)} KB`);
	return `tiles/${id}.pmtiles`;
}

// --- output
rmSync(OUT, { recursive: true, force: true });
for (const d of ['tiles', 'points', 'proj']) mkdirSync(path.join(OUT, d), { recursive: true });

// point tiles (wx-points-v1)
for (const [key, body] of cube) {
	const header = Buffer.alloc(16);
	header.write('WXP1', 0, 'ascii');
	header.writeUInt16LE(FIRST_YEAR, 4);
	header.writeUInt16LE(N_YEARS, 6);
	header.writeUInt16LE(TC, 8);
	header.writeUInt16LE(TC, 10);
	header[12] = N_DAYS;
	const raw = Buffer.concat([header, Buffer.from(body), Buffer.from(glacier.get(key))]);
	writeFileSync(path.join(OUT, 'points', `${key}.bin.gz`), gzipSync(raw, { level: 9 }));
}
writeFileSync(
	path.join(OUT, 'points', 'index.json'),
	JSON.stringify({
		format: 'wx-points-v1',
		tile_deg: 5,
		years: [FIRST_YEAR, LAST_YEAR],
		tiles: [...TILE_KEYS]
	})
);
console.log(`  points/  ${TILE_KEYS.size} tiles`);

// map layers
const layers = [];
const TH = { calibrated: THRESHOLD, raw: RAW_THRESHOLD };
/** Layer ids for the non-default threshold carry the suffix __raw (contract v1.5). */
const suffix = (th) => (th === 'calibrated' ? '' : `__${th}`);
const probLayer = (def, w, th = 'calibrated') => {
	const id = `prob__${def}__${w}${suffix(th)}`;
	const grid = buildGrid((key, k) => ({
		value: probability(whiteSeries(key, k, def, TH[th]), win[w].start, win[w].end)
	}));
	layers.push({
		id,
		kind: 'probability',
		definition: def,
		window: w,
		threshold: th,
		url: writeLayer(id, grid, 'probability'),
		colormap: 'probability',
		minzoom: 0,
		maxzoom: 6
	});
};
const changeLayer = (th = 'calibrated') => {
	const id = `change__christmas_day__1961_1990__1996_2025${suffix(th)}`;
	const grid = buildGrid((key, k) => {
		const s = whiteSeries(key, k, 'christmas_day', TH[th]);
		return { value: probability(s, 1996, 2025) - probability(s, 1961, 1990) };
	});
	layers.push({
		id,
		kind: 'change',
		definition: 'christmas_day',
		from: '1961_1990',
		to: '1996_2025',
		threshold: th,
		url: writeLayer(id, grid, 'change'),
		colormap: 'change',
		minzoom: 0,
		maxzoom: 6
	});
};
const trendLayer = (th = 'calibrated') => {
	const id = `trend__christmas_day__1950_2025${suffix(th)}`;
	const grid = buildGrid((key, k) => {
		const t = trend(whiteSeries(key, k, 'christmas_day', TH[th]));
		return { value: t.perDecade, insignificant: !t.significant };
	});
	layers.push({
		id,
		kind: 'trend',
		definition: 'christmas_day',
		window: '1950_2025',
		threshold: th,
		url: writeLayer(id, grid, 'trend'),
		colormap: 'trend',
		hatch_insignificant: true,
		minzoom: 0,
		maxzoom: 6
	});
};
// default (calibrated) threshold: the full fixture set
probLayer('christmas_day', '1996_2025');
probLayer('christmas_day', '1961_1990');
probLayer('christmas_day', '1950_2025');
probLayer('christmas_day', '2016_2025');
probLayer('all_three_days', '1996_2025');
probLayer('any_day', '1996_2025');
changeLayer();
trendLayer();
// raw threshold: the contract's minimum set, Snow on Christmas Day only
probLayer('christmas_day', '1950_2025', 'raw');
probLayer('christmas_day', '1961_1990', 'raw');
probLayer('christmas_day', '1996_2025', 'raw');
changeLayer('raw');
trendLayer('raw');

// projections (wx-proj-v1)
// approx is derived by the pipeline (contract v1.3) and can be long; fixtures include one
const LEVELS = [
	{ gwl: 1.5, label: '+1.5 °C', approx: 'around the 2030s' },
	{ gwl: 2.0, label: '+2 °C', approx: 'around the 2040s' },
	{ gwl: 3.0, label: '+3 °C', approx: 'not reached under SSP2-4.5 by most models' }
];
const logit = (p) => Math.log(p / (1 - p));
const inv = (x) => 1 / (1 + Math.exp(-x));
function projStats(p0, gwl) {
	const q = Math.min(0.995, Math.max(0.005, p0 / 100));
	const delta = -0.45 * gwl;
	return [delta * 1.7, delta, delta * 0.4].map((d) => Math.round(100 * inv(logit(q) + d)));
}
if (withProjections) {
	for (const key of TILE_KEYS) {
		const header = Buffer.alloc(16);
		header.write('WXQ1', 0, 'ascii');
		header[4] = LEVELS.length;
		header[5] = 3;
		header.writeUInt16LE(TC, 6);
		header.writeUInt16LE(TC, 8);
		const body = new Uint8Array(TC * TC * LEVELS.length * 3).fill(NODATA);
		const agree = LEVELS.map(() => new Uint8Array(Math.ceil((TC * TC) / 8)));
		for (let k = 0; k < TC * TC; k++) {
			if (isOcean(key, k)) continue;
			const p0 = probability(whiteSeries(key, k, 'christmas_day'), 1996, 2025);
			LEVELS.forEach((lv, l) => {
				const st = projStats(p0, lv.gwl);
				body.set(st, (k * LEVELS.length + l) * 3);
				if (Math.abs(st[1] - p0) >= 3) agree[l][k >> 3] |= 1 << (k & 7);
			});
		}
		const raw = Buffer.concat([header, Buffer.from(body), ...agree.map((a) => Buffer.from(a))]);
		writeFileSync(path.join(OUT, 'proj', `${key}.bin.gz`), gzipSync(raw, { level: 9 }));
	}
	for (const lv of LEVELS) {
		const id = `proj__christmas_day__gwl${lv.gwl.toFixed(1)}`;
		const grid = buildGrid((key, k) => ({
			value: projStats(probability(whiteSeries(key, k, 'christmas_day'), 1996, 2025), lv.gwl)[1]
		}));
		layers.push({
			id,
			kind: 'projection',
			definition: 'christmas_day',
			warming_level: lv.gwl,
			threshold: 'calibrated',
			url: writeLayer(id, grid, 'probability'),
			colormap: 'probability',
			minzoom: 0,
			maxzoom: 6
		});
		// contract v1.2: change vs today, hatched where models disagree on the direction
		const cid = `projchange__christmas_day__gwl${lv.gwl.toFixed(1)}`;
		const cgrid = buildGrid((key, k) => {
			const p0 = probability(whiteSeries(key, k, 'christmas_day'), 1996, 2025);
			const median = projStats(p0, lv.gwl)[1];
			return { value: median - p0, insignificant: Math.abs(median - p0) < 3 };
		});
		layers.push({
			id: cid,
			kind: 'projection_change',
			definition: 'christmas_day',
			warming_level: lv.gwl,
			threshold: 'calibrated',
			url: writeLayer(cid, cgrid, 'change'),
			colormap: 'change',
			hatch_disagreement: true,
			minzoom: 0,
			maxzoom: 6
		});
	}
}

// places.json
// Real city names and coordinates (GeoNames, CC BY 4.0); every value is FAKE.
const CITIES = [
	[
		'Munich',
		'Munich',
		'DE',
		'Bavaria',
		'München|Monaco di Baviera|Múnich',
		48.13743,
		11.57549,
		1260391
	],
	['Berlin', 'Berlin', 'DE', 'Berlin', '', 52.52437, 13.41053, 3426354],
	['Hamburg', 'Hamburg', 'DE', 'Hamburg', '', 53.57532, 10.01534, 1739117],
	['Frankfurt am Main', 'Frankfurt am Main', 'DE', 'Hesse', '', 50.11552, 8.68417, 650000],
	['Stuttgart', 'Stuttgart', 'DE', 'Baden-Wurttemberg', '', 48.78232, 9.17702, 589793],
	['Leipzig', 'Leipzig', 'DE', 'Saxony', '', 51.33962, 12.37129, 504971],
	['Dresden', 'Dresden', 'DE', 'Saxony', '', 51.05089, 13.73832, 486854],
	['Nuremberg', 'Nuremberg', 'DE', 'Bavaria', 'Nürnberg|Norimberga', 49.45421, 11.07752, 499237],
	[
		'Garmisch-Partenkirchen',
		'Garmisch-Partenkirchen',
		'DE',
		'Bavaria',
		'',
		47.49209,
		11.09576,
		26413
	],
	['Cologne', 'Cologne', 'DE', 'North Rhine-Westphalia', 'Köln|Colonia', 50.93333, 6.95, 963395],
	['Dortmund', 'Dortmund', 'DE', 'North Rhine-Westphalia', '', 51.51494, 7.466, 588462],
	['Hanover', 'Hanover', 'DE', 'Lower Saxony', 'Hannover', 52.37052, 9.73322, 515140],
	['Bremen', 'Bremen', 'DE', 'Bremen', '', 53.07516, 8.80777, 546501],
	['Vienna', 'Vienna', 'AT', 'Vienna', 'Wien|Vienne|Viena', 48.20849, 16.37208, 1691468],
	['Innsbruck', 'Innsbruck', 'AT', 'Tyrol', '', 47.26266, 11.39454, 112467],
	['Salzburg', 'Salzburg', 'AT', 'Salzburg', '', 47.79941, 13.04399, 145871],
	['Graz', 'Graz', 'AT', 'Styria', '', 47.06667, 15.45, 222326],
	['Zürich', 'Zurich', 'CH', 'Zurich', 'Zurich|Zurigo', 47.36667, 8.55, 341730],
	['Bern', 'Bern', 'CH', 'Bern', 'Berne', 46.94809, 7.44744, 121631],
	['Basel', 'Basel', 'CH', 'Basel-City', 'Bâle|Basilea', 47.55839, 7.57327, 164488],
	['Chur', 'Chur', 'CH', 'Grisons', '', 46.84986, 9.53287, 33756],
	['Genève', 'Geneve', 'CH', 'Geneva', 'Geneva|Genf|Ginevra', 46.20222, 6.14569, 183981],
	['Prague', 'Prague', 'CZ', 'Prague', 'Praha|Prag', 50.08804, 14.42076, 1165581],
	['Brno', 'Brno', 'CZ', 'South Moravian', 'Brünn', 49.19522, 16.60796, 369559],
	[
		'Copenhagen',
		'Copenhagen',
		'DK',
		'Capital Region',
		'København|Kopenhagen',
		55.67594,
		12.56553,
		1153615
	],
	['Aarhus', 'Aarhus', 'DK', 'Central Jutland', '', 56.15674, 10.21076, 285273],
	['Oslo', 'Oslo', 'NO', 'Oslo', '', 59.91273, 10.74609, 580000],
	['Stockholm', 'Stockholm', 'SE', 'Stockholm', '', 59.32938, 18.06871, 1515017],
	['Göteborg', 'Goteborg', 'SE', 'Vastra Gotaland', 'Gothenburg', 57.70716, 11.96679, 572799],
	['Malmö', 'Malmo', 'SE', 'Skane', 'Malmo', 55.60587, 13.00073, 301706],
	['Poznań', 'Poznan', 'PL', 'Greater Poland', 'Posen', 52.40692, 16.92993, 570352],
	['Wrocław', 'Wroclaw', 'PL', 'Lower Silesia', 'Breslau', 51.1, 17.03333, 634893],
	['Szczecin', 'Szczecin', 'PL', 'West Pomerania', 'Stettin', 53.42894, 14.55302, 407811],
	['Milan', 'Milan', 'IT', 'Lombardy', 'Milano|Mailand', 45.46427, 9.18951, 1236837],
	['Turin', 'Turin', 'IT', 'Piedmont', 'Torino|Turin', 45.07049, 7.68682, 870456],
	['Venice', 'Venice', 'IT', 'Veneto', 'Venezia|Venedig', 45.43713, 12.33265, 51298],
	['Ljubljana', 'Ljubljana', 'SI', 'Ljubljana', 'Laibach', 46.05108, 14.50513, 255115],
	['Zagreb', 'Zagreb', 'HR', 'City of Zagreb', 'Agram', 45.81444, 15.97798, 698966],
	['Bratislava', 'Bratislava', 'SK', 'Bratislava', 'Pressburg', 48.14816, 17.10674, 423737],
	['Budapest', 'Budapest', 'HU', 'Budapest', 'Budapesht', 47.49835, 19.04045, 1741041],
	['Strasbourg', 'Strasbourg', 'FR', 'Grand Est', 'Straßburg', 48.58392, 7.74553, 274845],
	['Luxembourg', 'Luxembourg', 'LU', 'Luxembourg', '', 49.61167, 6.13, 76684],
	['Chicago', 'Chicago', 'US', 'Illinois', '', 41.85003, -87.65005, 2720546],
	['Detroit', 'Detroit', 'US', 'Michigan', '', 42.33143, -83.04575, 677116],
	['Toronto', 'Toronto', 'CA', 'Ontario', '', 43.70011, -79.4163, 2600000],
	['Montréal', 'Montreal', 'CA', 'Quebec', 'Montreal', 45.50884, -73.58781, 1600000],
	['Ottawa', 'Ottawa', 'CA', 'Ontario', '', 45.41117, -75.69812, 812129],
	[
		'New York City',
		'New York City',
		'US',
		'New York',
		'New York|NYC',
		40.71427,
		-74.00597,
		8175133
	],
	['Boston', 'Boston', 'US', 'Massachusetts', '', 42.35843, -71.05977, 617594],
	['Buffalo', 'Buffalo', 'US', 'New York', '', 42.88645, -78.87837, 258071],
	['Cleveland', 'Cleveland', 'US', 'Ohio', '', 41.4995, -81.69541, 396815],
	['Milwaukee', 'Milwaukee', 'US', 'Wisconsin', '', 43.0389, -87.90647, 594833],
	['Pittsburgh', 'Pittsburgh', 'US', 'Pennsylvania', '', 40.44062, -79.99589, 305841],
	['Québec', 'Quebec', 'CA', 'Quebec', 'Quebec City|Ville de Québec', 46.81228, -71.21454, 528595],
	['Burlington', 'Burlington', 'US', 'Vermont', '', 44.47588, -73.21207, 42417],
	['Albany', 'Albany', 'US', 'New York', '', 42.65258, -73.75623, 97856]
];

function landCellNear(lon, lat) {
	const i0 = ((Math.round((lon + 180) / RES) % 3600) + 3600) % 3600;
	const j0 = Math.round((90 - lat) / RES);
	let best = null;
	for (let dj = -2; dj <= 2; dj++)
		for (let di = -2; di <= 2; di++) {
			const i = i0 + di;
			const j = j0 + dj;
			const tx = Math.floor(i / TC);
			const ty = Math.floor(j / TC);
			const key = `${tx}_${ty}`;
			if (!TILE_KEYS.has(key)) continue;
			const k = (j - ty * TC) * TC + (i - tx * TC);
			if (isOcean(key, k)) continue;
			const dist = di * di + dj * dj;
			if (!best || dist < best.dist) best = { key, k, dist };
		}
	return best;
}

const r1 = (v) => Math.round(v * 10) / 10;
const rows = [];
for (const [name, ascii, country, admin1, alt, lat, lon, pop] of CITIES) {
	const cell = landCellNear(lon, lat);
	if (!cell) {
		console.warn(`  dropped ${name}: no land cell within 2 cells`);
		continue;
	}
	const s = whiteSeries(cell.key, cell.k, 'christmas_day');
	const sRaw = whiteSeries(cell.key, cell.k, 'christmas_day', RAW_THRESHOLD);
	const t = trend(s);
	rows.push([
		name,
		ascii,
		country,
		admin1,
		alt,
		lat,
		lon,
		pop,
		r1(probability(s, 1950, 2025)),
		r1(probability(s, 1961, 1990)),
		r1(probability(s, 1996, 2025)),
		t.significant ? r1(t.perDecade) : null,
		// optional v1.5 fields: the raw threshold's values
		r1(probability(sRaw, 1961, 1990)),
		r1(probability(sRaw, 1996, 2025))
	]);
}
writeFileSync(
	path.join(OUT, 'places.json'),
	JSON.stringify({
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
			'trend',
			'p_then_raw',
			'p_now_raw'
		],
		definition: 'christmas_day',
		windows: { p_full: '1950_2025', p_then: '1961_1990', p_now: '1996_2025' },
		rows
	})
);
console.log(`  places.json  ${rows.length} places`);

// regions.json: FAKE country values (mean over the country's fixture places)
const COUNTRIES = {
	DE: ['DEU', 'Germany'],
	AT: ['AUT', 'Austria'],
	CH: ['CHE', 'Switzerland'],
	CZ: ['CZE', 'Czechia'],
	DK: ['DNK', 'Denmark'],
	NO: ['NOR', 'Norway'],
	SE: ['SWE', 'Sweden'],
	PL: ['POL', 'Poland'],
	IT: ['ITA', 'Italy'],
	US: ['USA', 'United States of America'],
	CA: ['CAN', 'Canada']
};
const regionRows = Object.entries(COUNTRIES).map(([iso2, [iso3, name]]) => {
	const rs = rows.filter((r) => r[2] === iso2);
	const mean = (idx) => r1(rs.reduce((a, r) => a + r[idx], 0) / rs.length);
	return [iso3, name, mean(9), mean(10), r1(mean(10) - mean(9))];
});
writeFileSync(
	path.join(OUT, 'regions.json'),
	JSON.stringify({
		definition: 'christmas_day',
		fields: ['iso_a3', 'name', 'p_then', 'p_now', 'change'],
		rows: regionRows
	})
);
console.log(`  regions.json  ${regionRows.length} regions`);

// admin1/: states and provinces (contract v1.6). The pipeline's own sample fixture
// (tests/fixtures/admin1_sample, clearly fake values, real Natural Earth outlines for a few
// countries) is copied as is, so the site is tested against the pipeline's exact format.
const ADMIN1_SAMPLE = path.resolve(
	import.meta.dirname,
	'..',
	'..',
	'tests',
	'fixtures',
	'admin1_sample',
	'admin1'
);
const hasAdmin1 = withAdmin1 && existsSync(path.join(ADMIN1_SAMPLE, 'index.json'));
if (hasAdmin1) {
	cpSync(ADMIN1_SAMPLE, path.join(OUT, 'admin1'), { recursive: true });
	console.log('  admin1/  copied from tests/fixtures/admin1_sample');
}

// manifest.json
const manifest = {
	schema_version: 1,
	data_version: '0.0-fixture',
	built: new Date(Date.UTC(2026, 10, 18)).toISOString(),
	build_hash: 'fixture',
	years: { first: FIRST_YEAR, last: LAST_YEAR },
	threshold_cm: THRESHOLD,
	station_equivalent_cm: 1,
	thresholds: [
		{
			id: 'calibrated',
			cm: THRESHOLD,
			default: true,
			station_equivalent_cm: 1,
			label: 'Calibrated to weather stations',
			description: `At least ${THRESHOLD} cm of snow in ERA5-Land, which matches at least 1 cm measured at weather stations (FIXTURE: made-up calibration).`
		},
		{
			id: 'raw',
			cm: RAW_THRESHOLD,
			label: `Raw ERA5-Land, at least ${RAW_THRESHOLD} cm`,
			description: `At least ${RAW_THRESHOLD} cm of snow in ERA5-Land as published (FIXTURE).`
		}
	],
	attribution:
		'FIXTURE DATA — fake values for development only. Place names: GeoNames (CC BY 4.0).',
	definitions: [
		{
			id: 'christmas_day',
			label: 'Snow on Christmas Day',
			short: 'Dec 25',
			description: `Daily-mean snow depth on 25 December is at least ${THRESHOLD} cm.`,
			default: true
		},
		{
			id: 'all_three_days',
			label: 'Snow on all three days (DWD)',
			short: 'Dec 24–26',
			description: `Daily-mean snow depth is at least ${THRESHOLD} cm on each of 24, 25 and 26 December.`
		},
		{
			id: 'any_day',
			label: 'Snow on any of the three days',
			short: 'any day',
			description: `Daily-mean snow depth is at least ${THRESHOLD} cm on at least one of 24, 25 or 26 December.`
		}
	],
	windows,
	layers,
	colormaps,
	glacier_style: 'hatched',
	points: { index: 'points/index.json', tile_deg: 5, format: 'wx-points-v1' },
	projections: withProjections
		? {
				available: true,
				warming_levels: LEVELS,
				baseline_window: '1996_2025',
				points: { tile_deg: 5, format: 'wx-proj-v1', path: 'proj/{tx}_{ty}.bin.gz' },
				models: ['FIXTURE-MODEL-A', 'FIXTURE-MODEL-B', 'FIXTURE-MODEL-C']
			}
		: { available: false },
	places: 'places.json',
	regions: 'regions.json',
	...(hasAdmin1
		? {
				admin1: {
					available: true,
					format: 'wx-admin1-v1',
					index: 'admin1/index.json',
					boundaries: 'admin1/boundaries.json',
					country: 'admin1/c/{country}.json',
					data_version: 'sample',
					build_hash: 'sample'
				}
			}
		: {})
};
writeFileSync(path.join(OUT, 'manifest.json'), JSON.stringify(manifest, null, '\t'));
console.log(`  manifest.json  ${layers.length} layers, ${windows.length} windows`);
