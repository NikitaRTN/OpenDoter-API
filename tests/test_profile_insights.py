import unittest
from unittest.mock import patch
from server_modules.profile_insights import impact_score, parse_filters, summarize, get_player_insights

class ProfileInsightsTests(unittest.TestCase):
    def row(self, **kw):
        r=dict(duration=1800,game_mode=22,player_slot=0,radiant_win=True,kills=8,deaths=4,assists=12,hero_damage=24000,tower_damage=6000,gold_per_min=550,xp_per_min=650)
        r.update(kw)
        return r
    def test_bounds(self):
        for r in [self.row(),self.row(deaths=0),self.row(hero_damage=999999),self.row(kills=0,assists=0)]:
            self.assertTrue(0 <= impact_score(r)['score'] <= 1000)
    def test_missing_not_zero(self):
        missing=impact_score(self.row(hero_damage=None))
        zero=impact_score(self.row(hero_damage=0))
        self.assertNotIn('damage',missing['components'])
        self.assertEqual(zero['components']['damage']['score'],0)
        self.assertLess(missing['coverage'],zero['coverage'])
    def test_short(self): self.assertIsNone(impact_score(self.row(duration=200))['score'])
    def test_no_win_bonus(self): self.assertEqual(impact_score(self.row(radiant_win=True)),impact_score(self.row(radiant_win=False)))
    def test_damage_monotonic(self): self.assertGreater(impact_score(self.row(hero_damage=40000))['score'],impact_score(self.row(hero_damage=1000))['score'])
    def test_death_penalty(self): self.assertLess(impact_score(self.row(deaths=10))['score'],impact_score(self.row(deaths=2))['score'])
    def test_turbo_normalization(self): self.assertLess(impact_score(self.row(game_mode=23))['score'],impact_score(self.row(game_mode=22))['score'])
    def test_roaming_not_support(self): self.assertEqual(impact_score(self.row(lane_role=4))['components'],impact_score(self.row(lane_role=1))['components'])
    def test_zero_filters(self): self.assertEqual(parse_filters({'win':['0'],'is_radiant':['0'],'lobby_type':['0']}),dict(win=0,is_radiant=0,lobby_type=0))
    def test_invalid_filter(self):
        for qs in [{'win':['2']},{'hero_id':['-1']},{'patch':['<script>']}]:
            with self.assertRaises(ValueError): parse_filters(qs)
    def test_weighted_rate(self): self.assertAlmostEqual(summarize([self.row(duration=600,hero_damage=10000),self.row(duration=1800,hero_damage=10000)])['hero_dpm'],500)
    def test_partial_support_coverage(self): self.assertGreater(impact_score(self.row(hero_healing=0,stuns=0,obs_placed=0))['coverage'],impact_score(self.row(hero_healing=0))['coverage'])
    def test_missing_all(self): self.assertIsNone(impact_score({'duration':1800})['score'])
    def test_empty(self): self.assertIsNone(summarize([])['impact'])

    def test_filtered_pagination_summary_and_zero_forwarding(self):
        import tempfile
        from pathlib import Path
        from urllib.parse import urlparse, parse_qs
        calls=[]
        allrows=[self.row(match_id=i,hero_id=49) for i in range(180,60,-1)]
        def fake(path,url,ttl,label):
            calls.append(url)
            if '/constants/' in url:return []
            q=parse_qs(urlparse(url).query)
            self.assertEqual(q.get('win'),['0'])
            self.assertEqual(q.get('hero_id'),['49'])
            offset=int(q['offset'][0]);limit=int(q['limit'][0])
            return allrows[offset:offset+limit]
        with tempfile.TemporaryDirectory() as tmp, patch('server_modules.profile_insights.get_player_dir',return_value=Path(tmp)), patch('server_modules.profile_insights._read_cached_or_fetch',side_effect=fake):
            a=get_player_insights('1',{'hero_id':['49'],'win':['0'],'page':['1']})
            b=get_player_insights('1',{'hero_id':['49'],'win':['0'],'page':['2']})
            c=get_player_insights('1',{'hero_id':['49'],'win':['0'],'page':['4']})
            self.assertEqual(a['summary'],b['summary'])
            self.assertEqual(a['summary']['games'],100)
            self.assertEqual(len(a['matches']),25)
            self.assertNotEqual(a['matches'][0]['match_id'],b['matches'][0]['match_id'])
            self.assertTrue(c['has_next'])
            self.assertEqual(c['matches'][0]['match_id'],105)

if __name__ == '__main__':unittest.main()
