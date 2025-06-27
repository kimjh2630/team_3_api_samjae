import os
import requests
import xml.etree.ElementTree as ET
from fastapi import APIRouter, HTTPException, Query
from dotenv import load_dotenv

router = APIRouter()
load_dotenv(dotenv_path="key.env")

MADMDTL_SERVICE_KEY = os.getenv("MADMDTL_SERVICE_KEY")
HSPTL_SERVICE_KEY = os.getenv("HSPTL_SERVICE_KEY")

def format_time_hhmm(val):
    if not val or val in ["0000", "00:00"]:
        return "정보 없음"
    if len(val) == 4 and val.isdigit():
        return f"{val[:2]}:{val[2:]}"
    return val

def get_ykiho_by_hpid(hpid: str) -> str:
    """
    hpid로 병원 기본정보 API를 조회해 ykiho(요양기관기호)를 반환
    """
    url = "http://apis.data.go.kr/B552657/HsptlAsembySearchService/getHsptlMdcncListInfoInqire"
    params = {
        "serviceKey": HSPTL_SERVICE_KEY,
        "HPID": hpid,
        "type": "xml"
    }
    response = requests.get(url, params=params, timeout=10, verify=False)
    root = ET.fromstring(response.text)
    item = root.find('.//item')
    if item is not None:
        ykiho = item.findtext('ykiho')
        if ykiho:
            return ykiho
    return None

def xml_item_to_dict(item):
    return {child.tag: child.text for child in item}

@router.get("/api/medical/detail")
async def get_medical_detail(hpid: str = None, ykiho: str = None):
    """
    hpid 또는 ykiho로 병원 상세정보 조회 (getDtlInfo2.7, XML 파싱)
    - hpid: 기관ID (공공데이터포털)
    - ykiho: 요양기관기호 (심평원)
    """
    if not ykiho:
        if not hpid:
            raise HTTPException(status_code=400, detail="hpid 또는 ykiho 중 하나는 필수입니다.")
        ykiho = get_ykiho_by_hpid(hpid)
        if not ykiho:
            raise HTTPException(status_code=404, detail="해당 hpid에 대한 ykiho(요양기관기호)를 찾을 수 없습니다.")
    params = {
        'serviceKey': MADMDTL_SERVICE_KEY,
        'ykiho': ykiho,
    }
    url = "https://apis.data.go.kr/B551182/MadmDtlInfoService2.7/getDtlInfo2.7"
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        root = ET.fromstring(response.text)
        item = root.find('.//item')
        if item is None:
            return {"success": False, "message": "상세정보 없음"}
        item_dict = xml_item_to_dict(item)
        def get(tag): return item_dict.get(tag) or "정보 없음"
        result = {
            '월요일 진료시작': format_time_hhmm(get('trmtMonStart')),
            '월요일 진료종료': format_time_hhmm(get('trmtMonEnd')),
            '화요일 진료시작': format_time_hhmm(get('trmtTueStart')),
            '화요일 진료종료': format_time_hhmm(get('trmtTueEnd')),
            '수요일 진료시작': format_time_hhmm(get('trmtWedStart')),
            '수요일 진료종료': format_time_hhmm(get('trmtWedEnd')),
            '목요일 진료시작': format_time_hhmm(get('trmtThuStart')),
            '목요일 진료종료': format_time_hhmm(get('trmtThuEnd')),
            '금요일 진료시작': format_time_hhmm(get('trmtFriStart')),
            '금요일 진료종료': format_time_hhmm(get('trmtFriEnd')),
            '토요일 진료시작': format_time_hhmm(get('trmtSatStart')),
            '토요일 진료종료': format_time_hhmm(get('trmtSatEnd')),
            '일요일 진료시작': format_time_hhmm(get('trmtSunStart')),
            '일요일 진료종료': format_time_hhmm(get('trmtSunEnd')),
            '점심시간': get('lunchWeek'),
            '휴진안내(공휴일)': get('noTrmtHoli'),
            '휴진안내(일요일)': get('noTrmtSun'),
        }
        return {"success": True, "item": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"상세정보 조회 실패: {str(e)}")