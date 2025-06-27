from fastapi import APIRouter, FastAPI, Depends, HTTPException, Body, Query
from pydantic import BaseModel, EmailStr, constr, validator
from sqlalchemy import create_engine, Column, Integer, String, UniqueConstraint, inspect, text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Optional
from datetime import datetime, timedelta
import hashlib
import requests
import jwt
from fastapi.responses import JSONResponse
import re
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

router = APIRouter()

# Database configuration
DATABASE_URL = os.getenv('DATABASE_URL', "postgresql://postgres:admin1234@database-1.ct8wqsmwwlb2.ap-northeast-2.rds.amazonaws.com:5432/postgres")

# Social login API keys
NAVER_LOGIN_CLIENT_ID = os.getenv('NAVER_LOGIN_CLIENT_ID')
NAVER_LOGIN_CLIENT_SECRET = os.getenv('NAVER_LOGIN_CLIENT_SECRET')
KAKAO_LOGIN_CLIENT_ID = os.getenv('KAKAO_LOGIN_CLIENT_ID')
GOOGLE_LOGIN_CLIENT_ID = os.getenv('GOOGLE_LOGIN_CLIENT_ID')

if not all([NAVER_LOGIN_CLIENT_ID, NAVER_LOGIN_CLIENT_SECRET, KAKAO_LOGIN_CLIENT_ID, GOOGLE_LOGIN_CLIENT_ID]):
    raise ValueError("Missing required social login API keys in environment variables")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# loginaccount 테이블 모델
class LoginAccount(Base):
    __tablename__ = "loginaccount"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False)
    nickname = Column(String(50), nullable=False)
    password_hash = Column(String(255), nullable=True)
    platform = Column(String(20), nullable=False)
    profile_image = Column(String, nullable=True)
    gender = Column(String(10), nullable=True)
    birthday = Column(String(20), nullable=True)
    phone = Column(String(30), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint('email', 'platform', name='_email_platform_uc'),)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Pydantic 모델
class LoginAccountCreate(BaseModel):
    email: EmailStr
    nickname: constr(min_length=2, max_length=30)
    password: Optional[str] = None
    platform: str
    profile_image: Optional[str] = None
    gender: Optional[str] = None
    birthday: Optional[str] = None
    phone: Optional[str] = None

    @validator('password')
    def password_rule(cls, v, values):
        platform = values.get('platform')
        if platform == 'local':
            if not v:
                raise ValueError('비밀번호는 필수입니다.')
            if not (6 <= len(v) <= 12):
                raise ValueError('비밀번호는 6자 이상 12자 이하여야 합니다.')
            if not re.search(r'[A-Za-z]', v) or not re.search(r'[0-9]', v):
                raise ValueError('비밀번호는 영어와 숫자를 모두 포함해야 합니다.')
        return v

    @validator('platform')
    def platform_check(cls, v):
        if v not in ['local', 'google', 'kakao', 'naver']:
            raise ValueError('지원하지 않는 플랫폼입니다.')
        return v

class LoginAccountOut(BaseModel):
    id: int
    email: str
    nickname: str
    platform: str
    profile_image: Optional[str] = None
    gender: Optional[str] = None
    birthday: Optional[str] = None
    phone: Optional[str] = None
    created_at: Optional[datetime] = None
    class Config:
        orm_mode = True

# 비밀번호 해시 함수
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

# 회원가입/소셜로그인 (없으면 생성, 있으면 업데이트)
@router.post("/loginaccount/", response_model=LoginAccountOut)
def create_or_update_loginaccount(account: LoginAccountCreate, db: Session = Depends(get_db)):
    # 이메일+플랫폼 중복 체크
    db_account = db.query(LoginAccount).filter(LoginAccount.email == account.email, LoginAccount.platform == account.platform).first()
    if db_account:
        raise HTTPException(status_code=409, detail="이미 가입된 이메일/플랫폼입니다.")
    # 닉네임 중복 체크
    if db.query(LoginAccount).filter(LoginAccount.nickname == account.nickname).first():
        raise HTTPException(status_code=409, detail="이미 사용중인 닉네임입니다.")
    # 로컬 회원 비밀번호 검증은 Pydantic validator에서 처리됨
    password_hash = hash_password(account.password) if account.password else None
    new_account = LoginAccount(
        email=account.email,
        nickname=account.nickname,
        password_hash=password_hash,
        platform=account.platform,
        profile_image=account.profile_image,
        gender=account.gender,
        birthday=account.birthday,
        phone=account.phone
    )
    db.add(new_account)
    db.commit()
    db.refresh(new_account)
    return new_account

