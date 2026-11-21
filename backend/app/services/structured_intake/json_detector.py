"""Content-only native JSON profile detection.

This is a pure classifier. It does not write, normalize, convert, or promote
sources. Called by the explicit Cyber2 promotion gate. Filename is accepted
for backwards-compatible callers but is NEVER examined.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator
from collections import deque

JSON_PROFILE_PLAIN = "plain"
JSON_PROFILE_SLACK = "slack"
JSON_PROFILE_SALESFORCE = "salesforce"
JSON_PROFILE_TEAMS = "teams"
JSON_PROFILE_GOOGLE = "google"
JSON_PROFILE_CUSTOM_API = "custom_api"


def _keys(value: Any) -> set[str]:
    return {str(k).lower() for k in value} if isinstance(value, dict) else set()


def _get(value: Any, name: str) -> Any:
    if not isinstance(value, dict):
        return None
    for key, item in value.items():
        if str(key).lower() == name.lower():
            return item
    return None


def _nodes(value: Any, *, max_nodes: int = 256, max_depth: int = 6) -> Iterator[Any]:
    """Bound recursive inspection, avoiding unbounded nested-source traversal."""
    queue = deque([(value, 0)])
    count = 0
    while queue and count < max_nodes:
        obj, depth = queue.popleft()
        count += 1
        yield obj
        if depth >= max_depth:
            continue
        if isinstance(obj, dict):
            children = list(obj.values())[:64]
        elif isinstance(obj, list):
            children = obj[:64]
        else:
            children = []
        queue.extend((child, depth + 1) for child in children if isinstance(child, (dict, list)))


def _slack(obj: Any) -> bool:
    k = _keys(obj)
    # Slack's message collection: ts + user + Slack-specific message syntax.
    if {'ts', 'text', 'user'} <= k and ('thread_ts' in k or 'reactions' in k or 'blocks' in k or _get(obj, 'type') == 'message'):
        return True
    messages = _get(obj, 'messages')
    if isinstance(messages, list) and messages and ('channel' in k or 'channels' in k or 'team' in k or 'workspace' in k):
        return any(isinstance(m, dict) and {'ts', 'text', 'user'} <= _keys(m) for m in messages[:32])
    # Slack workspace export with metadata; avoid empty-array false positives.
    return {'channels', 'users'} <= k and ('team' in k or 'workspace' in k) and 'messages' in k


def _salesforce(obj: Any) -> bool:
    k = _keys(obj)
    attrs = _get(obj, 'attributes')
    if isinstance(attrs, dict) and 'type' in _keys(attrs) and ('url' in _keys(attrs) or 'id' in k):
        return True
    records = _get(obj, 'records')
    if isinstance(records, list):
        if {'records', 'totalsize', 'done'} <= k:
            return True
        if records and any(isinstance(r, dict) and isinstance(_get(r,'attributes'),dict)
            and 'type' in _keys(_get(r,'attributes')) for r in records[:32]):
            return True
        # Salesforce object export: specific object + Salesforce record identifiers.
        if isinstance(_get(obj, 'object'), str) and records and any(
            isinstance(r, dict) and 'id' in _keys(r) and (
                'casenumber' in _keys(r) or 'contactid' in _keys(r) or 'accountid' in _keys(r))
            for r in records[:32]
        ):
            return True
    return False


def _teams(obj: Any) -> bool:
    k = _keys(obj)
    if {'teamid', 'channelid'} <= k:
        return True
    if 'channelidentity' in k and 'message' in k:
        return True
    if {'messagetype','body','from'} <= k and ('createddatetime' in k or 'id' in k):
        body = _get(obj,'body')
        return isinstance(body,dict) and 'content' in _keys(body)
    if 'chatid' in k and ('messages' in k or 'replies' in k):
        return True
    return False


def _google(obj: Any) -> bool:
    k = _keys(obj)
    resource = _get(obj, 'name')
    if isinstance(resource, str) and resource.startswith('spaces/') and '/messages/' in resource:
        return {'createtime','sender'} <= k
    if {'creator','created_date','text'} <= k and isinstance(_get(obj, 'creator'),dict):
        return 'name' in _keys(_get(obj, 'creator'))
    if 'spaces' in k and ('messages' in k or 'nextpagetoken' in k):
        return True
    return False


def _plain(obj: Any) -> bool:
    """Recognizable generic record payload; unsupported layouts remain Custom/API."""
    k = _keys(obj)
    if 'people' in k and isinstance(_get(obj,'people'),list):
        return True
    if {'first_name','last_name'} <= k or {'case_id','patient'} <= k:
        return True
    if 'record_id' in k and (('user' in k and 'event' in k) or ('type' in k and 'data' in k)):
        return True
    if {'case_id','email'} <= k or {'first_name','email'} <= k:
        return True
    if 'export' in k and isinstance(_get(obj,'export'),dict):
        export = _get(obj,'export')
        if 'records' in _keys(export) and 'batch' in _keys(export):
            return True
    return False


def detect_json_profile(*, source_path: Path, payload: Any) -> str:
    """Content-only profile detection with early exit on decisive evidence.

    Inspect at most 256 nested nodes. Stop immediately when a node supplies one
    distinctive vendor signature. If a *single node* supplies conflicting
    signatures, classify Custom/API. Weak/generic records do not block later
    decisive vendor matches. The filename is never read.
    """
    del source_path
    generic_plain = False
    for obj in _nodes(payload):
        # A decisive source signature terminates traversal immediately, rather
        # than scanning all the remaining records just for classification.
        matches = (
            (JSON_PROFILE_SLACK, _slack(obj)),
            (JSON_PROFILE_SALESFORCE, _salesforce(obj)),
            (JSON_PROFILE_TEAMS, _teams(obj)),
            (JSON_PROFILE_GOOGLE, _google(obj)),
        )
        found = [profile for profile, matched in matches if matched]
        if len(found) > 1:
            return JSON_PROFILE_CUSTOM_API
        if found:
            return found[0]
        if _plain(obj):
            generic_plain = True
    return JSON_PROFILE_PLAIN if generic_plain else JSON_PROFILE_CUSTOM_API
