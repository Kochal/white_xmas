<script lang="ts">
	import { onMount } from 'svelte';
	import Seo from '#lib/components/Seo.svelte';
	import { DOWNLOADS_URL, REPO_URL } from '#lib/config.ts';
	import { getDataSource } from '#lib/data/client.ts';
	import type { Manifest } from '#lib/data/manifest.ts';

	let manifest = $state.raw<Manifest | null>(null);

	const releaseUrl = $derived(
		manifest && !manifest.data_version.includes('fixture')
			? `${REPO_URL}/releases/tag/data-${manifest.data_version}`
			: null
	);

	onMount(() => {
		getDataSource()
			.then((ds) => (manifest = ds.manifest))
			.catch(() => {});
	});
</script>

<Seo
	title="Downloads · White Christmas"
	description="Download the white Christmas data: Cloud Optimized GeoTIFFs, the snow cube and a CSV for cities, under CC BY 4.0."
/>

<article class="prose">
	<h1>Downloads</h1>
	<p>
		Everything shown on this site can be downloaded as open data, for GIS users, scientists and
		journalists. The files are attached to the project's GitHub Releases.
	</p>
	<p class="cta">
		<a class="button" href={releaseUrl ?? DOWNLOADS_URL}>
			{releaseUrl ? `Data release ${manifest?.data_version}` : 'All releases'}
		</a>
		{#if manifest}
			<span class="muted small">
				Data version {manifest.data_version}, built {new Date(manifest.built).toLocaleDateString(
					'en',
					{
						dateStyle: 'medium'
					}
				)}, covering {manifest.years.first}–{manifest.years.last}.
			</span>
		{/if}
	</p>

	<h2>What's in a release</h2>
	<div class="table-wrap">
		<table>
			<thead>
				<tr><th>File</th><th>Format</th><th>Use it for</th></tr>
			</thead>
			<tbody>
				<tr>
					<td>Probability, change and trend maps</td>
					<td>Cloud Optimized GeoTIFF (Float32, NaN for no data)</td>
					<td>GIS analysis at the native 0.1° resolution</td>
				</tr>
				<tr>
					<td>Snow cube</td>
					<td>Zarr: snow depth (cm) per year and day, 24–26 December</td>
					<td>Your own definitions, thresholds and windows</td>
				</tr>
				<tr>
					<td>Cities</td>
					<td>CSV</td>
					<td>Spreadsheets and stories: values per place, as in the search</td>
				</tr>
				<tr>
					<td>Web data bundle</td>
					<td><code>whitexmas-web-data-&lt;version&gt;.tar.gz</code></td>
					<td>Exactly the files this site reads (map tiles, point data, JSON)</td>
				</tr>
			</tbody>
		</table>
	</div>

	<h2>Licence and citation</h2>
	<p>
		The data is licensed under
		<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>. It contains modified
		Copernicus Climate Change Service information; neither the European Commission nor ECMWF is
		responsible for any use that may be made of the Copernicus information or data it contains.
		Place names come from GeoNames (CC BY 4.0). The code is on
		<a href={REPO_URL}>GitHub</a> under the MIT licence.
	</p>
	{#if manifest?.attribution}
		<p class="muted small">{manifest.attribution}</p>
	{/if}
</article>

<style>
	.cta {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 8px 14px;
	}
	.button {
		display: inline-block;
		padding: 9px 16px;
		color: var(--surface);
		background: var(--accent);
		border-radius: 8px;
		text-decoration: none;
		font-weight: 600;
	}
	.small {
		font-size: 0.85rem;
	}
</style>