# 로그인 (로컬 계정)
class LoginRequest(BaseModel):
    email: str
    password: str
    platform: str

@router.post("/loginaccount/login")
async def login_account(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(LoginAccount).filter(LoginAccount.email == request.email, LoginAccount.platform == request.platform).first()

    if not user:
        raise HTTPException(status_code=401, detail="잘못된 이메일 또는 비밀번호입니다.")

    if user.platform == 'local':
        verified = user.password_hash == hashlib.sha256(request.password.encode()).hexdigest()
    else:
        raise HTTPException(status_code=400, detail="로컬 로그인 전용 엔드포인트입니다.")

    if not verified:
        raise HTTPException(status_code=401, detail="잘못된 이메일 또는 비밀번호입니다.")

    # Access Token 생성
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_to_encode = {"sub": user.email, "platform": user.platform, "token_type": "access"}
    access_expires_delta = datetime.utcnow() + access_token_expires
    access_to_encode.update({"exp": access_expires_delta.timestamp()})
    access_token = jwt.encode(access_to_encode, SECRET_KEY, algorithm=ALGORITHM)

    # Refresh Token 생성
    refresh_token_expires = timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    refresh_to_encode = {"sub": user.email, "platform": user.platform, "token_type": "refresh"}
    refresh_expires_delta = datetime.utcnow() + refresh_token_expires
    refresh_to_encode.update({"exp": refresh_expires_delta.timestamp()})
    refresh_token = jwt.encode(refresh_to_encode, SECRET_KEY, algorithm=ALGORITHM)

    return {
        "id": user.id,
        "email": user.email,
        "nickname": user.nickname,
        "platform": user.platform,
        "profile_image": user.profile_image,
        "gender": user.gender,
        "birthday": user.birthday,
        "phone": user.phone,
        "created_at": user.created_at.isoformat(),
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }

# 사용자 정보 조회
@router.get("/loginaccount/{email}", response_model=LoginAccountOut)
def get_account(email: str, platform: str, db: Session = Depends(get_db)):
    db_account = db.query(LoginAccount).filter(LoginAccount.email == email, LoginAccount.platform == platform).first()
    if not db_account:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    return db_account

# 소셜로그인 + JWT 발급
class SocialLoginRequest(BaseModel):
    provider: str  # 'kakao', 'naver', 'google'
    access_token: str  # 카카오/네이버는 access_token, 구글은 id_token

@router.post("/loginaccount/social")
def social_login(request: SocialLoginRequest, db: Session = Depends(get_db)):
    provider = request.provider.lower()
    social_access_token = request.access_token # 소셜 플랫폼에서 받은 토큰
    email = None
    nickname = None
    profile_image = None
    gender = None
    birthday = None
    phone = None
    platform = None # 최종 플랫폼 값

    if provider == "naver":
        headers = {
            "Authorization": f"Bearer {social_access_token}",
            "X-Naver-Client-Id": NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
        }
        resp = requests.get("https://openapi.naver.com/v1/nid/me", headers=headers)
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="네이버 토큰 검증 실패")
        user_info = resp.json().get("response")
        email = user_info.get("email")
        nickname = user_info.get("name") or user_info.get("nickname", "네이버유저")
        profile_image = user_info.get("profile_image")
        gender = user_info.get("gender")
        birthday = user_info.get("birthday")
        phone = user_info.get("mobile")
        platform = "naver"
    elif provider == "kakao":
        headers = {
            "Authorization": f"Bearer {social_access_token}",
            "Content-Type": "application/x-www-form-urlencoded;charset=utf-8"
        }
        # params = {
        #     "client_id": KAKAO_CLIENT_ID # KAKAO는 access_token으로 사용자 정보 조회 시 client_id 불필요
        # }
        resp = requests.get("https://kapi.kakao.com/v2/user/me", headers=headers)
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="카카오 토큰 검증 실패")
        user_info = resp.json()
        kakao_account = user_info.get("kakao_account", {})
        email = kakao_account.get("email")
        profile_properties = user_info.get("properties", {})
        nickname = profile_properties.get("nickname", "카카오유저")
        profile_image = profile_properties.get("profile_image")
        gender = kakao_account.get("gender")
        birthday = kakao_account.get("birthday")
        phone_number_info = kakao_account.get("phone_number")
        phone = phone_number_info # Kakao API에서 'phone_number' 필드는 직접 전화번호 문자열을 제공함
        platform = "kakao"
    elif provider == "google":
        params = {
            "id_token": social_access_token,
            "client_id": GOOGLE_LOGIN_CLIENT_ID
        }
        resp = requests.get("https://oauth2.googleapis.com/tokeninfo", params=params)
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="구글 토큰 검증 실패")
        user_info = resp.json()
        email = user_info.get("email")
        nickname = user_info.get("name", "구글유저")
        profile_image = user_info.get("picture")
        # Google API는 성별, 생년월일, 전화번호를 기본적으로 제공하지 않으므로, 이 부분은 비워둡니다.
        gender = None
        birthday = None
        phone = None
        platform = "google"
    else:
        raise HTTPException(status_code=400, detail="지원하지 않는 소셜로그인입니다.")

    if not email:
        raise HTTPException(status_code=400, detail="이메일 정보를 가져올 수 없습니다.")

    # DB에 저장/업데이트
    db_account = db.query(LoginAccount).filter(LoginAccount.email == email, LoginAccount.platform == platform).first()
    if db_account:
        # 기존 계정이 있으면 업데이트
        db_account.nickname = nickname
        db_account.profile_image = profile_image
        db_account.gender = gender
        db_account.birthday = birthday
        db_account.phone = phone
        db.commit()
        db.refresh(db_account)
    else:
        # 없으면 새로 생성
        new_account = LoginAccountCreate(
            email=email,
            nickname=nickname,
            platform=platform,
            profile_image=profile_image,
            gender=gender,
            birthday=birthday,
            phone=phone
        )
        db_account = create_or_update_loginaccount(new_account, db) # 기존 함수 재사용

    # Access Token 생성
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_to_encode = {"sub": db_account.email, "platform": db_account.platform, "token_type": "access"}
    access_expires_delta = datetime.utcnow() + access_token_expires
    access_to_encode.update({"exp": access_expires_delta.timestamp()})
    access_token = jwt.encode(access_to_encode, SECRET_KEY, algorithm=ALGORITHM)

    # Refresh Token 생성
    refresh_token_expires = timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    refresh_to_encode = {"sub": db_account.email, "platform": db_account.platform, "token_type": "refresh"}
    refresh_expires_delta = datetime.utcnow() + refresh_token_expires
    refresh_to_encode.update({"exp": refresh_expires_delta.timestamp()})
    refresh_token = jwt.encode(refresh_to_encode, SECRET_KEY, algorithm=ALGORITHM)

    return {
        "id": db_account.id,
        "email": db_account.email,
        "nickname": db_account.nickname,
        "platform": db_account.platform,
        "profile_image": db_account.profile_image,
        "gender": db_account.gender,
        "birthday": db_account.birthday,
        "phone": db_account.phone,
        "created_at": db_account.created_at.isoformat(),
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }

