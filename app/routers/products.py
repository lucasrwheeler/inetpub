from fastapi import APIRouter
from app.database import get_connection

router = APIRouter(prefix="/products", tags=["Products"])

@router.get("/")
def get_all_products():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Products")
    results = cursor.fetchall()
    conn.close()
    return results

@router.get("/{product_id}")
def get_product(product_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Products WHERE ProductID = %s", (product_id,))
    result = cursor.fetchone()
    conn.close()
    return result
