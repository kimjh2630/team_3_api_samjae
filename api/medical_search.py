from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import requests
import logging
import xml.etree.ElementTree as ET
from math import radians, sin, cos, sqrt, atan2
import threading
import time
import os
from dotenv import load_dotenv

router = APIRouter()
load_dotenv(dotenv_path="key.env")
# API 설정
class APIConfig:
    BASE_URL = "http://apis.data.go.kr/B552657/HsptlAsembySearchService"
    SERVICE_KEY = os.getenv("HSPTL_SERVICE_KEY")

# Pydantic 모델 정의
class MedicalFacility(BaseModel):
    hpid: Optional[str] = Field(None, description="기관ID")
    dutyName: Optional[str] = Field(None, description="기관명")
    dutyAddr: Optional[str] = Field(None, description="주소")
    dutyTel1: Optional[str] = Field(None, description="대표전화")
    # 운영 종료 시간
    dutyTime1c: Optional[str] = Field(None, description="진료시간(월요일)")
    dutyTime2c: Optional[str] = Field(None, description="진료시간(화요일)")
    dutyTime3c: Optional[str] = Field(None, description="진료시간(수요일)")
    dutyTime4c: Optional[str] = Field(None, description="진료시간(목요일)")
    dutyTime5c: Optional[str] = Field(None, description="진료시간(금요일)")
    dutyTime6c: Optional[str] = Field(None, description="진료시간(토요일)")
    dutyTime7c: Optional[str] = Field(None, description="진료시간(일요일)")
    dutyTime8c: Optional[str] = Field(None, description="진료시간(공휴일)")
    # 운영 시작 시간
    dutyTime1s: Optional[str] = Field(None, description="진료시간(월요일)")
    dutyTime2s: Optional[str] = Field(None, description="진료시간(화요일)")
    dutyTime3s: Optional[str] = Field(None, description="진료시간(수요일)")
    dutyTime4s: Optional[str] = Field(None, description="진료시간(목요일)")
    dutyTime5s: Optional[str] = Field(None, description="진료시간(금요일)")
    dutyTime6s: Optional[str] = Field(None, description="진료시간(토요일)")
    dutyTime7s: Optional[str] = Field(None, description="진료시간(일요일)")
    dutyTime8s: Optional[str] = Field(None, description="진료시간(공휴일)")
    wgs84Lat: Optional[str] = Field(None, description="위도")
    wgs84Lon: Optional[str] = Field(None, description="경도")
    dutyInf: Optional[str] = Field(None, description="기관설명")
    dgidIdName: Optional[str] = Field(None, description="진료과목")
    is_open: Optional[bool] = Field(None, description="현재 운영 여부")
    distance: Optional[float] = Field(None, description="현재 위치로부터의 거리(m)")
    today_open_status: Optional[str] = Field(None, description="오늘 운영 상태(운영중/운영종료/운영 시간 정보 없음)")

class Location(BaseModel):
    latitude: float
    longitude: float
    radius: Optional[int] = 1000  # 기본 검색 반경 1km

class SearchResponse(BaseModel):
    success: bool = Field(description="성공 여부")
    message: str = Field(description="응답 메시지")
    total_count: int = Field(description="총 결과 수")
    page_no: int = Field(description="현재 페이지")
    num_of_rows: int = Field(description="페이지당 결과 수")
    items: List[MedicalFacility] = Field(description="검색 결과 목록")
    timestamp: str = Field(description="조회 시간")
    current_location: Optional[Location] = Field(None, description="현재 위치 정보")

HOSPITAL_CACHE = []
CACHE_LAST_UPDATED = None

# 전체 병원 데이터 주기적 다운로드 및 캐싱

