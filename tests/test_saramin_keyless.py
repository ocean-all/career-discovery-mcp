import os
import unittest
from unittest.mock import Mock,patch
from urllib.parse import urlsplit,parse_qs
from jobmonitor.providers import Saramin
from jobmonitor.saramin_discovery import search_links_for_queries

class KeylessTests(unittest.TestCase):
    @patch.dict(os.environ,{'SARAMIN_ACCESS_KEY':''})
    def test_no_key_never_calls_api(self):
        http=Mock()
        self.assertEqual(list(Saramin(http,{'queries':['매장 운영']}).collect()),[])
        http.json.assert_not_called()
    def test_keyless_links_encode_search_words(self):
        result=search_links_for_queries(['여행 상품 운영'],30)
        self.assertFalse(result['api_key_required'])
        self.assertFalse(result['automatically_collected'])
        link=result['links'][0]
        self.assertEqual(parse_qs(urlsplit(link['saramin_url']).query)['searchword'],['여행 상품 운영'])
        self.assertIn('site:saramin.co.kr',parse_qs(urlsplit(link['google_url']).query)['q'][0])
    def test_no_scope_is_explicit(self):
        self.assertEqual(search_links_for_queries([])['links'],[])
