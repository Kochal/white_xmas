import { describe, expect, it } from 'vitest';
import { parseCountryFile } from './admin1';
import {
	atWindow,
	decadeBars,
	elevationText,
	flagNotes,
	futureRows,
	hasValues,
	headlineWindowId,
	pickStats,
	regionHeadline,
	seriesFit,
	spreadAt,
	trendInfo
} from './region-view';
import type { Manifest, Window } from './manifest';

const W = (id: string, kind: Window['kind']): Window => {
	const [start, end] = id.split('_').map(Number);
	return { id, label: `${start}–${end}`, start, end, kind };
};

const manifest = {
	windows: [
		W('1950_2025', 'full'),
		W('1961_1990', 'normal'),
		W('1996_2025', 'normal'),
		W('2016_2025', 'decade'),
		W('2006_2015', 'decade'),
		W('1996_2005', 'decade')
	],
	projections: {
		available: true,
		models: [],
		warming_levels: [
			{ gwl: 1.5, label: '+1.5 °C', approx: '' },
			{ gwl: 2, label: '+2 °C', approx: '' },
			{ gwl: 3, label: '+3 °C', approx: '' }
		]
	}
} as unknown as Manifest;

const stats = (p: number[]) => ({
	p,
	p_pop: p,
	share50: [10, 20, 30, 40, 50, 60],
	p5: [1, 2, 3, 4, 5, 6],
	p95: [91, 92, 93, 94, 95, 96],
	change: -5,
	change_pop: -4,
	trend: -1.5,
	trend_p: 0.03,
	trend_q: null,
	series: [10, 20, 30]
});

const country = parseCountryFile({
	country: 'DEU',
	country_name: 'Germany',
	years: [1950, 2025],
	thresholds: ['calibrated', 'raw'],
	definitions: ['christmas_day', 'any_day'],
	windows: ['1950_2025', '1961_1990', '1996_2025', '2016_2025', '2006_2015', '1996_2005'],
	windows_then_now: ['1961_1990', '1996_2025'],
	projections: {
		gwls: [1.5, 2, 3],
		models: ['a']
	},
	regions: [
		{
			id: 'DE-BY',
			name: 'Bavaria',
			stats: {
				calibrated: {
					christmas_day: stats([33, 41, 26, 22, 28, 30]),
					any_day: stats([50, 51, 52, 53, 54, 55])
				},
				raw: { christmas_day: stats([60, 61, 62, 63, 64, 65]) }
			},
			proj: {
				baseline: 26,
				p10: [16, 13, 8],
				p50: [21, 18, 11],
				p90: [27, 25, 19],
				change: [-5, -8, -15],
				agree: [true, true, false],
				n_models: 19,
				p50_pop: []
			}
		}
	]
});
const region = country.regions[0];

describe('pickStats', () => {
	it('returns the block for a threshold and definition', () => {
		const r = pickStats(country, region, 'raw', 'christmas_day')!;
		expect(r.threshold).toBe('raw');
		expect(r.stats.p[0]).toBe(60);
	});

	it('falls back to the first threshold and definition of the file', () => {
		const r = pickStats(country, region, 'bogus', 'bogus')!;
		expect([r.threshold, r.definition, r.stats.p[0]]).toEqual(['calibrated', 'christmas_day', 33]);
		// raw only has Snow on Christmas Day: another definition falls back within raw
		const raw = pickStats(country, region, 'raw', 'any_day')!;
		expect([raw.threshold, raw.definition]).toEqual(['raw', 'christmas_day']);
	});
});

describe('windows', () => {
	it('reads a per-window array by window id', () => {
		expect(atWindow(country, [1, 2, 3, 4, 5, 6], '1996_2025')).toBe(3);
		expect(atWindow(country, [1, 2, 3, 4, 5, 6], '1900_1910')).toBeNull();
	});

	it('uses the selected period for probability and trend maps, else the latest normal', () => {
		const idx = { windows: { p_full: '1950_2025', p_then: '1961_1990', p_now: '1996_2025' } };
		expect(headlineWindowId(country, idx, 'probability', '2016_2025')).toBe('2016_2025');
		expect(headlineWindowId(country, idx, 'trend', '1950_2025')).toBe('1950_2025');
		expect(headlineWindowId(country, idx, 'change', '1961_1990__1996_2025')).toBe('1996_2025');
		expect(headlineWindowId(country, idx, 'probability', '1900_1910')).toBe('1996_2025');
		expect(headlineWindowId(country, idx, 'projection', '2')).toBe('1996_2025');
	});

	it('lists the decades oldest first, only those in the file', () => {
		const bars = decadeBars(manifest, country, region.stats.calibrated.christmas_day);
		expect(bars.map((b) => b.window.id)).toEqual(['1996_2005', '2006_2015', '2016_2025']);
		expect(bars.map((b) => b.p)).toEqual([30, 28, 22]);
		const fewer = decadeBars(
			manifest,
			{ ...country, windows: ['1996_2005'] },
			region.stats.calibrated.christmas_day
		);
		expect(fewer.map((b) => b.window.id)).toEqual(['1996_2005']);
	});
});

