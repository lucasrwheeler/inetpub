import pymysql

def get_connection():
    return pymysql.connect(
        host="10.0.0.20",
        user="wpuser",
        password="StrongPassword123!",
        database="briko",
        cursorclass=pymysql.cursors.DictCursor
        # No autocommit=True — let each endpoint control its own transaction
    )