# Refresh Token을 이용한 Access Token 갱신 엔드포인트
class RefreshTokenRequest(BaseModel):
    refresh_token: str

@router.post("/loginaccount/refresh_token")
async def refresh_access_token(request: RefreshTokenRequest, db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(request.refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        platform = payload.get("platform")
        token_type = payload.get("token_type")

        if token_type != "refresh":
            raise HTTPException(status_code=401, detail="유효하지 않은 토큰 타입입니다.")

        user = db.query(LoginAccount).filter(LoginAccount.email == email, LoginAccount.platform == platform).first()
        if not user:
            raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다.")

        # 새로운 Access Token 생성
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_to_encode = {"sub": user.email, "platform": user.platform, "token_type": "access"}
        access_expires_delta = datetime.utcnow() + access_token_expires
        access_to_encode.update({"exp": access_expires_delta.timestamp()})
        new_access_token = jwt.encode(access_to_encode, SECRET_KEY, algorithm=ALGORITHM)

        return {"access_token": new_access_token, "token_type": "bearer"}

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh Token이 만료되었습니다. 다시 로그인해주세요.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="유효하지 않은 Refresh Token입니다.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"토큰 갱신 중 오류 발생: {e}")

# 회원정보 수정 (PATCH)
@router.patch("/loginaccount/{email}", response_model=LoginAccountOut)
def update_account(email: str, platform: str = Query(...), update: dict = Body(...), db: Session = Depends(get_db)):
    db_account = db.query(LoginAccount).filter(LoginAccount.email == email, LoginAccount.platform == platform).first()
    if not db_account:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    # 닉네임 중복 체크
    if "nickname" in update:
        new_nickname = update["nickname"]
        exists = db.query(LoginAccount).filter(LoginAccount.nickname == new_nickname, LoginAccount.email != email).first()
        if exists:
            raise HTTPException(status_code=409, detail="이미 사용중인 닉네임입니다.")
    # 비밀번호 변경 처리
    if "password" in update:
        db_account.password_hash = hash_password(update["password"])
        update.pop("password")
    # 전달된 필드만 업데이트
    for key, value in update.items():
        if hasattr(db_account, key):
            setattr(db_account, key, value)
    db.commit()
    db.refresh(db_account)
    return db_account

# 회원 탈퇴 (DELETE)
@router.delete("/loginaccount/{email}")
def delete_account(email: str, platform: str = Query(...), db: Session = Depends(get_db)):
    db_account = db.query(LoginAccount).filter(LoginAccount.email == email, LoginAccount.platform == platform).first()
    if not db_account:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    db.delete(db_account)
    db.commit()
    return {"message": "회원 탈퇴가 완료되었습니다."}

# .env 파일 로드
load_dotenv(dotenv_path='key.env')

# 환경 변수에서 SECRET_KEY와 ACCESS_TOKEN_EXPIRE_MINUTES 로드
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 7))

