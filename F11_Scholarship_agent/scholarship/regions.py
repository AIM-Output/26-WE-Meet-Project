"""지역 장학(지자체·지역 장학재단) 판정용 지명 사전 — 시·군·구 → 시·도. 표준 라이브러리만.

전남대 장학안내 게시판의 절반 이상이 '○○시 장학회'·'○○인재평생교육진흥원' 같은 지역 장학이다(2026-10-09 실측 160건).
지역 조건을 못 읽으면 전부 '확인 필요'로 쌓여 정작 받을 수 있는 장학이 묻힌다. 그래서 공지의 지명을 시·도로 바꿔
프로필(C2)의 거주 지역·출신 고교 지역(시·도 단위)과 대조한다.

  - 시·도가 다르면 '미달', 시·도가 같고 공지가 시·군 단위면 '모름'(시·군은 프로필에 없다), 시·도 단위면 '충족'.
  - 오인을 막는 규칙: 시·군 이름은 '시/군' 꼬리가 붙었을 때만 지명으로 본다('아산사회복지재단'은 아산시가 아니다).
    꼬리 없는 이름(서울장학재단·춘천인재육성)은 공지 맨 앞 [주관] 괄호에서 지역 재단다운 말(인재·장학·평생교육…)이 이어질 때만.
    본문에서는 거주·주소·출신 같은 말이 같은 줄에 있을 때만 지역 조건으로 본다('대전 일자리 박람회'는 조건이 아니다).
  - '전남대'의 '전남', '광주은행'의 '광주'처럼 낱말 안의 지명은 보지 않는다.
2026 행정구역: 강원·전북 특별자치도, 대구 군위군, 인천 제물포·영종·검단구, 전남광주통합특별시(광주+전남)까지 반영했다.
"""
from __future__ import annotations

import re
from typing import Optional

# 프로필(C2 schema.REGIONS)과 같은 짧은 이름
PROVINCES = ("서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남",
             "전북", "전남", "경북", "경남", "제주")

# 시·도 정식·옛 이름 → 짧은 이름 (여럿이면 그 시·도 모두)
PROVINCE_NAMES: dict[str, tuple[str, ...]] = {
    "서울특별시": ("서울",), "서울시": ("서울",),
    "부산광역시": ("부산",), "부산시": ("부산",),
    "대구광역시": ("대구",), "대구시": ("대구",),
    "인천광역시": ("인천",), "인천시": ("인천",),
    "광주광역시": ("광주",),
    "대전광역시": ("대전",), "대전시": ("대전",),
    "울산광역시": ("울산",), "울산시": ("울산",),
    "세종특별자치시": ("세종",), "세종시": ("세종",),
    "경기도": ("경기",),
    "강원특별자치도": ("강원",), "강원도": ("강원",),
    "충청북도": ("충북",), "충청남도": ("충남",),
    "전북특별자치도": ("전북",), "전라북도": ("전북",),
    "전라남도": ("전남",),
    "경상북도": ("경북",), "경상남도": ("경남",),
    "제주특별자치도": ("제주",), "제주도": ("제주",),
    "전남광주통합특별시": ("광주", "전남"),
}

_CITIES: dict[str, str] = {}      # '포항시' → '경북'
_AMBIGUOUS: dict[str, tuple[str, ...]] = {"광주시": ("광주", "경기"), "고성군": ("강원", "경남"),
                                          "강서구": ("서울", "부산")}


def _add(province: str, names: str, suffix: str) -> None:
    for n in names.split():
        key = n + suffix
        if key not in _AMBIGUOUS:
            _CITIES[key] = province


_add("경기", "수원 성남 의정부 안양 부천 광명 평택 동두천 안산 고양 과천 구리 남양주 오산 시흥 군포 의왕 하남 용인 "
            "파주 이천 안성 김포 화성 양주 포천 여주", "시")
