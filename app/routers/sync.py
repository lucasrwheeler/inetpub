from fastapi import APIRouter, Request
from app.database import get_connection
import requests  # Fixed lowercase 'i'


WC_API_URL = "http://localhost/wordpress/wp-json/wc/v3" # Ensure this is your store URL
WC_CONSUMER_KEY = "ck_..."
WC_CONSUMER_SECRET = "cs_..."


router = APIRouter(prefix="/sync", tags=["Sync"])


# -----------------------------
# PRODUCT SYNC (Brikō → WooCommerce)
# -----------------------------
@router.get("/products")
def sync_products():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            p.ProductID, p.Name, p.Theme, p.PieceCount, 
            p.BasePrice, p.ConditionType, p.Description, 
            i.QuantityAvailable
        FROM Products p
        LEFT JOIN Inventory i ON p.ProductID = i.ProductID
    """)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()


    products = []
    for row in rows:
        products.append({
            "id": row["ProductID"],
            "name": row["Name"],
            "regular_price": str(row["BasePrice"]),
            "description": row["Description"],
            "sku": str(row["ProductID"]),
            "stock_quantity": row["QuantityAvailable"] or 0,
            "categories": [{"name": row["Theme"]}] if row["Theme"] else [],
            "attributes": [
                {"name": "Piece Count", "options": [str(row["PieceCount"])]},
                {"name": "Condition", "options": [row["ConditionType"]]},
            ]
        })
    return products


# -----------------------------
# ORDER SYNC (WooCommerce → Brikō)
# -----------------------------


@router.get("/orders")
def list_sync_orders():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Orders ORDER BY OrderDate DESC")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows


@router.post("/orders/from-woocommerce")
async def receive_order(request: Request):
    try:
        data = await request.json()
    except Exception:
        return {"status": "ignored", "reason": "invalid JSON"}


    order_id = data.get("id")
    total = data.get("total")
    customer_id = data.get("customer_id")
    items = data.get("line_items", [])


    if not order_id:
        return {"status": "ignored", "reason": "No order ID found"}


    conn = get_connection()
    cursor = conn.cursor()


    try:
        # 1. Insert/Update Order
        cursor.execute("""
            INSERT INTO Orders (OrderID, CustomerID, TotalAmount)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE TotalAmount = VALUES(TotalAmount)
        """, (order_id, customer_id, total))


        # 2. Process Items
        for item in items:
            if isinstance(item, dict):
                p_id = item.get("product_id")
                qty = item.get("quantity")
                price = item.get("price")


                # Use the correct column name from your DB (PriceEach or PriceAtPurchase)
                cursor.execute("""
                    INSERT INTO OrderItems (OrderID, ProductID, Quantity, PriceAtPurchase)
                    VALUES (%s, %s, %s, %s)
                """, (order_id, p_id, qty, price))


                # 3. Update Brikō Inventory
                cursor.execute("""
                    UPDATE Inventory
                    SET QuantityAvailable = QuantityAvailable - %s
                    WHERE ProductID = %s
                """, (qty, p_id))


        conn.commit()
        print(f"Successfully synced Order #{order_id}")
        return {"status": "success", "order_id": order_id}


    except Exception as e:
        conn.rollback()
        print(f"Database Error: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        cursor.close()
        conn.close()


# -----------------------------
# VIEW CUSTOMERS (Brikō → Browser)
# -----------------------------
@router.get("/customers")
def list_customers():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT CustomerID, FirstName, LastName, Email, Phone, Address, SubscriptionStatus FROM Customers")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows


# ... (Keep the rest of your VIEW methods like /inventory, /orders, etc. below)


