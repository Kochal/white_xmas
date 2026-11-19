import { dev } from '$app/env';
import { PUBLIC_DATA_BASE, PUBLIC_DOWNLOADS_URL, PUBLIC_SITE_URL } from '$app/env/public';

/** Base path the site is served from: '' locally and on a custom domain, '/white_xmas' on github.io. */
export const BASE_PATH: string = __BASE_PATH__;

/** Base URL of the web data tree (no trailing slash). See README "Data". */
export const DATA_BASE = (
	PUBLIC_DATA_BASE ?? (dev ? `${BASE_PATH}/__fixtures/data` : `${BASE_PATH}/data`)
).replace(/\/$/, '');

export const REPO_URL = 'https://github.com/Kochal/white_xmas';

export const SITE_URL = (PUBLIC_SITE_URL ?? 'https://kochal.github.io/white_xmas').replace(
	/\/$/,
	''
);

export const DOWNLOADS_URL = PUBLIC_DOWNLOADS_URL ?? `${REPO_URL}/releases`;
