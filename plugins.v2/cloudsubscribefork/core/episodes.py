"""Narrow correction for Bangumi totals including opening/ending entries."""

def bangumi_main_episode_total(current, season, tmdb_total, subject):
    """Only replace an exact mixed total corroborated by both metadata sources."""
    if not isinstance(subject, dict):
        return current
    try:
        values = (current, season, tmdb_total, subject.get('eps'), subject.get('total_episodes'))
        if any(isinstance(value, bool) for value in values):
            return current
        old, season_number, main, bgm_main, mixed = map(int, values)
    except (TypeError, ValueError):
        return current
    if season_number == 1 and 0 < main == bgm_main < mixed == old:
        return main
    return current
