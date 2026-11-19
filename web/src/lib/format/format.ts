/** Plain-language and number formatting shared by the legend, panel and rankings. */

/** "about 3 in 10 years" for a probability in %. */
export function inTenYears(p: number | null): string {
	if (p === null || Number.isNaN(p)) return 'no data';
	if (p <= 0) return 'never';
	if (p < 5) return 'rarely (less than 1 in 20 years)';
	if (p >= 100) return 'every year';
	if (p > 95) return 'almost every year';
	const k = Math.max(1, Math.min(9, Math.round(p / 10)));
	return `about ${k} in 10 years`;
}

const MINUS = '\u2212';

export function formatPct(p: number | null, digits = 0): string {
	if (p === null || Number.isNaN(p)) return '–';
	return `${p.toFixed(digits)}%`;
}

/** Signed change in percentage points, e.g. "−3.1 pp". */
export function formatPp(v: number | null, unit = 'pp', digits = 1): string {
	if (v === null || Number.isNaN(v)) return '–';
	const s = Math.abs(v).toFixed(digits);
	const sign = Number(s) === 0 ? '±' : v < 0 ? MINUS : '+';
	return `${sign}${s} ${unit}`;
}

export function signed(v: number, digits = 1): string {
	const s = Math.abs(v).toFixed(digits);
	return `${Number(s) === 0 ? '' : v < 0 ? MINUS : '+'}${s}`;
}

export function latLonLabel(lat: number, lon: number): string {
	const la = Math.abs(lat).toFixed(1);
	const lo = Math.abs(lon).toFixed(1);
	const ns = la === '0.0' ? '' : lat > 0 ? 'N' : 'S';
	const ew = lo === '0.0' || lo === '180.0' ? '' : lon > 0 ? 'E' : 'W';
	return `${la}°${ns} ${lo}°${ew}`;
}

export function formatPopulation(pop: number): string {
	if (pop >= 1e6) return `${(pop / 1e6).toFixed(1)} M`;
	if (pop >= 1e3) return `${Math.round(pop / 1e3)} k`;
	return String(pop);
}
