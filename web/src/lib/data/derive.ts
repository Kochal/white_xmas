/**
 * Everything the place panel shows is derived here from a cell's raw Dec 24–26 snow
 * depths: any definition, any threshold, any window (contract: "The client derives all
 * three definitions, any threshold and any window from this data").
 */
import type { DefinitionId, Window } from './manifest';
import type { CellHistory } from './points';
import { tQuantile } from './stats';

/**
 * Is this year white? `days` are the depths (cm) on Dec 24, 25 and 26, `null` for nodata.
 * As in the pipeline (`definitions.py`), a year is unknown (`null`) when any day the
 * definition needs is missing. A stored 254 means "at least 254 cm".
 */
export function isWhite(
	days: (number | null)[],
	definition: DefinitionId,
	thresholdCm: number
): boolean | null {
	switch (definition) {
		case 'christmas_day':
			return days[1] === null ? null : days[1] >= thresholdCm;
		case 'all_three_days':
		case 'any_day': {
			if (days.some((d) => d === null)) return null;
			const snowy = (days as number[]).map((d) => d >= thresholdCm);
			return definition === 'all_three_days' ? snowy.every(Boolean) : snowy.some(Boolean);
		}
		default:
			throw new Error(`unknown definition "${definition}"`);
	}
}

/** Share of a window's years that must have data before a value is shown (pipeline: 0.8). */
export const MIN_VALID_FRACTION = 0.8;

/** Fewest valid years a window needs, as the pipeline's `min_valid_years`. */
export function minValidYears(start: number, end: number, fraction = MIN_VALID_FRACTION): number {
	return Math.ceil(fraction * (end - start + 1));
}

export type YearState = 'white' | 'green' | 'nodata';

export interface YearCell {
	year: number;
	state: YearState;
	/**
	 * Snow depth that goes with the definition, in cm: Dec 25 for `christmas_day`, the mean
	 * of the available days otherwise. `null` when there is no data.
	 */
	depth: number | null;
	/** Some day is stored as "≥ 254 cm", so `depth` is a lower bound. */
	capped: boolean;
}

function depthFor(days: (number | null)[], definition: DefinitionId): number | null {
	if (definition === 'christmas_day') return days[1];
	const known = days.filter((d): d is number => d !== null);
	return known.length ? known.reduce((a, b) => a + b, 0) / known.length : null;
}

/** One entry per year of the cell's history: white, green or nodata. */
export function yearStrip(
	cell: CellHistory,
	definition: DefinitionId,
	thresholdCm: number
): YearCell[] {
	return cell.years.map((year) => {
		const days = cell.depth(year);
		const w = isWhite(days, definition, thresholdCm);
		return {
			year,
			state: w === null ? 'nodata' : w ? 'white' : 'green',
			depth: depthFor(days, definition),
			capped: cell.capped(year)
		};
	});
}

export interface WindowProbability {
	/**
	 * Share of white years among years with data, in %; null when fewer than 80 % of the
	 * window's years have data (the map leaves those cells uncoloured too).
	 */
	p: number | null;
	nValid: number;
	nWhite: number;
	/** Mean snow depth (cm) in the white years; null without white years. */
	meanDepthWhite: number | null;
}

export function probability(strip: YearCell[], start: number, end: number): WindowProbability {
	let nValid = 0;
	let nWhite = 0;
	let depthSum = 0;
	let depthN = 0;
	for (const c of strip) {
		if (c.year < start || c.year > end || c.state === 'nodata') continue;
		nValid++;
		if (c.state === 'white') {
			nWhite++;
			if (c.depth !== null) {
				depthSum += c.depth;
				depthN++;
			}
		}
	}
	const enough = nValid > 0 && nValid >= minValidYears(start, end);
	return {
		p: enough ? (100 * nWhite) / nValid : null,
		nValid,
		nWhite,
		meanDepthWhite: depthN ? depthSum / depthN : null
	};
}

export interface DecadeProbability extends WindowProbability {
	window: Window;
}