_add("경기", "연천 가평 양평", "군")
_add("강원", "춘천 원주 강릉 동해 태백 속초 삼척", "시")
_add("강원", "홍천 횡성 영월 평창 정선 철원 화천 양구 인제 양양", "군")
_add("충북", "청주 충주 제천", "시")
_add("충북", "보은 옥천 영동 증평 진천 괴산 음성 단양", "군")
_add("충남", "천안 공주 보령 아산 서산 논산 계룡 당진", "시")
_add("충남", "금산 부여 서천 청양 홍성 예산 태안", "군")
_add("전북", "전주 군산 익산 정읍 남원 김제", "시")
_add("전북", "완주 진안 무주 장수 임실 순창 고창 부안", "군")
_add("전남", "목포 여수 순천 나주 광양", "시")
_add("전남", "담양 곡성 구례 고흥 보성 화순 장흥 강진 해남 영암 무안 함평 영광 장성 완도 진도 신안", "군")
_add("경북", "포항 경주 김천 안동 구미 영주 영천 상주 문경 경산", "시")
_add("경북", "의성 청송 영양 영덕 청도 고령 성주 칠곡 예천 봉화 울진 울릉", "군")
_add("경남", "창원 진주 통영 사천 김해 밀양 거제 양산", "시")
_add("경남", "의령 함안 창녕 남해 하동 산청 함양 거창 합천", "군")
_add("제주", "제주 서귀포", "시")
_add("부산", "기장", "군")
_add("대구", "달성 군위", "군")
_add("인천", "강화 옹진", "군")
_add("울산", "울주", "군")
# 이름이 하나뿐인 자치구 (중구·동구·서구·남구·북구·강서구는 여러 곳이라 시·도 이름과 같이 나올 때만 쓴다)
_add("서울", "종로 용산 성동 광진 동대문 중랑 성북 강북 도봉 노원 은평 서대문 마포 양천 구로 금천 영등포 동작 관악 "
            "서초 강남 송파 강동", "구")
_add("부산", "영도 부산진 동래 해운대 사하 금정 연제 수영 사상", "구")
_add("대구", "수성 달서", "구")
_add("인천", "미추홀 연수 남동 부평 계양 제물포 영종 검단", "구")
_add("광주", "광산", "구")
_add("대전", "유성 대덕", "구")

# 꼬리 없는 이름(춘천·달서)은 [주관] 괄호 맨 앞에서 이런 말이 이어질 때만 지역 재단으로 본다
_LOCAL_FOLLOW = r"(?:인재|장학|사랑|미래|시민|군민|구민|도민|평생|청년|복지|연구원|교육|희망|발전|향토)"
_BRACKET = re.compile(r"\[\s*(?:\(\s*(?:재|사|제)\s*\)\s*|재단법인\s*|사단법인\s*)?([가-힣]+)")
# 지명 뒤에 이어져도 되는 말 — 없거나(‘[통영시]’) 지역 재단 말이거나(‘포항시장학회’·‘정읍시민장학’) 아래 구·군(‘울산광역시남구장학’)
_REST_OK = re.compile(r"^(?:$|민?" + _LOCAL_FOLLOW + r"|[가-힣]{1,4}[구군])")
RESIDENCY_WORDS = re.compile(r"거주|주소|주민등록|출신|연고|관내|전입|졸업|태어난|원적|고등학교")
# 같은 줄에 이런 말이 있으면 조건이 아니라 접수처·문의처 주소다
_NOT_CONDITION = re.compile(r"접수처|제출처|보내|우편|방문|소재지|위치|홈페이지|이메일|e-?mail|문의|☎|팩스|FAX", re.I)
NATIONWIDE = re.compile(r"전국\s*(?:의|소재)?\s*(?:대학|대학생|대학교)|지역\s*(?:제한|무관)\s*(?:없|무)")


