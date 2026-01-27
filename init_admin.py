"""
Initialize admin table and create default admin user
"""

import sqlite3
import bcrypt
from datetime import datetime

def init_admin_table():
    conn = sqlite3.connect('nkuna_bank.db')
    cursor = conn.cursor()
    
    try:
        # Create admin table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email VARCHAR(120) UNIQUE NOT NULL,
                password_hash VARCHAR(200) NOT NULL,
                full_name VARCHAR(100),
                is_super_admin BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        print("✅ Admin table created successfully")
        
        # Check if admin already exists
        cursor.execute("SELECT id FROM admin WHERE email = 'admin@nkunabank.co.za'")
        existing_admin = cursor.fetchone()
        
        if existing_admin:
            print("✅ Admin already exists")
        else:
            # Create default admin
            hashed_password = bcrypt.hashpw('Admin@123'.encode('utf-8'), bcrypt.gensalt())
            
            cursor.execute('''
                INSERT INTO admin (email, password_hash, full_name, is_super_admin, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                'admin@nkunabank.co.za',
                hashed_password.decode('utf-8'),
                'System Administrator',
                1,  # is_super_admin = True
                datetime.now()
            ))
            
            print("✅ Default admin created successfully")
            print("   Email: admin@nkunabank.co.za")
            print("   Password: Admin@123")
            print("   Role: Super Administrator")
        
        conn.commit()
        
        # Verify the admin was created
        cursor.execute("SELECT id, email, full_name, is_super_admin FROM admin WHERE email = 'admin@nkunabank.co.za'")
        admin = cursor.fetchone()
        
        if admin:
            print(f"\n✅ Admin verification:")
            print(f"   ID: {admin[0]}")
            print(f"   Email: {admin[1]}")
            print(f"   Full Name: {admin[2]}")
            print(f"   Is Super Admin: {bool(admin[3])}")
            return True
        else:
            print("❌ Admin creation failed")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    success = init_admin_table()
    if success:
        print("\n🎉 Admin system initialized successfully!")
        print("You can now log in as admin using:")
        print("   Email: admin@nkunabank.co.za")
        print("   Password: Admin@123")
    else:
        print("\n❌ Failed to initialize admin system")