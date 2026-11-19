<script lang="ts">
	import type { WarmingLevel } from '#lib/data/manifest.ts';
	import type { ProjectedProbability } from '#lib/data/points.ts';

	interface Props {
		levels: WarmingLevel[];
		values: ProjectedProbability[];
		baseline: number | null;
		baselineLabel: string;
	}

	let { levels, values, baseline, baselineLabel }: Props = $props();

	const rows = $derived(
		levels.map((lv, k) => ({ lv, v: values[k] })).filter((r) => r.v !== undefined)
	);
</script>

<ul class="future">
	{#if baseline !== null}
		<li>
			<div class="label"><strong>Today</strong> <span class="muted">({baselineLabel})</span></div>
			<div class="track" aria-hidden="true">
				<span class="dot base" style:left="{baseline}%"></span>
			</div>
			<div class="value">{Math.round(baseline)}%</div>
		</li>
	{/if}
	{#each rows as { lv, v } (lv.gwl)}
		<li>
			<div class="label">
				<strong>{lv.label} world</strong> <span class="muted">{lv.approx}</span>
			</div>
			<div class="track" aria-hidden="true">
				<span class="band" style:left="{v.p10}%" style:width="{Math.max(1, v.p90 - v.p10)}%"></span>
				<span class="dot" style:left="{v.median}%"></span>
			</div>
			<div class="value">
				{v.median}% <span class="muted">(likely range {v.p10}–{v.p90}%)</span>
				{#if !v.agree}<span class="disagree">
						Models disagree on the direction of change here.
					</span>{/if}
			</div>
		</li>
	{/each}
</ul>

<style>
	.future {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: 12px;
	}
	li {
		display: grid;
		gap: 4px;
		font-size: 0.88rem;
	}
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
		opacity: 0.35;
		border-radius: 5px;
	}
	.dot {
		position: absolute;
		top: -2px;
		width: 14px;
		height: 14px;
		margin-left: -7px;
		border-radius: 50%;
		background: var(--accent);
		border: 2px solid var(--surface);
	}
	.dot.base {
		background: var(--text);
	}
	.value {
		font-variant-numeric: tabular-nums;
	}
	.disagree {
		display: block;
		color: var(--warn);
		font-size: 0.8rem;
	}
</style>
