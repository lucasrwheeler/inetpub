from fastapi import APIRouter, Request
from app.database import get_connection
import requests

WC_API_URL = "http://localhost/wordpress/wp-json/wc/v3"
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
            p.ProductID,
            p.Name,
            p.Theme,
            p.PieceCount,
            p.BasePrice,
            p.ConditionType,
            p.Description,
            i.QuantityAvailable
        FROM Products p
        LEFT JOIN Inventory i ON p.ProductID = i.ProductID
    """)
    rows = cursor.fetchall()
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
            "categories": [row["Theme"]] if row["Theme"] else [],
            "attributes": [
                {"name": "Piece Count", "options": [str(row["PieceCount"])]},
                {"name": "Condition", "options": [row["ConditionType"]]},
            ]
        })
    return products


# -----------------------------
# INVENTORY SYNC (Brikō → WooCommerce)
# -----------------------------
import requests

@router.post("/inventory/to-woocommerce")
def sync_inventory_to_woocommerce():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            p.ProductID,
            p.Name,
            i.QuantityAvailable
        FROM Products p
        LEFT JOIN Inventory i ON p.ProductID = i.ProductID
    """)

    rows = cursor.fetchall()
    conn.close()

    results = []

    for row in rows:
        product_id = row["ProductID"]
        stock = row["QuantityAvailable"] or 0

        url = f"{WC_API_URL}/products/{product_id}"

        payload = {
            "stock_quantity": stock,
            "manage_stock": True
        }

        response = requests.put(
            url,
            auth=(WC_CONSUMER_KEY, WC_CONSUMER_SECRET),
            json=payload
        )

        if response.status_code in (200, 201):
            results.append({
                "product_id": product_id,
                "name": row["Name"],
                "stock_sent": stock,
                "status": "updated"
            })
        else:
            results.append({
                "product_id": product_id,
                "name": row["Name"],
                "stock_sent": stock,
                "status": "error",
                "error": response.text
            })

    return {
        "status": "completed",
        "updated": results
    }



# -----------------------------
# ORDER SYNC (WooCommerce → Brikō)
# -----------------------------
@router.post("/orders/from-woocommerce")
async def receive_order(request: Request):

    # Read raw body safely
    body = await request.body()

    # Handle empty body (WooCommerce test pings)
    if not body:
        return {"status": "ignored", "reason": "empty body"}

    # Try to parse JSON safely
    try:
        data = await request.json()
    except Exception:
        return {"status": "ignored", "reason": "invalid JSON", "raw": body.decode(errors="ignore")}

    # Validate required fields
    required = ["id", "total", "customer_id", "line_items"]
    for field in required:
        if field not in data:
            return {"status": "ignored", "reason": f"missing field: {field}", "data": data}

    order_id = data["id"]
    total = data["total"]
    customer_id = data["customer_id"]
    items = data["line_items"]

    conn = get_connection()
    cursor = conn.cursor()

    # Insert order
    cursor.execute("""
        INSERT INTO Orders (OrderID, CustomerID, TotalAmount)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE TotalAmount = VALUES(TotalAmount)
    """, (order_id, customer_id, total))

    # Insert order items + update inventory
    for item in items:
        cursor.execute("""
            INSERT INTO OrderItems (OrderID, ProductID, Quantity, PriceAtPurchase)
            VALUES (%s, %s, %s, %s)
        """, (
            order_id,
            item["product_id"],
            item["quantity"],
            item["price"]
        ))

        cursor.execute("""
            UPDATE Inventory
            SET QuantityAvailable = QuantityAvailable - %s
            WHERE ProductID = %s
        """, (item["quantity"], item["product_id"]))

    conn.commit()
    cursor.close()
    conn.close()

    return {"status": "success", "order_id": order_id}

# -----------------------------
# VIEW INVENTORY (Brikō → Browser)
# -----------------------------
@router.get("/inventory")
def list_inventory():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            i.ProductID,
            p.Name,
            i.QuantityAvailable,
            i.StorageLocation,
            i.InventoryStatus
        FROM Inventory i
        JOIN Products p ON i.ProductID = p.ProductID
        ORDER BY i.ProductID
    """)

    rows = cursor.fetchall()
    conn.close()

    inventory = []
    for row in rows:
        inventory.append({
            "product_id": row["ProductID"],
            "name": row["Name"],
            "quantity": row["QuantityAvailable"],
            "location": row["StorageLocation"],
            "status": row["InventoryStatus"]
        })

    return inventory

#___________________________________________________________________________


# -----------------------------
# VIEW CUSTOMERS (Brikō → Browser)
# -----------------------------
@router.get("/customers")
def list_customers():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            CustomerID,
            FirstName,
            LastName,
            Email,
            Phone,
            Address,
            SubscriptionStatus
        FROM Customers
        ORDER BY CustomerID
    """)

    rows = cursor.fetchall()
    conn.close()

    customers = []
    for row in rows:
        customers.append({
            "customer_id": row["CustomerID"],
            "first_name": row["FirstName"],
            "last_name": row["LastName"],
            "email": row["Email"],
            "phone": row["Phone"],
            "address": row["Address"],
            "subscription_status": row["SubscriptionStatus"]
        })

    return customers


