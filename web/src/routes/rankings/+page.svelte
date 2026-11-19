<script lang="ts">
	import { onMount } from 'svelte';
	import { resolve } from '$app/paths';
	import Seo from '#lib/components/Seo.svelte';
	import { getDataSource } from '#lib/data/client.ts';
	import type { Admin1Index, RegionRow } from '#lib/data/admin1.ts';
	import { searchRegions } from '#lib/data/admin1-search.ts';
	import type { Manifest } from '#lib/data/manifest.ts';
	import type { Place, PlacesMeta } from '#lib/data/places.ts';
	import type { Region } from '#lib/data/regions.ts';
	import { formatPct, formatPopulation, formatPp, inTenYears } from '#lib/format/format.ts';
	import {
		METRIC_LABELS,
		countryOptions,
		isSmall,
		rankRegions,
		type RegionMetric
	} from '#lib/admin1-rankings.ts';
	import { declines, snowiest } from '#lib/rankings.ts';

	let manifest = $state.raw<Manifest | null>(null);
	let places = $state.raw<Place[]>([]);
	let meta = $state.raw<PlacesMeta | null>(null);
	let regions = $state.raw<Region[]>([]);
	let error = $state<string | null>(null);
	let minPop = $state(1_000_000);

	// states and provinces (contract v1.6): loaded on this page only, after the places
	let admin1 = $state.raw<Admin1Index | null>(null);
	let metric = $state<RegionMetric>('snowiest');
	let adminCountry = $state('');
	let adminQuery = $state('');

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
	const ADMIN_LIMIT = 25;
	const adminCountries = $derived(admin1 ? countryOptions(admin1.countries) : []);
	const adminCountryName = $derived(admin1?.countries[adminCountry]?.name ?? '');
	/** The ranking, or the matches of the search box when something is typed in it. */
	const adminRows = $derived.by<RegionRow[]>(() => {
		if (!admin1) return [];
		if (adminQuery.trim().length >= 2)
			return searchRegions(admin1.rows, admin1.countries, adminQuery, ADMIN_LIMIT).map(
				(h) => h.row
			);
		return rankRegions(admin1.rows, metric, { country: adminCountry || undefined }, ADMIN_LIMIT);
	});
	const searching = $derived(adminQuery.trim().length >= 2);
	const adminHeading = $derived(
		searching
			? 'Matching states and provinces'
			: `${METRIC_LABELS[metric]} ${adminCountryName ? `regions in ${adminCountryName}` : 'states and provinces worldwide'}`
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

	/** "Germany · low resolution": the country is left out inside a country list. */
	function regionMeta(r: RegionRow): string {
		return [
			!adminCountry || searching ? (admin1?.countries[r.country]?.name ?? r.country) : '',
			isSmall(r) ? 'low resolution' : ''
		]
			.filter(Boolean)
			.join(' · ');
	}

	function regionLink(r: RegionRow): string {
		return `${resolve('/')}?regions=1#/region/${encodeURIComponent(r.id)}`;
	}

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
			if (ds.hasAdmin1) admin1 = await ds.admin1Index().catch(() => null);
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

		{#if admin1}
			<h2 id="regions">States and provinces</h2>
			<p class="muted small">
				Area-weighted averages over each region's land, glaciers excluded, for the same definition
				and period as above. Click a name to open it on the map. Small regions rest on only a few 9
				km grid cells; they are left out of the world lists and marked in the country lists.
			</p>
			<div class="controls">
				<label>
					<span>Country</span>
					<select bind:value={adminCountry} disabled={searching} data-testid="region-country">
						<option value="">World</option>
						{#each adminCountries as c (c.code)}
							<option value={c.code}>{c.name} ({c.regions})</option>
						{/each}
					</select>
				</label>
				<fieldset class="seg" disabled={searching}>
					<legend class="visually-hidden">Ranking</legend>
					{#each Object.entries(METRIC_LABELS) as [id, label] (id)}
						<label class:checked={metric === id && !searching}>
							<input type="radio" name="metric" value={id} bind:group={metric} />
							{label}
						</label>
					{/each}
				</fieldset>
				<label class="find">
					<span>Find a state or province</span>
					<input
						type="search"
						bind:value={adminQuery}
						placeholder="e.g. Bavaria, Ontario"
						autocomplete="off"
						spellcheck="false"
						data-testid="region-find"
					/>
				</label>
			</div>
			<h3 id="admin-ranking">{adminHeading}, {nowLabel}</h3>
			<div class="table-wrap">
				<table aria-labelledby="admin-ranking" data-testid="region-ranking">
					<thead>
						<tr>
							<th scope="col">#</th>
							<th scope="col">Region</th>
							{#if metric === 'decline' && !searching}
								<th scope="col" class="num">{thenLabel}</th>
								<th scope="col" class="num">{nowLabel}</th>
								<th scope="col" class="num">Change</th>
							{:else}
								<th scope="col" class="num">Chance</th>
								<th scope="col" class="num hide-narrow">{thenLabel}</th>
								<th scope="col" class="num hide-narrow">Change</th>
							{/if}
						</tr>
					</thead>
					<tbody>
						{#each adminRows as r, k (r.id)}
							<tr>
								<td class="rank">{k + 1}</td>
								<td>
									<a href={regionLink(r)}>{r.name}</a>
									<span class="muted small">{regionMeta(r)}</span>
								</td>
								{#if metric === 'decline' && !searching}
									<td class="num">{formatPct(r.p_then)}</td>
									<td class="num">{formatPct(r.p_now)}</td>
									<td class="num"><strong>{formatPp(r.change, 'pp', 1)}</strong></td>
								{:else}
									<td class="num"><strong>{formatPct(r.p_now)}</strong></td>
									<td class="num hide-narrow">{formatPct(r.p_then)}</td>
									<td class="num hide-narrow">{formatPp(r.change, 'pp', 1)}</td>
								{/if}
							</tr>
						{:else}
							<tr>
								<td colspan="5" class="muted">
									{searching
										? 'No state or province matches.'
										: metric === 'decline'
											? 'No region had a white Christmas in 1 year in 10 and lost chance.'
											: 'No regions with values here.'}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}

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
	.controls {
		display: grid;
		gap: 10px;
		margin: 10px 0 4px;
	}
	.controls label span {
		display: block;
		margin-bottom: 2px;
		font-size: 0.8rem;
		color: var(--muted);
	}
	.controls select,
	.controls input[type='search'] {
		width: 100%;
		max-width: 420px;
		padding: 7px 8px;
		font: inherit;
		color: var(--text);
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 6px;
	}
	.seg {
		display: flex;
		max-width: 420px;
		margin: 0;
		padding: 2px;
		border: 0;
		background: var(--surface-2);
		border-radius: 8px;
	}
	.seg:disabled {
		opacity: 0.5;
	}
	.seg label {
		position: relative;
		flex: 1;
		padding: 6px 4px;
		text-align: center;
		font-size: 0.86rem;
		border-radius: 6px;
		color: var(--muted);
		cursor: pointer;
	}
	.seg label.checked {
		background: var(--surface);
		color: var(--text);
		font-weight: 600;
		box-shadow: 0 1px 2px rgb(0 0 0 / 0.12);
	}
	.seg label:has(input:focus-visible) {
		outline: 2px solid var(--accent);
	}
	.seg input {
		position: absolute;
		opacity: 0;
		inset: 0;
		margin: 0;
		cursor: pointer;
	}
	h3 {
		margin: 18px 0 6px;
		font-size: 1.05rem;
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
