<script lang="ts">
	import '../app.css';
	import { asset } from '$app/paths';
	import favicon from '#lib/assets/favicon.svg';
	import SiteHeader from '#lib/components/SiteHeader.svelte';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();
</script>

<svelte:head>
	<link rel="icon" href={favicon} type="image/svg+xml" />
	<link rel="apple-touch-icon" href={asset('apple-touch-icon.png')} />
	<meta name="theme-color" content="#f6f8fb" media="(prefers-color-scheme: light)" />
	<meta name="theme-color" content="#0f141c" media="(prefers-color-scheme: dark)" />
</svelte:head>

<a class="skip-link" href="#main">Skip to content</a>
<SiteHeader />
<main id="main">
	{@render children()}
</main>

<style>
	.skip-link {
		position: absolute;
		left: 8px;
		top: -40px;
		z-index: 100;
		padding: 8px 12px;
		background: var(--surface);
		border-radius: 6px;
	}
	.skip-link:focus {
		top: 8px;
	}
</style>
