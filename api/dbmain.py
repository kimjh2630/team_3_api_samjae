#backend/main.py
from fastapi import APIRouter, FastAPI, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import List, Optional

router = APIRouter()

#1. PostgreSQL 연결 문자열
DATABASE_URL = "postgresql://postgres:admin1234@database-1.ct8wqsmwwlb2.ap-northeast-2.rds.amazonaws.com:5432/postgres"

#2. SQLAlchemy용 엔진 생성
engine = create_engine(DATABASE_URL)

#3. 세션 생성기 정의
# - autocommit = False : 자동 커밋 비활성화
# - autoflush = False : 자동 플러시 비활성화
# - bind = Engine : 앞에서 만든 DB 엔진 사용
SessionLocal = sessionmaker(
    autocommit = False, 
    autoflush = False, 
    bind = engine
    )

#4. 베이스 클래스 생성(모든 ORM 모델의 부모 클래스)
Base = declarative_base()

#5. 사용자 테이블 모델 정의(users 테이블)
class User(Base):
    #테이블 이름 지정
    __tablename__ = "users"     

    id = Column(
        Integer, 
        primary_key = True, 
        index = True)           #기본키
    nickname = Column(
        String(50), 
        nullable = True)        #닉네임 (옵션)
    email = Column(
        String(255), 
        unique = True, 
        index = True, 
        nullable = False)       #이메일(고유, 인덱스)
    platform = Column(
        String(20), 
        nullable = False)       #로그인 플랫폼(ex. google, kakao, naver)

#6. 데이터베이스에 테이블이 없을 경우 생성
Base.metadata.create_all(bind=engine)

#7. FastAPI 앱 인스턴스 생성성
app = FastAPI()

#8. 의존성 주입 함수 : 요청마다 DB 세션을 열고 닫기
def get_db():
    db = SessionLocal()
    try:
        yield db        #의존성으로 주입되는 세션
    finally:    
        db.close()      #요청이 끝나면 세션 종료

#9. 사용자 요청을 위한 Pydantic 모델(입력 데이터 스키마)
class UserCreate(BaseModel):
    nickname: str | None = None     #닉네임은 선택 입력
    email: str                      #필수 입력
    platform: str                   #필수 입력(로그인 플랫폼)

#10. 사용자 정보를 반환할 Pydantic 모델 (출력용)
class UserOut(BaseModel):
    id: int
    nickname: str | None = None
    email: str
    platform: str

    class Config:
        orm_mode = True  # ORM 객체를 Pydantic 모델로 변환 가능하게 함

#11. 사용자 생성 또는 업데이트 API 엔드포인트
@router.post("/user/")
def create_or_update_user(user: UserCreate, db: Session = Depends(get_db)):
    #주어진 이메일로 기존 사용자 조회
    db_user = db.query(User).filter(User.email == user.email).first()

    if db_user:
        #사용자가 이미 존재하는 경우 : 닉네임과 플랫폼 정보 업데이트
        db_user.nickname = user.nickname
        db_user.platform = user.platform
        db.commit()             #변경사항 커밋
        db.refresh(db_user)     #최신 정보로 갱신
        return {
            "message": "User updated",
            "user": {
                "email": db_user.email,
                "nickname": db_user.nickname,
                "platform": db_user.platform,
            },
        }
    else:
        #사용자가 존재하지 않는 경우 : 새로 생성
        new_user = User(
            nickname=user.nickname,
            email=user.email,
            platform=user.platform,
        )
        db.add(new_user)        #세션에 추가
        db.commit()             #DB에 커밋
        db.refresh(new_user)    #삽입된 최신 값으로 갱신
        return {
            "message": "User created",
            "user": {
                "email": new_user.email,
                "nickname": new_user.nickname,
                "platform": new_user.platform,
            },
        }
    
#12. 모든 사용자 조회 (페이징 가능)
@router.get("/user/", response_model = List[UserOut])
def read_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    users = db.query(User).offset(skip).limit(limit).all()
    return users

#13. 이메일 또는 닉네임으으로 특정 사용자 조회
@router.get("/user/search", response_model = List[UserOut])
def search_users(email: Optional[str] = None, nickname: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(User)
    if email:
        query = query.filter(User.email == email)
    if nickname:
        query = query.filter(User.nickname == nickname)
    users = query.all()
    if not users:
        raise HTTPException(status_code = 404, detail = "Users not found")
    return users