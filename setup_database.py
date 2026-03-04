import mysql.connector

DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': ''  # Add your MySQL password
}

DATABASE_NAME = "basic_telegram_bot"


def create_database():
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()

    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DATABASE_NAME}")
    print(f"✅ Database '{DATABASE_NAME}' ensured.")

    cursor.close()
    conn.close()


def create_tables():
    config_with_db = DB_CONFIG.copy()
    config_with_db["database"] = DATABASE_NAME

    conn = mysql.connector.connect(**config_with_db)
    cursor = conn.cursor()

    # USERS TABLE
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id BIGINT NOT NULL UNIQUE,
            username VARCHAR(255),
            first_name VARCHAR(255),
            last_name VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("✅ Table 'users' ensured.")

    # URLS TABLE
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS urls (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            url TEXT NOT NULL,
            product_name TEXT,
            price FLOAT NOT NULL,
            vendor VARCHAR(50) NOT NULL,
            is_pending BOOLEAN DEFAULT TRUE,
            notification_count INT DEFAULT 0,
            curr_notification_count INT DEFAULT 0,
            last_notified_price FLOAT,
            is_out_of_stock BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            product_id TEXT,
            
            FOREIGN KEY (user_id) 
                REFERENCES users(user_id)
                ON DELETE CASCADE
        )
    """)
    print("✅ Table 'urls' ensured.")

    conn.commit()
    cursor.close()
    conn.close()


if __name__ == "__main__":
    print("🚀 Setting up database...")
    create_database()
    create_tables()
    print("🎉 Setup completed successfully!")