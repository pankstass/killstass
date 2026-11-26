"""Pure lifecycle and scoring rules, independent of official edition content."""
from datetime import datetime


def challenge_transition(status, action, actor_is_sender, expires_at, now):
    if status == 'pending' and expires_at <= now:
        return 'expired'
    if status != 'pending':
        raise ValueError('challenge_not_pending')
    allowed = {'cancelled'} if actor_is_sender else {'accepted', 'declined'}
    if action not in allowed:
        raise ValueError('challenge_action_forbidden')
    return action


def match_transition(status, action, is_submitter=False, kind='friend', is_creator=False):
    if action == 'start' and status == 'setup': return 'active'
    if action == 'cancel' and status == 'setup' and is_creator: return 'cancelled'
    # Hot-seat: one device, no remote opponent to confirm; finishing (or conceding, v1.13) locks the result.
    if kind == 'hotseat':
        if action in ('finish', 'concede') and status == 'active': return 'unconfirmed'
        raise ValueError('invalid_match_transition')
    # v1.13: a concession ends the match like finishing it; the opponent confirms (or disputes) it.
    if action in ('finish', 'concede') and status == 'active': return 'awaiting_confirmation'
    if action == 'confirm' and status == 'awaiting_confirmation' and not is_submitter: return 'confirmed'
    if action == 'dispute' and status == 'awaiting_confirmation' and not is_submitter: return 'disputed'
    if action == 'reopen' and status == 'disputed': return 'active'
    raise ValueError('invalid_match_transition')


def outcome(own, other):
    return 'win' if own > other else 'draw' if own == other else 'loss'


def score_after(old, delta, maximum):
    value = old + delta
    if not 0 <= value <= maximum: raise ValueError('score_out_of_range')
    return value


def primary_bonus(vp):
    if not isinstance(vp,int) or not 0 <= vp <= 6: raise ValueError('component_out_of_range')
    return (vp+1)//2


def kill_grade(incapacitated, thresholds):
    if incapacitated < 0: raise ValueError('kills_out_of_range')
    return sum(incapacitated >= threshold for threshold in thresholds)


def slot_allowed(row_user_id, actor_id, kind, is_creator):
    """Own slot always; the other slot only for the creator (controller) of a hot-seat match."""
    return row_user_id == actor_id or (kind == 'hotseat' and is_creator and row_user_id is None)


def invite_state(expires_at, used_at, now):
    if used_at is not None: raise ValueError('invite_used')
    if expires_at <= now: raise ValueError('invite_expired')
    return 'open'


def final_totals(players, scoring_mode):
    """Preview of end-of-battle totals; mirrors player_totals for an ended match.

    players: two dicts with crit, tac, grade, raw_vp, primary_op, primary_committed.
    """
    if scoring_mode != 'approved2025':
        return [{'base': p['raw_vp'], 'vp': p['raw_vp'], 'kill': None, 'kill_bonus': 0, 'primary_bonus': 0} for p in players]
    out = []
    for p, other in ((players[0], players[1]), (players[1], players[0])):
        kill_bonus = 1 if p['grade'] > other['grade'] else 0
        kill = p['grade'] + kill_bonus
        chosen = {'crit': p['crit'], 'tac': p['tac'], 'kill': kill}.get(p['primary_op']) if p['primary_committed'] else None
        bonus = primary_bonus(min(chosen, 6)) if chosen is not None else 0
        base = p['crit'] + p['tac'] + kill
        out.append({'base': base, 'vp': base + bonus, 'kill': kill, 'kill_bonus': kill_bonus, 'primary_bonus': bonus})
    return out


def redact_preview(row, is_viewer):
    """The primary choice stays secret until finish: only the viewer's own bonus is disclosed."""
    if is_viewer:
        return row
    return {**row, 'primary_op': None, 'primary_bonus': None, 'vp': None}


CLOCK_MODES = ('stopwatch', 'chess', 'countdown')


def clock_state(events, now):
    """Fold clock events (dicts: id, action, mode, limit_seconds, slot, server_ts) into elapsed seconds at `now`.

    A 'configure' event resets everything. Stopwatch tracks only the total; chess and countdown also
    charge the running time to the active slot. Countdown never stops the game when time runs out.
    """
    s = {'mode': None, 'limit_seconds': None, 'running': False, 'active_slot': None,
         'total_seconds': 0.0, 'slots': {1: 0.0, 2: 0.0}, 'started': False, 'seq': 0}
    since = None

    def charge(until):
        d = max(0.0, (until - since).total_seconds())
        s['total_seconds'] += d
        if s['active_slot']:
            s['slots'][s['active_slot']] += d

    for e in events:
        s['seq'] = e['id']
        a, ts = e['action'], e['server_ts']
        if a == 'configure':
            s.update(mode=e['mode'], limit_seconds=e['limit_seconds'], running=False, active_slot=None,
                     total_seconds=0.0, slots={1: 0.0, 2: 0.0}, started=False)
        elif a == 'start' and s['mode'] and not s['running']:
            s['running'], s['started'], since = True, True, ts
            if s['mode'] != 'stopwatch':
                s['active_slot'] = e['slot'] or s['active_slot'] or 1
        elif a == 'pause' and s['running']:
            charge(ts)
            s['running'] = False
        elif a == 'switch' and s['running'] and s['mode'] != 'stopwatch':
            charge(ts)
            since = ts
            s['active_slot'] = 3 - s['active_slot']
    if s['running']:
        charge(now)
    out = {**s, 'slots': [{'slot': k, 'elapsed_seconds': round(v, 3),
                           'remaining_seconds': round(s['limit_seconds'] - v, 3) if s['mode'] == 'countdown' else None}
                          for k, v in s['slots'].items()]}
    out['total_seconds'] = round(s['total_seconds'], 3)
    return out


def clock_command(state, action, slot=None, mode=None, limit_seconds=None):
    """Validate a clock command against the folded state.

    Returns the event to append, or None for a harmless repeat (double tap, second phone).
    Raises ValueError with an API error code otherwise.
    """
    if action == 'configure':
        if mode not in CLOCK_MODES: raise ValueError('clock_mode_invalid')
        if state['running']: raise ValueError('clock_running')
        if mode == 'countdown' and not (limit_seconds and 60 <= limit_seconds <= 36000): raise ValueError('clock_limit_invalid')
        return {'action': 'configure', 'mode': mode, 'limit_seconds': limit_seconds if mode == 'countdown' else None, 'slot': None}
    if not state['mode']: raise ValueError('clock_not_configured')
    if action == 'start':
        if state['running']: return None
        return {'action': 'start', 'mode': None, 'limit_seconds': None,
                'slot': None if state['mode'] == 'stopwatch' else (slot or state['active_slot'] or 1)}
    if action == 'pause':
        return {'action': 'pause', 'mode': None, 'limit_seconds': None, 'slot': None} if state['running'] else None
    if action == 'switch':
        if state['mode'] == 'stopwatch': raise ValueError('clock_mode_invalid')
        if not state['running']: raise ValueError('clock_not_running')
        if slot is None: raise ValueError('clock_slot_required')
        # `slot` is the side that ends its activation; a repeated press after the switch is a no-op.
        if slot != state['active_slot']: return None
        return {'action': 'switch', 'mode': None, 'limit_seconds': None, 'slot': slot}
    raise ValueError('clock_action_invalid')
