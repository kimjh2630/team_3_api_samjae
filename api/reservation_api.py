from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import List
from datetime import datetime
import os
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL', "postgresql://postgres:admin1234@database-1.ct8wqsmwwlb2.ap-northeast-2.rds.amazonaws.com:5432/postgres")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 예약 테이블 모델
class Reservation(Base):
    __tablename__ = "reservation"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    hospital_id = Column(String(100), nullable=False)
    hospital_name = Column(String(255), nullable=False)
    hospital_address = Column(String(255), nullable=True)
    reservation_date = Column(String(20), nullable=False)  # YYYY-MM-DD
    reservation_time = Column(String(10), nullable=False)   # HH:MM
    status = Column(String(20), default="예약완료")
    created_at = Column(DateTime, default=datetime.utcnow)

# 테이블 생성
Base.metadata.create_all(bind=engine)

# DB 세션 의존성

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Pydantic 모델
class ReservationCreate(BaseModel):
    user_id: int
    hospital_id: str
    hospital_name: str
    hospital_address: str
    reservation_date: str  # YYYY-MM-DD
    reservation_time: str  # HH:MM

class ReservationOut(BaseModel):
    id: int
    user_id: int
    hospital_id: str
    hospital_name: str
    hospital_address: str
    reservation_date: str
    reservation_time: str
    status: str
    created_at: datetime
    class Config:
        orm_mode = True

# FastAPI 라우터
router = APIRouter()

@router.post("/reservation/", response_model=ReservationOut)
def create_reservation(reservation: ReservationCreate, db: Session = Depends(get_db)):
    new_reservation = Reservation(
        user_id=reservation.user_id,
        hospital_id=reservation.hospital_id,
        hospital_name=reservation.hospital_name,
        hospital_address=reservation.hospital_address,
        reservation_date=reservation.reservation_date,
        reservation_time=reservation.reservation_time,
    )
    db.add(new_reservation)
    db.commit()
    db.refresh(new_reservation)
    return new_reservation

@router.get("/reservation/{user_id}", response_model=List[ReservationOut])
def get_reservations(user_id: int, db: Session = Depends(get_db)):
    return db.query(Reservation).filter(Reservation.user_id == user_id).all()

@router.delete("/reservation/{reservation_id}")
def delete_reservation(reservation_id: int, db: Session = Depends(get_db)):
    reservation = db.query(Reservation).filter(Reservation.id == reservation_id).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="예약 정보를 찾을 수 없습니다.")
    db.delete(reservation)
    db.commit()
    return {"message": "예약이 취소되었습니다."}

@router.patch("/reservation/{reservation_id}/cancel")
def cancel_reservation(reservation_id: int, db: Session = Depends(get_db)):
    reservation = db.query(Reservation).filter(Reservation.id == reservation_id).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="예약 정보를 찾을 수 없습니다.")
    reservation.status = "취소"
    db.commit()
    db.refresh(reservation)
    return {"message": "예약이 취소되었습니다.", "status": reservation.status}

@router.patch("/reservation/{reservation_id}/update")
def update_reservation(reservation_id: int, update: dict = Body(...), db: Session = Depends(get_db)):
    reservation = db.query(Reservation).filter(Reservation.id == reservation_id).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="예약 정보를 찾을 수 없습니다.")
    # 날짜/시간만 변경 허용
    if "reservation_date" in update:
        reservation.reservation_date = update["reservation_date"]
    if "reservation_time" in update:
        reservation.reservation_time = update["reservation_time"]
    db.commit()
    db.refresh(reservation)
    return {"message": "예약이 변경되었습니다.", "reservation": {
        "id": reservation.id,
        "reservation_date": reservation.reservation_date,
        "reservation_time": reservation.reservation_time
    }} 