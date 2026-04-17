from fastapi import APIRouter, Request, HTTPException
from app.database import get_connection
import json
from pydantic import BaseModel

router = APIRouter(prefix="/sync", tags=["Sync"])


# 1. Products for WooCommerce sync (MariaDB → WordPress)
@router.get("/products")
def sync_products():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT p.ProductID,
                   p.WooProductID,
                   p.Name,
                   p.Theme,
                   p.BasePrice,
                   p.Description,
                   i.QuantityAvailable
            FROM Products p
            LEFT JOIN Inventory i ON p.ProductID = i.ProductID
            """
        )
        rows = cursor.fetchall()
        products = []
        for r in rows:
            products.append(
                {
                    "name": r["Name"],
                    "regular_price": str(r["BasePrice"]),
                    "description": r["Description"],
                    "sku": str(r["ProductID"]),
                    "stock_quantity": r["QuantityAvailable"] or 0,
                }
            )
        return products
    finally:
        cursor.close()
        conn.close()


# 2. Inventory listing
@router.get("/inventory")
def list_inventory():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT p.ProductID,
                   p.WooProductID,
                   p.Name,
                   i.QuantityAvailable,
                   i.StorageLocation,
                   i.InventoryStatus
            FROM Inventory i
            JOIN Products p ON i.ProductID = p.ProductID
            """
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


# 2b. Employees
@router.get("/employees")
def list_employees():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT FirstName, LastName, Role, HourlyRate
            FROM Employees
            ORDER BY LastName, FirstName
            """
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


# 2c. Customers
@router.get("/customers")
def list_customers():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT FirstName, LastName, Email, Address
            FROM Customers
            ORDER BY LastName, FirstName
            """
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


# 2d. Events
@router.get("/events-full")
def list_events():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT EventID, EventName, EventType, EventDate, InstructorID, ProductID, Capacity
            FROM ClassesEvents
            ORDER BY EventDate ASC
            """
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


# ⭐ 2e. Event Registration
class EventRegistrationRequest(BaseModel):
    event_id: int
    first_name: str
    last_name: str
    email: str
    seats: int = 1


@router.post("/register-event")
def register_event(payload: EventRegistrationRequest):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO Customers (FirstName, LastName, Email)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
                FirstName = VALUES(FirstName),
                LastName  = VALUES(LastName)
            """,
            (payload.first_name, payload.last_name, payload.email)
        )

        cursor.execute("SELECT CustomerID FROM Customers WHERE Email = %s", (payload.email,))
        cust = cursor.fetchone()
        if not cust:
            raise Exception("Customer lookup failed after upsert.")
        customer_id = cust["CustomerID"]

        cursor.execute(
            """
            INSERT INTO EventRegistrations (EventID, CustomerID, SeatsReserved)
            VALUES (%s, %s, %s)
            """,
            (payload.event_id, customer_id, payload.seats)
        )

        conn.commit()
        return {
            "status": "success",
            "event_id": payload.event_id,
            "customer_id": customer_id,
            "seats": payload.seats
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        cursor.close()
        conn.close()


# ⭐ 2f. Event Registrations Listing (for WP Admin)
@router.get("/event-registrations")
def list_event_registrations():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT 
                er.RegistrationID,
                ce.EventName,
                c.FirstName,
                c.LastName,
                c.Email,
                er.SeatsReserved,
                er.RegistrationDate
            FROM EventRegistrations er
            JOIN Customers c ON er.CustomerID = c.CustomerID
            JOIN ClassesEvents ce ON er.EventID = ce.EventID
            ORDER BY er.RegistrationDate DESC
            """
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


# 3. WooCommerce → MariaDB order sync
@router.post("/orders/from-woocommerce")
async def receive_order(request: Request):
    raw = await request.body()
    print(f"DEBUG: Received raw payload for Order: {raw.decode('utf-8', errors='ignore')}")
    try:
        data = json.loads(raw)
        if isinstance(data, str):
            data = json.loads(data)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    billing = data.get("billing", {}) or {}
    order_id = data.get("id")
    email = billing.get("email", "no-email@example.com")

    line_items_raw = data.get("line_items", {})
    line_items = list(line_items_raw.values()) if isinstance(line_items_raw, dict) else line_items_raw

    if not line_items:
        return {"status": "skipped", "reason": "no line_items"}

    conn = get_connection()
    conn.autocommit(False)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO Customers (FirstName, LastName, Email, Phone, Address)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                FirstName = VALUES(FirstName),
                LastName  = VALUES(LastName),
                Phone     = VALUES(Phone),
                Address   = VALUES(Address)
            """,
            (
                billing.get("first_name"),
                billing.get("last_name"),
                email,
                billing.get("phone"),
                billing.get("address_1"),
            ),
        )

        cursor.execute("SELECT CustomerID FROM Customers WHERE Email = %s", (email,))
        cust_row = cursor.fetchone()
        customer_id = cust_row["CustomerID"]

        cursor.execute(
            """
            INSERT INTO Orders (OrderID, CustomerID, TotalAmount)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
                TotalAmount = VALUES(TotalAmount)
            """,
            (order_id, customer_id, data.get("total")),
        )

        for item in line_items:
            wc_product_id = item.get("product_id")
            qty = item.get("quantity", 1)
            price = item.get("price", 0)

            cursor.execute(
                "SELECT ProductID FROM Products WHERE WooProductID = %s",
                (wc_product_id,)
            )
            prod_row = cursor.fetchone()
            if not prod_row:
                continue

            product_id = prod_row["ProductID"]

            try:
                cursor.execute(
                    """
                    INSERT INTO OrderItems (OrderID, ProductID, Quantity, PriceAtPurchase)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        Quantity        = VALUES(Quantity),
                        PriceAtPurchase = VALUES(PriceAtPurchase)
                    """,
                    (order_id, product_id, qty, price),
                )
            except Exception:
                pass

            cursor.execute(
                """
                UPDATE Inventory
                SET QuantityAvailable = GREATEST(0, QuantityAvailable - %s)
                WHERE ProductID = %s
                """,
                (qty, product_id),
            )

        conn.commit()
        return {"status": "success", "order_id": order_id}

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        cursor.close()
        conn.close()



