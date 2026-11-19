# Moving to selfinit.dev

Plan: make **selfinit.dev** the primary domain and permanently redirect
**williamanderson.dev** to it (paths kept), using Cloudflare, where both
domains' DNS already lives.

Status: **not started** (planned 2026-11-17).

## 1. Before switching: build changes

- [ ] Write a copy of the RSS feed at the old Docusaurus feed paths
      (`/blog/rss.xml`, and `/blog/atom.xml` since some readers subscribed to
      that). With a real 301 in place, old subscribers get sent to
      `selfinit.dev/blog/rss.xml`, which must exist. (Not built yet; it's a
      small generator change.)

## 2. Point selfinit.dev at GitHub Pages

- [ ] GitHub: verify `selfinit.dev` under *Settings → Pages → Verified
      domains* for your account (prevents domain takeover).
- [ ] Cloudflare DNS for `selfinit.dev`, set to **DNS only** (grey cloud) so
      GitHub can issue the HTTPS certificate:
  - `A` records for `@`: `185.199.108.153`, `185.199.109.153`,
    `185.199.110.153`, `185.199.111.153`
  - `AAAA` records for `@`: `2606:50c0:8000::153`, `2606:50c0:8001::153`,
    `2606:50c0:8002::153`, `2606:50c0:8003::153`
  - `CNAME` `www` → `<your-github-username>.github.io`
- [ ] Repo: *Settings → Pages → Custom domain* = `selfinit.dev`, then tick
      **Enforce HTTPS** once the certificate is issued. (Deploying with
      GitHub Actions, so no `CNAME` file is needed in the output.)

## 3. Switch the site over

- [ ] `site.json`: `"url": "https://selfinit.dev"`. This updates canonical
      links, Open Graph URLs, social card image URLs, the RSS feed, redirect
      pages and the domain printed on social cards.
- [ ] Build, deploy, and check `https://selfinit.dev` works.

## 4. Redirect williamanderson.dev

- [ ] Remove `williamanderson.dev` as the custom domain of the old
      (Docusaurus) GitHub Pages site.
- [ ] Cloudflare DNS for `williamanderson.dev`: the `@` and `www` records
      must be **proxied** (orange cloud) for redirect rules to run. If
      nothing else needs them, a placeholder `A @ 192.0.2.1` (proxied) is
      enough.
- [ ] Cloudflare → `williamanderson.dev` → *Rules → Redirect Rules*:
  - When: hostname equals `williamanderson.dev` **or** `www.williamanderson.dev`
  - Then: *Dynamic* redirect to
    `concat("https://selfinit.dev", http.request.uri.path)`
  - Status `301`, **Preserve query string** on.
- [ ] **Email:** don't touch the `MX` (and SPF/DKIM `TXT`) records on
      `williamanderson.dev`. Redirect rules only affect web traffic, so
      `me@williamanderson.dev` keeps working.

## 5. Check

- [ ] Each of these should 301 to the same path on selfinit.dev, then land on
      the right page:
  ```sh
  curl -sI https://williamanderson.dev/
  curl -sI https://williamanderson.dev/blog/galaxymap
  curl -sI https://williamanderson.dev/blog/rss.xml
  curl -sI https://www.williamanderson.dev/2026-10-22/computercraft-os/
  ```
- [ ] Link previews: LinkedIn Post Inspector (linkedin.com/post-inspector)
      and a Discord message with a post link.
- [ ] Google Search Console: verify both domains, then use *Change of
      address* on williamanderson.dev → selfinit.dev.

## 6. Afterwards

- [ ] `giscus.json`: optionally drop `https://williamanderson.dev` from
      `origins` once it only redirects (harmless to keep).
- [ ] Update the website link on GitHub, LinkedIn and anywhere else that
      lists the old domain (talk slides, etc.).
- [ ] Optional: an `@selfinit.dev` email address, then update the About
      links in `site.json` and `pages/about.md`.