/** Probabilities for the manifest's decade windows, oldest first. */
export function decadeProbabilities(strip: YearCell[], windows: Window[]): DecadeProbability[] {
	return windows
		.filter((w) => w.kind === 'decade')
		.sort((a, b) => a.start - b.start)
		.map((w) => ({ window: w, ...probability(strip, w.start, w.end) }));
}

export interface Trend {
	/** OLS slope of the 0/100 yearly series, in percentage points per decade. */
	perDecade: number;
	/** Rough 90 % confidence range of the slope (t distribution), pp per decade. */
	low90: number;
	high90: number;
	/**
	 * Two-sided Mann–Kendall p-value with ties correction, the test the pipeline uses for
	 * the trend map's hatching and places.json (`indicators.mann_kendall_p`).
	 */
	pValue: number;
	n: number;
}

/** Standard normal upper tail ×2: erfc(|z|/√2) (Abramowitz & Stegun 7.1.26, error < 1.5e-7). */
function twoSidedNormalP(z: number): number {
	const x = Math.abs(z) / Math.SQRT2;
	const t = 1 / (1 + 0.3275911 * x);
	const poly =
		t *
		(0.254829592 + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429))));
	return poly * Math.exp(-x * x);
}

/** Two-sided Mann–Kendall p for a 0/1 series in year order, ties corrected (as the pipeline). */
export function mannKendallP(values: number[]): number | null {
	const n = values.length;
	if (n < 3) return null;
	let s = 0;
	for (let i = 0; i < n - 1; i++)
		for (let j = i + 1; j < n; j++) s += Math.sign(values[j] - values[i]);
	const ones = values.filter((v) => v > 0).length;
	const zeros = n - ones;
	const tie = (t: number) => t * (t - 1) * (2 * t + 5);
	const variance = (n * (n - 1) * (2 * n + 5) - tie(zeros) - tie(ones)) / 18;
	if (variance <= 0) return 1;
	const z = s > 0 ? (s - 1) / Math.sqrt(variance) : s < 0 ? (s + 1) / Math.sqrt(variance) : 0;
	return Math.min(1, twoSidedNormalP(z));
}

/**
 * Trend of white (100) / green (0) years over a window: the slope and its rough 90 % range
 * from ordinary least squares, the significance from Mann–Kendall (as on the map). Null
 * with fewer than three valid years or fewer than 80 % of the window's years.
 */
export function olsTrend(strip: YearCell[], start: number, end: number): Trend | null {
	const pts = strip.filter((c) => c.year >= start && c.year <= end && c.state !== 'nodata');
	const n = pts.length;
	if (n < 3 || n < minValidYears(start, end)) return null;
	const mkP = mannKendallP(pts.map((c) => (c.state === 'white' ? 1 : 0))) ?? 1;
	const mx = pts.reduce((a, c) => a + c.year, 0) / n;
	const my = pts.reduce((a, c) => a + (c.state === 'white' ? 100 : 0), 0) / n;
	let sxx = 0;
	let sxy = 0;
	for (const c of pts) {
		const dx = c.year - mx;
		sxx += dx * dx;
		sxy += dx * ((c.state === 'white' ? 100 : 0) - my);
	}
	if (sxx === 0) return null;
	const slope = sxy / sxx;
	let sse = 0;
	for (const c of pts) {
		const r = (c.state === 'white' ? 100 : 0) - my - slope * (c.year - mx);
		sse += r * r;
	}
	const df = n - 2;
	const se = Math.sqrt(sse / df / sxx);
	if (se === 0 || !Number.isFinite(se)) {
		return {
			perDecade: slope * 10,
			low90: slope * 10,
			high90: slope * 10,
			pValue: mkP,
			n
		};
	}
	const half = tQuantile(0.95, df) * se * 10;
	return {
		perDecade: slope * 10,
		low90: slope * 10 - half,
		high90: slope * 10 + half,
		pValue: mkP,
		n
	};
}
