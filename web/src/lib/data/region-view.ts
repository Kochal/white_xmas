/**
 * Pure derivations for the region panel: which statistics to show for the controls'
 * selection (threshold, definition, period), and the numbers behind each block.
 * No rendering here, so it is unit-tested.
 */
import type { CountryFile, Admin1Index, RegionDetail, RegionStats } from './admin1';
import type { Manifest, Window } from './manifest';

export interface PickedStats {
	threshold: string;
	definition: string;
	stats: RegionStats;
}

/**
 * The statistics block for a threshold and definition. An unknown threshold or definition
 * (a shared link, a country file without it) falls back to the country file's first one,
 * which is the default.
 */
export function pickStats(
	country: CountryFile,
	region: RegionDetail,
	threshold: string,
	definition: string
): PickedStats | null {
	const th = region.stats[threshold] ? threshold : (country.thresholds[0] ?? threshold);
	const byDef = region.stats[th];
	if (!byDef) return null;
	const def = byDef[definition] ? definition : (country.definitions[0] ?? definition);
	const stats = byDef[def];
	return stats ? { threshold: th, definition: def, stats } : null;
}

/** Value of a per-window array for a window id, or null when the window isn't in the file. */
export function atWindow<T>(country: CountryFile, values: T[], windowId: string): T | null {
	const k = country.windows.indexOf(windowId);
	return k >= 0 && k < values.length ? values[k] : null;
}

/**
 * The window of the headline: the selected period when it is one of the file's windows
 * (probability and trend maps), else the latest 30-year normal, like the place panel.
 */
export function headlineWindowId(
	country: CountryFile,
	index: Pick<Admin1Index, 'windows'>,
	kind: string,
	period: string
): string {
	if ((kind === 'probability' || kind === 'trend') && country.windows.includes(period))
		return period;
	return country.windows_then_now[1] ?? index.windows.p_now;
}

export interface DecadeBar {
	window: Window;
	p: number | null;
}

/** The manifest's decade windows that the country file has, oldest first. */
export function decadeBars(
	manifest: Pick<Manifest, 'windows'>,
	country: CountryFile,
	stats: RegionStats
): DecadeBar[] {
	return manifest.windows
		.filter((w) => w.kind === 'decade' && country.windows.includes(w.id))
		.sort((a, b) => a.start - b.start)
		.map((w) => ({ window: w, p: atWindow(country, stats.p, w.id) }));
}

export interface TrendInfo {
	perDecade: number;
	p: number | null;
	/** p below the data's alpha: the trend is clear, not year-to-year chance. */
	significant: boolean;
}

export function trendInfo(stats: RegionStats, alpha: number): TrendInfo | null {
	if (stats.trend === null) return null;
	return {
		perDecade: stats.trend,
		p: stats.trend_p,
		significant: stats.trend_p !== null && stats.trend_p < alpha
	};
}

/** Least-squares line through a yearly series (gaps skipped); null with fewer than 3 points. */
export function seriesFit(
	series: (number | null)[]
): { at: (k: number) => number; perYear: number } | null {
	const pts: [number, number][] = [];
	series.forEach((v, k) => {
		if (v !== null) pts.push([k, v]);
	});
	if (pts.length < 3) return null;
	const n = pts.length;
	const mx = pts.reduce((s, p) => s + p[0], 0) / n;
	const my = pts.reduce((s, p) => s + p[1], 0) / n;
	let sxx = 0;
	let sxy = 0;
	for (const [x, y] of pts) {
		sxx += (x - mx) ** 2;
		sxy += (x - mx) * (y - my);
	}
	if (sxx === 0) return null;
	const perYear = sxy / sxx;
	return { perYear, at: (k) => my + perYear * (k - mx) };
}

export interface Spread {
	p5: number;
	p95: number;
	/** % of the area where a white Christmas is more likely than not. */
	share50: number | null;
}

/** Spread inside the region for a window; null when the cells' percentiles are unknown. */
export function spreadAt(
	country: CountryFile,
	stats: RegionStats,
	windowId: string
): Spread | null {
	const p5 = atWindow(country, stats.p5, windowId);
	const p95 = atWindow(country, stats.p95, windowId);
	if (p5 === null || p95 === null) return null;
	return { p5, p95, share50: atWindow(country, stats.share50, windowId) };
}

/** A region where every value is null (no land, all glacier): nothing to chart. */
export function hasValues(stats: RegionStats): boolean {
	return stats.p.some((v) => v !== null) || stats.series.some((v) => v !== null);
}

export interface FutureValue {
	p10: number;
	median: number;
	p90: number;
	agree: boolean;
}

/**
 * Projections lined up with the manifest's warming levels (the panel's FutureRanges reads
 * them by position). Levels the region has no numbers for are left out together.
 */
export function futureRows(
	manifest: Pick<Manifest, 'projections'>,
	country: CountryFile,
	region: RegionDetail
): {
	levels: Manifest['projections']['warming_levels'];
	values: FutureValue[];
	baseline: number | null;
} | null {
	const pr = country.projections;
	const proj = region.proj;
	if (!pr || !proj || !manifest.projections.available) return null;
	const levels: Manifest['projections']['warming_levels'] = [];
	const values: FutureValue[] = [];
	for (const lv of manifest.projections.warming_levels) {
		const k = pr.gwls.findIndex((g) => Math.abs(g - lv.gwl) < 1e-9);
		if (k < 0) continue;
		const p10 = proj.p10[k];
		const p50 = proj.p50[k];
		const p90 = proj.p90[k];
		if (p10 == null || p50 == null || p90 == null) continue;
		levels.push(lv);
		values.push({ p10, median: p50, p90, agree: proj.agree[k] ?? false });
	}
	return levels.length ? { levels, values, baseline: proj.baseline } : null;
}

const FALLBACK_FLAG_TEXT: Record<string, string> = {
	low_res:
		'Low resolution: this region covers very few grid cells (about 9 km each), so its value can be off for a small valley or island.',
	admin0: 'This region is the whole territory: the data has no states or provinces for it.',
	nearest_cell:
		'No land grid cell lies inside this region, so the value is from the nearest land cell.',
	no_land: 'No land grid cell lies inside or near this region, so there are no values.',
	all_glacier: 'All land here is glacier, which the maps leave out, so there are no values.'
};

/**
 * Short notes for a region's flags, in a stable order. The wording for the flags the contract
 * defines is plain language written here; the data's own sentence covers any flag added later.
 */
export function flagNotes(
	flags: string[],
	texts: Record<string, string>
): { flag: string; text: string }[] {
	const order = ['low_res', 'nearest_cell', 'no_land', 'all_glacier', 'admin0'];
	const known = order.filter((f) => flags.includes(f));
	const other = flags.filter((f) => !order.includes(f) && texts[f]);
	return [...known, ...other].map((flag) => ({
		flag,
		text: FALLBACK_FLAG_TEXT[flag] ?? texts[flag] ?? flag
	}));
}

/** "107–2,341 m, mean 512 m", or '' when unknown. */
export function elevationText(elev: RegionDetail['elev_m']): string {
	if (!elev) return '';
	const f = (v: number) => Math.round(v).toLocaleString('en');
	const [min, mean, max] = elev;
	if (Math.round(max) - Math.round(min) < 30) return `about ${f(mean)} m`;
	return `${f(min)} to ${f(max)} m, average ${f(mean)} m`;
}
