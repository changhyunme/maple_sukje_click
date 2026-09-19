"""Window-only OCR gates for reward actions; no blind claim retries."""
from __future__ import annotations

import json
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

from mac_gesture import click_ratio, find_window_id
from ui_guard import ClickVerificationError

ROOT = Path(__file__).resolve().parent


class Screen:
    def __init__(self, data, path):
        self.rows = data['rows']
        self.active = data['active']
        self.path = str(path)

    def text(self, region=(0, 0, 1, 1)):
        x, y, w, h = region
        return '\n'.join(row['text'] for row in self.rows
                         if x <= row['x'] <= x + w and y <= row['y'] <= y + h)

    def has(self, pattern, region=(0, 0, 1, 1)):
        return re.search(pattern, self.text(region)) is not None


class UI:
    def __init__(self, pid, task):
        self.pid = pid
        self.directory = ROOT / '.run_audit' / 'scheduled' / (
            f'{datetime.now():%Y%m%d-%H%M%S-%f}-{task}-{pid}')
        self.directory.mkdir(parents=True)
        self.events = []
        self.serial = 0
        self.binary = ROOT / '.run_audit' / 'screen_ocr'
        source = ROOT / 'screen_ocr.swift'
        if not self.binary.exists() or self.binary.stat().st_mtime < source.stat().st_mtime:
            subprocess.run(['swiftc', str(source), '-o', str(self.binary)], check=True)

    def capture(self, label):
        self.serial += 1
        path = self.directory / f'{self.serial:03d}-{label}.png'
        subprocess.run(['screencapture', '-x', '-l', str(find_window_id(self.pid)), str(path)], check=True)
        subprocess.run(['sips', '-Z', '1200', str(path)], check=True, stdout=subprocess.DEVNULL)
        data = json.loads(subprocess.check_output([str(self.binary), str(path)], text=True))
        path.with_suffix('.json').write_text(json.dumps(data, ensure_ascii=False, indent=2))
        return Screen(data, path)

    def wait(self, label, classify, timeout=12):
        """Require the same semantic result twice, including numeric values."""
        deadline = time.monotonic() + timeout
        previous = None
        while time.monotonic() < deadline:
            screen = self.capture(label)
            value = classify(screen)
            if value is not None and value == previous:
                self.events.append({'action': label, 'verified_twice': True,
                                    'state': value, 'evidence': screen.path})
                return screen, value
            previous = value
            time.sleep(1)
        raise ClickVerificationError(f'{label}: expected state not stable; evidence: {self.directory}')

    def click(self, label, x, y, classify, timeout=12):
        self.events.append({'action': label + '_input', **click_ratio(self.pid, x, y)})
        time.sleep(1)
        return self.wait(label, classify, timeout)

    def save(self, result):
        result['events'] = self.events
        result['evidence_directory'] = str(self.directory)
        (self.directory / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        return result


def field(screen):
    if not menu(screen) and not screen.has('아이템 획득') and screen.has('캐릭터', (0.25, 0.90, 0.45, 0.09)):
        # The field HUD can remain visible behind a modal; require no modal title.
        if not screen.has('친구|미션|부스터|여정', (0.35, 0.08, 0.30, 0.15)):
            return 'field'


def menu(screen):
    if screen.has('성장 던전', (0.67, 0.58, 0.12, 0.15)) and screen.has('친구', (0.67, 0.37, 0.12, 0.12)):
        return 'menu'


def open_menu(ui):
    screen, state = ui.wait('initial', lambda s: 'sleep' if s.has('절전 모드 해제') else menu(s) or field(s))
    if state == 'sleep':
        subprocess.run(['python3', str(ROOT / 'mac_gesture.py'), 'unlock', str(ui.pid)], check=True, stdout=subprocess.DEVNULL)
        ui.wait('awake', field)
    if state != 'menu':
        ui.click('menu', .936, .095, menu)


def reward(screen):
    if screen.has('아이템 획득', (0.3, 0.2, 0.4, 0.2)):
        return 'reward'


def close_to_field(ui, label, x, y):
    _, state = ui.click(label, x, y, lambda s: menu(s) or field(s))
    if state == 'menu':
        ui.click(label + '_menu', .936, .095, field)
