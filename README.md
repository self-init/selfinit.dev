# self-init

Source for [self-init](https://selfinit.dev), the new version of my blog.

## Quick start

Requires [uv](https://docs.astral.sh/uv/) (it installs the right Python and
dependencies).

```sh
uv run python build.py           # build the site into output/
uv run python serve.py           # dev server on :8000, rebuilds on any change (includes drafts)
```

`build.py` options: `--drafts` (include `draft: true` posts), `--config FILE`
(default `site.json`), `--output DIR`.

Problems are collected across the whole build and listed together. If there
are any errors the existing output is left untouched and the exit status is 1,
so CI fails and the dev server keeps serving the last good build.

## Writing posts

A post is a Markdown file in `posts/`, or a folder holding one `.md` file plus
its images and other files (copied next to the rendered post, so relative
links like `./diagram.png` work).

```markdown
---
title: Building a Unix-like OS for ComputerCraft   # required
date: 2026-10-22          # or start the file/folder name with YYYY-MM-DD
slug: computercraft-os    # optional; default: made from the title
description: ...          # optional; used for previews/search, and as the summary if there's no truncate marker
tags: [Hecate, Software Dev]   # must be in tags.json
series: Hecate OS              # must be in series.json; parts are ordered by date
thumbnail: ./cover.png    # optional; default: the post's first image; false = none
og_image: ./card.png      # optional; replaces the generated social card
comments: false           # optional; hide the comment section
discussion: 12            # optional; show this existing GitHub Discussion (e.g. a migrated thread)
draft: true               # optional; left out unless built with --drafts
---

Intro paragraph...

<!-- truncate -->

Everything above the marker is the summary shown in post lists.
```

Markdown extras:

- **Figures:** an image alone in its paragraph becomes a figure, and its title
  is the caption (Markdown allowed):
  `![Alt text](./map.png "Caption with a [link](https://example.com)")`.
  Images in posts open enlarged when clicked.
- **Code block titles:** ` ```ts title="bimap.ts" `.

The site has light and dark themes. It follows the reader's system setting
until they pick one with the button at the end of the menu bar (remembered
in their browser). Colours are variables at the top of `static/styles.css`,
with the dark values just below.

Comments use [giscus](https://giscus.app) (GitHub Discussions). Posts are
matched to discussions by path, and giscus creates one on the first comment.
`static/giscus-theme.css` and `giscus-theme-dark.css` style them to match
the site's two themes; giscus loads them from the live site, and on the dev
server `comments.js` passes them inline.
`giscus.json` (read by giscus from this repo) limits which sites may load
the comments: the site's domains and the local dev server.

Pages (About, ...) work the same way in `pages/`, with only `title`, `slug`,
`description`, `og_image`, `draft` and `sidebar` (`false` for a full-width
page without the sidebar).

Posts are full width with an "About the author" box underneath; list pages
and standalone pages have the sidebar, the same on every page.

## Configuration

| File | What it holds |
|---|---|
| `site.json` | Title, description, URL, author, sidebar About (text, photo, links), icons, nav (items can have `children` for a dropdown, or `"menu": "recent"`/`"series"`/`"tags"` for an automatic one), post/page `collections` and their URL patterns, list sizes, `thumbnails`, `thumbnail_layout` (`column`/`beside`), `social_cards`, `comments` (giscus: `repo`, `repo_id`, `category`, `category_id`, `reactions`, `input_position`, `lang`, `theme`, `theme_dark`). |
| `tags.json`, `series.json` | Registries: `"Name": "slug"`, or `"Name": {"slug": ..., "description": ...}`, or `"Name": null`. JSON, YAML or TOML. |
| `redirects.json` | Old paths to new URLs: `"/blog/old-post/": "/2026-10-22/new-post/"`. Targets are checked to exist. |

## What the build produces

Post pages, standalone pages, the paginated front page, tag and series pages
and their indexes, `feed.xml`, `sitemap.xml`, `robots.txt`, `data/*.json`,
a 404 page that redirects mistyped post URLs, redirect pages, social cards
(`og-card.png`) and list thumbnails. Generated images are cached in `.cache/`;
each build removes cached images it no longer uses, and editing the drawing
code (`lib/cards.py`, `lib/images.py`) redraws them.

## Layout

```
build.py, serve.py              entry points
lib/                            the generator (config, sources, models, rendering, images, cards)
templates/, static/             Jinja templates, CSS, JS and web fonts (IBM Plex Sans and Mono)
icons/, images/, fonts/         logo/favicon/pattern, About photo, IBM Plex Mono (for social cards)
posts/, pages/                  content
docs/                           notes (e.g. the planned domain move)
```

## License

Code (generator, templates, styles): [MIT](LICENSE). Writing: CC BY 4.0. The
photo and icons are all rights reserved, and the fonts are under the OFL. See
[`LICENSE-CONTENT.md`](LICENSE-CONTENT.md) for details.
