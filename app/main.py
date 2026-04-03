from fastapi import FastAPI
from app.routers import products, inventory, customers, orders, employees, events, registrations
from app.routers import products, inventory, customers, orders, employees, events, registrations, sync


app = FastAPI(
    title="Brikō API",
    description="Backend API for Brikō retail + events system",
    version="1.0.0"
)

app.include_router(products.router)
app.include_router(inventory.router)
app.include_router(customers.router)
app.include_router(orders.router)
app.include_router(employees.router)
app.include_router(events.router)
app.include_router(registrations.router)
app.include_router(sync.router)


@app.get("/")
def root():
    return {"message": "Brikō API is running"}

