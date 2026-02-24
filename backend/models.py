from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Time, Text
from database import Base

class VisitList(Base):
    __tablename__ = "visit_list"

    vn = Column(String(20), primary_key=True, index=True)
    vstdate = Column(Date, index=True)
    hn = Column(String(9))
    name = Column(String(255))
    cid = Column(String(13))

    # Pttype and Closed_visit data
    close_visit = Column(String(1))
    pttype = Column(String(10))
    pttypename = Column(String(100))
    department = Column(String(100))
    auth_code = Column(String(50), nullable=True)
    close_seq = Column(String(50), nullable=True)
    close_staff = Column(String(100), nullable=True)

    # Finance Data
    income = Column(Float, default=0.0)
    uc_money = Column(Float, default=0.0)
    paid_money = Column(Float, default=0.0)
    arrearage = Column(Float, default=0.0)

    # Other Data
    outdepcode = Column(String(100), nullable=True)
    vsttime = Column(String(10))
    ovstost = Column(String(10), nullable=True)

    # Additional Field
    date = Column(String(10), nullable=True) # Ymd + 543
    endpoint = Column(String(100), nullable=True) # ClaimCode from NHSO API