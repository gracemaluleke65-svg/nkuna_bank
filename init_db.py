"""
Database initialization script for Nkuna Bank
Run this once to create all tables
"""

from app import app, db

def init_database():
    """Initialize the database with all tables"""
    with app.app_context():
        # Create all tables
        db.create_all()
        
        # Create default admin if not exists
        from app import create_default_admin
        create_default_admin()
        
        print("✅ Database initialized successfully!")
        print("✅ All tables created")
        print("✅ Default admin user ready")

if __name__ == "__main__":
    init_database()