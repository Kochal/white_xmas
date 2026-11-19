<script lang="ts">
	import { onMount } from 'svelte';
	import { searchPlaces, warmSearch, type Place, type SearchHit } from '#lib/data/places.ts';
	import { formatPct } from '#lib/format/format.ts';

	interface Props {
		/** Loads places on first focus, so the first page load stays light. */
		loadPlaces: () => Promise<Place[]>;
		onpick: (place: Place) => void;
	}

	let { loadPlaces, onpick }: Props = $props();

	let query = $state('');
	// raw: 34k plain objects must not become deep reactive proxies (slow, and breaks the index cache)
	let places = $state.raw<Place[] | null>(null);
	let loadError = $state<string | null>(null);
	let open = $state(false);
	let active = $state(-1);
	let input: HTMLInputElement;

	/** The query the results are for; trails `query` by DEBOUNCE_MS while typing. */
	let searched = $state('');
	const DEBOUNCE_MS = 100;
	let timer: ReturnType<typeof setTimeout> | undefined;
	function schedule() {
		clearTimeout(timer);
		timer = setTimeout(() => (searched = query), DEBOUNCE_MS);
	}
	function flush() {
		clearTimeout(timer);
		searched = query;
	}

	const hits = $derived<SearchHit[]>(
		places && searched.trim() ? searchPlaces(places, searched, 8) : []
	);

	// Text typed into the prerendered box before the app hydrated: pick it up.
	onMount(() => {
		if (input.value) {
			query = input.value;
			flush();
			ensurePlaces();
			open = document.activeElement === input;
		}
		return () => clearTimeout(timer);
	});
	const listId = 'place-search-list';

	async function ensurePlaces() {
		if (places || loadError) return;
		try {
			const list = await loadPlaces();
			// build the index now (the box has focus), not on the first keystroke
			warmSearch(list);
			places = list;
		} catch (e) {
			loadError = e instanceof Error ? e.message : String(e);
		}
	}

	function pick(h: SearchHit) {
		query = h.place.name;
		open = false;
		active = -1;
		onpick(h.place);
	}

	function onkeydown(e: KeyboardEvent) {
		if (e.key === 'ArrowDown') {
			e.preventDefault();
			open = true;
			active = Math.min(hits.length - 1, active + 1);
		} else if (e.key === 'ArrowUp') {
			e.preventDefault();
			active = Math.max(0, active - 1);
		} else if (e.key === 'Enter') {
			if (searched !== query) flush(); // don't act on stale results
			const h = hits[active >= 0 ? active : 0];
			if (h) {
				e.preventDefault();
				pick(h);
			}
		} else if (e.key === 'Escape') {
			if (open) {
				open = false;
				active = -1;
			} else {
				query = '';
				flush();
			}
		}
	}

	const countryName = (() => {
		try {
			const dn = new Intl.DisplayNames(['en'], { type: 'region' });
			return (code: string) => (code ? (dn.of(code) ?? code) : '');
		} catch {
			return (code: string) => code;
		}
	})();

	export function focus() {
		input?.focus();
	}
</script>

<div class="search" role="search">
	<label for="place-search" class="visually-hidden">Search for a place</label>
	<svg class="icon" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
		<circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" stroke-width="2" />
		<path d="M16.5 16.5L21 21" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
	</svg>
	<input
		bind:this={input}
		id="place-search"
		type="search"
		role="combobox"
		autocomplete="off"
		spellcheck="false"
		placeholder="Search a city or town"
		aria-autocomplete="list"
		aria-controls={listId}
		aria-expanded={open && hits.length > 0}
		aria-activedescendant={open && active >= 0 ? `place-opt-${active}` : undefined}
		bind:value={query}
		onfocus={() => {
			ensurePlaces();
			open = true;
		}}
		oninput={() => {
			open = true;
			active = -1;
			ensurePlaces();
			schedule();
		}}
		onblur={() => setTimeout(() => (open = false), 150)}
		{onkeydown}
	/>
	{#if open && query.trim()}
		<ul
			id={listId}
			role="listbox"
			aria-label="Places"
			aria-busy={searched !== query}
			class:stale={searched !== query && hits.length > 0}
		>
			{#each hits as h, k (h.place.name + h.place.lat + h.place.lon)}
				<li
					id="place-opt-{k}"
					role="option"
					aria-selected={k === active}
					class:active={k === active}
					onmousedown={(e) => {
						e.preventDefault();
						pick(h);
					}}
				>
					<span class="name">
						{h.place.name}{#if h.matched !== h.place.name && h.matched !== h.place.ascii}
							<span class="muted"> ({h.matched})</span>{/if}
					</span>
					<span class="where muted">
						{[h.place.admin1, countryName(h.place.country)].filter(Boolean).join(', ')}
					</span>
					{#if h.place.p_now !== null}
						<span class="p" title="White Christmas probability, recent 30 years">
							{formatPct(h.place.p_now)}
						</span>
					{/if}
				</li>
			{:else}
				<li class="empty muted" role="presentation">
					{loadError
						? `Places could not be loaded: ${loadError}`
						: !places
							? 'Loading places…'
							: searched !== query
								? 'Searching…'
								: 'No place found. Try another spelling, or click the map.'}
				</li>
			{/each}
		</ul>
	{/if}
</div>

<style>
	.search {
		position: relative;
	}
	.icon {
		position: absolute;
		left: 10px;
		top: 50%;
		transform: translateY(-50%);
		color: var(--muted);
		pointer-events: none;
	}
	input {
		width: 100%;
		padding: 9px 12px 9px 36px;
		font: inherit;
		font-size: 1rem;
		color: var(--text);
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 8px;
	}
	input:focus {
		outline: 2px solid var(--accent);
		outline-offset: 0;
		border-color: transparent;
	}
	ul {
		position: absolute;
		z-index: 30;
		top: calc(100% + 4px);
		left: 0;
		right: 0;
		margin: 0;
		padding: 4px;
		list-style: none;
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 8px;
		box-shadow: var(--shadow);
		max-height: 320px;
		overflow-y: auto;
	}
	ul.stale li {
		opacity: 0.55;
	}
	li {
		display: grid;
		grid-template-columns: 1fr auto;
		gap: 0 8px;
		padding: 7px 10px;
		border-radius: 6px;
		cursor: pointer;
	}
	li.active,
	li:hover {
		background: var(--accent-soft);
	}
	.name {
		font-weight: 550;
		overflow-wrap: anywhere;
	}
	.where {
		grid-column: 1;
		font-size: 0.82rem;
	}
	.p {
		grid-column: 2;
		grid-row: 1 / span 2;
		align-self: center;
		font-variant-numeric: tabular-nums;
		font-size: 0.9rem;
	}
	li.empty {
		display: block;
		cursor: default;
		font-size: 0.88rem;
	}
	li.empty:hover {
		background: none;
	}
</style>
