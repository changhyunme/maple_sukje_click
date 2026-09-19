import unittest
from fast_hunt_guard import fast_hunt_state, remaining_free_claims
from semantic_ui import Screen
from ui_guard import ClickVerificationError


def screen(body):
    rows = [{'text': '빠른 사냥', 'x': .48, 'y': .17},
            {'text': '무기 소환하기: 1/1', 'x': .13, 'y': .31}]
    rows += [{'text': text, 'x': .48, 'y': .63 + i * .035}
             for i, text in enumerate(body)]
    return Screen({'rows': rows, 'active': {}}, 'test')


class GuardTests(unittest.TestCase):
    def test_paid_tab_background_quest_is_not_free(self):
        self.assertEqual(fast_hunt_state(screen(['이번 회차 비용', '750', '금일 구매 가능 횟수 : 2/3'])), ('paid', 0))

    def test_ad_count_is_local(self):
        self.assertEqual(fast_hunt_state(screen(['광고 보상 남은 횟수', '0/1'])), ('ad', 0))

    def test_accumulated_free_claims(self):
        self.assertEqual(fast_hunt_state(screen(['무료 보상 남은 횟수', '2/1'])), ('free', 2))

    def test_wrong_tab_stops_before_claim(self):
        class UI:
            def wait(self, label, classify):
                s = screen(['이번 회차 비용', '500'])
                return s, classify(s)
        with self.assertRaises(ClickVerificationError):
            remaining_free_claims(UI(), 'ad')
        self.assertEqual(remaining_free_claims(UI(), 'free'), 0)

    def test_title_in_background_does_not_qualify(self):
        s = screen(['광고 보상 남은 횟수', '1/1'])
        s.rows[0]['y'] = .90
        self.assertIsNone(fast_hunt_state(s))
