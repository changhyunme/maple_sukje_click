#!/usr/bin/env python3
"""Inspect live friend bulk send/receive on every invocation.

The number beside the bottom-right button is the reward, not a purchase price.
A same-day cache must not hide gifts which arrive later in the day.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from instance_registry import instance_name
from semantic_ui import UI, close_to_field, open_menu, reward
from ui_guard import ClickVerificationError


def friend_state(screen):
    if reward(screen) or not screen.has('친구', (.4, .1, .2, .065)):
        return None
    text = screen.text((.60, .84, .09, .085))
    counter = re.search(r'(\d+)\s*/\s*500', text)
    button = screen.text((.68, .84, .17, .075))
    if not counter:
        return None
    value = int(counter.group(1))
    if not 0 <= value <= 500:
        return None
    if re.search(r'주고받기\s*완료', button):
        return ('done', value)
    if screen.active['friend_bulk'] <= .35:
        return None
    if re.search(r'일괄\s*전달', button):
        return ('send', value)
    if re.search(r'모두\s*수[령렁]', button):
        return ('receive', value)
    return None


def run(pid, *, force=False, already_open=False):
    # force is retained for CLI compatibility; inspection is always live now.
    ui = UI(pid, 'friend-bulk')
    try:
        if not already_open:
            open_menu(ui)
            _, state = ui.click('friend_open', .714, .424, friend_state)
        else:
            _, state = ui.wait('friend_resume', friend_state)
        initial = state[1]
        amounts = {}
        for _ in range(2):
            action, before = state
            if action == 'done':
                break
            if action in amounts:
                raise ClickVerificationError('same bulk action still offered after successful exchange')
            ui.click('friend_' + action, .762, .875, reward)
            # The popup and a real counter increase are both mandatory.
            _, state = ui.click('dismiss_' + action, .135, .86,
                                lambda s: friend_state(s) if friend_state(s)
                                and friend_state(s)[1] > before else None)
            amounts[action] = state[1] - before
        if state[0] != 'done':
            raise ClickVerificationError('bulk exchange did not finish within send + receive')
        close_to_field(ui, 'friend_close', .85, .142)
        result = ui.save({'pid': pid, 'status': 'completed', 'initial_points': initial,
                          'final_points': state[1], 'rewards': amounts,
                          'checked_at': datetime.now().astimezone().isoformat(),
                          'scope': 'currently_available_gifts'})
        # This is an audit record, never a same-day skip gate.
        path = Path(__file__).with_name('.friend_bulk_state.json')
        try:
            records = json.loads(path.read_text())
        except (OSError, ValueError):
            records = {}
        records[instance_name(pid)] = {k: v for k, v in result.items() if k != 'events'}
        path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n')
        return result
    except Exception as exc:
        ui.save({'pid': pid, 'status': 'failed', 'error': str(exc)})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('pid', type=int)
    parser.add_argument('--force', action='store_true', help='compatibility: live inspection is always performed')
    parser.add_argument('--already-open', action='store_true')
    args = parser.parse_args()
    print(json.dumps(run(args.pid, force=args.force, already_open=args.already_open), ensure_ascii=False))
