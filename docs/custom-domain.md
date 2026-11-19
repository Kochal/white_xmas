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
- **The two switches must agree, and the build checks it.** The variable picks the build, but the
  domain GitHub actually serves comes from Settings → Pages → Custom domain. If they differ the
  site has no data (a root build on github.io requests `kochal.github.io/data/…`; a `/white_xmas`
  build on the domain requests `/white_xmas/data/…`). So the "Resolve base path and site URL" step
  reads the Pages settings (`gh api repos/$GITHUB_REPOSITORY/pages`, field `cname`) and **fails the
  build with an `::error::`** when `cname` differs from `PAGES_CUSTOM_DOMAIN` (empty equals unset).
  A failed build never deploys, so the previous working deployment stays live. If the API call
  itself fails (for example the token may not read Pages), the step prints a `::warning::` and
  carries on: the guard never blocks a deploy because of its own failure. The call needs only
  `pages: read`, which the workflow's existing `pages: write` already includes, so no permission
  was widened. **Whether the job's `GITHUB_TOKEN` can make that call is untested until the first
  dispatch run**; look for the warning in that run's log. (The decision logic was run locally
  against a fake `gh` for: both unset, both set, variable only, domain only, API failure.)
  Consequence for the cutover: a run started between steps 3a and 3b fails on purpose.
- **Every build is checked.** `npm run check:build` (`web/scripts/check-build.mjs`) runs after
  each build in `pages.yml`, and `web.yml` builds and checks both variants on every pull request.
  A root build fails the check if any file contains `/white_xmas` (the repository link
  `github.com/Kochal/white_xmas` is exempt) or a `kochal.github.io` URL (other `github.io` links
  are fine), and every page's canonical, `og:url`, `og:image` and `twitter:image` must be on the
  site URL, which is required (no site URL is an error, not a skipped check). A `/white_xmas` build
  fails if an HTML link points outside its base or a script contains a string literal starting
  `"/data/` or `"/_app/`. Limit: URLs assembled some other way, for example from separate string
  pieces, are not found; the data base itself is built from `BASE_PATH` in one place
  (`web/src/lib/config.ts`). The data tree is skipped: it arrives after the build.
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

What GoDaddy's DNS editor may show differently (not checked against a GoDaddy account; recognise
them by what they are):

- The `www` CNAME's value is often shown as `@`, which means the apex, `snowatchristmas.com`.
- The parking `A` record on `@` is often shown with the value **Parked** instead of the two IPs.
  Delete it all the same.
- A `_domainconnect` CNAME (`_domainconnect.gd.domaincontrol.com`) also exists in public DNS.
  **Leave it**; it is unrelated and harmless.

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

**Gate: do not start step 2 until Settings → Pages (account) shows `snowatchristmas.com` as
Verified.** Step 2 relies on it.

### 2. Point the domain at GitHub Pages (GoDaddy DNS)

**This deliberately deviates from GitHub's documented order.** GitHub's page says to add the custom
domain to the Pages site (Save) _before_ creating the DNS records, so that nobody else can host a
site on your domain in between (source 1). Here DNS comes first, because saving the domain first
would send visitors of the live github.io address to a domain that still shows the GoDaddy parking
page until DNS has propagated. That is only safe because of step 1: a verified domain, together with
its immediate subdomains such as `www`, cannot be used by other GitHub users' Pages sites
(sources 2 and 3), which is the takeover that GitHub's ordering guards against. Hence the gate
above.

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

4. **Optionally add four `AAAA` records** on `@` for IPv6 (source 1; keep the `A` records too:
   GitHub recommends an `A` record in addition to an `AAAA` record, never `AAAA` alone):

   | Type | Name | Value                 |
   | ---- | ---- | --------------------- |
   | AAAA | `@`  | `2606:50c0:8000::153` |
   | AAAA | `@`  | `2606:50c0:8001::153` |
   | AAAA | `@`  | `2606:50c0:8002::153` |
   | AAAA | `@`  | `2606:50c0:8003::153` |

5. **Change the `www` CNAME** from `snowatchristmas.com` to `kochal.github.io`. Point it directly
   at `kochal.github.io`, without the repository name (source 1). Do not leave it pointing at the
   apex: GitHub says a custom subdomain pointed at the apex domain causes problems enforcing HTTPS
   (source 1); that sentence does not name `www`, so applying it to `www` is our inference, but it
   is the safe reading.
