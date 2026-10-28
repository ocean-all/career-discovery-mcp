import unittest
from datetime import datetime
from urllib.parse import urlsplit, parse_qs
from jobmonitor.core import KST
from jobmonitor.google_discovery import search_links

class GoogleTests(unittest.TestCase):
    def test_date_window_and_today_included(self):
        value=search_links("신입 채용",at=datetime(2026,10,27,9,tzinfo=KST))
        self.assertEqual(value['after'],'2026-09-27')
        self.assertEqual(value['before'],'2026-10-28')
        self.assertEqual(len(value['links']),1)
        self.assertTrue(all('after:2026-09-27' in i['query'] for i in value['links']))
    def test_query_is_url_encoded(self):
        value=search_links('물류 R&D + Excel',7)
        self.assertEqual(len(value['links']),1)
        self.assertIn('물류 R&D + Excel',parse_qs(urlsplit(value['links'][0]['url']).query)['q'][0])
    def test_bounds(self):
        for days in [0,366]:
            with self.assertRaises(ValueError): search_links(days=days)
