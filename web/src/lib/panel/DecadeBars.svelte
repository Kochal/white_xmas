<script lang="ts">
	import type { DecadeProbability } from '#lib/data/derive.ts';

	interface Props {
		decades: DecadeProbability[];
	}

	let { decades }: Props = $props();

	const BAR = 34;
	const GAP = 12;
	const H = 70;
	const width = $derived(decades.length * (BAR + GAP) - GAP);
	const short = (d: DecadeProbability) =>
		`${String(d.window.start).slice(2)}–${String(d.window.end).slice(2)}`;
	const summary = $derived(
		decades
			.map((d) => `${d.window.label}: ${d.p === null ? 'no data' : `${Math.round(d.p)}%`}`)
			.join('; ')
	);
</script>

<svg
	viewBox="-2 -16 {width + 4} {H + 34}"
	role="img"
	aria-label="White Christmas probability per decade. {summary}"
>
	{#each [50, 100] as g (g)}
		<line x1="-2" x2={width + 2} y1={H - (g / 100) * H} y2={H - (g / 100) * H} class="grid" />
		<text x={width + 2} y={H - (g / 100) * H - 3} text-anchor="end" class="label">{g}%</text>
	{/each}
	<line x1="-2" x2={width + 2} y1={H} y2={H} class="axis" />
	{#each decades as d, k (d.window.id)}
		{@const x = k * (BAR + GAP)}
		{@const h = d.p === null ? 0 : Math.max(1, (d.p / 100) * H)}
		<rect {x} y={H - h} width={BAR} height={h} rx="2" class="bar">
			<title>
				{d.window.label}: {d.p === null
					? 'no data'
					: `${d.p.toFixed(0)}% (${d.nWhite} of ${d.nValid} years)`}
			</title>
		</rect>
		<text x={x + BAR / 2} y={H - h - 4} text-anchor="middle" class="value">
			{d.p === null ? '–' : `${Math.round(d.p)}%`}
		</text>
		<text x={x + BAR / 2} y={H + 14} text-anchor="middle" class="label">{short(d)}</text>
	{/each}
</svg>

<style>
	svg {
		display: block;
		width: 100%;
		max-width: 420px;
		height: auto;
	}
	.bar {
		fill: var(--accent);
		opacity: 0.85;
	}
	.grid {
		stroke: var(--line);
		stroke-dasharray: 2 3;
	}
	.axis {
		stroke: var(--line);
	}
	text {
		font-family: var(--font);
	}
	.value {
		font-size: 11px;
		fill: var(--text);
		font-variant-numeric: tabular-nums;
	}
	.label {
		font-size: 10.5px;
		fill: var(--muted);
	}
</style>
