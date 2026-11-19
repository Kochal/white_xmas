<script lang="ts">
	import { page } from '$app/state';
	import { BASE_PATH, SITE_URL } from '#lib/config.ts';

	interface Props {
		title: string;
		description: string;
	}

	let { title, description }: Props = $props();

	// Social cards need absolute URLs; SITE_URL already includes the base path.
	const path = $derived(page.url.pathname.slice(BASE_PATH.length) || '/');
	const canonical = $derived(`${SITE_URL}${path}`);
	const image = `${SITE_URL}/og-image.png`;
</script>

<svelte:head>
	<title>{title}</title>
	<meta name="description" content={description} />
	<link rel="canonical" href={canonical} />
	<meta property="og:type" content="website" />
	<meta property="og:site_name" content="White Christmas" />
	<meta property="og:title" content={title} />
	<meta property="og:description" content={description} />
	<meta property="og:url" content={canonical} />
	<meta property="og:image" content={image} />
	<meta property="og:image:width" content="1200" />
	<meta property="og:image:height" content="630" />
	<meta
		property="og:image:alt"
		content="A map of Europe shaded by how often there is snow on the ground at Christmas"
	/>
	<meta name="twitter:card" content="summary_large_image" />
	<meta name="twitter:title" content={title} />
	<meta name="twitter:description" content={description} />
	<meta name="twitter:image" content={image} />
</svelte:head>
