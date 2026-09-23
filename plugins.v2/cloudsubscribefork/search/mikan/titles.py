"""Bounded search aliases from the identified media, never from release titles."""
import re
from typing import Any, Iterable, List


def unique_titles(values: Iterable[Any]) -> List[str]:
    titles, seen = [], set()
    for value in values:
        if not isinstance(value, str):
            continue
        title = value.strip()
        if not title or len(title) > 200 or title.casefold() in seen:
            continue
        seen.add(title.casefold())
        titles.append(title)
    return titles


def metadata_aliases(media: Any) -> List[str]:
    """MoviePilot's identified TMDB/Bangumi media carries alternative names."""
    names = getattr(media, 'names', None)
    if not isinstance(names, (list, tuple)):
        names = []
    return unique_titles([
        *names,
        *(getattr(media, field, None) for field in
          ('en_title', 'hk_title', 'tw_title', 'sg_title')),
    ])


def search_keywords(base: List[str], aliases: List[str], limit: int = 6) -> List[str]:
    # Keep the requested title first; reserve early slots for alternative Chinese
    # translations instead of losing them behind a three-title truncation.
    chinese = [title for title in aliases if re.search(r'[\u4e00-\u9fff]', title)]
    return unique_titles([*base[:1], *chinese, *base[1:], *aliases])[:limit]