def fetch_and_cache_hospitals():
    global HOSPITAL_CACHE, CACHE_LAST_UPDATED
    try:
        cache = []
        page_no = 1
        num_of_rows = 5000
        while True:
            params = {
                'serviceKey': APIConfig.SERVICE_KEY,
                'type': 'xml',
                'pageNo': page_no,
                'numOfRows': num_of_rows,
            }
            url = f"{APIConfig.BASE_URL}/getHsptlBassInfoInqire"
            response = requests.get(url, params=params, timeout=120, verify=False)
            if response.status_code == 200:
                root = ET.fromstring(response.text)
                items = root.findall('.//item')
                if not items:
                    break
                for item in items:
                    item_dict = {child.tag: child.text for child in item}
                    cache.append(item_dict)
                if len(items) < num_of_rows:
                    break
                page_no += 1
            else:
                print(f"[병원 전체 데이터 캐싱 실패] {response.status_code}: {response.text}")
                break
        HOSPITAL_CACHE = cache
        CACHE_LAST_UPDATED = datetime.now()
        print(f"[병원 전체 데이터 캐싱 완료] {len(HOSPITAL_CACHE)}건 (진료과목 포함)")
    except Exception as e:
        print(f"[병원 전체 데이터 캐싱 예외] {e}")


def schedule_cache_refresh(interval_sec=86400):
    def refresh():
        while True:
            fetch_and_cache_hospitals()
            time.sleep(interval_sec)
    threading.Thread(target=refresh, daemon=True).start()

schedule_cache_refresh()

# 캐시가 비어있을 때 fallback으로 실시간 fetch

def get_hospital_data_fallback():
    try:
        cache = []
        page_no = 1
        num_of_rows = 5000
        while True:
            params = {
                'serviceKey': APIConfig.SERVICE_KEY,
                'type': 'xml',
                'pageNo': page_no,
                'numOfRows': num_of_rows,
            }
            url = f"{APIConfig.BASE_URL}/getHsptlMdcncFullDown"
            response = requests.get(url, params=params, timeout=120, verify=False)
            if response.status_code == 200:
                root = ET.fromstring(response.text)
                items = root.findall('.//item')
                if not items:
                    break
                for item in items:
                    item_dict = {child.tag: child.text for child in item}
                    cache.append(item_dict)
                if len(items) < num_of_rows:
                    break
                page_no += 1
            else:
                print(f"[병원 데이터 fallback 실패] {response.status_code}: {response.text}")
                break
        return cache
    except Exception as e:
        print(f"[병원 데이터 fallback 예외] {e}")
        return []

# 검색/필터링 함수

def filter_hospitals(
    keyword=None, region=None, subject=None, latitude=None, longitude=None, radius=None, is_open=None
):
    hospitals = HOSPITAL_CACHE if HOSPITAL_CACHE else get_hospital_data_fallback()
    results = hospitals
    if keyword:
        results = [h for h in results if keyword in (h.get('dutyName') or '') or keyword in (h.get('dutyAddr') or '')]
    if region:
        results = [h for h in results if region in (h.get('dutyAddr') or '')]
    if subject:
        subject = subject.strip().lower()
        results = [h for h in results if h.get('dutyName') and subject in h.get('dutyName').lower()]
        # 디버깅: subject가 포함되지 않은 dutyName이 결과에 있으면 로그로 출력
        for h in results:
            if subject not in h.get('dutyName', '').lower():
                print(f"[검색오류] subject 미포함: {h.get('dutyName')}")
    # 거리 필터링 및 distance 계산
    if latitude is not None and longitude is not None:
        for h in results:
            try:
                lat = float(h.get('wgs84Lat', 0))
                lon = float(h.get('wgs84Lon', 0))
                h['distance'] = calculate_distance(latitude, longitude, lat, lon)
            except Exception:
                h['distance'] = float('inf')
        if radius:
            results = [h for h in results if h['distance'] <= radius]
        results.sort(key=lambda h: h.get('distance', float('inf')))
    # 운영여부 필터링
    if is_open is not None:
        results = [h for h in results if is_facility_open(h) == is_open]
    return results