# -----------------------------
# VIEW ORDERS (Brikō → Browser)
# -----------------------------
@router.get("/orders")
def list_orders():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            o.OrderID,
            o.CustomerID,
            c.FirstName,
            c.LastName,
            o.OrderDate,
            o.TotalAmount,
            o.OrderStatus
        FROM Orders o
        JOIN Customers c ON o.CustomerID = c.CustomerID
        ORDER BY o.OrderID
    """)

    rows = cursor.fetchall()
    conn.close()

    orders = []
    for row in rows:
        orders.append({
            "order_id": row["OrderID"],
            "customer_id": row["CustomerID"],
            "customer_name": f"{row['FirstName']} {row['LastName']}",
            "order_date": row["OrderDate"],
            "total_amount": row["TotalAmount"],
            "status": row["OrderStatus"]
        })

    return orders


#------------------------------------------------------------------------------
@router.get("/order-items")
def list_order_items():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            oi.OrderItemID,
            oi.OrderID,
            oi.ProductID,
            p.Name,
            oi.Quantity,
            oi.PriceEach
        FROM OrderItems oi
        JOIN Products p ON oi.ProductID = p.ProductID
        ORDER BY oi.OrderItemID
    """)

    rows = cursor.fetchall()
    conn.close()

    items = []
    for row in rows:
        items.append({
            "order_item_id": row["OrderItemID"],
            "order_id": row["OrderID"],
            "product_id": row["ProductID"],
            "product_name": row["Name"],
            "quantity": row["Quantity"],
            "price_each": row["PriceEach"]
        })

    return items

@router.get("/events")
def list_events():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            EventID,
            EventName,
            EventType,
            EventDate,
            InstructorID,
            ProductID,
            Capacity
        FROM ClassesEvents
        ORDER BY EventDate
    """)

    rows = cursor.fetchall()
    conn.close()

    events = []
    for row in rows:
        events.append({
            "event_id": row["EventID"],
            "name": row["EventName"],
            "type": row["EventType"],
            "date": row["EventDate"],
            "instructor_id": row["InstructorID"],
            "product_id": row["ProductID"],
            "capacity": row["Capacity"]
        })

    return events



@router.get("/registrations")
def list_registrations():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            r.RegistrationID,
            r.EventID,
            e.EventName,
            r.CustomerID,
            c.FirstName,
            c.LastName,
            r.RegistrationDate,
            r.SeatsReserved
        FROM EventRegistrations r
        JOIN ClassesEvents e ON r.EventID = e.EventID
        JOIN Customers c ON r.CustomerID = c.CustomerID
        ORDER BY r.RegistrationID
    """)

    rows = cursor.fetchall()
    conn.close()

    registrations = []
    for row in rows:
        registrations.append({
            "registration_id": row["RegistrationID"],
            "event_id": row["EventID"],
            "event_name": row["EventName"],
            "customer_id": row["CustomerID"],
            "customer_name": f"{row['FirstName']} {row['LastName']}",
            "registration_date": row["RegistrationDate"],
            "seats_reserved": row["SeatsReserved"]
        })

    return registrations


@router.get("/employees")
def list_employees():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            EmployeeID,
            FirstName,
            LastName,
            Role,
            HourlyRate,
            ClockInTime,
            ClockOutTime
        FROM Employees
        ORDER BY EmployeeID
    """)

    rows = cursor.fetchall()
    conn.close()

    employees = []
    for row in rows:
        employees.append({
            "employee_id": row["EmployeeID"],
            "first_name": row["FirstName"],
            "last_name": row["LastName"],
            "role": row["Role"],
            "hourly_rate": float(row["HourlyRate"]) if row["HourlyRate"] is not None else None,
            "clock_in": row["ClockInTime"],
            "clock_out": row["ClockOutTime"]
        })

    return employees


# -----------------------------
# CUSTOMER SYNC (WooCommerce → Brikō)
# -----------------------------
@router.post("/customers/from-woocommerce")
def sync_customers_from_woocommerce():

    # 1. Fetch customers from WooCommerce
    url = f"{WC_API_URL}/customers"
    response = requests.get(url, auth=(WC_CONSUMER_KEY, WC_CONSUMER_SECRET))

    if response.status_code not in (200, 201):
        return {
            "status": "error",
            "error": response.text
        }

    customers = response.json()

    conn = get_connection()
    cursor = conn.cursor()

    results = []

    # 2. Insert/update each customer
    for c in customers:
        customer_id = c["id"]
        first = c.get("first_name", "")
        last = c.get("last_name", "")
        email = c.get("email", "")
        phone = c.get("billing", {}).get("phone", "")
        address = c.get("billing", {}).get("address_1", "")
        subscription = "None"  # WooCommerce doesn't track this

        cursor.execute("""
            INSERT INTO Customers (CustomerID, FirstName, LastName, Email, Phone, Address, SubscriptionStatus)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                FirstName = VALUES(FirstName),
                LastName = VALUES(LastName),
                Email = VALUES(Email),
                Phone = VALUES(Phone),
                Address = VALUES(Address)
        """, (customer_id, first, last, email, phone, address, subscription))

        results.append({
            "customer_id": customer_id,
            "name": f"{first} {last}",
            "email": email,
            "status": "updated"
        })

    conn.commit()
    cursor.close()
    conn.close()

    return {
        "status": "completed",
        "updated_customers": results
    }

