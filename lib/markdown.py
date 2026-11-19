"""The site's Markdown renderer: CommonMark + tables + strikethrough, plus

- Figures: an image alone in its own paragraph becomes
      <figure><img ...><figcaption>...</figcaption></figure>
  with the image's title as the caption. Markdown works in the caption:
      ![Alt text for screen readers](./map.png "The caption. [Source](https://example.com)")
  Images inside running text stay plain inline images. A lone image with no
  title is still a figure, just without a caption.
- Lazy loading: every image gets loading="lazy" decoding="async".
- Image sizes: images next to the post (relative paths) get width/height
  attributes, so lazy-loaded images don't make the page jump. Pass
  env={'base_dir': <post folder>, 'where': <file for messages>} to render;
  a missing image file is a warning.
- Code block titles (Docusaurus-style info strings):
      ```ts title="bimap.ts"
  renders a title bar above the block. Other options in the info string
  (showLineNumbers, {1,3-4}, ...) are parsed but not used yet.
"""
import re

import markdown_it
from markdown_it.rules_core import StateCore
from markupsafe import escape

from .build_environment import BuildEnvironment
from .images import image_size

# key="value", key='value' or key=value in a fence's info string.
FENCE_ATTR_RE = re.compile(r'''(\w+)=(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)'|(\S+))''')

md = markdown_it.MarkdownIt('commonmark').enable('table').enable('strikethrough')


def _mark_figures(state: StateCore):
    """Turn <p> around a lone image into <figure>, and flag the image."""
    tokens = state.tokens
    for i in range(len(tokens) - 2):
        opening, inline, closing = tokens[i:i + 3]
        if opening.type != 'paragraph_open' or inline.type != 'inline' or closing.type != 'paragraph_close':
            continue
        children = [c for c in inline.children or [] if not (c.type == 'text' and not c.content.strip())]
        if len(children) == 1 and children[0].type == 'image':
            opening.tag = closing.tag = 'figure'
            children[0].meta['figure'] = True


def _render_image(self, tokens, idx, options, env):
    token = tokens[idx]
    token.attrs['loading'] = 'lazy'
    token.attrs['decoding'] = 'async'
    _add_size(token, env)
    caption = token.attrs.pop('title', None) if token.meta.get('figure') else None
    html = self.image(tokens, idx, options, env)
    if caption:
        html += f'<figcaption>{md.renderInline(str(caption))}</figcaption>'
    return html


def _add_size(token, env):
    base_dir = (env or {}).get('base_dir')
    src = str(token.attrs.get('src', ''))
    if base_dir is None or not src or re.match(r'^([a-zA-Z][a-zA-Z0-9+.-]*:|/|#)', src):
        return  # remote, root-relative or no context: leave as is
    path = base_dir / src.split('#', 1)[0].split('?', 1)[0]
    if not path.is_file():
        BuildEnvironment.emit_warning(f"{env.get('where', base_dir)}: image '{src}' not found.")
        return
    size = image_size(path)
    if size:
        token.attrs['width'], token.attrs['height'] = str(size[0]), str(size[1])


def parse_fence_info(info: str) -> tuple[str, dict[str, str]]:
    """'ts title="bimap.ts" showLineNumbers' -> ('ts', {'title': 'bimap.ts'})"""
    info = info.strip()
    lang, _, rest = info.partition(' ') if not info.startswith(('{', 'title=')) else ('', '', info)
    attrs = {}
    for m in FENCE_ATTR_RE.finditer(rest):
        value = next(v for v in m.groups()[1:] if v is not None)
        attrs[m.group(1)] = re.sub(r'\\(.)', r'\1', value)
    return lang, attrs


def _render_fence(self, tokens, idx, options, env):
    token = tokens[idx]
    lang, attrs = parse_fence_info(token.info)
    token.info = lang                       # the default renderer only sees the language
    html = self.fence(tokens, idx, options, env)
    title = attrs.get('title')
    if not title:
        return html
    return (f'<figure class="code-block"><figcaption class="code-block__title">{escape(title)}</figcaption>'
            f'{html}</figure>\n')


md.core.ruler.push('figures', _mark_figures)
md.add_render_rule('image', _render_image)
md.add_render_rule('fence', _render_fence)
