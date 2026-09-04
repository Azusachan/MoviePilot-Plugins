"""Reserve episodes already submitted for the same subscription and season."""
def unreserved_episodes(pending, subscribe_id, season, targets):
    reserved = set()
    for item in (pending or {}).values():
        if (int(item.get('subscribe_id') or 0) == int(subscribe_id or 0)
                and int(item.get('season') or 0) == int(season or 0)
                and item.get('task_type') == 'magnet'
                and not item.get('upgrade')):
            reserved.update(int(value) for value in item.get('target_episodes', []) if int(value) > 0)
    return sorted(set(targets or []) - reserved)
