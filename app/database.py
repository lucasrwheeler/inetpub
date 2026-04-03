
import pymysql

def get_connection():
    return pymysql.connect(
        host="10.0.0.20",  # your RHEL MariaDB server
        user="wpuser",     # or your dedicated API user
        password="StrongPassword123!",
        database="briko",
        cursorclass=pymysql.cursors.DictCursor
    )
