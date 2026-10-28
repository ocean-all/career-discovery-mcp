from __future__ import annotations

import hashlib
import html
import json
import re
import sqlite3
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def now():
    return datetime.now(KST)


def clean(value):
    if isinstance(value, dict):
        value = value.get("name", "")
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", str(value or "")))).strip()


def canonical(url):
    p = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in {"ref", "fbclid", "gclid"}]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or "/", urlencode(sorted(query)), ""))


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def norm(text):
    return re.sub(r"[^\w가-힣]", "", unicodedata.normalize("NFKC", text).lower())


def parse_deadline(text):
    # Require a full year; never infer a current year from an old blog post.
    if not re.search(r"마감|접수\s*기한|지원\s*기한|deadline", text, re.I):
        return None
    matches = re.findall(r"(20\d{2})[.년/\-]\s*(\d{1,2})[.월/\-]\s*(\d{1,2})(?:일)?(?:\s+(\d{1,2}):(\d{2}))?", text)
    if len(matches) != 1:
        return None  # multiple dates need an explicit configured deadline
    y, m, d, h, minute = matches[0]
    try:
        return datetime(int(y), int(m), int(d), int(h or 23), int(minute or 59), tzinfo=KST).isoformat()
    except ValueError:
        return None


def assess(text, experience_code=None, profile=None):
    profile = profile or {}
    low = text.lower()
    junior = bool(re.search(r"신입|경력\s*무관|경력\s*없|entry[ -]level", low)) or str(experience_code) in {"0", "1", "3"}
    senior = bool(re.search(r"경력\s*\d+\s*년\s*이상|박사\s*(?:필수|이상)|시니어|senior", low)) or str(experience_code) == "2"
    eligibility = "mixed_review" if junior and senior else "entry" if junior else "experienced_only" if senior else "unknown"
    if profile is not None:
        score,reasons=0,[]
        for key,points in [('roles',30),('industries',25),('skills',20),('education_keywords',10)]:
            hits=[term for term in profile.get(key,[]) if term.casefold() in low]
            if hits:
                score+=points
                reasons.append(f"{key}: {', '.join(hits)}")
        if profile.get('experience')=='entry':
            if junior:
                score+=15
                reasons.append('신입/경력무관 표기')
            if eligibility=='experienced_only':
                score-=60
            elif eligibility in {'mixed_review','unknown'}:
                reasons.append('신입 조건 직접 확인 필요')
        for term in profile.get('exclude_keywords',[]):
            if term.casefold() in low:
                score-=40
                reasons.append(f'제외 조건 가능성: {term} (문맥 확인)')
        missing=[term for term in profile.get('must_have',[]) if term.casefold() not in low]
        if missing:
            reasons.append('필수조건 미확인: '+', '.join(missing))
    return max(0, min(100, score)), eligibility, reasons


@dataclass
class Job:
    source: str
    source_id: str
    url: str
    title: str
    company: str = ""
    text: str = ""
    location: str = ""
    deadline: str | None = None
    active: str = "unknown"
    verification: str = "unverified"
    confidence: float = 0.0
    evidence: list = field(default_factory=list)
    attachments: list = field(default_factory=list)
    experience_code: str | None = None
    score: int = 0
    eligibility: str = "unknown"
    reasons: list = field(default_factory=list)

    def prepare(self, profile=None):
        p = urlsplit(self.url)
        if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password:
            raise ValueError("Job source must have a public web URL")
        # Keep official attribution/tracking parameters in the displayed source URL.
        self.title, self.company = clean(self.title), clean(self.company)
        self.text = clean(self.text)
        self.score, self.eligibility, self.reasons = assess(
            " ".join([self.title, self.company, self.text]), self.experience_code, profile)
        if self.deadline:
            dt = datetime.fromisoformat(self.deadline)
            if dt.tzinfo is None:
                raise ValueError("deadline must include timezone")
            self.deadline = dt.astimezone(KST).isoformat()
        return self

    def fingerprint(self):
        # Distinct source IDs remain separate; only exact URL aliases merge automatically.
        return digest(canonical(self.url))

    def content_hash(self):
        data = asdict(self)
        for key in ("evidence", "score", "eligibility", "reasons"):
            data.pop(key)  # observation times and ranking preferences are not posting changes
        return digest(json.dumps(data, ensure_ascii=False, sort_keys=True))


