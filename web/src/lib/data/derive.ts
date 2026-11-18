/**
 * Everything the place panel shows is derived here from a cell's raw Dec 24–26 snow
 * depths: any definition, any threshold, any window (contract: "The client derives all
 * three definitions, any threshold and any window from this data").
 */
import type { DefinitionId, Window } from './manifest';
import type { CellHistory } from './points';
import { tQuantile, tTwoSidedP } from './stats';

/**
 * Is this year white? Three-valued: `null` when missing days leave it undecided.
 * `days` are the depths (cm) on Dec 24, 25 and 26, `null` for nodata.
 * A stored 254 means "at least 254 cm", which is above any sensible threshold.
 */
export function isWhite(
	days: (number | null)[],
	definition: DefinitionId,
	thresholdCm: number
): boolean | null {
	const snowy = (d: number | null) => (d === null ? null : d >= thresholdCm);
	switch (definition) {
		case 'christmas_day':
			return snowy(days[1]);
		case 'all_three_days': {
			const s = days.map(snowy);
			if (s.includes(false)) return false;
			return s.includes(null) ? null : true;
		}
		case 'any_day': {
			const s = days.map(snowy);
			if (s.includes(true)) return true;
			return s.includes(null) ? null : false;
		}
		default:
			throw new Error(`unknown definition "${definition}"`);
	}
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
	/** Share of white years among years with data, in %; null without valid years. */
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
	return {
		p: nValid ? (100 * nWhite) / nValid : null,
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
	/** Two-sided p-value of the slope (OLS t test; ignores autocorrelation). */
	pValue: number;
	n: number;
}

/**
 * Ordinary least squares trend of white (100) / green (0) years over a window. The OLS
 * standard error on 0/1 data is only a rough guide, which the panel says plainly.
 */
export function olsTrend(strip: YearCell[], start: number, end: number): Trend | null {
	const pts = strip.filter((c) => c.year >= start && c.year <= end && c.state !== 'nodata');
	const n = pts.length;
	if (n < 3) return null;
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
			pValue: slope === 0 ? 1 : 0,
			n
		};
	}
	const half = tQuantile(0.95, df) * se * 10;
	return {
		perDecade: slope * 10,
		low90: slope * 10 - half,
		high90: slope * 10 + half,
		pValue: tTwoSidedP(slope / se, df),
		n
	};
}
