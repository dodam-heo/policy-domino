"""Deprecated compatibility layer for the pre-registered annual standards pilot.

Static policy profiles and manually enumerated agency roles have been retired.
The active production pipeline uses independent legal sources (v4) and
unseeded live official-source discovery (v4.institutional_impact).
"""
SOURCE_PROFILES = {}

def scan_policy_standards(fetch,existing_events,existing_actions):
    return [], [], {"registered":0,"confirmed":0,"metrics":0,"errors":[],
        "scope":"수동 등록 대상 없음; 공식 법령의 일반 수집 파이프라인 사용"}

def link_verified_welfare_dependencies(events,actions):
    # Do not inject pre-selected social-program dependency percentages.
    return {"linked_rules":0,"linked_actions":0}
