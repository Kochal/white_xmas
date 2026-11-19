<script lang="ts">
	import { onMount } from 'svelte';
	import { resolve } from '$app/paths';
	import Seo from '#lib/components/Seo.svelte';
	import { getDataSource } from '#lib/data/client.ts';
	import type { Manifest } from '#lib/data/manifest.ts';
	import type { Place, PlacesMeta } from '#lib/data/places.ts';
	import type { Region } from '#lib/data/regions.ts';
	import { formatPct, formatPopulation, formatPp, inTenYears } from '#lib/format/format.ts';
	import { declines, snowiest } from '#lib/rankings.ts';

	let manifest = $state.raw<Manifest | null>(null);
	let places = $state.raw<Place[]>([]);
	let meta = $state.raw<PlacesMeta | null>(null);
	let regions = $state.raw<Region[]>([]);
	let error = $state<string | null>(null);
	let minPop = $state(1_000_000);

	const POP_OPTIONS = [
		{ value: 100_000, label: '100,000+' },
		{ value: 500_000, label: '500,000+' },
		{ value: 1_000_000, label: '1 million+' }
	];

	const top = $derived(snowiest(places, minPop, 25));
	const drops = $derived(declines(places, minPop, 25));
	/** Countries that used to have white Christmases, biggest decline first. */
	const regionRows = $derived(
		regions
			.filter((r) => r.change !== null && r.p_then !== null && r.p_then >= 10)
			.sort((a, b) => a.change! - b.change!)
			.slice(0, 25)
	);
	const allRegions = $derived(
		[...regions].sort((a, b) => a.name.localeCompare(b.name, 'en', { sensitivity: 'base' }))
	);
	const winLabel = (id: string | undefined) =>
		manifest?.windows.find((w) => w.id === id)?.label ?? id?.replace('_', '–') ?? '';
	const nowLabel = $derived(winLabel(meta?.windows.p_now));
	const thenLabel = $derived(winLabel(meta?.windows.p_then));
	/** places.json values are for the default threshold (contract v1.5). */
	const thresholdLabel = $derived(
		manifest && manifest.thresholds.length > 1
			? ` (${(manifest.thresholds.find((t) => t.default) ?? manifest.thresholds[0]).label.toLowerCase()})`
			: ''
	);
	const defLabel = $derived(
		manifest?.definitions.find((d) => d.id === meta?.definition)?.label ?? 'Snow on Christmas Day'
	);

	const countryName = (() => {
		try {
			const dn = new Intl.DisplayNames(['en'], { type: 'region' });
			return (c: string) => (c ? (dn.of(c) ?? c) : '');
		} catch {
			return (c: string) => c;
		}
	})();

	function mapLink(p: Place): string {
		const q = new URLSearchParams({
			map: `8/${p.lat.toFixed(4)}/${p.lon.toFixed(4)}`,
			at: `${p.lat.toFixed(4)},${p.lon.toFixed(4)}`,
			place: p.name
		});
		return `${resolve('/')}?${q}`;
	}

	onMount(async () => {
		try {
			const ds = await getDataSource();
			manifest = ds.manifest;
			const [p, r] = await Promise.all([ds.places(), ds.regions().catch(() => [])]);
			places = p.places;
			meta = p.meta;
			regions = r;
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	});
</script>

<Seo
	title="Rankings: the snowiest cities at Christmas, and the biggest declines · White Christmas"
	description="Which big cities most often have snow on the ground at Christmas, and where white Christmases have become rarer since 1961–1990."
/>

<div class="prose wide">
	<h1>Rankings</h1>
	<p class="lede">
		{defLabel}{thresholdLabel}, for places with at least
		<label class="inline">
			<span class="visually-hidden">Minimum population</span>
			<select bind:value={minPop}>
				{#each POP_OPTIONS as o (o.value)}
					<option value={o.value}>{o.label}</option>
				{/each}
			</select>
		</label>
		people. Each value is the 9 km grid cell the place sits in, so mountain towns and valley cities can
		differ from their surroundings.
	</p>

	{#if error}
		<p role="alert">The rankings couldn't be loaded: {error}</p>
	{:else if !places.length}
		<p class="muted" aria-live="polite">Loading…</p>
	{:else}
		<h2 id="snowiest">Snowiest big cities, {nowLabel}</h2>
		<div class="table-wrap">
			<table aria-labelledby="snowiest">
				<thead>
					<tr>
						<th scope="col">#</th>
						<th scope="col">Place</th>
						<th scope="col" class="num">Chance</th>
						<th scope="col" class="hide-narrow">In plain words</th>
					</tr>
				</thead>
				<tbody>
					{#each top as p, k (p.name + p.lat + p.lon)}
						<tr>
							<td class="rank">{k + 1}</td>
							<td>
								<a href={mapLink(p)}>{p.name}</a>
								<span class="muted small">
									{countryName(p.country)} · {formatPopulation(p.pop)}
								</span>
							</td>
							<td class="num"><strong>{formatPct(p.p_now)}</strong></td>
							<td class="hide-narrow muted">{inTenYears(p.p_now)}</td>
						</tr>
					{:else}
						<tr><td colspan="4" class="muted">No places of this size in the data.</td></tr>
					{/each}
				</tbody>
			</table>
		</div>

		<h2 id="declines">Largest declines, {thenLabel} → {nowLabel}</h2>
		<p class="muted small">
			Places that had a white Christmas in at least 1 in 10 years in {thenLabel}, sorted by the
			change in percentage points (pp).
		</p>
		<div class="table-wrap">
			<table aria-labelledby="declines">
				<thead>
					<tr>
						<th scope="col">#</th>
						<th scope="col">Place</th>
						<th scope="col" class="num">{thenLabel}</th>
						<th scope="col" class="num">{nowLabel}</th>
						<th scope="col" class="num">Change</th>
					</tr>
				</thead>
				<tbody>
					{#each drops as p, k (p.name + p.lat + p.lon)}
						<tr>
							<td class="rank">{k + 1}</td>
							<td>
								<a href={mapLink(p)}>{p.name}</a>
								<span class="muted small">{countryName(p.country)}</span>
							</td>
							<td class="num">{formatPct(p.p_then)}</td>
							<td class="num">{formatPct(p.p_now)}</td>
							<td class="num"><strong>{formatPp(p.p_now! - p.p_then!, 'pp', 0)}</strong></td>
						</tr>
					{:else}
						<tr><td colspan="5" class="muted">No declines among places of this size.</td></tr>
					{/each}
				</tbody>
			</table>
		</div>

		{#if regions.length}
			<h2 id="countries">By country</h2>
			<p class="muted small">
				Area-weighted averages over each country's land, glaciers excluded. The table shows the 25
				largest declines among countries that had a white Christmas in at least 1 in 10 years in
				{thenLabel}.
			</p>
			{#snippet regionTable(rows: Region[], label: string)}
				<div class="table-wrap">
					<table aria-label={label}>
						<thead>
							<tr>
								<th scope="col">Country</th>
								<th scope="col" class="num">{thenLabel}</th>
								<th scope="col" class="num">{nowLabel}</th>
								<th scope="col" class="num">Change</th>
							</tr>
						</thead>
						<tbody>
							{#each rows as r, k (`${r.iso_a3}-${r.name}-${k}`)}
								<tr>
									<td>{r.name}</td>
									<td class="num">{formatPct(r.p_then)}</td>
									<td class="num">{formatPct(r.p_now)}</td>
									<td class="num">{formatPp(r.change, 'pp', 1)}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/snippet}
			{@render regionTable(regionRows, 'Largest declines by country')}
			<details class="all">
				<summary>All {allRegions.length} countries and territories, A–Z</summary>
				{@render regionTable(allRegions, 'All countries')}
			</details>
		{/if}
	{/if}
</div>

<style>
	.wide {
		max-width: 820px;
	}
	.lede {
		font-size: 1.02rem;
	}
	.inline select {
		font: inherit;
		padding: 2px 4px;
		color: var(--text);
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 6px;
	}
	td a {
		font-weight: 600;
	}
	.small {
		display: block;
		font-size: 0.8rem;
	}
	.num {
		text-align: right;
		font-variant-numeric: tabular-nums;
		white-space: nowrap;
	}
	.all {
		margin-top: 12px;
	}
	.all summary {
		cursor: pointer;
		color: var(--accent);
		padding: 6px 0;
	}
	.rank {
		color: var(--muted);
		width: 2.2em;
		font-variant-numeric: tabular-nums;
	}
	@media (max-width: 520px) {
		.hide-narrow {
			display: none;
		}
	}
</style>
