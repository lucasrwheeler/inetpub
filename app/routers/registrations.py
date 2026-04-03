from fastapi import APIRouter
from app.database import get_connection

router = APIRouter(prefix="/registrations", tags=["Event Registrations"])

@router.get("/")
def get_registrations():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT EventRegistrations.*, 
               Customers.FirstName, Customers.LastName,
               ClassesEvents.EventName
        FROM EventRegistrations
        JOIN Customers ON EventRegistrations.CustomerID = Customers.CustomerID
        JOIN ClassesEvents ON EventRegistrations.EventID = ClassesEvents.EventID
    """)
    results = cursor.fetchall()
    conn.close()
    return results
