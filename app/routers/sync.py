from fastapi import APIRouter, Request
from app.database import get_connection
import json

router = APIRouter(prefix="/sync", tags=["Sync"])

# 1. Product Data for Sync Button (MariaDB -> WordPress)
@router.get("/products")
def sync_products():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.ProductID, p.Name, p.Theme, p.BasePrice, p.Description, i.QuantityAvailable
        FROM Products p
        LEFT JOIN Inventory i ON p.ProductID = i.ProductID
    """)
    rows = cursor.fetchall()
    conn.close()

    return [{
        "name": r["Name"],
        "regular_price": str(r["BasePrice"]),
        "description": r["Description"],
        "sku": str(r["ProductID"]),
        "stock_quantity": r["QuantityAvailable"] or 0
    } for r in rows]

# 2. Warehouse Inventory for Admin Page
@router.get("/inventory")
def list_inventory():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.Name, i.QuantityAvailable, i.StorageLocation, i.InventoryStatus
        FROM Inventory i JOIN Products p ON i.ProductID = p.ProductID
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

# 3. Order & Customer Webhook (WooCommerce -> MariaDB)
@router.post("/orders/from-woocommerce")
async def receive_order(request: Request):
    try:
        data = await request.json()
        billing = data.get("billing", {})
        order_id = data.get("id")
        email = billing.get("email", "no-email@example.com")
        
        print(f"--- START SYNC: Order {order_id} ---")

        conn = get_connection()
        cursor = conn.cursor()
        
        # Step A: Customer Sync
        cursor.execute("""
            INSERT INTO Customers (FirstName, LastName, Email, Phone, Address)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                FirstName=VALUES(FirstName), LastName=VALUES(LastName),
                Phone=VALUES(Phone), Address=VALUES(Address)
        """, (billing.get("first_name"), billing.get("last_name"), email, billing.get("phone"), billing.get("address_1")))
        
        # Step B: Order Entry
        cursor.execute("SELECT CustomerID FROM Customers WHERE Email = %s", (email,))
        cust_row = cursor.fetchone()
        if cust_row:
            customer_id = cust_row["CustomerID"] if isinstance(cust_row, dict) else cust_row[0]
            cursor.execute("""
                INSERT INTO Orders (OrderID, CustomerID, TotalAmount) 
                VALUES (%s, %s, %s) 
                ON DUPLICATE KEY UPDATE TotalAmount=VALUES(TotalAmount)
            """, (order_id, customer_id, data.get("total")))

        # Step C: Inventory Update
        line_items = data.get("line_items", [])
        for item in line_items:
            sku = item.get("sku")
            qty = item.get("quantity", 1)
            
            if sku:
                cursor.execute("""
                    UPDATE Inventory 
                    SET QuantityAvailable = QuantityAvailable - %s 
                    WHERE ProductID = %s
                """, (qty, sku))

        conn.commit()
        print(f"--- END SYNC: Order {order_id} Finished ---")
        return {"status": "success"}

    except Exception as e:
        print(f"ERROR: {e}")
        return {"status": "error"}
    finally:
        if 'conn' in locals(): conn.close()

# 4. Events Full List
@router.get("/events-full")
def get_events():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT e.EventName, e.EventDate, emp.FirstName as Instructor, e.Capacity FROM ClassesEvents e LEFT JOIN Employees emp ON e.InstructorID = emp.EmployeeID")
    rows = cursor.fetchall()
    conn.close()
    return rows

# 5. Employees List
@router.get("/employees")
def list_employees():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT FirstName, LastName, Role, HourlyRate FROM Employees")
    rows = cursor.fetchall()
    for r in rows: r["HourlyRate"] = float(r["HourlyRate"]) if r["HourlyRate"] else 0
    conn.close()
    return rows

# 6. Customers List
@router.get("/customers")
def list_customers():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT FirstName, LastName, Email, Address FROM Customers")
    rows = cursor.fetchall()
    conn.close()
    return rows


