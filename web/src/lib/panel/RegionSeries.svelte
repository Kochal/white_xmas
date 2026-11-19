<script lang="ts">
	import { seriesFit } from '#lib/data/region-view.ts';
	import { formatPct } from '#lib/format/format.ts';

	interface Props {
		/** % of the region that was white, per year from `firstYear`. */
		series: (number | null)[];
		firstYear: number;
		/** Highlighted window (the headline's period). */
		window?: { start: number; end: number } | null;
	}

	let { series, firstYear, window = null }: Props = $props();

	const W = 320;
	const H = 92;
	const PAD = { l: 30, r: 6, t: 8, b: 18 };
	const lastYear = $derived(firstYear + series.length - 1);
	const known = $derived(series.filter((v): v is number => v !== null));
	/** Axis top: 100 % for snowy regions, a tighter scale for regions where it rarely snows. */
	const top = $derived(
		Math.min(100, Math.max(20, Math.ceil(Math.max(0, ...known) / 10) * 10 + 10))
	);
	const x = (k: number) => PAD.l + (k / Math.max(1, series.length - 1)) * (W - PAD.l - PAD.r);
	const y = (v: number) => PAD.t + (1 - Math.min(v, top) / top) * (H - PAD.t - PAD.b);

	/** Runs of consecutive years with data, so a gap is a gap, not a line through it. */
	const runs = $derived.by(() => {
		const out: { k: number; v: number }[][] = [];
		let cur: { k: number; v: number }[] = [];
		series.forEach((v, k) => {
			if (v === null) {
				if (cur.length) out.push(cur);
				cur = [];
			} else cur.push({ k, v });
		});
		if (cur.length) out.push(cur);
		return out;
	});
	const path = (run: { k: number; v: number }[]) =>
		run.map((p, i) => `${i ? 'L' : 'M'}${x(p.k).toFixed(1)} ${y(p.v).toFixed(1)}`).join('');
	const fit = $derived(seriesFit(series));
	const ticks = $derived(
		Array.from({ length: series.length }, (_, k) => firstYear + k).filter((yr) => yr % 10 === 0)
	);
	const winX = $derived(
		window
			? {
					x0: x(Math.max(0, window.start - firstYear) - 0.5),
					x1: x(Math.min(series.length - 1, window.end - firstYear) + 0.5)
				}
			: null
	);
	const gridValues = $derived([0, top / 2, top]);
	const summary = $derived(
		known.length
			? `Share of the region with snow on the ground at Christmas, ${firstYear} to ${lastYear}: ` +
					`from ${formatPct(Math.min(...known))} to ${formatPct(Math.max(...known))} a year, ` +
					`${formatPct(known.reduce((a, b) => a + b, 0) / known.length)} on average.`
			: 'No yearly values for this region.'
	);
</script>

<figure class="series" data-testid="region-series">
	<svg viewBox="0 0 {W} {H}" role="img" aria-label={summary}>
		{#if winX}
			<rect
				class="win"
				x={winX.x0}
				y={PAD.t}
				width={winX.x1 - winX.x0}
				height={H - PAD.t - PAD.b}
				rx="2"
			/>
		{/if}
		{#each gridValues as g (g)}
			<line class="grid" x1={PAD.l} x2={W - PAD.r} y1={y(g)} y2={y(g)} />
			<text class="label" x={PAD.l - 4} y={y(g) + 3.5} text-anchor="end">{Math.round(g)}%</text>
		{/each}
		{#each ticks as yr (yr)}
			<text class="label" x={x(yr - firstYear)} y={H - 4} text-anchor="middle">{yr}</text>
		{/each}
		{#each runs as run, i (i)}
			{#if run.length === 1}
				<circle class="dot" cx={x(run[0].k)} cy={y(run[0].v)} r="1.6" />
			{:else}
				<path class="line" d={path(run)} />
			{/if}
		{/each}
		{#if fit}
			<line
				class="fit"
				x1={x(0)}
				x2={x(series.length - 1)}
				y1={y(fit.at(0))}
				y2={y(fit.at(series.length - 1))}
			/>
		{/if}
	</svg>
	<table class="visually-hidden">
		<caption>Share of the region with snow on the ground at Christmas, by year</caption>
		<thead>
			<tr><th scope="col">Year</th><th scope="col">Share of the region</th></tr>
		</thead>
		<tbody>
			{#each series as v, k (k)}
				<tr>
					<th scope="row">{firstYear + k}</th><td>{v === null ? 'no data' : formatPct(v, 1)}</td>
				</tr>
			{/each}
		</tbody>
	</table>
	<figcaption>
		<span><i class="key line"></i>share of the region that was white</span>
		{#if fit}<span><i class="key fit"></i>fitted trend</span>{/if}
		{#if winX}<span><i class="key window"></i>selected period</span>{/if}
	</figcaption>
</figure>

<style>
	.series {
		margin: 0;
	}
	svg {
		display: block;
		width: 100%;
		max-width: 420px;
		height: auto;
	}
	text {
		font-family: var(--font);
	}
	.label {
		font-size: 10px;
		fill: var(--muted);
		font-variant-numeric: tabular-nums;
	}
	.grid {
		stroke: var(--line);
		stroke-dasharray: 2 3;
	}
	.line {
		fill: none;
		stroke: var(--accent);
		stroke-width: 1.6;
		stroke-linejoin: round;
	}
	.dot {
		fill: var(--accent);
	}
	.fit {
		stroke: var(--text);
		stroke-width: 1.4;
		stroke-dasharray: 5 3;
	}
	.win {
		fill: var(--accent-soft);
	}
	figcaption {
		display: flex;
		flex-wrap: wrap;
		gap: 2px 14px;
		margin-top: 2px;
		font-size: 0.8rem;
		color: var(--muted);
	}
	figcaption span {
		display: inline-flex;
		align-items: center;
		gap: 5px;
	}
	.key {
		display: inline-block;
		width: 16px;
		height: 0;
		border-top: 2px solid var(--accent);
	}
	.key.fit {
		border-top: 2px dashed var(--text);
	}
	.key.window {
		height: 10px;
		border: 0;
		background: var(--accent-soft);
		box-shadow: inset 0 0 0 1px var(--accent);
	}
</style>
