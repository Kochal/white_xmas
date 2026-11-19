<script lang="ts">
	import { resolve } from '$app/paths';
	import type { Admin1Index, CountryFile, RegionRow } from '#lib/data/admin1.ts';
	import {
		definitionText,
		thresholdById,
		thresholdNote,
		type Manifest
	} from '#lib/data/manifest.ts';
	import {
		atWindow,
		decadeBars,
		elevationText,
		flagNotes,
		futureRows,
		hasValues,
		headlineWindowId,
		pickStats,
		spreadAt,
		trendInfo
	} from '#lib/data/region-view.ts';
	import { formatP, formatPct, formatPp, frequencyLine } from '#lib/format/format.ts';
	import type { Selection } from '#lib/map/layers.ts';
	import DecadeBars from './DecadeBars.svelte';
	import FutureRanges from './FutureRanges.svelte';
	import PanelShell from './PanelShell.svelte';
	import RegionSeries from './RegionSeries.svelte';
	import SpreadBar from './SpreadBar.svelte';

	interface Props {
		manifest: Manifest;
		index: Admin1Index | null;
		row: RegionRow;
		/** The row's country file; null while it loads. */
		country: CountryFile | null;
		error: string | null;
		selection: Selection;
		expanded: boolean;
		onclose: () => void;
		ontoggle: () => void;
		ondefinition: (id: string) => void;
	}

	let {
		manifest,
		index,
		row,
		country,
		error,
		selection,
		expanded,
		onclose,
		ontoggle,
		ondefinition
	}: Props = $props();

	const detail = $derived(country?.regions.find((r) => r.id === row.id) ?? null);
	const picked = $derived(
		country && detail ? pickStats(country, detail, selection.threshold, selection.definition) : null
	);
	const threshold = $derived(thresholdById(manifest, picked?.threshold ?? selection.threshold));
	const definition = $derived(
		manifest.definitions.find((d) => d.id === (picked?.definition ?? selection.definition)) ??
			manifest.definitions[0]
	);
	const win = (id: string | undefined) => manifest.windows.find((w) => w.id === id);

	const headId = $derived(
		country && index
			? headlineWindowId(country, index, selection.kind, selection.period)
			: (index?.windows.p_now ?? '')
	);
	const headWin = $derived(win(headId));
	const thenWin = $derived(win(country?.windows_then_now[0]));
	const nowWin = $derived(win(country?.windows_then_now[1]));
	const fullWin = $derived(manifest.windows.find((w) => w.kind === 'full'));

	const stats = $derived(picked?.stats ?? null);
	const head = $derived(stats && country ? atWindow(country, stats.p, headId) : null);
	const headPop = $derived(stats && country ? atWindow(country, stats.p_pop, headId) : null);
	const pThen = $derived(
		stats && country && thenWin ? atWindow(country, stats.p, thenWin.id) : null
	);
	const pNow = $derived(stats && country && nowWin ? atWindow(country, stats.p, nowWin.id) : null);
	/** The headline window's value for every threshold the file offers ("38 % · 62 %"). */
	const byThreshold = $derived(
		country && detail && picked && country.thresholds.length > 1
			? country.thresholds
					.map((id) => ({
						t: thresholdById(manifest, id),
						p: detail.stats[id]?.[picked.definition]
							? atWindow(country, detail.stats[id][picked.definition].p, headId)
							: undefined
					}))
					.filter(
						(b): b is { t: ReturnType<typeof thresholdById>; p: number | null } => b.p !== undefined
					)
			: []
	);
	const decades = $derived(stats && country ? decadeBars(manifest, country, stats) : []);
	const trend = $derived(stats && country ? trendInfo(stats, country.trend_alpha) : null);
	const spread = $derived(stats && country ? spreadAt(country, stats, headId) : null);
	const future = $derived(country && detail ? futureRows(manifest, country, detail) : null);
	const notes = $derived(flagNotes(row.flags, index?.flags ?? {}));
	const showData = $derived(!!stats && hasValues(stats));
	const countryName = $derived(index?.countries[row.country]?.name ?? country?.country_name ?? '');
	const subtitle = $derived(
		[
			detail?.name_local && detail.name_local !== row.name ? detail.name_local : '',
			detail?.type,
			countryName
		]
			.filter(Boolean)
			.join(' · ')
	);
	const elevation = $derived(detail ? elevationText(detail.elev_m) : '');
	const nPlaces = $derived(detail?.places ?? 0);
</script>

<PanelShell
	label="Region details"
	testid="region-panel"
	title={row.name}
	{subtitle}
	{expanded}
	{onclose}
	{ontoggle}