# 환경 변수 유효성 검사
if not SECRET_KEY:
    raise ValueError("JWT_SECRET_KEY 환경 변수가 설정되지 않았습니다.")

# 로그인 엔드포인트에서 로그인 성공 시 JWT 토큰을 생성하여 응답 데이터에 access_token과 token_type 필드를 추가
@router.post("/loginaccount/login")
async def login_account(login_account_data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(LoginAccount).filter(LoginAccount.email == login_account_data.email).first()

    if not user:
        raise HTTPException(status_code=401, detail="잘못된 이메일 또는 비밀번호입니다.")

    # 플랫폼에 따른 비밀번호 확인 (로컬 로그인)
    if user.platform == 'local':
        # 저장된 해시된 비밀번호와 입력된 비밀번호를 비교
        verified = user.password == hashlib.sha256(login_account_data.password.encode()).hexdigest()
    else:
        # 소셜 로그인은 비밀번호 필드가 없으므로, 여기에 다른 로직 추가 필요 (예: access_token 유효성 검사 등)
        # 지금은 로컬 로그인만 다루므로 이 부분은 단순화
        verified = False # 소셜 로그인은 이 엔드포인트를 통해 직접 비밀번호를 확인하지 않음

    if not verified:
        raise HTTPException(status_code=401, detail="잘못된 이메일 또는 비밀번호입니다.")

    # JWT 토큰 생성
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": user.email, "platform": user.platform}
    expires_delta = datetime.utcnow() + access_token_expires
    to_encode.update({"exp": expires_delta.timestamp()})

    access_token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    # 사용자 데이터와 토큰을 함께 반환
    return {
        "id": user.id,
        "email": user.email,
        "nickname": user.nickname,
        "platform": user.platform,
        "profile_image": user.profile_image,
        "gender": user.gender,
        "birthday": user.birthday,
        "phone": user.phone,
        "created_at": user.created_at.isoformat(),
        "access_token": access_token,
        "token_type": "bearer",
    } 