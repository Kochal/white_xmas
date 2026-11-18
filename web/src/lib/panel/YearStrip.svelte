<script lang="ts">
	import type { YearCell } from '#lib/data/derive.ts';

	interface Props {
		strip: YearCell[];
		/** Highlighted window (e.g. the selected period). */
		window?: { start: number; end: number } | null;
		depthLabel: string;
	}

	let { strip, window = null, depthLabel }: Props = $props();

	const first = $derived(strip[0]?.year ?? 0);
	const n = $derived(strip.length || 1);
	const counts = $derived({
		white: strip.filter((c) => c.state === 'white').length,
		green: strip.filter((c) => c.state === 'green').length,
		nodata: strip.filter((c) => c.state === 'nodata').length
	});
	const ticks = $derived(strip.filter((c) => c.year % 10 === 0).map((c) => c.year));
	const summary = $derived(
		`Year strip, ${first} to ${first + strip.length - 1}: ${counts.white} white years, ${counts.green} green years` +
			(counts.nodata ? `, ${counts.nodata} without data` : '')
	);
	const pct = (year: number) => ((year - first) / n) * 100;

	function title(c: YearCell): string {
		if (c.state === 'nodata') return `${c.year}: no data`;
		const d =
			c.depth === null ? '' : ` (${c.capped ? '≥ ' : ''}${Math.round(c.depth)} cm ${depthLabel})`;
		return `${c.year}: ${c.state === 'white' ? 'white' : 'green'}${d}`;
	}
</script>

<figure class="strip" data-testid="year-strip">
	<div class="cells" role="img" aria-label={summary}>
		{#if window}
			<div
				class="win-overlay"
				style:left="{pct(Math.max(first, window.start))}%"
				style:width="{pct(window.end + 1) - pct(Math.max(first, window.start))}%"
			></div>
		{/if}
		{#each strip as c (c.year)}
			<span class="cell {c.state}" title={title(c)}></span>
		{/each}
	</div>
	<div class="ticks" aria-hidden="true">
		{#each ticks as y (y)}
			<span style:left="{pct(y + 0.5)}%">{y}</span>
		{/each}
	</div>
	<figcaption>
		<span><i class="key white"></i>white ({counts.white})</span>
		<span><i class="key green"></i>green ({counts.green})</span>
		{#if counts.nodata}<span><i class="key nodata"></i>no data ({counts.nodata})</span>{/if}
		{#if window}<span><i class="key window"></i>selected period</span>{/if}
	</figcaption>
</figure>

<style>
	.strip {
		margin: 0;
	}
	.cells {
		position: relative;
		display: flex;
		gap: 1px;
		height: 34px;
		padding: 3px 0;
	}
	.win-overlay {
		position: absolute;
		top: 0;
		bottom: 0;
		background: var(--accent-soft);
		border-radius: 3px;
		box-shadow: inset 0 0 0 1px var(--accent);
	}
	.cell {
		position: relative;
		flex: 1 1 0;
		min-width: 0;
		border-radius: 1.5px;
	}
	.cell.white {
		background: var(--white-year);
		box-shadow: inset 0 0 0 1px var(--white-year-edge);
	}
	.cell.green {
		background: var(--green-year);
	}
	.cell.nodata {
		background: repeating-linear-gradient(135deg, var(--nodata) 0 2px, transparent 2px 4px);
	}
	.ticks {
		position: relative;
		height: 16px;
		font-size: 11px;
		color: var(--muted);
		font-variant-numeric: tabular-nums;
	}
	.ticks span {
		position: absolute;
		transform: translateX(-50%);
	}
	figcaption {
		display: flex;
		flex-wrap: wrap;
		gap: 4px 14px;
		margin-top: 4px;
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
		width: 10px;
		height: 12px;
		border-radius: 2px;
	}
	.key.white {
		background: var(--white-year);
		box-shadow: inset 0 0 0 1px var(--white-year-edge);
	}
	.key.green {
		background: var(--green-year);
	}
	.key.nodata {
		background: var(--nodata);
	}
	.key.window {
		width: 16px;
		background: var(--accent-soft);
		box-shadow: inset 0 0 0 1px var(--accent);
	}
</style>
