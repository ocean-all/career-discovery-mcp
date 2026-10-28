"""Local user preferences; AI dialogue belongs to the host skill, not a hidden API."""
from __future__ import annotations
import json
from copy import deepcopy
from .cli_helpers import atomic_json

EMPTY = {
    "version": 1, "state": "draft", "user_intent": "",
    "roles": [], "industries": [], "skills": [], "education_keywords": [],
    "locations": [], "experience": "unknown", "must_have": [], "exclude_keywords": [],
    "search_terms": [], "proposed_expansions": [], "days": 30,
}
LISTS = {k for k,v in EMPTY.items() if isinstance(v,list)}


def validate(value):
    if not isinstance(value,dict) or set(value)-set(EMPTY):
        raise ValueError("Profile must be an object using the documented fields")
    p=deepcopy(EMPTY)
    p.update(value)
    if type(p['version']) is not int or p['version'] != 1 or p['state'] not in {'draft','confirmed'}:
        raise ValueError("Unsupported version/state")
    if p['experience'] not in {'unknown','entry','experienced','any'}:
        raise ValueError("experience must be unknown, entry, experienced or any")
    if type(p['days']) is not int or not 1<=p['days']<=365:
        raise ValueError("days must be 1–365")
    if not isinstance(p['user_intent'],str) or len(p['user_intent'])>2000:
        raise ValueError("user_intent must be text up to 2000 characters")
    for key in LISTS:
        items=p[key]
        if not isinstance(items,list) or len(items)>20 or any(not isinstance(s,str) or not s.strip() or len(s)>80 for s in items):
            raise ValueError(f"{key}: up to 20 nonempty strings, 80 characters each")
        p[key]=list(dict.fromkeys(s.strip() for s in items))
    if p['state']=='confirmed' and not (p['roles'] or p['industries']):
        raise ValueError("A confirmed profile needs roles or industries")
    return p


def load(root):
    path=root/'profile.json'
    return validate(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else deepcopy(EMPTY)


def save(root,value):
    profile=validate(value)
    atomic_json(root/'profile.json',profile)
    return {"saved":True,"state":profile['state'],"message":"Preferences saved locally. Proposed expansions are not searched until accepted into roles/industries/search_terms."}


def search_plan(profile):
    p=validate(profile)
    if p['state']!='confirmed':
        return {"ready":False,"queries":[],"message":"Discuss proposed scope with the user and save the accepted scope as confirmed. Do not infer preferences from expansion suggestions."}
    roles=p['roles'] or ['']
    industries=p['industries'] or ['']
    terms=[]
    for role in roles:
        for industry in industries:
            terms.append(' '.join(x for x in [industry,role] if x))
    terms+=p['search_terms']
    terms=list(dict.fromkeys(terms))
    markers={'entry':'신입','experienced':'경력','any':'','unknown':''}
    queries=[' '.join(x for x in [s,markers[p['experience']],'채용'] if x) for s in terms]
    return {"ready":True,"days":p['days'],"queries":queries[:24],"saramin_keywords":terms[:24],
            "truncated":len(terms)>24,"proposed_expansions_excluded":True,
            "review_constraints":{"locations":p['locations'],"must_have":p['must_have'],"exclude_keywords":p['exclude_keywords']},
            "warning":"Search terms do not guarantee eligibility. Verify mandatory conditions and original deadlines. Queries are sent to the selected search provider when used."}
