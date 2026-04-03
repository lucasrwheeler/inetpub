from fastapi import APIRouter
from app.database import get_connection

router = APIRouter(prefix="/customers", tags=["Customers"])

@router.get("/")
def get_customers():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Customers")
    results = cursor.fetchall()
    conn.close()
    return results
