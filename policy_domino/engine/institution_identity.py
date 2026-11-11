"""Resolve identified public institutions without promoting generic legal roles.

An official regulation can assign work to '시장·군수·구청장' without naming
which local authority. Such roles remain in the original legal evidence but
do not constitute distinct identified agencies or downstream agency actions.
"""
from __future__ import annotations
import re

UNSPECIFIED_ROLE = re.compile(
    r"^(?:시장|군수|구청장|교육감|시[·ㆍ/]?도지사|지방자치단체(?:의)?장|"
    r"장관|청장|처장|위원장|이사장|기관장|단체장|원장|국장|과장|담당자)$"
)
ROLE_SUFFIX = re.compile(
    r"(?:장관|청장|처장|위원장|이사장|교육감|시장|군수|구청장|지사)$"
)


def institution_name(value: object) -> str:
    name=" ".join(str(value or "").split()).strip()
    if not name or UNSPECIFIED_ROLE.fullmatch(name):
        return ""
    # A named public office-holder can identify its parent government body.
    for pattern in (
        r"^(.+?부)\s*장관$",
        r"^(.+?구)\s*청장$",
        r"^(.+?청)\s*장$",
        r"^(.+?처)\s*장$",
        r"^(.+?위원회)\s*위원장$",
        r"^(.+?공단)\s*이사장$",
        r"^(.+?시)\s*장$",
        r"^(.+?군)\s*수$",
        r"^(.+?(?:도|시))\s*지사$",
    ):
        match=re.fullmatch(pattern,name)
        if match:
            return match.group(1)
    # Do not infer a location, school board or other organization from an
    # unqualified role or from an unrecognized office-holder title.
    if ROLE_SUFFIX.search(name):
        return ""
    return name
