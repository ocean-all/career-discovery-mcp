import io
import json
import os
import tempfile
import unittest
import urllib.error
import zipfile
from datetime import datetime, timedelta
from email.message import Message
from pathlib import Path
from unittest.mock import patch, Mock

from jobmonitor.core import Job, Store, KST, assess, canonical, parse_deadline
from jobmonitor.providers import Saramin, Naver, saramin_job
from jobmonitor.http import HTTP, FetchError, public_https
from jobmonitor.careers import Careers, validate_sources, jobposting
from jobmonitor.extract import extract_document, html_page
from jobmonitor.discovery import render_results
from jobmonitor.cli import run, next_run, load_env

RAW = {
    "id":"123", "url":"https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=123&utm_source=api",
    "active":1, "company":{"detail":{"name":"가상유통"}},
    "position":{"title":"매장 운영 연구 신입", "experience-level":{"code":1,"name":"신입"},
                "location":{"name":"서울"}, "required-education-level":{"name":"학력무관"}},
    "keyword":"Excel,상품관리", "close-type":{"code":"1"}, "expiration-timestamp":"1793250000"
}

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name)/"jobs.sqlite")
    def tearDown(self):
        self.store.close()
        self.temp.cleanup()
    def test_saramin_schema(self):
        j = saramin_job(RAW).prepare({"roles":["연구"],"industries":["유통"],"skills":["Excel"],"education_keywords":["학력무관"],"experience":"entry"})
        self.assertEqual(j.company,"가상유통")
        self.assertEqual(j.eligibility,"entry")
        self.assertGreaterEqual(j.score,70)
        self.assertIn("utm_source",j.url)
        self.assertEqual(j.verification,"official_api_metadata")
    def test_open_ended_date_is_not_deadline(self):
        j = saramin_job({**RAW,"close-type":{"code":"2"}})
        self.assertIsNone(j.deadline)
    def test_canonical_keeps_identity(self):
        self.assertEqual(canonical("https://x.com/job?id=2&utm_source=x#foo"),"https://x.com/job?id=2")
        self.assertNotEqual(canonical("https://x.com/job?id=2"),canonical("https://x.com/job?id=3"))
    def test_new_unchanged_changed_versions(self):
        j = saramin_job(RAW)
        jid, kind = self.store.upsert(j)
        self.assertEqual(kind,"new")
        j.evidence[0]["retrieved_at"] = "different time"
        self.assertIsNone(self.store.upsert(j)[1])
        j.title += " 수정"
        self.assertEqual(self.store.upsert(j)[1],"changed")
        self.assertEqual(len(self.store.jobs()),1)
        self.assertEqual(self.store.db.execute("select count(*) from versions").fetchone()[0],2)
    def test_exact_url_dedupe_and_conservative_cross_source(self):
        j = saramin_job(RAW)
        self.store.upsert(j)
        alias = Job("manual","1",j.url+"&utm_medium=test",j.title,j.company)
        self.store.upsert(alias)
        self.assertEqual(len(self.store.jobs()),1)
        other = Job("company","2","https://company.example/jobs/3",j.title,j.company)
        self.store.upsert(other)
        self.assertEqual(len(self.store.duplicate_candidates()),1)
    def test_quota_persistent(self):
        self.store.reserve("saramin",1)
        with self.assertRaises(RuntimeError):
            self.store.reserve("saramin",1)
    def test_report_deadline_and_expired(self):
        at = datetime(2026,10,27,9,tzinfo=KST)
        j = saramin_job(RAW)
        j.deadline = (at+timedelta(days=1)).isoformat()
        self.store.upsert(j,at.isoformat())
        report=self.store.report(at)
        self.assertIn("3일 이내 마감",report)
        self.assertIn("가상유통",report)
        j.deadline = (at-timedelta(days=1)).isoformat()
        self.store.upsert(j,at.isoformat())
        self.assertIn("deadline_passed",self.store.report(at))
    def test_missing_from_search_not_closed(self):
        self.store.upsert(saramin_job(RAW))
        self.assertEqual(self.store.jobs()[0][1].active,"open")
    def test_entry_vs_senior(self):
        self.assertEqual(assess("물류 신입 경력 5년 이상")[1],"mixed_review")
        self.assertEqual(assess("물류 경력 5년 이상")[1],"experienced_only")
        self.assertEqual(assess("물류 연구")[1],"unknown")
    def test_deadline_requires_year_and_ambiguity(self):
        self.assertIsNone(parse_deadline("10월 30일 마감"))
        self.assertIsNone(parse_deadline("2026-10-01 ~ 2026-10-30"))
        self.assertEqual(parse_deadline("마감 2026.10.30 18:00"),"2026-10-30T18:00:00+09:00")
    def test_reject_naive_deadline(self):
        with self.assertRaises(ValueError):
            Job("x","1","https://x.com","x",deadline="2026-10-30T09:00:00").prepare()

