from fastapi import APIRouter
from app.database import get_connection

router = APIRouter(prefix="/orders", tags=["Orders"])

@router.get("/")
def get_orders():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT Orders.*, Customers.FirstName, Customers.LastName
        FROM Orders
        JOIN Customers ON Orders.CustomerID = Customers.CustomerID
    """)
    results = cursor.fetchall()
    conn.close()
    return results