>
	{#each notes as n (n.flag)}
		<p class="note" data-testid="region-flag-{n.flag}">{n.text}</p>
	{/each}

	{#if error}
		<p role="alert">Couldn't load the data for this region: {error}</p>
	{:else if !country || !detail}
		<p class="muted" aria-live="polite">
			{country ? 'This region is not in the data.' : 'Loading the snow history…'}
		</p>
	{:else if !stats || !showData}
		<p>There are no values for this region{notes.length ? ', see above' : ''}.</p>
	{:else}
		<section class="headline" aria-live="polite">
			<p class="big" data-testid="headline">{formatPct(head)}</p>
			{#if head !== null}
				<p>
					<strong>{frequencyLine(definition.label, head)}</strong>
					<span class="muted">
						(share of the region's land, {headWin?.label})
					</span>
				</p>
				{#if byThreshold.length}
					<p class="both" data-testid="both-thresholds">
						{#each byThreshold as b, k (b.t.id)}
							{#if k > 0}<span class="sep" aria-hidden="true">·</span>{/if}
							<span class:current={b.t.id === threshold.id}>
								{formatPct(b.p)}
								{b.t.default ? 'calibrated' : 'raw ERA5-Land'}
							</span>
						{/each}
					</p>
				{/if}
			{:else}
				<p>No value for {headWin?.label ?? 'this period'}.</p>
			{/if}
			<p class="people small" data-testid="pop-weighted">
				{#if headPop !== null}
					Where people live: <strong>{formatPct(headPop)}</strong>, weighting the
					{nPlaces.toLocaleString('en')} places of 15,000+ people by their population.
				{:else}
					No place of 15,000+ people lies in this region, so there is no value weighted by
					population.
				{/if}
			</p>
		</section>

		<label class="def">
			<span class="visually-hidden">Definition</span>
			<select value={definition.id} onchange={(e) => ondefinition(e.currentTarget.value)}>
				{#each manifest.definitions.filter((d) => country.definitions.includes(d.id)) as d (d.id)}
					<option value={d.id}>{d.label}</option>
				{/each}
			</select>
		</label>
		<p class="muted small">
			{definitionText(manifest, definition, threshold)}
			{#if thresholdNote(manifest, threshold)}<span data-testid="threshold-note">
					{thresholdNote(manifest, threshold)}
				</span>{:else if threshold.description}<span data-testid="threshold-note">
					{threshold.description}
				</span>{/if}
		</p>

		{#if thenWin && nowWin}
			<section>
				<h3>Then vs now</h3>
				<div class="thenNow">
					<div>
						<span class="muted">{thenWin.label}</span>
						<strong>{formatPct(pThen)}</strong>
					</div>
					<span class="arrow" aria-hidden="true">→</span>
					<div>
						<span class="muted">{nowWin.label}</span>
						<strong>{formatPct(pNow)}</strong>
					</div>
					{#if pThen !== null && pNow !== null}
						<div class="delta">{formatPp(pNow - pThen)}</div>
					{/if}
				</div>
			</section>
		{/if}

		{#if decades.length}
			<section>
				<h3>By decade</h3>
				<DecadeBars {decades} label="Share of the region with a white Christmas, per decade." />
			</section>
		{/if}

		<section>
			<h3>Every year since {country.years[0]}</h3>
			<RegionSeries series={stats.series} firstYear={country.years[0]} window={headWin} />
			{#if trend}
				<p class="trend" data-testid="region-trend">
					<strong>{formatPp(trend.perDecade, 'pp per decade')}</strong>
					{#if trend.significant}
						<span class="sig yes" data-testid="trend-significance">● clear trend</span>
						<span class="muted">({trend.p === null ? '' : formatP(trend.p)})</span>
					{:else}
						<span class="sig" data-testid="trend-significance">○ not a clear trend</span>
						{#if trend.p !== null}<span class="muted">({formatP(trend.p)})</span>{/if}
					{/if}
					<span class="muted">{fullWin?.label ?? ''}</span>
				</p>
				<p class="muted small">
					The slope is a straight line through the yearly shares. A trend is called clear when a
					Mann–Kendall test gives p &lt; {country.trend_alpha}, as on the map; if not, the line is
					within what luck from year to year produces.
				</p>
			{/if}
		</section>

		{#if spread}
			<section data-testid="region-spread">
				<h3>Inside the region</h3>
				<SpreadBar p5={spread.p5} p95={spread.p95} mean={head} />
				<p class="small">
					Across its 9 km grid cells the chance runs from about <strong>
						{formatPct(spread.p5)}
					</strong>
					to
					<strong>{formatPct(spread.p95)}</strong>. The dot is the average.
					{#if spread.share50 !== null}
						In <strong>{formatPct(spread.share50)}</strong> of the area, a white Christmas is more likely
						than not.
					{/if}
					{#if elevation}Land elevation: {elevation}.{/if}
				</p>
			</section>
		{/if}

		{#if future}
			<section>
				<h3>In a warmer world</h3>
				<FutureRanges
					levels={future.levels}
					values={future.values}
					baseline={future.baseline}
					baselineLabel={nowWin?.label ?? ''}
				/>
				<p class="muted small">
					Projections are for snow on Christmas Day, calibrated threshold, from {country.projections
						?.models.length ?? manifest.projections.models.length} climate models. Each model's average
					over the region counts once; the range is the spread between models (10th to 90th percentile).
					Models work on ~100 km grids, so mountains are smoothed.
				</p>
			</section>
		{/if}

		<p class="muted small fine">
			An average over {detail.land_km2 !== null
				? `${Math.round(detail.land_km2).toLocaleString('en')} km² of land`
				: 'the region’s land'} in ERA5-Land 9 km grid cells, glaciers left out.
			<a href={resolve('/methodology')} data-testid="method-link">How regions are calculated</a>.
		</p>
	{/if}
</PanelShell>

<style>
	.people {
		margin-top: 6px !important;
	}
	.trend {
		margin: 6px 0 4px;
		font-variant-numeric: tabular-nums;
	}
	.sig {
		margin: 0 0.3em;
		padding: 1px 7px;
		font-size: 0.82rem;
		border: 1px solid var(--line);
		border-radius: 999px;
		white-space: nowrap;
	}
	.sig.yes {
		border-color: var(--accent);
		background: var(--accent-soft);
	}
</style>