class ProviderTests(unittest.TestCase):
    @patch.dict(os.environ,{"SARAMIN_ACCESS_KEY":"test-only"})
    def test_pagination_is_page_number(self):
        http=Mock()
        first=[{**RAW,"id":str(i)} for i in range(110)]
        http.json.side_effect=[{"jobs":{"total":111,"job":first}}, {"jobs":{"total":111,"job":[RAW]}}]
        self.assertEqual(len(list(Saramin(http,{"queries":["물류"],"pages_per_query":2}).collect())),111)
        self.assertEqual(http.json.call_args_list[1].args[1]["start"],1)
    @patch.dict(os.environ,{"SARAMIN_ACCESS_KEY":"test-only"})
    def test_http_200_api_error(self):
        http=Mock(); http.json.return_value={"code":4,"message":"quota"}
        with self.assertRaises(FetchError):
            list(Saramin(http,{"queries":["물류"]}).collect())
    @patch.dict(os.environ,{"NAVER_CLIENT_ID":"test-id","NAVER_CLIENT_SECRET":"test-secret","NAVER_MODE":"hub"})
    def test_naver_hub_headers_and_no_store(self):
        http=Mock(); http.json.return_value={"items":[{"title":"b"},{"title":"a"}]}
        result=Naver(http).search("물류")
        self.assertEqual(result["items"][0]["title"],"b")
        call=http.json.call_args
        self.assertEqual(call.args[0],"https://naverapihub.apigw.ntruss.com/search/v1/blog")
        self.assertEqual(call.kwargs["headers"]["X-NCP-APIGW-API-KEY"],"test-secret")
    @patch.dict(os.environ,{"NAVER_CLIENT_ID":"test-id","NAVER_CLIENT_SECRET":"test-secret","NAVER_MODE":"legacy"})
    def test_legacy(self):
        http=Mock(); http.json.return_value={"items":[]}
        Naver(http).search("물류")
        self.assertIn("X-Naver-Client-Secret", http.json.call_args.kwargs["headers"])
    def test_viewer_escapes_untrusted_html(self):
        rendered=render_results({"items":[{"title":"<script>x</script><b>y</b>","link":"javascript:alert(1)"}]})
        self.assertNotIn("<script>",rendered)
        self.assertNotIn("javascript:",rendered)
        self.assertIn("<b>y</b>",rendered)

