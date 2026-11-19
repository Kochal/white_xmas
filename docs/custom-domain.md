# Serving the site from snowatchristmas.com

Cutover runbook for moving the site from `https://kochal.github.io/white_xmas/` (a GitHub Pages
project site under the base path `/white_xmas`) to `https://snowatchristmas.com/` (the domain root).
Everything in the repository is already prepared; what is left are settings in three places
(GoDaddy, the GitHub account, the repository) that only the repository owner can change.

Facts checked against GitHub's docs on 2026-11-19 are marked with a source number, see
[Sources](#sources). Things the docs do not state are marked **not in the docs**.

## What the code does

- **One repository variable switches the build.** `.github/workflows/pages.yml` reads
  `PAGES_CUSTOM_DOMAIN`.
  - Unset (today): `BASE_PATH=/white_xmas`, `PUBLIC_SITE_URL=https://kochal.github.io/white_xmas`.
  - `snowatchristmas.com`: `BASE_PATH=''` (the domain root), `PUBLIC_SITE_URL=https://snowatchristmas.com`.
  - The old pair `PAGES_BASE_PATH` / `PAGES_SITE_URL` is gone. A repository variable cannot be
    empty, and `vars.X || '/white_xmas'` treats an empty value as unset, so a root build could not
    be selected that way. The workflow also rejects a value that is not a bare host name
    (no `https://`, no path).
- **Every build is checked.** `npm run check:build` (`web/scripts/check-build.mjs`) runs after
  each build in `pages.yml`, and `web.yml` builds and checks both variants on every pull request.
  A root build fails the check if any file contains `/white_xmas` (the repository link
  `github.com/Kochal/white_xmas` is exempt) or a `github.io` URL, and every page's canonical,
  `og:url`, `og:image` and `twitter:image` must be on the site URL. A `/white_xmas` build fails if
  a link points outside its base. The data tree is skipped: it arrives after the build.
- **The data needs no change and no CORS setup.** The 194 MB bundle is fetched from `<base>/data`,
  a relative path on the same origin as the page, so on the new domain it is simply
  `https://snowatchristmas.com/data/...`. Range requests for the PMTiles work the same way. The
  only cross-origin request is the OpenFreeMap basemap, which answers with
  `access-control-allow-origin: *` (checked with `curl -I -H "Origin: https://snowatchristmas.com"`).
- **No `web/static/CNAME`.** GitHub's docs say that with a GitHub Actions publishing source "no
  `CNAME` file is created" and any existing `CNAME` file is ignored (source 1). The domain is
  set in the Pages settings (step 3) and a file would do nothing, so it is left out.
- Nothing else depends on the host: there is no service worker, web manifest or sitemap;
  `robots.txt` has no absolute URLs; the e2e tests use `localhost`; internal links use
  SvelteKit's `resolve()`. Browser caches are per origin, so a returning visitor fetches the tiles
  they need again from the new origin.

## DNS records today (measured 2026-11-19 from public DNS)

| Name  | Type  | Value                                              | What it is           |
| ----- | ----- | -------------------------------------------------- | -------------------- |
| `@`   | A     | `3.33.130.190`, `15.197.148.33`                    | GoDaddy parking page |
| `@`   | NS    | `ns19.domaincontrol.com`, `ns20.domaincontrol.com` | GoDaddy DNS: keep    |
| `www` | CNAME | `snowatchristmas.com`                              | GoDaddy default      |
| `@`   | AAAA  | none                                               |                      |

Take a screenshot of the GoDaddy DNS page before changing anything: it is the rollback record.
Keep any `MX` and `TXT` records you use for e-mail.

## Steps, in order

Steps 1 to 2 change nothing that visitors of the current site see. Steps 3 and 4 are done back to
back.

### 1. Verify the domain on the GitHub account (stops takeover)

Verification stops other GitHub users from using the domain, including after a site is disabled or
a repository deleted, and covers its immediate subdomains (source 2). GitHub recommends doing it
before adding the domain to a repository (source 3).

1. GitHub → profile picture → **Settings → Pages** (the account settings, not the repository's)
   → **Add a domain** → enter `snowatchristmas.com`.
2. GitHub shows a TXT record. In GoDaddy → **DNS → Add new record**:
   - Type `TXT`, Name `_github-pages-challenge-Kochal` (GoDaddy appends the domain; the full name
     is `_github-pages-challenge-Kochal.snowatchristmas.com`), Value: the string GitHub shows.
     The name format is from source 2; the value is shown only in GitHub's page.
3. Check: `dig +short TXT _github-pages-challenge-Kochal.snowatchristmas.com` (see
   [Checks](#checks)). It can be immediate or take up to 24 hours (source 2).
4. Back in GitHub, **Continue verifying → Verify**.
5. Keep the TXT record permanently; removing it un-verifies the domain (source 2).

### 2. Point the domain at GitHub Pages (GoDaddy DNS)

In GoDaddy → **DNS** for `snowatchristmas.com`:

1. **Delete** the two parking `A` records on `@` (`3.33.130.190`, `15.197.148.33`).
2. **Delete** any GoDaddy _Domain Forwarding_ (Domain settings → Forwarding) and any parked or
   "Websites + Marketing" page attached to the domain, or it can override the records.
3. **Add four `A` records** on `@` (source 1; a short TTL such as 600 s makes a rollback quicker):

   | Type | Name | Value             |
   | ---- | ---- | ----------------- |
   | A    | `@`  | `185.199.108.153` |
   | A    | `@`  | `185.199.109.153` |
   | A    | `@`  | `185.199.110.153` |
   | A    | `@`  | `185.199.111.153` |

4. **Add four `AAAA` records** on `@` (source 1, which "highly recommends" them alongside the A records):

   | Type | Name | Value                 |
   | ---- | ---- | --------------------- |
   | AAAA | `@`  | `2606:50c0:8000::153` |
   | AAAA | `@`  | `2606:50c0:8001::153` |
   | AAAA | `@`  | `2606:50c0:8002::153` |
   | AAAA | `@`  | `2606:50c0:8003::153` |

5. **Change the `www` CNAME** from `snowatchristmas.com` to `kochal.github.io`. Point it directly
   at `kochal.github.io`, without the repository name (source 1). Do not point it at the apex:
   that causes HTTPS problems (source 1).
6. Add **no** wildcard record (`*`): GitHub strongly advises against it (source 1).
7. Wait until `dig` shows the new records (see [Checks](#checks)); DNS changes can take up to
   24 hours to propagate (source 1), usually minutes.

Until step 3, the domain is expected to answer with a GitHub 404 page instead of the parking page
(not tested: it depends on GitHub); the live site on github.io is unaffected.

### 3. Switch the site to the domain (do 3a to 3c within a few minutes)

The current deployment is built for `/white_xmas`, so it would show a broken page at the domain
root until the next deploy. Nobody uses the domain yet, but the old github.io address is the live
one, so keep this window short: have the three tabs open and do them in order.

a. **Repository variable.** Repository → **Settings → Secrets and variables → Actions →
Variables → New repository variable**: name `PAGES_CUSTOM_DOMAIN`, value `snowatchristmas.com`.
(If a push to `main` happens while `PAGES_ENABLED` is `true`, it now deploys the domain build.)

b. **Custom domain.** Repository → **Settings → Pages → Custom domain** → `snowatchristmas.com`
→ **Save** (source 1). With an Actions source no commit or `CNAME` file is created. GitHub runs
a DNS check; if it fails, wait for DNS (step 2) and press **Check again**.

c. **Deploy.** Repository → **Actions → pages → Run workflow** (leave `data_version` empty and
`require_data` ticked). The `test` job runs the web checks first; `build` runs
`check:build` for `BASE_PATH=''`; `deploy` publishes. This takes a few minutes. Until it
finishes, the old build is what is served.

### 4. HTTPS

1. After the DNS check passes GitHub provisions a certificate (Let's Encrypt). It can take up to an hour
   (source 4); the checkbox below can take up to 24 hours to appear (source 1).
2. **Settings → Pages → Enforce HTTPS**, tick it once available (source 5).
3. If the certificate does not appear after the delay, **remove** the custom domain, wait a minute,
   type it again and **Save** (source 5). If you use `CAA` records, one must allow
   `letsencrypt.org` (source 4). Extra `A`/`AAAA` records on the apex or a stray `www` record that does not
   point to GitHub can also block it (source 5).
4. Optional: put `https://snowatchristmas.com` into the repository's **About → Website** field.

## Checks

On Windows, `dig` is not installed (source 1); use `Resolve-DnsName` or install BIND. On
Linux/macOS/Git Bash:

```sh
dig snowatchristmas.com +noall +answer -t A       # expect the four 185.199.108-111.153
dig snowatchristmas.com +noall +answer -t AAAA    # expect 2606:50c0:8000-8003::153
dig www.snowatchristmas.com +nostats +nocomments +nocmd   # CNAME kochal.github.io. then GitHub IPs
dig +short TXT _github-pages-challenge-Kochal.snowatchristmas.com
```

PowerShell: `Resolve-DnsName snowatchristmas.com -Type A` (and `-Type AAAA`, `www.snowatchristmas.com`,
`_github-pages-challenge-Kochal.snowatchristmas.com -Type TXT`).

Once deployed:

```sh
curl -sI https://snowatchristmas.com/                      # 200, server: GitHub.com
curl -sI https://snowatchristmas.com/data/manifest.json    # 200
curl -s  https://snowatchristmas.com/ | grep -o '<link rel="canonical"[^>]*>'   # https://snowatchristmas.com/
curl -sI http://snowatchristmas.com/                       # 301 to https once HTTPS is enforced
curl -sI https://www.snowatchristmas.com/                  # 301 to https://snowatchristmas.com/ (GitHub redirects www to the apex)
curl -sI https://kochal.github.io/white_xmas/              # see "old URL" below
```

Then open the site in a browser: the map must render with data and a place search must work
(DevTools → Network: `data/` requests are 200/206 on `snowatchristmas.com`, none on `github.io`).
In the Actions log, the "Resolve base path and site URL" step prints
`Building for base path '' and site URL https://snowatchristmas.com`.

## The old github.io address

GitHub's docs describe the apex/`www` redirects (source 1) but **do not state** what happens to
`kochal.github.io/white_xmas` once a custom domain is set. Community reports say it answers with a
301 to the custom domain, path preserved (not confirmed by the docs). So check it with the last
`curl -I` above: expect `301` and `location: https://snowatchristmas.com/...`.
If it returns 404 instead, old links break; the usual fix is a one-file redirect page in a
`Kochal/kochal.github.io` user-site repository. That is outside this change; ask for it if needed.

## Rollback

Each part can be undone on its own, in this order:

1. **Site back on github.io:** delete the repository variable `PAGES_CUSTOM_DOMAIN` (or set the
   Pages custom domain empty with **Remove**) and run **Actions → pages → Run workflow**. The
   build is again `/white_xmas`. Remove the custom domain in **Settings → Pages** at the same
   time, or the domain keeps serving the page.
2. **DNS:** restore the records from your GoDaddy screenshot (two parking `A` records, `www` CNAME to
   `snowatchristmas.com`). Do not leave the GitHub `A`/`AAAA` records pointing at Pages while the
   site is disabled or the domain is removed: an unverified domain left like that can be claimed by
   another GitHub user (source 3). The verification TXT record from step 1 may stay.
3. Nothing in the repository needs reverting: both builds are tested in CI on every change.

## Sources

1. [Managing a custom domain for your GitHub Pages site](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/managing-a-custom-domain-for-your-github-pages-site):
   A/AAAA records, `www` CNAME, no wildcard, `dig`, the Settings → Pages field, the `CNAME` file
   being ignored with Actions, HTTPS up to 24 hours, 24-hour DNS propagation.
2. [Verifying your custom domain for GitHub Pages](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/verifying-your-custom-domain-for-github-pages):
   account-level verification, TXT record name format, keep the record.
3. [About custom domains and GitHub Pages](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/about-custom-domains-and-github-pages):
   verify before adding, takeover risk, `www`/apex redirects.
4. [Troubleshooting custom domains and GitHub Pages](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/troubleshooting-custom-domains-and-github-pages):
   up to an hour for HTTPS, CAA, remove and re-add the domain.
5. [Securing your GitHub Pages site with HTTPS](https://docs.github.com/en/pages/getting-started-with-github-pages/securing-your-github-pages-site-with-https):
   Enforce HTTPS, restarting provisioning, mixed content.