def fetch_medical_data(params: dict) -> dict:
    try:
        params.update({
            'serviceKey': APIConfig.SERVICE_KEY,
            'type': 'xml'
        })
        response = requests.get(
            f"{APIConfig.BASE_URL}/getHsptlMdcncListInfoInqire",
            params=params,
            timeout=30,
            verify=False
        )
        if response.status_code == 200:
            root = ET.fromstring(response.text)
            result = {
                'response': {
                    'header': {},
                    'body': {
                        'items': []
                    }
                }
            }
            header = root.find('header')
            if header is not None:
                result['response']['header'] = {
                    'resultCode': header.findtext('resultCode'),
                    'resultMsg': header.findtext('resultMsg')
                }
            body = root.find('body')
            if body is not None:
                items = body.find('items')
                if items is not None:
                    for item in items.findall('item'):
                        item_dict = {}
                        for child in item:
                            item_dict[child.tag] = child.text
                        result['response']['body']['items'].append(item_dict)
                    total_count = body.findtext('totalCount')
                    if total_count:
                        result['response']['body']['totalCount'] = int(total_count)
            return result
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"API 호출 실패: {response.text}"
            )
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=503, detail=f"API 서버 연결 실패: {str(e)}")
    except ET.ParseError as e:
        raise HTTPException(status_code=500, detail=f"XML 파싱 실패: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"서버 내부 오류: {str(e)}")

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    distance = R * c
    return distance * 1000

def is_facility_open(facility: dict) -> Optional[bool]:
    from datetime import datetime
    now = datetime.now()
    weekday = now.weekday() + 1 # 1(월) ~ 7(일)

    start_time_key = f'dutyTime{weekday}s'
    end_time_key = f'dutyTime{weekday}c'

    start_time_str = facility.get(start_time_key, '')
    end_time_str = facility.get(end_time_key, '')

    # '정보없음' 또는 '0000' 등의 문자열을 None으로 처리하는 헬퍼 함수 (필요시 추가)
    def _clean_time_str(time_str):
        if not time_str or '정보없음' in time_str or '0000' in time_str:
            return None
        return time_str.strip()

    cleaned_start_time_str = _clean_time_str(start_time_str)
    cleaned_end_time_str = _clean_time_str(end_time_str)

    # 운영 시간 정보가 없는 경우
    if cleaned_start_time_str is None and cleaned_end_time_str is None:
        # 공휴일 시간 등을 추가로 고려할 수 있으나, 기본은 정보 없음으로 판단
        return None

    # 시간 문자열을 today의 DateTime 객체로 파싱
    # Python에서는 날짜 없이 시간만으로 DateTime 비교가 어렵기 때문에 오늘 날짜를 붙입니다.
    # 자정을 넘어가는 시간 처리가 중요합니다.
    def _parse_time_to_today_datetime(time_str):
        if time_str is None or len(time_str) != 4:
            return None
        try:
            hour = int(time_str[:2])
            minute = int(time_str[2:])
            # 유효하지 않은 시간 값 체크
            if hour < 0 or hour >= 24 or minute < 0 or minute >= 60:
                return None
            return datetime(now.year, now.month, now.day, hour, minute)
        except (ValueError, TypeError):
            return None

    start_datetime_today = _parse_time_to_today_datetime(cleaned_start_time_str)
    end_datetime_today = _parse_time_to_today_datetime(cleaned_end_time_str)

    # 현재 시간 (분 단위까지 비교)
    current_time_today = datetime(now.year, now.month, now.day, now.hour, now.minute)

    # 운영 상태 판단 로직
    # 1. 시작 시간, 종료 시간 모두 유효한 경우
    if start_datetime_today is not None and end_datetime_today is not None:
        # 1-1. 일반적인 운영 시간 (시작 <= 종료)
        if start_datetime_today <= end_datetime_today:
            return current_time_today >= start_datetime_today and current_time_today < end_datetime_today
        # 1-2. 자정을 넘어가는 운영 시간 (시작 > 종료, 예: 22:00 ~ 02:00)
        else:
            # 현재 시간이 시작 시간 이후이거나 (오늘), 현재 시간이 종료 시간 이전인 경우 (다음날)
            # Python datetime 비교는 날짜를 포함하므로, end_datetime_today는 실제 다음날 02:00으로 간주해야 함
            # 로직: (현재 시간 >= 시작 시간) or (현재 시간 < 종료 시간)
            # 예: 22:00 ~ 02:00. 현재 23:00 -> 23:00 >= 22:00 (True) -> 운영중
            # 예: 22:00 ~ 02:00. 현재 01:00 -> 01:00 >= 22:00 (False), 01:00 < 02:00 (True) -> 운영중
            # 예: 22:00 ~ 02:00. 현재 03:00 -> 03:00 >= 22:00 (False), 03:00 < 02:00 (False) -> 운영종료
            return current_time_today >= start_datetime_today or current_time_today < end_datetime_today

    # 2. 시작 시간만 유효한 경우 (24시간 운영 등으로 간주할 수 있으나, API 데이터 특성 확인 필요)
    elif start_datetime_today is not None and cleaned_end_time_str is None:
         # 시작 시간 이후면 운영중으로 간주 (간단 처리)
         return current_time_today >= start_datetime_today

    # 3. 종료 시간만 유효한 경우 (매우 드물지만 처리)
    elif cleaned_start_time_str is None and end_datetime_today is not None:
         # 종료 시간 이전이면 운영중으로 간주 (간단 처리)
         return current_time_today < end_datetime_today

    # 그 외 경우 (시간 형식이 이상하거나 알 수 없는 경우)
    return None

def format_time_range(time_range: str) -> str:
    try:
        if '-' in time_range:
            start, end = time_range.split('-')
            if len(start) == 4 and len(end) == 4:
                start_fmt = f"{int(start[:2]):02d}:{int(start[2:]):02d}"
                end_fmt = f"{int(end[:2]):02d}:{int(end[2:]):02d}"
                return f"{start_fmt} ~ {end_fmt}"
        elif len(time_range) == 4 and time_range.isdigit():
            start_fmt = f"{int(time_range[:2]):02d}:{int(time_range[2:]):02d}"
            end_fmt = f"{int(time_range[:2]):02d}:{int(time_range[2:]):02d}"
            return f"{start_fmt} ~ {end_fmt}"
    except Exception:
        pass
    return time_range

def format_single_time(time_str: str) -> str:
    if time_str.isdigit() and len(time_str) == 4:
        hour = int(time_str[:2])
        minute = int(time_str[2:])
        if 0 <= hour < 24 and 0 <= minute < 60:
            return f"{hour:02d}:{minute:02d}"
    return "정보 없음"

def process_operating_hours(item: dict):
    # print(item) # 디버깅을 위해 필요시 활성화
    for i in range(1, 8 + 1):  # 1~7: 월~일, 8: 공휴일
        start_key = f'dutyTime{i}s'
        end_key = f'dutyTime{i}c'
        start_val = item.get(start_key, '')
        end_val = item.get(end_key, '')

        formatted_start = format_single_time(start_val)
        formatted_end = format_single_time(end_val)

        # 시작 시간과 종료 시간 정보가 모두 없을 경우
        if formatted_start == "정보 없음" and formatted_end == "정보 없음":
            item[f'dutyTime{i}'] = '운영 시간 정보 없음'
        # 시작 시간 또는 종료 시간 정보가 하나라도 있을 경우
        else:
            # 시작 시간만 있고 종료 시간 정보가 없는 경우
            if formatted_start != "정보 없음" and formatted_end == "정보 없음":
                item[f'dutyTime{i}'] = f"{formatted_start} ~ 정보 없음"
            # 종료 시간만 있고 시작 시간 정보가 없는 경우 (일반적이지 않으나 처리)
            elif formatted_start == "정보 없음" and formatted_end != "정보 없음":
                 item[f'dutyTime{i}'] = f"정보 없음 ~ {formatted_end}"
            # 시작 시간과 종료 시간 정보가 모두 있는 경우
            else:
                item[f'dutyTime{i}'] = f"{formatted_start} ~ {formatted_end}"

def get_today_open_status(facility: dict) -> str:
    # is_facility_open 함수를 사용하여 운영 상태 판단
    status = is_facility_open(facility)
    if status is None:
        # is_facility_open이 None을 반환한 경우 (시간 정보 없음 또는 판단 불가)
        # 상세한 판단 로직을 is_facility_open 내부에 두었으므로 여기서 추가 판단은 필요 없음
        return '운영 시간 정보 없음'
    elif status:
        return '운영중'
    else:
        return '운영종료'

@router.get("/api/medical/search")
async def search_medical_facilities(
    Q0: Optional[str] = Query(None, description="시도 (예: 서울특별시)"),
    QN: Optional[str] = Query(None, description="의료기관명"),
    latitude: float = Query(None, description="현재 위도"),
    longitude: float = Query(None, description="현재 경도"),
    radius: int = Query(None, description="검색 반경(m)"),
    is_open: bool = Query(None, description="운영중인 곳만"),
    page_no: int = Query(1, ge=1, description="페이지 번호"),
    num_of_rows: int = Query(20, ge=1, le=100, description="페이지당 결과 수")
):
    try:
        results = filter_hospitals(
            region=Q0,
            subject=QN,  # QN(의료기관명)을 subject로 넘김
            latitude=latitude,
            longitude=longitude,
            radius=radius,
            is_open=is_open
        )
        total_count = len(results)
        start = (page_no - 1) * num_of_rows
        end = start + num_of_rows
        page_items = results[start:end]
        for h in page_items:
            process_operating_hours(h)
            h['is_open'] = is_facility_open(h)
            h['today_open_status'] = get_today_open_status(h)
        return {
            "success": True,
            "message": "검색 완료",
            "total_count": total_count,
            "page_no": page_no,
            "num_of_rows": num_of_rows,
            "items": [MedicalFacility(**h) for h in page_items],
            "timestamp": datetime.now().isoformat(),
            "current_location": Location(latitude=latitude, longitude=longitude, radius=radius) if latitude and longitude and radius else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"서버 내부 오류: {str(e)}")

@router.get("/api/medical/nearby")
async def get_nearby_medical_facilities(
    latitude: float = Query(..., description="현재 위도"),
    longitude: float = Query(..., description="현재 경도"),
    radius: int = Query(1000, description="검색 반경(m)"),
    subject: str = Query(None, description="진료과목명"),
    is_open: bool = Query(None, description="운영중인 곳만"),
    page_no: int = Query(1, ge=1),
    num_of_rows: int = Query(20, ge=1, le=100)
):
    try:
        results = filter_hospitals(None, None, subject, latitude, longitude, radius, is_open)
        total_count = len(results)
        start = (page_no - 1) * num_of_rows
        end = start + num_of_rows
        page_items = results[start:end]
        for h in page_items:
            process_operating_hours(h)
            h['is_open'] = is_facility_open(h)
            h['today_open_status'] = get_today_open_status(h)
        return {
            "success": True,
            "message": "검색 완료",
            "total_count": total_count,
            "page_no": page_no,
            "num_of_rows": num_of_rows,
            "items": [MedicalFacility(**h) for h in page_items],
            "timestamp": datetime.now().isoformat(),
            "current_location": Location(latitude=latitude, longitude=longitude, radius=radius)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"서버 내부 오류: {str(e)}")

@router.get("/api/medical/all")
async def get_all_medical_facilities():
    hospitals = HOSPITAL_CACHE if HOSPITAL_CACHE else get_hospital_data_fallback()
    for h in hospitals:
        process_operating_hours(h)
        h['is_open'] = is_facility_open(h)
        h['today_open_status'] = get_today_open_status(h)
    return {
        "success": True,
        "items": hospitals,
        "total_count": len(hospitals),
        "timestamp": datetime.now().isoformat()
    }

@router.get("/api/medical/{hospital_id}")
async def get_medical_facility_by_id(hospital_id: str):
    hospitals = HOSPITAL_CACHE if HOSPITAL_CACHE else get_hospital_data_fallback()
    for h in hospitals:
        if (h.get('hpid') or h.get('hospital_id')) == hospital_id:
            process_operating_hours(h)
            h['is_open'] = is_facility_open(h)
            h['today_open_status'] = get_today_open_status(h)
            return {
                "success": True,
                "item": h,
                "timestamp": datetime.now().isoformat()
            }
    raise HTTPException(status_code=404, detail='병원 정보를 찾을 수 없습니다.')