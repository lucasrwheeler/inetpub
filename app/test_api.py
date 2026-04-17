import time
import mysql.connector
import requests
Import json

# -------------------------
# DATABASE CONFIG
# -------------------------
DB_CONFIG = {
    "host": "10.0.1.200",
    "user": "api_user",
    "password": "StrongPasswordAPI!",
    "database": "briko"
}

# -------------------------
# AI API CONFIG
# -------------------------
API_URL = "https://ai.cyberlab.csusb.edu/api/chat/completions"
API_KEY = "sk-6c7f04ab29c84ad992852990222bcf8a"
MODEL = "mistral:7b"   # You can change this to granite4:latest or others

# -------------------------
# DATABASE FUNCTIONS
# -------------------------
def get_new_tickets(cursor):
    cursor.execute("SELECT id, message FROM support_tickets WHERE status='new'")
    return cursor.fetchall()

def update_ticket(cursor, ticket_id, category, priority, summary):
    cursor.execute("""
        UPDATE support_tickets
        SET status='processed',
            ai_category=%s,
            ai_priority=%s,
            ai_summary=%s
        WHERE id=%s
    """, (category, priority, summary, ticket_id))

# -------------------------
# AI CALL
# -------------------------
def send_to_ai(text):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": (
                    "You are an AI support assistant. "
                    "Read the ticket and respond ONLY in valid JSON with this exact format:\n\n"
                    "{\n"
                    "  \"category\": \"...\",\n"
                    "  \"priority\": \"High | Medium | Low\",\n"
                    "  \"summary\": \"...\"\n"
                    "}\n\n"
                    f"Ticket:\n{text}"
                )
            }
        ]
    }

    response = requests.post(API_URL, json=payload, headers=headers)
    data = response.json()

    ai_text = data["choices"][0]["message"]["content"]

    try:
        parsed = json.loads(ai_text)
        # Expecting: {"category": "...", "priority": "...", "summary": "..."}
        return {
            "category": parsed.get("category", "General"),
            "priority": parsed.get("priority", "Medium"),
            "summary": parsed.get("summary", ai_text)
        }
    except json.JSONDecodeError:
        # Fallback if AI doesn't return valid JSON
        return {
            "category": "General",
            "priority": "Medium",
            "summary": ai_text
        }

# -------------------------
# MAIN AGENT LOOP
# -------------------------
def run_agent():
    db = mysql.connector.connect(**DB_CONFIG)
    cursor = db.cursor()

    while True:
        tickets = get_new_tickets(cursor)

        for ticket_id, message in tickets:
            try:
                ai = send_to_ai(message)
                update_ticket(cursor, ticket_id, ai["category"], ai["priority"], ai["summary"])
                db.commit()
            except Exception as e:
                cursor.execute("UPDATE support_tickets SET status='error' WHERE id=%s", (ticket_id,))
                db.commit()

        time.sleep(10)

if __name__ == "__main__":
    run_agent()



