<script lang="ts">
	import Seo from '#lib/components/Seo.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
</script>

<Seo
	title="Methodology · White Christmas"
	description="How the white Christmas statistics are computed from ERA5-Land reanalysis: definitions, windows, trends, projections and their limits."
/>

<article class="prose">
	<h1>{data.html ? (data.title ?? 'Methodology') : 'Methodology'}</h1>
	{#if data.html}
		<!-- eslint-disable-next-line svelte/no-at-html-tags -- trusted Markdown from this repository, rendered at build time -->
		{@html data.html}
	{:else}
		<p>
			The full methodology is being written. In short: for every 9 km land cell on Earth, the site
			uses the daily-mean snow depth on 24, 25 and 26 December from the ERA5-Land reanalysis, 1950
			to the latest December, and counts the years with at least 1 cm of snow on the ground.
		</p>
		<h2>Definitions</h2>
		<ul>
			<li><strong>Snow on Christmas Day</strong> (default): at least 1 cm on 25 December.</li>
			<li>
				<strong>Snow on all three days</strong>: at least 1 cm on each of 24, 25 and 26 December,
				the rule used by the German weather service (DWD).
			</li>
			<li>
				<strong>Snow on any of the three days</strong>: at least 1 cm on 24, 25 or 26 December.
			</li>
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
