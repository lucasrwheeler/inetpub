from fastapi import APIRouter
from app.database import get_connection

router = APIRouter(prefix="/inventory", tags=["Inventory"])

@router.get("/")
def get_inventory():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT Inventory.*, Products.Name 
        FROM Inventory 
        JOIN Products ON Inventory.ProductID = Products.ProductID
    """)
    results = cursor.fetchall()
    conn.close()
    return results