class Store:
    def __init__(self, path, profile=None):
        self.profile = profile
        self.db = sqlite3.connect(path, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS jobs (
          id INTEGER PRIMARY KEY, fingerprint TEXT UNIQUE NOT NULL,
          data TEXT NOT NULL, hash TEXT NOT NULL, first_seen TEXT NOT NULL,
          last_seen TEXT NOT NULL, last_verified TEXT);
        CREATE TABLE IF NOT EXISTS aliases (
          source TEXT, source_id TEXT, job_id INTEGER REFERENCES jobs(id),
          PRIMARY KEY(source,source_id));
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY, job_id INTEGER, kind TEXT, at TEXT,
          old_hash TEXT, new_hash TEXT, UNIQUE(job_id,kind,at));
        CREATE TABLE IF NOT EXISTS versions (
          job_id INTEGER, hash TEXT, data TEXT, at TEXT,
          PRIMARY KEY(job_id,hash));
        CREATE TABLE IF NOT EXISTS runs (
          id INTEGER PRIMARY KEY, started TEXT, finished TEXT, status TEXT, details TEXT);
        CREATE TABLE IF NOT EXISTS quota (
          day TEXT, provider TEXT, used INTEGER NOT NULL, PRIMARY KEY(day,provider));
        CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY);
        INSERT OR IGNORE INTO schema_version VALUES(1);
        ''')
        self.db.commit()

    def close(self):
        self.db.close()

    def reserve(self, provider, limit):
        day = now().date().isoformat()
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO quota VALUES(?,?,0)", (day, provider))
            cur = self.db.execute("UPDATE quota SET used=used+1 WHERE day=? AND provider=? AND used<?", (day, provider, limit))
            if not cur.rowcount:
                raise RuntimeError(f"{provider}: local daily request budget exhausted")

    def upsert(self, job, at=None):
        job.prepare(self.profile)
        at = at or now().isoformat()
        with self.db:
            row = self.db.execute("SELECT j.* FROM aliases a JOIN jobs j ON j.id=a.job_id WHERE a.source=? AND a.source_id=?", (job.source, job.source_id)).fetchone()
            if row is None:
                row = self.db.execute("SELECT * FROM jobs WHERE fingerprint=?", (job.fingerprint(),)).fetchone()
            if row is not None:
                previous = Job(**json.loads(row["data"]))
                if (previous.source, previous.source_id) != (job.source, job.source_id) and previous.confidence > job.confidence:
                    self.db.execute("INSERT OR IGNORE INTO aliases VALUES(?,?,?)", (job.source, job.source_id, row["id"]))
                    return row["id"], None
            payload = json.dumps(asdict(job), ensure_ascii=False, sort_keys=True)
            h = job.content_hash()
            kind = "new" if row is None else "changed" if row["hash"] != h else None
            verified_at = at if job.confidence >= .7 else None
            if row is None:
                cur = self.db.execute("INSERT INTO jobs(fingerprint,data,hash,first_seen,last_seen,last_verified) VALUES(?,?,?,?,?,?)", (job.fingerprint(), payload, h, at, at, verified_at))
                jid = cur.lastrowid
            else:
                jid = row["id"]
                self.db.execute("UPDATE jobs SET data=?,hash=?,last_seen=?,last_verified=? WHERE id=?", (payload, h, at, verified_at, jid))
            self.db.execute("INSERT OR IGNORE INTO aliases VALUES(?,?,?)", (job.source, job.source_id, jid))
            self.db.execute("INSERT OR IGNORE INTO versions VALUES(?,?,?,?)", (jid, h, payload, at))
            if kind:
                self.db.execute("INSERT INTO events(job_id,kind,at,old_hash,new_hash) VALUES(?,?,?,?,?)", (jid, kind, at, row["hash"] if row else None, h))
            return jid, kind

    def jobs(self):
        return [(row, Job(**json.loads(row["data"]))) for row in self.db.execute("SELECT * FROM jobs")]

    def duplicate_candidates(self):
        buckets = {}
        for row, job in self.jobs():
            if job.company:
                key = norm(job.company) + ":" + norm(job.title)
                buckets.setdefault(key, []).append(row["id"])
        return [ids for ids in buckets.values() if len(ids) > 1]

    def report(self, at=None):
        at = at or now()
        since = (at - timedelta(days=1)).isoformat()
        events = {}
        for e in self.db.execute("SELECT job_id,kind FROM events WHERE at>=? AND at<=?", (since, at.isoformat())):
            events.setdefault(e["job_id"], set()).add(e["kind"])
        lines = [f"# 채용 모니터 — {at:%Y-%m-%d %H:%M} Asia/Seoul", "", "출처와 확인 수준을 확인한 뒤 원문에서 지원 조건을 최종 확인하세요.", ""]
        jobs = sorted(self.jobs(), key=lambda pair: pair[1].score, reverse=True)
        for heading, predicate in [
            ("신규 (최근 24시간)", lambda r,j: "new" in events.get(r["id"], set())),
            ("변경 (최근 24시간)", lambda r,j: "changed" in events.get(r["id"], set())),
            ("3일 이내 마감", lambda r,j: j.deadline and j.active != "closed" and at <= datetime.fromisoformat(j.deadline) <= at + timedelta(days=3)),
        ]:
            lines.extend([f"## {heading}", ""])
            selected = [(r,j) for r,j in jobs if predicate(r,j)]
            if not selected:
                lines.extend(["해당 없음. 수집 실패·미연결은 아래 상태를 확인하세요.", ""])
            for row, j in selected:
                expired = j.deadline and datetime.fromisoformat(j.deadline) < at
                stale_note = "; 48시간 이상 재확인 안 됨" if at - datetime.fromisoformat(row["last_seen"]) > timedelta(days=2) else ""
                label = (j.company + " | " + j.title).replace("[", "\\[").replace("]", "\\]")
                safe_url = j.url.replace("(", "%28").replace(")", "%29").replace(" ", "%20")
                lines.extend([f"- [{label}]({safe_url}) — {j.score}점, {j.eligibility}; {j.verification} ({j.confidence:.0%})",
                              f"  - 마감: {j.deadline or '미확인/상시'}; 상태: {'deadline_passed' if expired else j.active}; 확인: {row['last_verified'] or '원문 미확인'}{stale_note}",
                              f"  - 근거: {'; '.join(j.reasons)}"])
        lines.extend(["", "## 실행 상태", ""])
        for row in self.db.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 3"):
            lines.append(f"- {row['started']}: {row['status']} — {row['details']}")
        lines.extend(["", f"중복 검토 후보 (자동 병합 안 함): {self.duplicate_candidates()}", "",
                      "목록에 없다는 이유만으로 공고를 마감 처리하지 않습니다. 검색 범위는 설정된 질의·페이지 수에 한정됩니다."])
        return "\n".join(lines) + "\n"
