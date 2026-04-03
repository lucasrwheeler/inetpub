from fastapi import APIRouter
from app.database import get_connection

router = APIRouter(prefix="/events", tags=["Events"])

@router.get("/")
def get_events():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ClassesEvents.*, 
               Employees.FirstName AS InstructorFirstName,
               Employees.LastName AS InstructorLastName
        FROM ClassesEvents
        LEFT JOIN Employees ON ClassesEvents.InstructorID = Employees.EmployeeID
    """)
    results = cursor.fetchall()
    conn.close()
    return results
