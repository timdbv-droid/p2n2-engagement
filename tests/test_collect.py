import importlib.util
import json
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / 'collect.py'
spec = importlib.util.spec_from_file_location('collector', path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class CollectorTests(unittest.TestCase):
    def test_metrics_and_profile_scope(self):
        u = '12345678-1234-1234-1234-123456789abc'
        a = {"recordType":"song","id":u,"creatorHandle":"p2n2","is_public":True,"title":"One","commentCount":8,"upvoteCount":12,"playCount":100}
        b = {"recordType":"song","id":"23456789-1234-1234-1234-123456789abc","creatorHandle":"elsewhere","is_public":True,"title":"Not ours","commentCount":99}
        snapshot = m.build_snapshot([a,b])
        self.assertEqual(snapshot['songs_found'],1)
        self.assertEqual(snapshot['songs'][0]['comments'],8)
        self.assertEqual(snapshot['songs'][0]['likes'],12)
        self.assertEqual(snapshot['songs'][0]['plays'],100)
    def test_missing_not_zero(self):
        a = {"recordType":"song","id":"12345678-1234-1234-1234-123456789abc","creatorHandle":"p2n2","is_public":True,"playCount":3,"commentCount":0}
        snapshot = m.build_snapshot([a])
        self.assertEqual(snapshot['songs'][0]['comments'], 0)
        self.assertIsNone(snapshot['songs'][0]['likes'])
        self.assertEqual(snapshot['metrics_coverage']['likes'],0)
    def test_missing_comments_fails(self):
        a = {"recordType":"song","id":"12345678-1234-1234-1234-123456789abc","creatorHandle":"p2n2","is_public":True,"playCount":3}
        with self.assertRaisesRegex(RuntimeError, 'no comment counts'):
            m.build_snapshot([a])
    def test_suspicious_partial_scrape_fails(self):
        a = {"recordType":"song","id":"12345678-1234-1234-1234-123456789abc","creatorHandle":"p2n2","is_public":True,"commentCount":1}
        with self.assertRaisesRegex(RuntimeError, 'incomplete scrape'):
            m.build_snapshot([a], {"songs":[{"id":str(i)} for i in range(20)]})
    def test_no_scrape_no_overwrite(self):
        with self.assertRaises(RuntimeError):m.build_snapshot([])
        with self.assertRaises(RuntimeError):m.build_snapshot([{"recordType":"song","id":"12345678-1234-1234-1234-123456789abc","creatorHandle":"p2n2","is_public":True}])
    def test_private_song_excluded(self):
        a = {'id':'12345678-1234-1234-1234-123456789abc','creatorHandle':'p2n2','title':'Private','is_public':False,'comment_count':5}
        self.assertIsNone(m.normalize_song(a))
        b = dict(a, is_public=True, is_hidden=True)
        self.assertIsNone(m.normalize_song(b))
    def test_profile_envelope(self):
        data = {'clips':[{'id':'12345678-1234-1234-1234-123456789abc','title':'Public'}]}
        self.assertEqual(len(m.extract_profile_songs(data)),1)
    def test_delta(self):
        a = {"id":"12345678-1234-1234-1234-123456789abc","creatorHandle":"p2n2","is_public":True,"commentCount":8,"upvoteCount":12,"playCount":100}
        prev = {"songs":[{"id":a['id'],"comments":6,"likes":10,"plays":95}]}
        self.assertEqual(m.build_snapshot([a],prev)['songs'][0]['delta_comments'],2)

if __name__=='__main__': unittest.main()