describe('trend and series', () => {
	it('calls a trend likely when p is below the data alpha (no adjusted value)', () => {
		const s = region.stats.calibrated.christmas_day;
		expect(trendInfo(s, 0.1)).toEqual({
			perDecade: -1.5,
			p: 0.03,
			q: null,
			adjusted: false,
			likely: true
		});
		expect(trendInfo({ ...s, trend_p: 0.1 }, 0.1)?.likely).toBe(false);
		expect(trendInfo({ ...s, trend_p: null }, 0.1)?.likely).toBe(false);
		expect(trendInfo({ ...s, trend: null }, 0.1)).toBeNull();
	});

	it('uses the Benjamini-Hochberg q instead of p when the data has it', () => {
		const s = region.stats.calibrated.christmas_day;
		// clear on its own (p 0.03) but not after adjusting for thousands of regions
		const unlikely = trendInfo({ ...s, trend_q: 0.4 }, 0.1)!;
		expect([unlikely.likely, unlikely.adjusted, unlikely.q]).toEqual([false, true, 0.4]);
		const likely = trendInfo({ ...s, trend_p: 0.0004, trend_q: 0.02 }, 0.1)!;
		expect([likely.likely, likely.adjusted]).toEqual([true, true]);
	});

	it('fits a line through a yearly series, skipping gaps', () => {
		const fit = seriesFit([0, 10, null, 30, 40])!;
		expect(fit.perYear).toBeCloseTo(10);
		expect(fit.at(2)).toBeCloseTo(20);
		expect(seriesFit([5, null, 7])).toBeNull();
		expect(seriesFit([4, 4, 4, 4])!.perYear).toBe(0);
	});

	it('knows when a region has no values at all', () => {
		expect(hasValues(region.stats.calibrated.christmas_day)).toBe(true);
		expect(hasValues({ ...stats([]), p: [null, null], series: [null] })).toBe(false);
	});
});

describe('regionHeadline', () => {
	it('says what the number is: the share of the land that has snow', () => {
		expect(regionHeadline('Bavaria', 'christmas_day', 'Snow on Christmas Day', '28%')).toBe(
			'On a typical Christmas Day about 28% of the land in Bavaria has snow'
		);
		expect(regionHeadline('Tyrol', 'all_three_days', 'x', '9%')).toContain('on all three days');
		expect(regionHeadline('Tyrol', 'any_day', 'x', '9%')).toContain(
			'at least one of 24–26 December'
		);
		expect(regionHeadline('Tyrol', 'new_def', 'Snow on New Year', '9%')).toBe(
			'Snow on New Year: about 9% of the land in Tyrol'
		);
	});
});

describe('spread', () => {
	it('reads the percentiles and area share for a window', () => {
		expect(spreadAt(country, region.stats.calibrated.christmas_day, '1996_2025')).toEqual({
			p5: 3,
			p95: 93,
			share50: 30
		});
		expect(spreadAt(country, { ...stats([]), p5: [null, null, null] }, '1996_2025')).toBeNull();
	});

	it('words the elevation range', () => {
		expect(elevationText([107, 512, 2341])).toBe('107 to 2,341 m, average 512 m');
		expect(elevationText([10, 12, 20])).toBe('about 12 m');
		expect(elevationText(null)).toBe('');
	});
});

describe('futureRows', () => {
	it('lines the region up with the manifest warming levels', () => {
		const f = futureRows(manifest, country, region)!;
		expect(f.levels.map((l) => l.gwl)).toEqual([1.5, 2, 3]);
		expect(f.values[0]).toEqual({ p10: 16, median: 21, p90: 27, agree: true });
		expect(f.values[2].agree).toBe(false);
		expect(f.baseline).toBe(26);
	});

	it('is null without projections, and skips levels the region lacks', () => {
		expect(futureRows(manifest, { ...country, projections: null }, region)).toBeNull();
		expect(futureRows(manifest, country, { ...region, proj: null })).toBeNull();
		const partial = { ...region, proj: { ...region.proj!, p50: [21, null, 11] } };
		expect(futureRows(manifest, country, partial)!.levels.map((l) => l.gwl)).toEqual([1.5, 3]);
		const off = { projections: { ...manifest.projections, available: false } } as Manifest;
		expect(futureRows(off, country, region)).toBeNull();
	});
});

describe('flagNotes', () => {
	it('words the flags in plain language, low resolution first', () => {
		const notes = flagNotes(['admin0', 'low_res'], { low_res: 'fewer than 3 land cells' });
		expect(notes.map((n) => n.flag)).toEqual(['low_res', 'admin0']);
		expect(notes[0].text).toMatch(/^Low resolution/);
		expect(notes[0].text).not.toMatch(/fewer than 3/);
	});

	it('uses the data text for a flag it does not know, and skips one without text', () => {
		const notes = flagNotes(['future_flag', 'mystery'], { future_flag: 'Something new.' });
		expect(notes).toEqual([{ flag: 'future_flag', text: 'Something new.' }]);
	});
});
