<script lang="ts">
	interface Props {
		/** 5th and 95th percentile of the cells' probabilities, and the regional average (all %). */
		p5: number;
		p95: number;
		mean: number | null;
	}

	let { p5, p95, mean }: Props = $props();

	const lo = $derived(Math.max(0, Math.min(100, p5)));
	const hi = $derived(Math.max(lo, Math.min(100, p95)));
</script>

<div class="spread" data-testid="spread-bar">
	<div class="track" aria-hidden="true">
		<span class="band" style:left="{lo}%" style:width="{Math.max(1.5, hi - lo)}%"></span>
		{#if mean !== null}<span class="dot" style:left="{Math.max(0, Math.min(100, mean))}%"
			></span>{/if}
	</div>
	<div class="scale" aria-hidden="true">
		<span>0%</span><span>50%</span><span>100%</span>
	</div>
</div>

<style>
	.track {
		position: relative;
		height: 10px;
		margin: 0 7px;
		background: var(--surface-2);
		border-radius: 5px;
	}
	.band {
		position: absolute;
		top: 0;
		bottom: 0;
		background: var(--accent);
		opacity: 0.4;
		border-radius: 5px;
	}
	.dot {
		position: absolute;
		top: -2px;
		width: 14px;
		height: 14px;
		margin-left: -7px;
		border-radius: 50%;
		background: var(--text);
		border: 2px solid var(--surface);
	}
	.scale {
		display: flex;
		justify-content: space-between;
		margin: 4px 0 0;
		font-size: 0.72rem;
		color: var(--muted);
		font-variant-numeric: tabular-nums;
	}
</style>
