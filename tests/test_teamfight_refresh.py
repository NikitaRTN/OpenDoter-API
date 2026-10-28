import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from server_modules import matches

class TeamfightRefreshTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.blob = self.folder / 'parsed_blob.json'
        self.old = {'players': [{'gold': 123}], 'teamfights': [{'start': 10, 'end': 20, 'legacy': True}], 'other': 'retained'}
        self.blob.write_text(json.dumps(self.old), encoding='utf-8')
        (self.folder / 'parsed.jsonl').write_text('events', encoding='utf-8')

    def test_rebuild_changes_only_teamfights(self):
        fights = [{'start': 10, 'end': 20, 'actions_version': 1, 'actions': [{'time': 11}]}]
        def build(match_id, jsonl, out):
            self.assertEqual(jsonl, self.folder / 'parsed.jsonl')
            out.write_text(json.dumps({'players': ['different'], 'teamfights': fights}), encoding='utf-8')
        with patch.object(matches, 'build_blob', side_effect=build):
            matches.refresh_teamfight_details('123', self.folder, self.blob)
        result = json.loads(self.blob.read_text(encoding='utf-8'))
        self.assertEqual(result['players'], self.old['players'])
        self.assertEqual(result['other'], self.old['other'])
        self.assertEqual(result['teamfights'], fights)
        self.assertEqual(list(self.folder.glob('*.tmp')), [])

    def test_failed_or_invalid_build_leaves_original_untouched(self):
        original = self.blob.read_bytes()
        def invalid(match_id, jsonl, out):
            out.write_text('{"teamfights": [{"actions_version": 1}]}', encoding='utf-8')
        with patch.object(matches, 'build_blob', side_effect=invalid):
            with self.assertRaises(RuntimeError): matches.refresh_teamfight_details('123', self.folder, self.blob)
        self.assertEqual(self.blob.read_bytes(), original)
        with patch.object(matches, 'build_blob', side_effect=RuntimeError('build failed')):
            with self.assertRaises(RuntimeError): matches.refresh_teamfight_details('123', self.folder, self.blob)
        self.assertEqual(self.blob.read_bytes(), original)
        self.assertEqual(list(self.folder.glob('*.tmp')), [])

    def test_missing_log_does_not_modify_blob(self):
        (self.folder / 'parsed.jsonl').unlink()
        with self.assertRaises(RuntimeError): matches.refresh_teamfight_details('123', self.folder, self.blob)
        self.assertEqual(json.loads(self.blob.read_text(encoding='utf-8')), self.old)

    def test_cached_match_refreshes_only_when_requested(self):
        (self.folder / 'match.json').write_text('{}', encoding='utf-8')
        with patch.object(matches, 'get_match_dir', return_value=self.folder), \
             patch.object(matches, 'refresh_teamfight_details') as refresh, \
             patch.object(matches, '_refresh_players_index_after_parse'):
            matches.parse_match('123')
            refresh.assert_not_called()
            matches.parse_match('123', refresh_teamfights=True)
            refresh.assert_called_once_with('123', self.folder, self.blob)
            self.assertEqual(matches.parse_status['123']['state'], 'done')

if __name__ == '__main__': unittest.main()