6. Add **no** wildcard record (`*`): GitHub strongly advises against it (source 1).
7. Wait until `dig` shows the new records (see [Checks](#checks)); DNS changes can take up to
   24 hours to propagate (source 1), usually minutes.

Until step 3, the domain is expected to answer with a GitHub 404 page instead of the parking page
(not tested: it depends on GitHub); the live site on github.io is unaffected.

### 3. Switch the site to the domain (do 3a to 3c within a few minutes)

The current deployment is built for `/white_xmas`, so it would show a broken page at the domain
root until the next deploy. Nobody uses the domain yet, but the old github.io address is the live
one, so keep this window short: have the three tabs open and do them in order. Do the cutover at a
quiet time. 3c must come **after** 3b: the build fails on purpose while the variable and the Pages
domain disagree (see [What the code does](#what-the-code-does)).

a. **Repository variable.** Repository → **Settings → Secrets and variables → Actions →
Variables → New repository variable**: name `PAGES_CUSTOM_DOMAIN`, value `snowatchristmas.com`.
(A push to `main` between 3a and 3b fails the build on purpose, because the variable and the Pages
domain disagree; after 3b, pushes deploy the domain build.)

b. **Custom domain.** Repository → **Settings → Pages → Custom domain** → `snowatchristmas.com`
→ **Save** (source 1). With an Actions source no commit or `CNAME` file is created. GitHub runs
a DNS check; if it fails, wait for DNS (step 2) and press **Check again**.

**Right after Save, run these two and note what visitors get** (see the HTTPS gap below):

```sh
curl -sI https://snowatchristmas.com/
curl -sI https://kochal.github.io/white_xmas/
```

c. **Deploy.** Repository → **Actions → pages → Run workflow** (leave `data_version` empty and
`require_data` ticked). The `test` job runs the web checks first; `build` runs
`check:build` for `BASE_PATH=''`; `deploy` publishes. This takes a few minutes. Until it
finishes, the old build is what is served.

- [ ] **After this first run, open its log** (job `build` → step "Resolve base path and site URL")
      and confirm there is **no `::warning::` about the Pages settings** ("Could not read the Pages
      settings…"). A warning in an otherwise green run is easy to miss. If it is there, the
      custom-domain guard is **off** (the token cannot read the Pages API): tell the orchestrator or
      the repository owner, and take care by hand that the variable and the Pages domain agree.

### 4. HTTPS

**The HTTPS gap.** After Save, GitHub needs to issue the certificate for the new name: up to about
an hour (source 4), and the **Enforce HTTPS** checkbox can take up to 24 hours (source 1). The docs
do not say what is served meanwhile. Expect that `https://snowatchristmas.com` can show a
certificate warning, or that the site is reachable over plain HTTP only. If the github.io address
redirects to the domain at once (see [The old github.io address](#the-old-githubio-address)), the
live audience can see that too, whereas today github.io has HTTPS. There is no documented way to
get the certificate before saving the domain. So: pick a quiet time, **do not share or announce the
new domain until Enforce HTTPS is ticked**, and use the two `curl` commands after Save to watch it.

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

Undoing the site switch is one coupled operation (the variable, the Pages domain and a
re-deploy go together, in the order below). DNS is separate and comes after.

1. **Site back on github.io.** Do these three in this order, back to back:
   1. **Delete** the repository variable `PAGES_CUSTOM_DOMAIN`. On its own this changes nothing
      that is live. A run started now fails on purpose: the guard sees the Pages domain still set.
   2. **Remove** the custom domain in **Settings → Pages**. **This starts the outage:** the
      deployed root build is now served at `kochal.github.io/white_xmas/` and has no data
      (it requests `kochal.github.io/data/…`).
   3. **Run Actions → pages → Run workflow immediately.** The build is `/white_xmas` again. The
      site has no data until that run's deploy finishes, about 3–4 minutes.

   All three are needed because the variable and the Pages domain are independent switches: with
   only the domain removed, the next build is still a root build and has no data on
   `kochal.github.io/white_xmas/`; with only the variable deleted, a `/white_xmas` build is served
   at `snowatchristmas.com/` and has no data there. The workflow's guard only stops a _wrong new_
   deploy (it fails a run whose variable and Pages domain disagree, so such a run never replaces
   the live site); it does not prevent the outage between 2 and 3, and it does not undo a deploy
   that already happened.

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
