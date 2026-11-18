/** Small numerical helpers: Student's t distribution via the regularized incomplete beta. */

function logGamma(x: number): number {
	// Lanczos approximation (g = 7, n = 9)
	const c = [
		0.99999999999980993, 676.5203681218851, -1259.1392167224028, 771.32342877765313,
		-176.61502916214059, 12.507343278686905, -0.13857109526572012, 9.9843695780195716e-6,
		1.5056327351493116e-7
	];
	if (x < 0.5) return Math.log(Math.PI / Math.sin(Math.PI * x)) - logGamma(1 - x);
	const xx = x - 1;
	let a = c[0];
	const t = xx + 7.5;
	for (let i = 1; i < 9; i++) a += c[i] / (xx + i);
	return 0.5 * Math.log(2 * Math.PI) + (xx + 0.5) * Math.log(t) - t + Math.log(a);
}

function betaContinuedFraction(a: number, b: number, x: number): number {
	const tiny = 1e-300;
	let c = 1;
	let d = 1 - ((a + b) * x) / (a + 1);
	if (Math.abs(d) < tiny) d = tiny;
	d = 1 / d;
	let h = d;
	for (let m = 1; m <= 300; m++) {
		const m2 = 2 * m;
		let aa = (m * (b - m) * x) / ((a + m2 - 1) * (a + m2));
		d = 1 + aa * d;
		if (Math.abs(d) < tiny) d = tiny;
		c = 1 + aa / c;
		if (Math.abs(c) < tiny) c = tiny;
		d = 1 / d;
		h *= d * c;
		aa = (-(a + m) * (a + b + m) * x) / ((a + m2) * (a + m2 + 1));
		d = 1 + aa * d;
		if (Math.abs(d) < tiny) d = tiny;
		c = 1 + aa / c;
		if (Math.abs(c) < tiny) c = tiny;
		d = 1 / d;
		const delta = d * c;
		h *= delta;
		if (Math.abs(delta - 1) < 1e-12) break;
	}
	return h;
}

/** Regularized incomplete beta function I_x(a, b). */
export function incompleteBeta(x: number, a: number, b: number): number {
	if (x <= 0) return 0;
	if (x >= 1) return 1;
	const front = Math.exp(
		logGamma(a + b) - logGamma(a) - logGamma(b) + a * Math.log(x) + b * Math.log(1 - x)
	);
	return x < (a + 1) / (a + b + 2)
		? (front * betaContinuedFraction(a, b, x)) / a
		: 1 - (front * betaContinuedFraction(b, a, 1 - x)) / b;
}

/** Two-sided p-value of a t statistic with `df` degrees of freedom. */
export function tTwoSidedP(t: number, df: number): number {
	if (!Number.isFinite(t)) return 0;
	return incompleteBeta(df / (df + t * t), df / 2, 0.5);
}

/** Quantile q (0.5 < q < 1) of Student's t distribution, by bisection. */
export function tQuantile(q: number, df: number): number {
	const target = 2 * (1 - q); // two-sided tail
	let lo = 0;
	let hi = 1000;
	for (let k = 0; k < 200; k++) {
		const mid = (lo + hi) / 2;
		if (tTwoSidedP(mid, df) > target) lo = mid;
		else hi = mid;
	}
	return (lo + hi) / 2;
}
