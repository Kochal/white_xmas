// A deterministic, obviously fake "climate" for fixture data. Nothing here is
// real: probabilities follow a smooth latitude gradient, a few made-up mountain
// bumps, a gentle downward trend and shared year-to-year noise.

export const FIRST_YEAR = 1950;
export const LAST_YEAR = 2025;
export const N_YEARS = LAST_YEAR - FIRST_YEAR + 1;
export const N_DAYS = 3; // Dec 24, 25, 26
export const NODATA = 255;

/** Uniform [0, 1) hash of integers. */
export function h32(...ns) {
	let h = 0x9e3779b9 | 0;
	for (const n of ns) {
		h = Math.imul(h ^ (n | 0), 0x85ebca6b);
		h ^= h >>> 13;
		h = Math.imul(h, 0xc2b2ae35);
		h ^= h >>> 16;
	}
	return (h >>> 0) / 4294967296;
}

function normal(...ns) {
	const u1 = Math.max(1e-9, h32(...ns, 1));
	const u2 = h32(...ns, 2);
	return Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
}

const gauss = (lon, lat, lon0, lat0, sx, sy) =>
	Math.exp(-(((lon - lon0) / sx) ** 2) - ((lat - lat0) / sy) ** 2);

/** Fake elevation in km. */
export function fakeElevation(lon, lat) {
	return (
		2.2 * gauss(lon, lat, 10.5, 46.6, 2.6, 0.7) + // "Alps"
		1.0 * gauss(lon, lat, 8.0, 60.0, 1.5, 1.2) + // "Norway"
		0.9 * gauss(lon, lat, -74.2, 44.1, 1.2, 0.8) + // "Adirondacks"
		0.5 * gauss(lon, lat, 13.0, 50.4, 1.0, 0.3) // "Ore Mountains"
	);
}

/** Fake water bodies, so fixtures contain nodata cells. */
export function isFakeWater(lon, lat) {
	if (lon > 5 && lon < 8 && lat > 56 && lat < 60) return true; // "North Sea"
	if (lon > 18.5 && lat > 55 && lat < 59) return true; // "Baltic"
	if (lon > -87.8 && lon < -86.3 && lat > 41.7 && lat < 46) return true; // "Lake Michigan"
	if (lon > -73.8 && lon < -70 && lat < 41.0 + (lon + 73.8) * 0.5) return true; // "Atlantic"
	return false;
}

/** Fake glacier: a small disk in the "Alps". */
export function isFakeGlacier(lon, lat) {
	return Math.hypot(lon - 8.0, (lat - 46.5) * 1.4) < 0.25;
}

function region(lon) {
	return lon < -30 ? 1 : 2;
}

/**
 * Snow depth (whole cm, 0…254, or 255 = nodata) for one cell, year and day.
 * @param {number} i grid column, @param {number} j grid row
 * @param {number} year @param {number} day 0 = Dec 24, 1 = Dec 25, 2 = Dec 26
 */
export function fakeDepth(i, j, lon, lat, year, day) {
	if (isFakeWater(lon, lat)) return NODATA;
	if (isFakeGlacier(lon, lat)) return day === 1 && year % 7 === 0 ? 254 : 180 + ((year * 3) % 60);
	// a fake data gap and a single missing day, to exercise nodata handling
	if (i >= 1900 && i < 1950 && j >= 350 && j < 353 && year <= 1951) return NODATA;
	if (i === 1900 && j === 400 && year === 1960 && day === 0) return NODATA;

	const elev = fakeElevation(lon, lat);
	const maritime = lon > 0 && lon < 9 ? -0.25 * (9 - lon) : 0;
	const continental = region(lon) === 1 ? 0.6 : 0;
	const latent =
		-1.5 + 0.17 * (lat - 45) + 2.3 * elev + maritime + continental - 0.022 * (year - FIRST_YEAR);
	const anomaly = 1.3 * normal(region(lon), year);
	const u = Math.min(1 - 1e-9, Math.max(1e-9, h32(i, j, year)));
	const white25 = latent + anomaly + 0.9 * Math.log(u / (1 - u)) > 0;
	const depth = Math.min(
		253,
		Math.round(2 + 40 * elev + 15 * h32(i, j, year, 7) + 8 * Math.max(0, latent + anomaly))
	);
	if (day === 1) return white25 ? depth : 0;
	const flip = h32(i, j, year, day + 11);
	if (white25) return flip < 0.85 ? Math.max(1, Math.round(depth * (day === 0 ? 0.9 : 1.05))) : 0;
	return flip < (day === 0 ? 0.1 : 0.14) ? 1 + Math.floor(4 * h32(i, j, year, day + 21)) : 0;
}
