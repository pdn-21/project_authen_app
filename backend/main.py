from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import date, datetime
import models
import time as sys_time
import os
import pytz  # <--- 1. เพิ่ม import
import requests

from database import engine, get_db, get_his_db

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# --- 2. ตั้งค่า Timezone ไทย ---
THAI_TZ = pytz.timezone('Asia/Bangkok')

def get_thai_today_str():
    return datetime.now(THAI_TZ).date().isoformat()

def to_thai_date(date_obj):
    if not date_obj:
        return None
    if isinstance(date_obj, str):
        date_obj = datetime.strptime(date_obj, "%Y-%m-%d").date()
    thai_year = date_obj.year + 543
    return f"{thai_year}{date_obj.strftime('%m%d')}"

# --- 3. แก้ไข Default Value ในทุก Endpoint ---

@app.get("/")
def read_root():
    return {
        "message": "API Service is running (UTC+7)", 
        "server_time": datetime.now(THAI_TZ).strftime("%Y-%m-%d %H:%M:%S")
    }

@app.get("/visits")
def get_visits(
    # ใช้ Default เป็นเวลาไทย
    start_date: str = None, 
    end_date: str = None,
    db: Session = Depends(get_db)
):
    # ถ้าไม่ได้ส่งค่ามา ให้ใช้วันปัจจุบันของไทย
    if start_date is None: start_date = get_thai_today_str()
    if end_date is None: end_date = get_thai_today_str()

    visits = db.query(models.VisitList).filter(
        models.VisitList.vstdate >= start_date,
        models.VisitList.vstdate <= end_date
    ).order_by(models.VisitList.vstdate.desc(), models.VisitList.vn.asc()).all()
    
    return visits

@app.post("/sync/visits")
def sync_visits(
    start_date: str = None,
    end_date: str = None,
    db: Session = Depends(get_db),
    his_db: Session = Depends(get_his_db)
):
    if start_date is None: start_date = get_thai_today_str()
    if end_date is None: end_date = get_thai_today_str()

    try:
        sql_main = text("""
            SELECT 
                (SELECT IF(vn IS NOT NULL, 'Y', 'N') FROM nhso_confirm_privilege WHERE vn = v.vn LIMIT 1) AS close_visit,
                v.vn, v.vstdate, v.hn, CONCAT(pt.pname, pt.fname, '  ', pt.lname) AS name, pt.cid,
                v.income,p.pttype, p.name AS pttypename, k.department, vp.auth_code,
                (SELECT nhso_seq FROM nhso_confirm_privilege WHERE vn = v.vn LIMIT 1) AS close_seq,
                (SELECT d.name FROM nhso_confirm_privilege x 
                 LEFT JOIN doctor d ON d.code = x.confirm_staff 
                 WHERE x.vn = v.vn LIMIT 1) AS close_staff,
                o.vsttime, o.ovstost
            FROM vn_stat as v
            LEFT JOIN patient as pt ON pt.cid = v.cid
            LEFT JOIN ovst as o ON o.vn = v.vn
            LEFT JOIN pttype as p ON p.pttype = v.pttype
            LEFT JOIN kskdepartment as k ON k.depcode = o.main_dep
            LEFT JOIN visit_pttype as vp ON vp.vn = v.vn
            WHERE v.vstdate BETWEEN :start_date AND :end_date
            ORDER BY v.vn ASC
        """)
        
        result = his_db.execute(sql_main, {"start_date": start_date, "end_date": end_date}).fetchall()
        
        count = 0
        for row in result:
            sql_money = text("""
                SELECT 
                    SUM(IF(paidst = '02', sum_price, NULL)) AS uc_money,
                    SUM(IF(paidst IN ('01', '03'), sum_price, NULL)) AS paid_money,
                    SUM(IF(paidst = '00', sum_price, NULL)) AS arrearage
                FROM opitemrece
                WHERE vn = :vn
            """)
            money_res = his_db.execute(sql_money, {"vn": row.vn}).fetchone()
            
            sql_dept = text("""
                SELECT k.department
                FROM ptdepart as p
                LEFT JOIN kskdepartment as k ON k.depcode = p.outdepcode
                WHERE p.vn = :vn
                ORDER BY p.outtime DESC
                LIMIT 1
            """)
            dept_res = his_db.execute(sql_dept, {"vn": row.vn}).scalar()

            visit = db.query(models.VisitList).filter(models.VisitList.vn == row.vn).first()
            
            if not visit:
                visit = models.VisitList(vn=row.vn)
                db.add(visit)
            
            visit.vstdate = row.vstdate
            visit.hn = row.hn
            visit.name = row.name
            visit.cid = row.cid
            visit.close_visit = row.close_visit
            visit.pttype = row.pttype
            visit.pttypename = row.pttypename
            visit.department = row.department
            visit.auth_code = row.auth_code
            visit.close_seq = row.close_seq
            visit.close_staff = row.close_staff
            visit.income = float(row.income or 0)
            visit.vsttime = str(row.vsttime) if row.vsttime else None
            visit.ovstost = row.ovstost
            
            visit.uc_money = float(money_res.uc_money or 0)
            visit.paid_money = float(money_res.paid_money or 0)
            visit.arrearage = float(money_res.arrearage or 0)
            visit.outdepcode = dept_res
            visit.date = to_thai_date(row.vstdate)
            
            count += 1
        
        db.commit()
        return {"status": "success", "synced_count": count, "message": f"Synced {start_date} to {end_date}"}

    except Exception as e:
        return HTTPException(status_code=500, detail=str(e))

@app.post("/sync/nhso")
def check_nhso_status(
    check_date: str = None,
    db: Session = Depends(get_db)
):
    if check_date is None: check_date = get_thai_today_str()

    print(f"\n--- เริ่มต้นตรวจสอบสิทธิ์ (Date: {check_date}) ---")
    
    visits = db.query(models.VisitList).filter(
        models.VisitList.vstdate == check_date,
        models.VisitList.endpoint == None,
        models.VisitList.cid != None
    ).all()
    
    total_visits = len(visits)
    print(f"🔎 พบรายการที่ต้องตรวจสอบ: {total_visits}")
    
    updated_count = 0
    errors = []
    
    token = os.getenv("NHSO_API_TOKEN")
    api_url = os.getenv("NHSO_API_URL")
    
    headers = {
        "Authorization": token,
        "Accept": "application/json"
    }

    for i, v in enumerate(visits):
        try:
            print(f"[{i+1}/{total_visits}] Check CID: {v.cid} ... ", end="", flush=True)
            sys_time.sleep(0.3) 
            
            params = {
                "personalId": v.cid,
                "serviceDate": check_date
            }
            
            response = requests.get(api_url, headers=headers, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                service_histories = data.get("serviceHistories", [])
                
                if service_histories and len(service_histories) > 0:
                    claim_code = service_histories[0].get("claimCode")
                    if claim_code:
                        v.endpoint = claim_code
                        updated_count += 1
                        print(f"✅ OK ({claim_code})")
                    else:
                        print(f"⚠️ No Code")
                else:
                    print(f"⚠️ No History")
            else:
                print(f"❌ HTTP {response.status_code}")
                
        except Exception as e:
            error_msg = f"Err: {str(e)}"
            print(f"❌ {error_msg}")
            errors.append(error_msg)
            continue

    db.commit()
    print(f"--- จบการทำงาน (Updated: {updated_count}) ---\n")
    
    return {
        "status": "success", 
        "total_checked": total_visits,
        "updated_count": updated_count,
        "errors": errors[:5]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)