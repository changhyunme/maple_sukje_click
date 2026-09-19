#!/usr/bin/env python3
"""Inspect Journey Treasure and use at most two available daily accelerations.

Never choose a treasure card implicitly. A full gauge and an unavailable
button are separate outcomes, neither is proof of a daily claim.
"""
from __future__ import annotations

import argparse
import json
import re

from semantic_ui import UI, close_to_field, field, open_menu
from ui_guard import ClickVerificationError


def journey_entry(screen):
    if screen.has(r'20\s*-\s*10.*개방'):
        return 'locked'
    if screen.has('여정의 상자', (0, .14, .17, .12)):
        return 'open'


def treasure_state(screen):
    if not screen.has('보물 경험치', (.30, .49, .13, .06)):
        return None
    match = re.search(r'EXP\s*([\d.]+)\s*%', screen.text((.32, .535, .10, .045)))
    if not match or not screen.has('가속하기', (.705, .5, .12, .06)):
        return None
    percent = float(match.group(1))
    if not 0 <= percent <= 200:
        return None
    if percent >= 200:
        return ('full', percent)
    active = screen.active['journey_accelerate'] > .35
    return ('available' if active else 'unavailable', percent)


def chapter_state(screen):
    match = re.search(r'(?<!\d)(\d{1,2})\s*\.\s*[가-힣]', screen.text((.34, .07, .26, .045)))
    if match:
        return int(match.group(1))


def run(pid):
    ui = UI(pid, 'journey')
    try:
        open_menu(ui)
        _, chapter = ui.wait('chapter', chapter_state)
        if chapter < 20:
            ui.click('menu_close', .936, .095, field)
            return ui.save({'pid': pid, 'status': 'locked', 'chapter': chapter,
                            'reason': 'requires_20-10_clear', 'accelerations': 0})
        _, entry = ui.click('journey_open', .922, .317, journey_entry)
        if entry == 'locked':
            ui.click('menu_close', .936, .095, field)
            return ui.save({'pid': pid, 'status': 'locked', 'reason': 'requires_20-10_clear', 'accelerations': 0})
        _, state = ui.click('treasure_open', .08, .411, treasure_state)
        initial = state[1]
        count = 0
        while state[0] == 'available' and count < 2:
            before = state[1]
            # Only the identified gauge button is allowed. If a new dialog
            # appears, stop for inspection instead of guessing a confirm or
            # clicking a reward-card/purchase button.
            _, state = ui.click('accelerate_' + str(count + 1), .760, .530,
                                lambda s: treasure_state(s) if treasure_state(s)
                                and treasure_state(s)[1] > before else None,
                                timeout=60)
            count += 1
        status = ('pending_reward_selection' if state[0] == 'full' else
                  'unavailable' if count == 0 else
                  'remaining_available' if state[0] == 'available' else 'completed')
        close_to_field(ui, 'journey_close', .930, .090)
        return ui.save({'pid': pid, 'status': status, 'accelerations': count,
                        'initial_exp': initial, 'final_exp': state[1],
                        'button_state': state[0]})
    except Exception as exc:
        ui.save({'pid': pid, 'status': 'failed', 'error': str(exc)})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('pid', type=int)
    args = parser.parse_args()
    print(json.dumps(run(args.pid), ensure_ascii=False))
