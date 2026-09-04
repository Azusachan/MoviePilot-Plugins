"""Personal Japanese-anime fansub policy; source candidates only, never files.

Preference tiers are subjective, based on the references documented in FORK.md.
Encoding groups alone do not establish subtitle provenance.
"""
import re

TIERS = (
    r"SweetSub|千夏|Airota|拨雪寻春|撥雪尋春|Haru[ &]+Hana|喵萌奶茶|Nekomoe[ ._-]*Kissaten",
    r"诸神|諸神|Kamigami|澄空|Sumisora|华盟|華盟|CASO|北宇治|Kitauji|霜庭云花|霜庭雲花|STYH",
    r"桜都|樱都|櫻都|Sakurato|豌豆|Dymy|动漫国|動漫國|DMG|极影|極影|KTXP",
)
NO_SUBS = re.compile(r"无字幕|無字幕|无字版|無字版|生肉|\b(?:unsubbed|no[ ._-]*subs?|subtitle[ ._-]*free)\b", re.I)
CHINESE = re.compile(r"简[体體繁中]|簡[体體繁中]|繁[体體简簡中]|中[日英双雙文]|[简簡繁]日|\b(?:CHS|CHT|BIG5|SC|TC|ZH|CHI|ZHO)(?:\b|_)", re.I)


def fansub_priority(title):
    """None rejects; larger integer is preferred. Unknown named subs are fallback."""
    title = str(title or "")
    if NO_SUBS.search(title) or not CHINESE.search(title):
        return None
    # Only release tags establish the group, not incidental prose in a description.
    tags = " ".join(left or right for left, right in
                    re.findall(r"\[([^\]]+)\]|【([^】]+)】", title))
    for index, pattern in enumerate(TIERS):
        if re.search(pattern, tags, re.I):
            return 400 - index * 100
    if re.search(r"[^\s\[\]]{2,}(?:字幕组|字幕組|字幕社|字幕屋)", tags):
        return 100
    return None


def filter_fansubs(resources):
    accepted = []
    for resource in resources:
        priority = fansub_priority(resource.get("title") or resource.get("name"))
        if priority is not None:
            accepted.append({**resource, "fansub_priority": priority})
    return sorted(accepted, key=lambda item: -item["fansub_priority"])


def is_japanese_anime(media):
    category = str(getattr(media, "category", "") or "")
    genres = getattr(media, "genre_ids", None) or []
    return "日番" in category or (
        str(getattr(media, "original_language", "")) == "ja"
        and any(str(value) == "16" for value in genres)
    )
