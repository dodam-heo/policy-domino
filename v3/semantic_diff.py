"""Conservative complete-provision comparison, not stray token substitutions.

The output is a source-backed before/after sentence pair, or no automatic
instruction when correspondence cannot be established. It is sector agnostic.
"""
from __future__ import annotations

import difflib
import re

BULLET=re.compile(r"(?:^|(?<=\s))\d{1,3}\.\s")
PARA_MARKS=set("①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳")
OPEN={"(":")","[":"]","「":"」","『":"』","{":"}"}
CLOSE=set(OPEN.values())
OPERATIVE_END=re.compile(r"(?:다|것|함|됨|있음)\.$")
FORMAT_ONLY=re.compile(r"[\s·ㆍ,，;；:：\-.]")
VALUE=re.compile(r"\d[\d,]*(?:\.\d+)?\s*(?:만원|원|명|일|년|개월|%|퍼센트|세|호)?")
MAX_SENTENCE=850
MAX_PAIRS=30

def compact(value):
    return " ".join(str(value or "").split()).strip()

def fingerprint(s):
    return FORMAT_ONLY.sub("",compact(s))

def sentences(body):
    """Split on top-level legal duties, never inside parentheses or citations.

    A full clause can contain numbered paragraphs and attached qualifications.
    Return complete short source excerpts instead of isolated changed tokens.
    """
    raw=str(body or "").strip()
    if not raw:return []
    pieces=[];start=0;stack=[]
    def add(end):
        chunk=compact(raw[start:end])
        if chunk and (not pieces or pieces[-1]!=chunk):pieces.append(chunk)
    for i,ch in enumerate(raw):
        if ch in OPEN:stack.append(OPEN[ch])
        elif ch in CLOSE and stack and stack[-1]==ch:stack.pop()
        if stack:continue
        if ch in PARA_MARKS and i>start and raw[i-1].isspace() and compact(raw[start:i]):
            add(i);start=i
        elif ch=="\n":
            add(i);start=i+1
        elif ch=="." and i>0 and raw[i-1] not in "0123456789" and (
            i==len(raw)-1 or raw[i+1].isspace()):
            # "제1항의..." is not a sentence break; punctuation is.
            add(i+1);start=i+1
    add(len(raw))
    out=[];seen=set()
    for p in pieces:
        key=fingerprint(p)
        # The official source's nested XML sometimes contained the exact
        # same paragraph twice. Deduplicate only full identical statements.
        if key in seen and len(key)>=35:continue
        seen.add(key);out.append(p)
    return out

def similarity(a,b):
    if not a or not b:return 0
    if max(len(a),len(b))>MAX_SENTENCE:return 0
    n,m=fingerprint(a),fingerprint(b)
    if n==m:return 1.0
    if not n or not m:return 0
    matcher=difflib.SequenceMatcher(None,n,m,autojunk=True)
    blocks=matcher.get_matching_blocks()
    longest=max((x.size for x in blocks),default=0)
    if longest<min(10,max(5,len(n)//5,len(m)//5)):
        return 0
    return matcher.ratio()

def changed_words(old,new):
    a,b=fingerprint(old),fingerprint(new)
    matcher=difflib.SequenceMatcher(None,a,b,autojunk=False)
    return " ".join(a[i:j]+" "+b[k:l] for tag,i,j,k,l in matcher.get_opcodes()
                    if tag!="equal").strip()

def make_pair(old,new,article,kind):
    old,new=compact(old),compact(new)
    if fingerprint(old)==fingerprint(new):return None
    if max(len(old),len(new))>MAX_SENTENCE:return None
    if old and new and similarity(old,new)<0.60:return None
    meaningful=max(len(fingerprint(old)),len(fingerprint(new)))>=13
    if not meaningful:return None
    return {"article":article,"before":old,"after":new,"kind":kind,
            "match_confidence":"문장 대조 확인" if old and new else
                               "변경 조문 내 문장 신설·삭제 확인"}

def pairs(change,limit=MAX_PAIRS):
    old,new=sentences(change.get("before","")),sentences(change.get("after",""))
    article=change.get("article","")
    old_norm={fingerprint(s) for s in old}
    new_norm={fingerprint(s) for s in new}
    sm=difflib.SequenceMatcher(None,[fingerprint(s) for s in old],
                                [fingerprint(s) for s in new],autojunk=False)
    found=[]
    for op,a0,a1,b0,b1 in sm.get_opcodes():
        if op=="equal":continue
        obsolete=old[a0:a1];incoming=new[b0:b1]
        matched_old=set();matched_new=set()
        candidates=sorted(
            ((similarity(aa,bb),i,j) for i,aa in enumerate(obsolete)
                                    for j,bb in enumerate(incoming)),
            reverse=True)
        for score,i,j in candidates:
            if score<0.60:break
            if i in matched_old or j in matched_new:continue
            p=make_pair(obsolete[i],incoming[j],article,"문장 개정")
            if p:
                found.append(p);matched_old.add(i);matched_new.add(j)
        for i,aa in enumerate(obsolete):
            if i in matched_old or fingerprint(aa) in new_norm:continue
            p=make_pair(aa,"",article,"문장 삭제")
            if p:found.append(p)
        for j,bb in enumerate(incoming):
            if j in matched_new or fingerprint(bb) in old_norm:continue
            p=make_pair("",bb,article,"문장 신설")
            if p:found.append(p)
    dedup=[];seen=set()
    for p in found:
        key=(fingerprint(p["before"]),fingerprint(p["after"]))
        if key not in seen:
            seen.add(key);dedup.append(p)
        if len(dedup)>=limit:break
    return dedup

def operation_for(pair,definitions):
    old,new=pair["before"],pair["after"]
    delta=changed_words(old,new)
    context=old+" "+new
    # A substantive duration change is not mistakenly classified as a
    # broader application or authorization merely due to nearby keywords.
    if re.search(r"\d[\d,]*\s*(?:일|개월|년)\b",delta) and re.search(
            r"기한|기간|이내|처리|접수|심사",context):
        hit=next(((name,location) for name,words,location in definitions
                  if name=="처리기한·시행"),None)
        if hit:return hit
    for name,words,location in definitions:
        if any(word in delta for word in words):
            return name,location
    for name,words,location in definitions:
        if any(word in context for word in words):
            return name,location
    return None

def evidence_effects(event,operations):
    result=[]
    seen=set()
    for change in event.get("changes",[]):
        for pair in pairs(change):
            label=operation_for(pair,operations)
            if not label:continue
            work,location=label
            key=(pair["article"],fingerprint(pair["before"]),
                 fingerprint(pair["after"]),work)
            if key in seen:continue
            seen.add(key)
            result.append({
                "article":pair["article"],"old":pair["before"],"new":pair["after"],
                "context":pair["after"] or pair["before"],
                "old_context":pair["before"],"kind":pair["kind"],
                "operations":[work],"location":location,
                "semantic_pair":True,
                "match_confidence":pair["match_confidence"],
                "source_url":change.get("source_url") or event.get("url","")
            })
            if len(result)>=70:return result
    return result
