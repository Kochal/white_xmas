<script lang="ts">
	import type { Colormap, Layer } from '#lib/data/manifest.ts';
	import { inTenYears, signed } from '#lib/format/format.ts';

	interface Props {
		layer: Layer | null;
		colormap: Colormap | null;
		title: string;
		subtitle: string;
		glaciers: boolean;
	}

	let { layer, colormap, title, subtitle, glaciers }: Props = $props();
	let more = $state(false);

	const gradient = $derived.by(() => {
		if (!colormap) return '';
		const [lo, hi] = colormap.domain;
		const stops = colormap.stops.map(
			([v, c]) => `${c} ${(((v - lo) / (hi - lo)) * 100).toFixed(1)}%`
		);
		return `linear-gradient(to right, ${stops.join(', ')})`;
	});

	interface Tick {
		pos: number;
		label: string;
	}

	const ticks = $derived.by((): Tick[] => {
		if (!colormap) return [];
		const [lo, hi] = colormap.domain;
		const at = (v: number) => ((v - lo) / (hi - lo)) * 100;
		if (layer?.kind === 'probability' || layer?.kind === 'projection')
			return [0, 25, 50, 75, 100].map((v) => ({ pos: at(v), label: `${v}%` }));
		const mid = (lo + hi) / 2;
		return [lo, mid, hi].map((v) => ({
			pos: at(v),
			label: v === mid ? '0' : `${signed(v, 0)}${v === hi ? '+' : ''}`
		}));
	});

	const caption = $derived.by(() => {
		if (!layer) return '';
		switch (layer.kind) {
			case 'probability':
			case 'projection':
				return `Share of years with snow on the ground. 30% means ${inTenYears(30)}.`;
			case 'change':
				return 'Percentage points between the two periods. Brown: fewer white Christmases; blue: more.';
			case 'trend':
				return 'Percentage points per decade (linear trend). Brown: declining; blue: rising.';
		}
	});
</script>

<section class="legend" class:more aria-label="Legend">
	<div class="head">
		<div class="titles">
			<h2>{title}</h2>
			{#if subtitle}<p class="sub">{subtitle}</p>{/if}
		</div>
		<button class="more-toggle" aria-expanded={more} onclick={() => (more = !more)}>
			{more ? 'Less' : 'Key'}
		</button>
	</div>
	{#if colormap && layer}
		<div class="bar" style:background={gradient} aria-hidden="true"></div>
		<div class="ticks" aria-hidden="true">
			{#each ticks as t (t.pos)}
				<span style:left="{t.pos}%">{t.label}</span>
			{/each}
		</div>
		{#if layer.kind === 'probability' || layer.kind === 'projection'}
			<div class="plain" aria-hidden="true">
				<span>never</span><span>1 in 2 years</span><span>every year</span>
			</div>
		{/if}
		<p class="unit">{caption}</p>
		<ul class="keys">
			{#if layer.kind === 'trend' && layer.hatch_insignificant}
				<li><span class="swatch hatch-light"></span> Hatched: not statistically significant</li>
			{/if}
			{#if glaciers}
				<li><span class="swatch glacier"></span> Glacier: snow every year, not coloured</li>
			{/if}
			<li><span class="swatch none"></span> No colour: ocean or no data</li>
		</ul>
	{:else}
		<p class="unit">There's no map layer for this combination. Click a place to see its numbers.</p>
	{/if}
</section>

<style>
	.legend {
		padding: 10px 12px 8px;
		background: var(--surface);
		border-radius: var(--radius);
		box-shadow: var(--shadow);
		font-size: 0.82rem;
		width: 280px;
		max-width: calc(100vw - 32px);
	}
	.head {
		display: flex;
		align-items: flex-start;
		gap: 8px;
	}
	.more-toggle {
		display: none;
		margin-left: auto;
		padding: 1px 8px;
		font: inherit;
		font-size: 0.75rem;
		color: var(--accent);
		background: var(--accent-soft);
		border: 0;
		border-radius: 999px;
		cursor: pointer;
	}
	@media (max-width: 720px) {
		.legend {
			width: 230px;
			padding: 8px 10px 6px;
			font-size: 0.75rem;
		}
		.more-toggle {
			display: inline-block;
		}
		.legend:not(.more) .unit,
		.legend:not(.more) .keys,
		.legend:not(.more) .plain {
			display: none;
		}
	}
	.titles {
		flex: 1;
		min-width: 0;
		margin-bottom: 6px;
	}
	.sub {
		margin: 1px 0 0;
		color: var(--muted);
		font-size: 0.78rem;
	}
	h2 {
		margin: 0;
		font-size: 0.85rem;
		font-weight: 650;
	}
	.bar {
		height: 12px;
		border-radius: 3px;
		border: 1px solid var(--line);
	}
	.ticks {
		position: relative;
		height: 16px;
		margin: 2px 8px 0;
		color: var(--muted);
		font-variant-numeric: tabular-nums;
	}
	.ticks span {
		position: absolute;
		transform: translateX(-50%);
		white-space: nowrap;
	}
	.plain {
		display: flex;
		justify-content: space-between;
		color: var(--text);
		font-size: 0.78rem;
	}
	.unit {
		margin: 4px 0 6px;
		color: var(--muted);
		line-height: 1.35;
	}
	.keys {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: 3px;
		color: var(--muted);
	}
	.keys li {
		display: flex;
		align-items: center;
		gap: 6px;
	}
	.swatch {
		display: inline-block;
		flex: none;
		width: 18px;
		height: 12px;
		border: 1px solid var(--line);
		border-radius: 2px;
	}
	.glacier {
		background: repeating-linear-gradient(135deg, #7d8590 0 2px, #d5d9e0 2px 6px);
	}
	.hatch-light {
		background: repeating-linear-gradient(135deg, #969696 0 2px, #f4f2ee 2px 6px);
	}
	.none {
		background: transparent;
		border-style: dashed;
	}
</style>
