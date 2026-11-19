<script lang="ts">
	import { onMount } from 'svelte';
	import Seo from '#lib/components/Seo.svelte';
	import { getDataSource } from '#lib/data/client.ts';
	import { thresholdNote, type Manifest } from '#lib/data/manifest.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	// The threshold and definitions come from the data (manifest.json), which arrives at
	// deploy time, so they are filled in here rather than at build time.
	let manifest = $state.raw<Manifest | null>(null);
	const note = $derived(manifest ? thresholdNote(manifest) : null);

	onMount(() => {
		getDataSource()
			.then((ds) => (manifest = ds.manifest))
			.catch(() => {});
	});
</script>

<Seo
	title="Methodology · White Christmas"
	description="How the white Christmas statistics are computed from ERA5-Land reanalysis: definitions, windows, trends, projections and their limits."
/>

<article class="prose">
	<h1>{data.html ? (data.title ?? 'Methodology') : 'Methodology'}</h1>

	{#if manifest}
		<aside class="dataset" data-testid="dataset-threshold">
			{#if manifest.thresholds.length > 1}
				<p>
					<strong>This dataset</strong> ({manifest.data_version}) can be shown with two snow-depth
					thresholds. Switch between them above the map; the place panel shows both values.
				</p>
				<ul>
					{#each manifest.thresholds as t (t.id)}
						<li>
							<strong>{t.label}</strong>{t.default ? ' (default)' : ''}: {t.description ||
								`daily-mean snow depth of at least ${t.cm} cm in ERA5-Land.`}
							{#if thresholdNote(manifest, t)}{thresholdNote(manifest, t)}{/if}
						</li>
					{/each}
				</ul>
			{:else}
				<p>
					<strong>This dataset</strong> ({manifest.data_version}) counts a day as snowy when the
					daily-mean snow depth in ERA5-Land is at least
					<strong>{manifest.threshold_cm} cm</strong>.
					{#if note}{note}{/if}
				</p>
			{/if}
			<p class="defs-title">Definitions (with the default threshold):</p>
			<ul>
				{#each manifest.definitions as d (d.id)}
					<li><strong>{d.label}</strong>: {d.description}</li>
				{/each}
			</ul>
		</aside>
	{/if}

	{#if data.html}
		<!-- eslint-disable-next-line svelte/no-at-html-tags -- trusted Markdown from this repository, rendered at build time -->
		{@html data.html}
	{:else}
		<p>
			The full methodology is being written. In short: for every 9 km land cell on Earth, the site
			uses the daily-mean snow depth on 24, 25 and 26 December from the ERA5-Land reanalysis, 1950
			to the latest December, and counts the years in which the snow depth reaches the dataset's
			threshold (see above).
		</p>
		<h2>Definitions</h2>
		<ul>
			<li>
				<strong>Snow on Christmas Day</strong> (default): the threshold is reached on 25 December.
			</li>
			<li>
				<strong>Snow on all three days</strong>: reached on each of 24, 25 and 26 December, the rule
				used by the German weather service (DWD).
			</li>
			<li><strong>Snow on any of the three days</strong>: reached on 24, 25 or 26 December.</li>
		</ul>
		<h2>What a reanalysis can and cannot tell you</h2>
		<p>
			ERA5-Land combines weather observations with a model to give a consistent picture everywhere,
			but each value is the average over a grid cell of about 9 km. It smooths mountains and valleys
			and is not a measurement in your garden. Probabilities from a few decades of yes/no years are
			uncertain, and trends more so; the site says so where it matters.
		</p>
	{/if}
</article>

<style>
	.dataset {
		margin: 0 0 1.5rem;
		padding: 10px 14px;
		background: var(--accent-soft);
		border-radius: 8px;
		font-size: 0.92rem;
	}
	.dataset p {
		margin: 0 0 6px;
	}
	.defs-title {
		margin-top: 8px !important;
	}
	.dataset ul {
		margin: 0;
		padding-left: 1.2rem;
	}
</style>
