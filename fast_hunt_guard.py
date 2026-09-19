"""Read free fast-hunt availability from the modal, excluding background quests."""
import re
from ui_guard import ClickVerificationError


def fast_hunt_state(screen):
    if not screen.has(r'빠른\s*사냥', (.30, .12, .40, .12)):
        return None
    body = screen.text((.28, .54, .44, .30))
    if '이번 회차 비용' in body:
        return ('paid', 0)
    match = re.search(r'(무료|광고) 보상 남은 횟수[\s\S]*?(?<!\d)(\d+)\s*/\s*\d+', body)
    if match:
        return ('free' if match[1] == '무료' else 'ad', int(match[2]))


def remaining_free_claims(ui, kind):
    _, state = ui.wait('fast_hunt_' + kind + '_availability', fast_hunt_state)
    if kind == 'free' and state[0] == 'paid':
        return 0
    if state[0] != kind:
        raise ClickVerificationError(f'expected {kind} fast-hunt tab, observed {state[0]}')
    return state[1]
