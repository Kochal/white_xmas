import { defineEnvVars } from '@sveltejs/kit/env';

const optional = (value: string | undefined) => (value ? value : undefined);

export const variables = defineEnvVars({
	PUBLIC_DATA_BASE: {
		public: true,
		static: true,
		schema: optional,
		description:
			'Where the web data (manifest.json, tiles/, points/ …) is served from. Defaults to `<base>/data` in a build and to the fixture dataset in `vite dev`.'
	},
	PUBLIC_SITE_URL: {
		public: true,
		static: true,
		schema: optional,
		description:
			'Absolute site URL, used for social preview tags. Defaults to the GitHub Pages URL.'
	},
	PUBLIC_DOWNLOADS_URL: {
		public: true,
		static: true,
		schema: optional,
		description: 'Where open-data downloads live. Defaults to the GitHub Releases page.'
	}
});