class HTTPTests(unittest.TestCase):
    @patch("socket.getaddrinfo",return_value=[(2,1,6,"",("127.0.0.1",443))])
    def test_private_blocked(self,_):
        with self.assertRaises(FetchError): public_https("https://anything.example")
    def test_scheme_blocked(self):
        for url in ["http://example.com","file:///etc/passwd","https://user:pass@example.com"]:
            with self.assertRaises(FetchError): public_https(url)
    @patch("jobmonitor.http.public_https",return_value="example.com")
    def test_retry_quota_counts_attempts(self,_):
        store=Mock(); http=HTTP(store,sleep=lambda _:None)
        response=Mock(); response.__enter__=Mock(return_value=response); response.__exit__=Mock(return_value=False)
        response.read.side_effect=[b'{}',b'']; response.headers={}
        http.opener=Mock()
        http.opener.open.side_effect=[urllib.error.HTTPError("secret",429,"",{},None),response]
        self.assertEqual(http.json("https://example.com",{},headers={},reserve=("x",2)),{})
        self.assertEqual(store.reserve.call_count,2)
    @patch("jobmonitor.http.public_https",return_value="example.com")
    def test_redirect_no_secret_forwarding(self,_):
        http=HTTP(Mock(),sleep=lambda _:None); http.opener=Mock()
        http.opener.open.side_effect=urllib.error.HTTPError("secret",302,"",{"Location":"https://evil.com"},None)
        with self.assertRaises(FetchError) as error:
            http.get("https://example.com?access-key=TOPSECRET",reserve=("x",2))
        self.assertNotIn("TOPSECRET",str(error.exception))
        self.assertEqual(http.opener.open.call_count,1)
    def test_robots_denial(self):
        http=HTTP(); http.get=Mock(return_value=(b"User-agent: *\nDisallow: /jobs",{}))
        with self.assertRaises(FetchError):
            http.check_robots("https://example.com/jobs/1",{})
    @patch("jobmonitor.http.public_https",return_value="example.com")
    def test_unapproved_host(self,_):
        with self.assertRaises(FetchError): HTTP().get("https://example.com/jobs",policy={})

class ExtractionTests(unittest.TestCase):
    def test_html_and_json_ld(self):
        page=html_page(b'<title>Job</title><script>ignore()</script><main>retail</main><a href="/job.pdf">JD</a><script type="application/ld+json">{"@type":"JobPosting","title":"Retail"}</script>',"https://example.com/")
        self.assertNotIn("ignore",page.text)
        self.assertEqual(page.links[0][0],"https://example.com/job.pdf")
        self.assertEqual(jobposting(page.structured)["title"],"Retail")
    def test_hwpx(self):
        b=io.BytesIO()
        with zipfile.ZipFile(b,"w") as z:
            z.writestr("Contents/section0.xml",'<root xmlns:h="urn:x"><h:t>물류 신입</h:t></root>')
        self.assertIn("물류 신입",extract_document(b.getvalue(),".hwpx").text)
    @patch("jobmonitor.extract.shutil.which",return_value=None)
    def test_optional_hwp_missing(self,_):
        self.assertIn("optional",extract_document(b"x",".hwp").warnings[0])
    @patch("jobmonitor.extract.ocr_image",return_value=("물류 신입 2026-10-30", ""))
    def test_image_ocr(self,_):
        result=extract_document(b"image",".png")
        self.assertEqual(result.method,"ocr")
        self.assertIn("물류",result.text)
    def test_permission_registry_blocks_platforms(self):
        with self.assertRaises(ValueError):
            validate_sources({"hosts":{"jasoseol.com":{"allow_fetch":True,"permission_reference":"x"}}})
    def test_company_identity_and_attachment_evidence(self):
        http=Mock(); headers=Message(); headers["Content-Type"]="text/html; charset=utf-8"
        text="가상유통 물류 연구 신입 학력무관 Excel 우대 상세 모집 업무 "*4
        http.get.return_value=(text.encode(),headers)
        cfg={"hosts":{"example.com":{"allow_fetch":True,"permission_reference":"terms"}},"pages":[{"url":"https://example.com/job/1","company":"가상유통","title":"물류 연구","expected_terms":["가상유통","신입"]}]}
        jobs=list(Careers(http,cfg).collect(self.fail))
        self.assertEqual(jobs[0].verification,"original_identity_matched")
        self.assertIsNone(jobs[0].deadline)
    def test_company_missing_identity_not_verified(self):
        careers=Careers(Mock(),{"hosts":{},"pages":[]})
        page=html_page(("unrelated text "*20).encode(),"https://example.com/job")
        j=careers.posting({"url":"https://example.com/job","expected_terms":["company"]},page)
        self.assertLess(j.confidence,.7)
    def test_schedule_timezone(self):
        at=datetime(2026,10,27,8,59,tzinfo=KST)
        self.assertEqual(next_run(at).hour,9)
        self.assertEqual(next_run(at+timedelta(minutes=1)).day,28)


