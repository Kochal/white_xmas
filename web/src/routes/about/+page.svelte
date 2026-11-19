<script lang="ts">
	import { onMount } from 'svelte';
	import { resolve } from '$app/paths';
	import Seo from '#lib/components/Seo.svelte';
	import { REPO_URL } from '#lib/config.ts';
	import { getDataSource } from '#lib/data/client.ts';
	import type { Manifest } from '#lib/data/manifest.ts';

	let manifest = $state.raw<Manifest | null>(null);

	onMount(() => {
		getDataSource()
			.then((ds) => (manifest = ds.manifest))
			.catch(() => {});
	});
</script>

<Seo
	title="About and credits · White Christmas"
	description="Who made this site, where the data comes from and how to credit it."
/>

<article class="prose">
	<h1>About</h1>
	<p>
		Will it be a white Christmas? This site answers the question with history rather than a
		forecast: how often there has been snow on the ground at Christmas, anywhere on Earth, since
		1950, how that has changed, and how it is likely to change in a warmer world.
	</p>
	<p>
		The numbers come from a reanalysis, not from a weather station near you. Each value describes a
		grid cell of about 9 km, and mountains and valleys inside a cell are averaged. Read the
		<a href={resolve('/methodology')}>methodology</a> for the details and the limits.
	</p>
	<p>
		The code and the data pipeline are open source on <a href={REPO_URL}>GitHub</a>. Corrections and
		ideas are welcome there.
	</p>

	<h2>Credits</h2>
	<dl>
		<dt>Climate data</dt>
		<dd>
			<a href="https://cds.climate.copernicus.eu/datasets/derived-era5-land-daily-statistics">
				ERA5-Land
			</a>
			from the Copernicus Climate Change Service (C3S), produced by ECMWF. Contains modified Copernicus
			Climate Change Service information; neither the European Commission nor ECMWF is responsible for
			any use that may be made of the Copernicus information or data it contains.
			<br /><span class="muted small">
				Muñoz-Sabater, J. et al. (2021): ERA5-Land: a state-of-the-art global reanalysis dataset for
				land applications. Earth System Science Data, 13, 4349–4383.
			</span>
		</dd>
		<dt>Climate projections</dt>
		<dd>
			CMIP6 climate models (World Climate Research Programme), used to estimate how the chance
			changes at +1.5, +2 and +3 °C of global warming.
		</dd>
		<dt>Place names</dt>
		<dd>
			<a href="https://www.geonames.org/">GeoNames</a>, licensed under
			<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>.
		</dd>
		<dt>Country boundaries</dt>
		<dd><a href="https://www.naturalearthdata.com/">Natural Earth</a> (public domain).</dd>
		<dt>Basemap</dt>
		<dd>
			<a href="https://openfreemap.org/">OpenFreeMap</a>, ©
			<a href="https://openmaptiles.org/">OpenMapTiles</a>, data ©
			<a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>.
		</dd>
		<dt>Software</dt>
		<dd>
			<a href="https://maplibre.org/">MapLibre GL JS</a>,
			<a href="https://protomaps.com/docs/pmtiles">PMTiles</a>,
			<a href="https://svelte.dev/">SvelteKit</a>.
		</dd>
	</dl>

	{#if manifest}
		<h2>This dataset</h2>
		<p class="muted small">
			Data version {manifest.data_version} (build {manifest.build_hash}), {manifest.years
				.first}–{manifest.years.last}, threshold {manifest.threshold_cm} cm.
			{manifest.attribution}
		</p>
	{/if}
</article>

<style>
	dl {
		display: grid;
		grid-template-columns: minmax(120px, max-content) 1fr;
		gap: 10px 18px;
	}
	dt {
		font-weight: 600;
	}
	dd {
		margin: 0;
	}
	.small {
		font-size: 0.85rem;
	}
	@media (max-width: 520px) {
		dl {
			grid-template-columns: 1fr;
			gap: 2px;
		}
		dd {
			margin-bottom: 10px;
		}
	}
</style>
