import { describe, expect, it } from 'vitest';
import { formatP, formatPct, formatPp, frequencyLine, inTenYears, latLonLabel } from './format';

describe('inTenYears: plain-language frequency', () => {
	it('says "about k in 10 years" in the middle of the range', () => {
		expect(inTenYears(31)).toBe('about 3 in 10 years');
		expect(inTenYears(10)).toBe('about 1 in 10 years');
		expect(inTenYears(86)).toBe('about 9 in 10 years');
	});

	it('handles the ends honestly', () => {
		expect(inTenYears(0)).toBe('never');
		expect(inTenYears(3)).toBe('rarely (less than 1 in 20 years)');
		expect(inTenYears(97)).toBe('almost every year');
		expect(inTenYears(100)).toBe('every year');
		expect(inTenYears(null)).toBe('no data');
	});
});

describe('frequencyLine', () => {
	it('reads as a sentence for every probability, including never and every year', () => {
		expect(frequencyLine('Snow on Christmas Day', 0)).toBe('Snow on Christmas Day: never');
		expect(frequencyLine('Snow on Christmas Day', 63)).toBe(
			'Snow on Christmas Day: about 6 in 10 years'
		);
		expect(frequencyLine('Snow on Christmas Day', 100)).toBe('Snow on Christmas Day: every year');
		expect(frequencyLine('Snow on Christmas Day', 63)).not.toMatch(/ in (never|every|about)/);
	});
});

describe('number formatting', () => {
	it('formats probabilities and changes with a real minus sign', () => {
		expect(formatPct(31.04)).toBe('31%');
		expect(formatPct(null)).toBe('–');
		expect(formatPp(-3.14)).toBe('−3.1 pp');
		expect(formatPp(2)).toBe('+2.0 pp');
		expect(formatPp(-3.14, 'pp/decade')).toBe('−3.1 pp/decade');
	});

	it('labels coordinates with hemispheres', () => {
		expect(latLonLabel(48.1, 11.6)).toBe('48.1°N 11.6°E');
		expect(latLonLabel(-33.9, -70.7)).toBe('33.9°S 70.7°W');
		// the antimeridian and the equator / prime meridian have no hemisphere letter
		expect(latLonLabel(65.5, -180)).toBe('65.5°N 180.0°');
		expect(latLonLabel(0, 0)).toBe('0.0° 0.0°');
	});
});

describe('formatP', () => {
	it('reads as a sentence fragment, with few digits for large p', () => {
		expect(formatP(0.43)).toBe('p = 0.43');
		expect(formatP(0.0312)).toBe('p = 0.03');
		expect(formatP(0.004)).toBe('p = 0.004');
		expect(formatP(0.0004)).toBe('p < 0.001');
		expect(formatP(0)).toBe('p < 0.001');
	});
});
