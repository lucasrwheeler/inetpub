from fastapi import APIRouter
from app.database import get_connection

router = APIRouter(prefix="/employees", tags=["Employees"])

@router.get("/")
def get_employees():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Employees")
    results = cursor.fetchall()
    conn.close()
    return results