class EndToEndTests(unittest.TestCase):
    def test_demo_rerun_is_idempotent_and_isolated(self):
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            shutil.copytree(Path(__file__).resolve().parents[1]/"examples",root/"examples")
            (root/"data").mkdir()
            store=Store(root/"data/demo.sqlite")
            try:
                self.assertEqual(run(root,store,demo=True),0)
                self.assertEqual(run(root,store,demo=True),0)
                self.assertEqual(len(store.jobs()),2)
                self.assertEqual(store.db.execute("select count(*) from events").fetchone()[0],2)
                self.assertIn("DEMO",(root/"reports/demo/latest.md").read_text(encoding="utf-8"))
                self.assertFalse((root/"data/jobs.sqlite").exists())
            finally: store.close()
    @patch.dict(os.environ,{"SARAMIN_ACCESS_KEY":""})
    def test_missing_key_writes_keyless_discovery_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"config.json").write_text('{"saramin":{"queries":["물류"]}}', encoding="utf-8")
            (root/"sources.json").write_text('{"hosts":{},"pages":[]}')
            store=Store(root/"jobs.sqlite")
            try:
                self.assertEqual(run(root,store),0)
                self.assertIn("discovery_only",(root/"reports/latest.md").read_text(encoding="utf-8"))
                self.assertEqual(len(store.jobs()),0)
            finally: store.close()
    def test_invalid_config_still_writes_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"config.json").write_text('invalid')
            store=Store(root/"jobs.sqlite")
            try:
                self.assertEqual(run(root,store),2)
                self.assertIn("configuration",(root/"reports/latest.md").read_text(encoding="utf-8"))
            finally: store.close()
    def test_alias_does_not_downgrade_verification(self):
        store=Store(":memory:")
        try:
            j=saramin_job(RAW)
            store.upsert(j)
            alias=Job("manual","x",j.url,j.title,j.company)
            self.assertIsNone(store.upsert(alias)[1])
            self.assertEqual(store.jobs()[0][1].confidence,.75)
        finally: store.close()
    def test_posted_date_is_not_deadline(self):
        self.assertIsNone(parse_deadline("게시일 2026-10-27"))

class PDFIntegrationTests(unittest.TestCase):
    def test_real_pdf_text_extraction(self):
        try:
            from pypdf import PdfWriter
            from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
        except ImportError:
            self.skipTest("optional pypdf not installed")
        writer=PdfWriter()
        page=writer.add_blank_page(width=400,height=300)
        font=DictionaryObject({NameObject("/Type"):NameObject("/Font"),NameObject("/Subtype"):NameObject("/Type1"),NameObject("/BaseFont"):NameObject("/Helvetica")})
        page[NameObject("/Resources")]=DictionaryObject({NameObject("/Font"):DictionaryObject({NameObject("/F1"):writer._add_object(font)})})
        stream=DecodedStreamObject()
        stream.set_data(b"BT /F1 12 Tf 30 240 Td (Retail Excel entry level research job description) Tj ET")
        page[NameObject("/Contents")]=writer._add_object(stream)
        buf=io.BytesIO(); writer.write(buf)
        result=extract_document(buf.getvalue(),".pdf")
        self.assertIn("Retail Excel",result.text)
        self.assertFalse(result.warnings)
    def test_scanned_pdf_requires_ocr_warning(self):
        try:
            from pypdf import PdfWriter
        except ImportError:
            self.skipTest("optional pypdf not installed")
        writer=PdfWriter(); writer.add_blank_page(width=200,height=200)
        buf=io.BytesIO(); writer.write(buf)
        with patch("jobmonitor.extract.shutil.which",return_value=None):
            result=extract_document(buf.getvalue(),".pdf")
        self.assertTrue(any("scanned/empty" in w for w in result.warnings))

if __name__ == "__main__": unittest.main()
