<script lang="ts">
	import { onMount } from 'svelte';
	import { DATA_BASE } from '#lib/config.ts';
	import { loadManifest, type Manifest } from '#lib/data/manifest.ts';

	let manifest = $state<Manifest | null>(null);
	let error = $state<string | null>(null);

	onMount(() => {
		loadManifest(DATA_BASE)
			.then((m) => (manifest = m))
			.catch((e: Error) => (error = e.message));
	});
</script>

<svelte:head>
	<title>White Christmas</title>
</svelte:head>

<div class="prose">
	<h1>How likely is a white Christmas where you live?</h1>
	<p>The map is on its way. This page checks that the data loads.</p>
	{#if manifest}
		<p data-testid="data-status">
			Data version {manifest.data_version}: {manifest.layers.length} map layers,
			{manifest.years.first}–{manifest.years.last}.
		</p>
	{:else if error}
		<p role="alert">{error}</p>
	{:else}
		<p>Loading data…</p>
	{/if}
</div>
