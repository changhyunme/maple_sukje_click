import unittest
from unittest.mock import patch

from friend_runner import friend_state
from journey_runner import chapter_state, treasure_state
from full_flow_runner import completion_status
from semantic_ui import Screen, UI, field
from ui_guard import ClickVerificationError


def screen(rows, active=None):
    return Screen({'rows': [{'text': t, 'x': x, 'y': y} for t, x, y in rows],
                   'active': active or {'friend_bulk': 0, 'journey_accelerate': 0}}, 'fixture')


def friend(button, counter='30/500', colored=1):
    return screen([('친구', .48, .145), (counter, .65, .89), (button, .78, .875)],
                  {'friend_bulk': colored})


def treasure(percent, colored=0):
    return screen([('보물 경험치', .363, .516), (f'EXP {percent}%', .379, .556),
                   ('가속하기', .760, .533)], {'journey_accelerate': colored})


class RecognitionTests(unittest.TestCase):
    def test_bulk_number_is_not_price_or_fixed_reward(self):
        self.assertEqual(friend_state(friend('일괄 전달')), ('send', 30))
        self.assertEqual(friend_state(friend('모두 수령', '280/500')), ('receive', 280))

    def test_completion_below_daily_cap(self):
        self.assertEqual(friend_state(friend('주고받기 완료', '440/500', 0)), ('done', 440))

    def test_unknown_or_disabled_button_stops(self):
        self.assertIsNone(friend_state(friend('구매하기')))
        self.assertIsNone(friend_state(friend('일괄 전달', colored=0)))
        self.assertIsNone(friend_state(friend('일괄 전달', counter='not visible')))

    def test_popup_must_be_dismissed_before_next_claim(self):
        s = friend('모두 수령', '280/500')
        s.rows.append({'text': '아이템 획득', 'x': .48, 'y': .27})
        self.assertIsNone(friend_state(s))

    def test_gray_is_not_full_or_daily_completion(self):
        self.assertEqual(treasure_state(treasure(68.2)), ('unavailable', 68.2))
        self.assertEqual(treasure_state(treasure(200)), ('full', 200))
        self.assertEqual(treasure_state(treasure(68.2, 1)), ('available', 68.2))

    def test_chapter_ignores_stage_and_other_numbers(self):
        s = screen([('11.오르비스 탑', .46, .095), ('Stage 9/10', .48, .135),
                    ('20-10 클리어 시 개방됩니다.', .50, .39)])
        self.assertEqual(chapter_state(s), 11)

    def test_field_hud_behind_menu_is_not_field(self):
        s = screen([('캐릭터', .35, .95), ('성장 던전', .71, .685), ('친구', .71, .447)])
        self.assertIsNone(field(s))

    def test_pending_journey_is_not_overall_complete(self):
        self.assertEqual(completion_status({'pre_mission_status': 'completed',
                         'journey_treasure': {'status': 'pending_reward_selection'}}), 'partial')


class ActionGateTests(unittest.TestCase):
    def test_wait_requires_same_counter_twice(self):
        ui = UI.__new__(UI)
        ui.events = []
        ui.directory = 'fixture'
        observations = iter([friend('모두 수령', '30/500'), friend('모두 수령', '280/500'),
                             friend('모두 수령', '280/500')])
        ui.capture = lambda _: next(observations)
        with patch('semantic_ui.time.sleep'):
            _, value = ui.wait('counter', friend_state)
        self.assertEqual(value, ('receive', 280))
        self.assertEqual(len(ui.events), 1)

    def test_timeout_does_not_repeat_claim_click(self):
        ui = UI.__new__(UI)
        ui.events = []
        ui.pid = 123
        ui.wait = lambda *a: (_ for _ in ()).throw(ClickVerificationError('timeout'))
        with patch('semantic_ui.click_ratio', return_value={}) as click, patch('semantic_ui.time.sleep'):
            with self.assertRaises(ClickVerificationError):
                ui.click('reward', .76, .875, lambda s: None)
        click.assert_called_once()


if __name__ == '__main__':
    unittest.main()
