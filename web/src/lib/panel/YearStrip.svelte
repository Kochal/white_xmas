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

	/** The year whose details are shown; tap a cell or use the arrow keys. */
	let selected = $state<number | null>(null);
	let cellsEl: HTMLDivElement;
	const last = $derived(strip[strip.length - 1]?.year ?? 0);
	const focusYear = $derived(selected ?? last);
	const selectedCell = $derived(strip.find((c) => c.year === selected) ?? null);

	function select(year: number, focus = false) {
		const y = Math.max(first, Math.min(last, year));
		selected = y;
		if (focus) cellsEl?.querySelector<HTMLButtonElement>(`[data-year="${y}"]`)?.focus();
	}

	function onkeydown(e: KeyboardEvent) {
		const step: Record<string, number> = {
			ArrowLeft: -1,
			ArrowRight: 1,
			ArrowDown: -1,
			ArrowUp: 1,
			PageDown: -10,
			PageUp: 10
		};
		if (e.key in step) select(focusYear + step[e.key], true);
		else if (e.key === 'Home') select(first, true);
		else if (e.key === 'End') select(last, true);
		else return;
		e.preventDefault();
	}

	function title(c: YearCell): string {
		if (c.state === 'nodata') return `${c.year}: no data`;
		const d =
			c.depth === null ? '' : ` (${c.capped ? '≥ ' : ''}${Math.round(c.depth)} cm ${depthLabel})`;
		return `${c.year}: ${c.state === 'white' ? 'white' : 'green'}${d}`;
	}
</script>

<figure class="strip" data-testid="year-strip">
	<div class="cells" role="group" aria-label={summary} bind:this={cellsEl}>
		{#if window}
			<div
				class="win-overlay"
				style:left="{pct(Math.max(first, window.start))}%"
				style:width="{pct(window.end + 1) - pct(Math.max(first, window.start))}%"
			></div>
		{/if}
		{#each strip as c (c.year)}
			<button
				type="button"
				class="cell {c.state}"
				class:selected={selected === c.year}
				data-year={c.year}
				tabindex={c.year === focusYear ? 0 : -1}
				aria-label={title(c)}
				aria-pressed={selected === c.year}
				title={title(c)}
				onclick={() => select(c.year)}
				{onkeydown}
			></button>
		{/each}
	</div>
	<div class="ticks" aria-hidden="true">
		{#each ticks as y (y)}
			<span style:left="{pct(y + 0.5)}%">{y}</span>
		{/each}
	</div>
	<div class="detail" aria-live="polite" data-testid="year-detail">
		{#if selectedCell}
			<button
				type="button"
				class="step"
				aria-label="Previous year"
				disabled={selectedCell.year <= first}
				onclick={() => select(selectedCell.year - 1)}
			>
				‹
			</button>
			<span class="detail-text">{title(selectedCell)}</span>
			<button
				type="button"
				class="step"
				aria-label="Next year"
				disabled={selectedCell.year >= last}
				onclick={() => select(selectedCell.year + 1)}
			>
				›
			</button>
		{:else}
			<span class="muted">Tap a year, or use the arrow keys, for its details.</span>
		{/if}
	</div>
	<table class="visually-hidden">
		<caption>Snow at Christmas, year by year</caption>
		<thead>
			<tr>
				<th scope="col">Year</th><th scope="col">White or green</th><th scope="col">Snow depth</th>
			</tr>
		</thead>
		<tbody>
			{#each strip as c (c.year)}
				<tr>
					<th scope="row">{c.year}</th>
					<td>{c.state === 'nodata' ? 'no data' : c.state}</td>
					<td>
						{c.depth === null
							? '–'
							: `${c.capped ? '≥ ' : ''}${Math.round(c.depth)} cm ${depthLabel}`}
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
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
		padding: 0;
		border: 0;
		border-radius: 1.5px;
		background: none;
		cursor: pointer;
	}
	.cell:focus-visible,
	.cell.selected {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
		z-index: 1;
	}
	.detail {
		display: flex;
		align-items: center;
		gap: 6px;
		min-height: 30px;
		font-size: 0.85rem;
	}
	.detail-text {
		flex: 1;
		text-align: center;
		font-variant-numeric: tabular-nums;
	}
	.step {
		width: 30px;
		height: 30px;
		border: 1px solid var(--line);
		border-radius: 6px;
		background: var(--surface);
		color: var(--text);
		font-size: 1.1rem;
		line-height: 1;
		cursor: pointer;
	}
	.step:disabled {
		opacity: 0.4;
		cursor: default;
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