def _lookup(word: str, with_suffix: bool) -> Optional[tuple[tuple[str, ...], str, str]]:
    """낱말 → (시·도들, 수준 province|city, 이름). with_suffix=False 면 꼬리 없는 이름도 찾아 본다."""
    for name, provs in PROVINCE_NAMES.items():
        if word.startswith(name):
            return provs, "province", name
    for name, provs in _AMBIGUOUS.items():
        if word.startswith(name):
            return provs, "city", name
    for name, prov in _CITIES.items():
        if word.startswith(name):
            return (prov,), "city", name
    if not with_suffix:
        for short in PROVINCES:
            if re.match(short + _LOCAL_FOLLOW, word):
                return (short,), "province", short
        for name, prov in _CITIES.items():
            if re.match(name[:-1] + _LOCAL_FOLLOW, word) and len(name) > 2:
                return (prov,), "city", name[:-1]            # '춘천인재…' → 춘천 (꼬리 없는 이름 그대로)
    return None


def _scan(text: str) -> list[tuple[tuple[str, ...], str, str]]:
    """글 안의 지명(꼬리 붙은 시·군·구, 시·도 정식 이름)을 찾는다. 낱말 안의 것(전남대·광주은행)은 보지 않는다."""
    out = []
    for m in re.finditer(r"(?<![가-힣])([가-힣]{2,12})", text or ""):
        hit = _lookup(m.group(1), True)
        if hit:
            out.append(hit)
    return out


def detect(title: str, body: str = "") -> Optional[dict]:
    """공지의 지역 조건 → {provinces, level(province|city), names, quote} · 없으면 None.

    순서: ① 제목의 [주관] 괄호(지역 재단·지자체) ② 제목의 시·도/시·군 이름 중 지역 재단 꼬리가 붙은 것
         ③ 본문에서 거주·주소·출신 말과 같은 줄에 있는 지명. 전국 대상이라고 쓴 공지는 지역 조건이 없다."""
    provs: set[str] = set()
    names: list[str] = []
    level = "province"
    quote: Optional[str] = None
    for m in _BRACKET.finditer(title or ""):                  # ① [주관] — 꼬리 없는 이름도 지역 재단 말이 이어지면
        word = m.group(1)
        hit = _lookup(word, False)
        if hit and (hit[2] not in PROVINCE_NAMES and hit[2] not in _CITIES and hit[2] not in _AMBIGUOUS
                    or _REST_OK.match(word[len(hit[2]):])):
            provs.update(hit[0]); names.append(hit[2]); quote = title
            if hit[1] == "city":
                level = "city"
    if not provs:                                            # ② 제목의 정식 지명 ('광주광역시 대학생 학자금')
        for m in re.finditer(r"(?<![가-힣])([가-힣]{2,14})", title or ""):
            word = m.group(1)
            hit = _lookup(word, True)
            if hit and _REST_OK.match(word[len(hit[2]):]):
                provs.update(hit[0]); names.append(hit[2]); quote = title
                if hit[1] == "city":
                    level = "city"
    if body and NATIONWIDE.search(body) and not provs:
        return None
    from_title = bool(provs)
    body_lines: list[str] = []
    for ln in (body or "").splitlines():                     # ③ 본문의 거주·출신 조건 줄
        if len(ln) > 220 or not RESIDENCY_WORDS.search(ln) or _NOT_CONDITION.search(ln):
            continue
        hits = _scan(ln)
        if not hits:
            continue
        for p, lv, nm in hits:
            provs.update(p); names.append(nm)
            if lv == "city":
                level = "city"
        body_lines.append(ln.strip()[:200])
        quote = quote or ln.strip()
    if not provs:
        return None
    # 본문 근거가 '주소·거주'만 말하는가, '출신 고교'도 말하는가 — 거주지만 다를 때 미달로 단정할지가 여기서 갈린다(match)
    return {"provinces": sorted(provs), "level": level, "names": list(dict.fromkeys(names)), "quote": quote,
            "fromTitle": from_title, "bodyLines": body_lines[:3],
            "mentionsSchool": any(re.search(r"출신|고등학교|고교", ln) for ln in body_lines)}


def province_of(name: Optional[str]) -> tuple[str, ...]:
    """'광주광역시'·'광주' → ('광주',). 모르면 ()."""
    if not name:
        return ()
    if name in PROVINCES:
        return (name,)
    hit = _lookup(name, True)
    return hit[0] if hit else ()
