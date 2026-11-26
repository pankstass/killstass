"""v1.14: one light request for the menu groups (GET /api/nav-summary) — the short summaries on the tiles of the
group pages (#muster, #results, #club) and the dot on a group whose sections wait for the player: a result to
confirm, an incoming challenge or friend request, a planned game night without an answer. Counts only."""
from fastapi import Depends
from . import main as core


@core.app.get('/api/nav-summary')
def nav_summary(u=Depends(core.user)):
    with core.pool.connection() as c:
        r = core.one(c, '''SELECT
        (SELECT count(*)::int FROM matches m JOIN match_players p ON p.match_id=m.id AND p.user_id=%(u)s
          WHERE m.status='awaiting_confirmation' AND m.submitted_by IS DISTINCT FROM %(u)s) AS to_confirm,
        (SELECT count(*)::int FROM player_results WHERE user_id=%(u)s) AS games,
        (SELECT round(100.0*count(*) FILTER(WHERE result='win')/nullif(count(*),0))::int FROM player_results WHERE user_id=%(u)s) AS win_rate,
        (SELECT count(*)::int FROM matches m JOIN match_players p ON p.match_id=m.id AND p.user_id=%(u)s
          WHERE m.status IN ('setup','active')) AS live,
        (SELECT count(*)::int FROM challenges WHERE recipient_id=%(u)s AND status='pending' AND expires_at>now()) AS challenges,
        (SELECT count(*)::int FROM friendships WHERE recipient_id=%(u)s AND status='pending') AS requests,
        (SELECT count(*)::int FROM friendships WHERE %(u)s IN (requester_id,recipient_id) AND status='accepted') AS friends,
        (SELECT min(starts_at) FROM game_nights WHERE status='planned' AND ends_at>now()) AS next_night,
        (SELECT count(*)::int FROM game_nights n WHERE n.status='planned' AND n.ends_at>now()
          AND NOT EXISTS(SELECT 1 FROM game_night_rsvps r WHERE r.night_id=n.id AND r.user_id=%(u)s)) AS unanswered,
        (SELECT count(*)::int FROM tournaments t WHERE t.status='active' AND (t.owner_id=%(u)s
          OR EXISTS(SELECT 1 FROM tournament_players p WHERE p.tournament_id=t.id AND p.user_id=%(u)s))) AS tournaments,
        (SELECT count(*)::int FROM rosters WHERE user_id=%(u)s) AS rosters,
        (SELECT count(*)::int FROM rosters WHERE user_id=%(u)s AND NOT coalesce((summary->>'valid')::boolean,false)) AS rosters_invalid,
        (SELECT count(*)::int FROM boards WHERE owner_id=%(u)s AND match_id IS NULL) AS maps''', {'u': u['id']})
    return {'history': {'games': r['games'], 'to_confirm': r['to_confirm'], 'live': r['live']},
            'stats': {'games': r['games'], 'win_rate': r['win_rate']},
            'friends': {'friends': r['friends'], 'challenges': r['challenges'], 'requests': r['requests']},
            'nights': {'next': r['next_night'], 'unanswered': r['unanswered']},
            'tournaments': {'active': r['tournaments']},
            'rosters': {'count': r['rosters'], 'invalid': r['rosters_invalid']},
            'maps': {'count': r['maps']}}
