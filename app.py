"""
Nkuna Bank - Complete Banking Solution
Developer: Shichabo Nkuna
Render Deployment Ready
"""

from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, Blueprint
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, FloatField, DateField, SelectField, BooleanField, IntegerField, TextAreaField
from wtforms.validators import DataRequired, Length, Email, ValidationError, NumberRange, Optional, EqualTo, Regexp
from wtforms.widgets import PasswordInput
from datetime import datetime, timedelta
from sqlalchemy import func, desc, or_, and_
import random
import string
import re
import os

# Initialize Flask app
app = Flask(__name__, static_url_path='/static', static_folder='static')

# Configuration for Render
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Database configuration
database_url = os.environ.get('DATABASE_URL', 'sqlite:///nkuna_bank.db')
# Fix for Render's PostgreSQL URL (if it starts with postgres://, change to postgresql://)
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Engine options with SSL support for PostgreSQL
engine_options = {
    'pool_pre_ping': True,
    'pool_recycle': 280,
    'pool_size': 5,
    'max_overflow': 0,
    'pool_timeout': 30,
}

# If using PostgreSQL, add sslmode=require to connect_args
if database_url.startswith('postgresql://'):
    engine_options['connect_args'] = {'sslmode': 'require'}

app.config['SQLALCHEMY_ENGINE_OPTIONS'] = engine_options

# Initialize extensions
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

# ==================== CUSTOM FILTERS ====================

def time_ago(value):
    """Custom filter to show time ago"""
    if not value:
        return ''
    
    now = datetime.utcnow()
    diff = now - value
    
    if diff.days > 365:
        years = diff.days // 365
        return f'{years} year{"s" if years > 1 else ""} ago'
    if diff.days > 30:
        months = diff.days // 30
        return f'{months} month{"s" if months > 1 else ""} ago'
    if diff.days > 0:
        return f'{diff.days} day{"s" if diff.days > 1 else ""} ago'
    if diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f'{hours} hour{"s" if hours > 1 else ""} ago'
    if diff.seconds > 60:
        minutes = diff.seconds // 60
        return f'{minutes} minute{"s" if minutes > 1 else ""} ago'
    return 'Just now'

def extract_currency(text):
    """Extract currency amount from text"""
    match = re.search(r'R[\d,]+\.\d{2}', str(text))
    return match.group(0) if match else None

# Register custom filters
app.jinja_env.filters['time_ago'] = time_ago
app.jinja_env.filters['extract_currency'] = extract_currency

# ==================== MODELS ====================

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    id_number = db.Column(db.String(13), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    phone_number = db.Column(db.String(15), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"User('{self.full_name}', '{self.email}')"

class Account(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    account_number = db.Column(db.String(10), unique=True, nullable=False)
    account_type = db.Column(db.String(20), default='MAIN')
    balance = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref='accounts')
    
    def __repr__(self):
        return f"Account('{self.account_number}', '{self.account_type}', R{self.balance:.2f})"

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.String(20), unique=True, nullable=False)
    from_account = db.Column(db.String(10), nullable=False)
    to_account = db.Column(db.String(10), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    transaction_type = db.Column(db.String(20))
    description = db.Column(db.String(200))
    status = db.Column(db.String(20), default='PENDING')
    fee = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    undo_deadline = db.Column(db.DateTime)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref='transactions')
    
    def __repr__(self):
        return f"Transaction('{self.transaction_id}', '{self.status}', R{self.amount:.2f})"

class Goal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    target_amount = db.Column(db.Float, nullable=False)
    current_amount = db.Column(db.Float, default=0.0)
    target_date = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    auto_deposit = db.Column(db.Boolean, default=False)
    auto_deposit_amount = db.Column(db.Float, nullable=True)
    auto_deposit_day = db.Column(db.Integer, nullable=True)
    
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref='goals')
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    account = db.relationship('Account', backref='goal', uselist=False)
    
    def __repr__(self):
        return f"Goal('{self.name}', R{self.current_amount:.2f}/R{self.target_amount:.2f})"

class BillPayment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref='bill_payments')
    bill_type = db.Column(db.String(50))
    amount = db.Column(db.Float, nullable=False)
    reference_number = db.Column(db.String(50))
    meter_number = db.Column(db.String(50))
    status = db.Column(db.String(20), default='PENDING')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"BillPayment('{self.bill_type}', R{self.amount:.2f})"

class Admin(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    full_name = db.Column(db.String(100))
    is_super_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"Admin('{self.email}')"

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref='notifications')
    title = db.Column(db.String(100), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    notification_type = db.Column(db.String(20))
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)
    
    def __repr__(self):
        return f"Notification('{self.title}', read={self.is_read})"

class BankRevenue(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    revenue_type = db.Column(db.String(50))
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(200))
    reference_id = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"BankRevenue('{self.revenue_type}', R{self.amount:.2f})"

# ==================== UTILITY FUNCTIONS ====================

def validate_south_african_id(id_number):
    """Simplified ID validation - just check 13 digits"""
    if len(id_number) != 13 or not id_number.isdigit():
        return False, "ID must be exactly 13 digits and contain only numbers"
    return True, "ID is valid"

def extract_dob_from_id(id_number):
    """Extracts date of birth from SA ID number - simplified"""
    if len(id_number) != 13 or not id_number.isdigit():
        return None
    
    year_str = id_number[0:2]
    month_str = id_number[2:4]
    day_str = id_number[4:6]
    
    try:
        year = int(year_str)
        month = int(month_str)
        day = int(day_str)
    except ValueError:
        return None
    
    current_year_short = datetime.now().year % 100
    if year <= current_year_short:
        full_year = 2000 + year
    else:
        full_year = 1900 + year
    
    try:
        dob = datetime(full_year, month, day)
        return dob
    except ValueError:
        return None

def generate_account_number():
    """Generates a unique 10-digit account number"""
    while True:
        first_digit = random.choice(string.digits[1:])
        rest_digits = ''.join(random.choices(string.digits, k=9))
        account_number = first_digit + rest_digits
        
        existing = Account.query.filter_by(account_number=account_number).first()
        if not existing:
            return account_number

def generate_transaction_id():
    """Generates unique transaction ID"""
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    random_suffix = ''.join(random.choices(string.digits, k=4))
    return f"TRX{timestamp}{random_suffix}"

def calculate_transaction_fee(amount):
    """Calculates transaction fee (1% of amount, min R2, max R100)"""
    fee = amount * 0.01
    if fee < 2:
        return 2.00
    elif fee > 100:
        return 100.00
    return round(fee, 2)

def calculate_age(birth_date):
    """Calculate age from birth date"""
    today = datetime.now().date()
    age = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        age -= 1
    return age

def validate_minimum_age(birth_date, min_age=18):
    """Check if user meets minimum age requirement"""
    age = calculate_age(birth_date)
    return age >= min_age, age

def format_currency(amount):
    """Format amount as South African Rand"""
    if amount is None:
        return "R0.00"
    return f"R{amount:,.2f}"

def get_main_account(user_id):
    """Get user's main account"""
    return Account.query.filter_by(user_id=user_id, account_type='MAIN').first()

def can_undo_transaction(transaction):
    """Check if transaction can be undone"""
    if transaction.status != 'COMPLETED':
        return False
    if not transaction.undo_deadline:
        return False
    return datetime.utcnow() < transaction.undo_deadline

def get_days_remaining(target_date):
    """Calculate days remaining until target date"""
    if not target_date:
        return 0
    
    today = datetime.now().date()
    if target_date < today:
        return 0
    return (target_date - today).days

def validate_phone_number(phone):
    """Validate South African phone number"""
    phone_clean = re.sub(r'\D', '', phone)
    
    if len(phone_clean) == 10 and phone_clean.startswith('0'):
        return True, phone_clean
    elif len(phone_clean) == 11 and phone_clean.startswith('27'):
        return True, '0' + phone_clean[2:]
    else:
        return False, "Invalid phone number format. Use 0812345678 or +27812345678"

def create_notification(user_id, title, message, notification_type="INFO", expires_in_days=30):
    """Create a notification for a user"""
    expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type,
        expires_at=expires_at
    )
    db.session.add(notification)
    return notification

def get_unread_notifications(user_id, limit=10):
    """Get unread notifications for a user"""
    return Notification.query.filter_by(
        user_id=user_id,
        is_read=False
    ).filter(
        Notification.expires_at > datetime.utcnow()
    ).order_by(
        Notification.created_at.desc()
    ).limit(limit).all()

def calculate_goal_progress(goal):
    """Calculate goal progress percentage"""
    if goal.target_amount > 0:
        return (goal.current_amount / goal.target_amount) * 100
    return 0

def validate_transfer_limit(user_id, amount):
    """Validate daily transfer limit (R50,000)"""
    today = datetime.now().date()
    today_transfers = Transaction.query.filter(
        Transaction.user_id == user_id,
        Transaction.transaction_type == 'TRANSFER',
        func.date(Transaction.created_at) == today
    ).all()
    
    total_today = sum(t.amount for t in today_transfers)
    return (total_today + amount) <= 50000

def record_bank_revenue(revenue_type, amount, description, reference_id=None):
    """Record bank revenue"""
    revenue = BankRevenue(
        revenue_type=revenue_type,
        amount=amount,
        description=description,
        reference_id=reference_id
    )
    db.session.add(revenue)
    return revenue

def mark_notification_as_read(notification_id):
    """Mark a notification as read"""
    notification = Notification.query.get(notification_id)
    if notification:
        notification.is_read = True
        db.session.commit()
        return True
    return False

def mark_all_notifications_as_read(user_id):
    """Mark all notifications as read for a user"""
    Notification.query.filter_by(user_id=user_id, is_read=False).update({'is_read': True})
    db.session.commit()

def check_low_balance_alert(user_id):
    """Check for low balance and create alert if needed"""
    main_account = get_main_account(user_id)
    if main_account and main_account.balance < 100:
        create_notification(
            user_id=user_id,
            title='Low Balance Alert',
            message=f'Your account balance is low ({format_currency(main_account.balance)}). Please deposit funds to avoid service interruptions.',
            notification_type='WARNING'
        )

def calculate_bank_health():
    """Calculate bank health metrics"""
    total_users = User.query.count()
    total_balance = db.session.query(func.sum(Account.balance)).scalar() or 0
    total_transactions = Transaction.query.count()
    total_revenue = db.session.query(func.sum(BankRevenue.amount)).scalar() or 0
    
    return {
        'total_users': total_users,
        'total_balance': total_balance,
        'total_transactions': total_transactions,
        'total_revenue': total_revenue
    }

def apply_monthly_charges():
    """Apply monthly account fees"""
    accounts = Account.query.filter_by(account_type='MAIN').all()
    processed = 0
    
    for account in accounts:
        if account.balance >= 50:  # Only charge if balance is sufficient
            fee = 50.0  # Monthly account fee
            account.balance -= fee
            
            transaction = Transaction(
                transaction_id=generate_transaction_id(),
                from_account=account.account_number,
                to_account='BANK_FEES',
                amount=fee,
                transaction_type='MONTHLY_FEE',
                description='Monthly account maintenance fee',
                status='COMPLETED',
                user_id=account.user_id
            )
            
            record_bank_revenue(
                revenue_type='MONTHLY_FEE',
                amount=fee,
                description=f'Monthly fee for account {account.account_number}',
                reference_id=transaction.transaction_id
            )
            
            db.session.add(transaction)
            processed += 1
    
    db.session.commit()
    return processed

# ==================== FORMS ====================

class RegistrationForm(FlaskForm):
    full_name = StringField('Full Name', validators=[
        DataRequired(message="Full name is required"),
        Length(min=2, max=100, message="Name must be between 2 and 100 characters")
    ], render_kw={"placeholder": "Enter your full name"})
    
    id_number = StringField('South African ID Number', validators=[
        DataRequired(message="ID number is required"),
        Length(min=13, max=13, message="ID number must be exactly 13 digits"),
        Regexp(r'^\d+$', message="ID number must contain only numbers")
    ], render_kw={"placeholder": "Enter 13-digit SA ID"})
    
    email = StringField('Email Address', validators=[
        DataRequired(message="Email is required"),
        Email(message="Enter a valid email address"),
        Length(max=120)
    ], render_kw={"placeholder": "your.email@example.com"})
    
    phone_number = StringField('Phone Number', validators=[
        DataRequired(message="Phone number is required"),
        Length(min=10, max=15)
    ], render_kw={"placeholder": "0812345678 or +27812345678"})
    
    password = PasswordField('Password', validators=[
        DataRequired(message="Password is required"),
        Length(min=6, message="Password must be at least 6 characters"),
        EqualTo('confirm_password', message="Passwords must match")
    ], widget=PasswordInput(hide_value=False))
    
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(message="Please confirm your password")
    ], widget=PasswordInput(hide_value=False))
    
    submit = SubmitField('Register Account')
    
    def validate_id_number(self, id_number):
        is_valid, message = validate_south_african_id(id_number.data)
        if not is_valid:
            raise ValidationError(message)
        
        user = User.query.filter_by(id_number=id_number.data).first()
        if user:
            raise ValidationError('This ID number is already registered.')
    
    def validate_email(self, email):
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, email.data):
            raise ValidationError('Please enter a valid email address.')
        
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('This email is already registered.')
    
    def validate_phone_number(self, phone_number):
        is_valid, message = validate_phone_number(phone_number.data)
        if not is_valid:
            raise ValidationError(message)

class LoginForm(FlaskForm):
    email = StringField('Email Address', validators=[
        DataRequired(message="Email is required"),
        Email(message="Enter a valid email address")
    ], render_kw={"placeholder": "your.email@example.com"})
    
    password = PasswordField('Password', validators=[
        DataRequired(message="Password is required")
    ], widget=PasswordInput(hide_value=False))
    
    remember = BooleanField('Remember Me')
    submit = SubmitField('Login')

class TransferForm(FlaskForm):
    to_account = StringField('Recipient Account Number', validators=[
        DataRequired(message="Account number is required"),
        Length(min=10, max=10, message="Account number must be 10 digits"),
        Regexp(r'^\d+$', message="Account number must contain only numbers")
    ], render_kw={"placeholder": "Enter 10-digit account number"})
    
    amount = FloatField('Amount', validators=[
        DataRequired(message="Amount is required"),
        NumberRange(min=0.01, max=1000000, message="Amount must be between R0.01 and R1,000,000")
    ], render_kw={"placeholder": "0.00", "step": "0.01"})
    
    description = StringField('Description (Optional)', validators=[
        Optional(),
        Length(max=100, message="Description cannot exceed 100 characters")
    ], render_kw={"placeholder": "e.g., Rent payment, Birthday gift"})
    
    submit = SubmitField('Transfer Money')

class DepositForm(FlaskForm):
    amount = FloatField('Deposit Amount', validators=[
        DataRequired(message="Amount is required"),
        NumberRange(min=10, max=50000, message="Deposit must be between R10 and R50,000")
    ], render_kw={"placeholder": "0.00", "step": "0.01"})
    
    description = StringField('Deposit Reference (Optional)', validators=[
        Optional(),
        Length(max=100)
    ], render_kw={"placeholder": "e.g., Salary, Cash deposit"})
    
    submit = SubmitField('Make Deposit')

class GoalForm(FlaskForm):
    name = StringField('Goal Name', validators=[
        DataRequired(message="Goal name is required"),
        Length(min=2, max=100, message="Goal name must be between 2 and 100 characters")
    ], render_kw={"placeholder": "e.g., New Car, Vacation, House Deposit"})
    
    target_amount = FloatField('Target Amount', validators=[
        DataRequired(message="Target amount is required"),
        NumberRange(min=100, max=1000000, message="Target must be between R100 and R1,000,000")
    ], render_kw={"placeholder": "0.00", "step": "0.01"})
    
    target_date = DateField('Target Date', validators=[
        DataRequired(message="Target date is required")
    ], render_kw={"placeholder": "YYYY-MM-DD"})
    
    auto_deposit = BooleanField('Enable Auto-deposit')
    
    auto_deposit_amount = FloatField('Auto-deposit Amount', validators=[
        Optional(),
        NumberRange(min=10, max=10000, message="Auto-deposit must be between R10 and R10,000")
    ], render_kw={"placeholder": "0.00", "step": "0.01"})
    
    auto_deposit_day = IntegerField('Day of Month', validators=[
        Optional(),
        NumberRange(min=1, max=28, message="Day must be between 1 and 28")
    ], render_kw={"placeholder": "1-28"})
    
    submit = SubmitField('Create Goal')
    
    def validate_target_date(self, target_date):
        if target_date.data < datetime.now().date():
            raise ValidationError("Target date cannot be in the past")

class BillPaymentForm(FlaskForm):
    bill_type = SelectField('Bill Type', choices=[
        ('', 'Select Bill Type'),
        ('ELECTRICITY', 'Electricity'),
        ('WATER', 'Water'),
        ('AIR_TIME', 'Airtime'),
        ('DATA', 'Data Bundle')
    ], validators=[DataRequired(message="Please select a bill type")])
    
    amount = FloatField('Amount', validators=[
        DataRequired(message="Amount is required"),
        NumberRange(min=1, max=5000, message="Amount must be between R1 and R5,000")
    ], render_kw={"placeholder": "0.00", "step": "0.01"})
    
    reference_number = StringField('Reference/Meter Number', validators=[
        DataRequired(message="Reference number is required"),
        Length(max=50, message="Reference cannot exceed 50 characters")
    ], render_kw={"placeholder": "Enter meter or reference number"})
    
    phone_number = StringField('Phone Number (for airtime/data)', validators=[
        Optional(),
        Length(min=10, max=15)
    ], render_kw={"placeholder": "For airtime/data purchases only"})
    
    submit = SubmitField('Pay Bill')

class AdminLoginForm(FlaskForm):
    email = StringField('Email Address', validators=[
        DataRequired(message="Email is required"),
        Email(message="Enter a valid email address")
    ], render_kw={"placeholder": "admin@example.com"})
    
    password = PasswordField('Password', validators=[
        DataRequired(message="Password is required")
    ], widget=PasswordInput(hide_value=False))
    
    remember = BooleanField('Remember Me')
    submit = SubmitField('Admin Login')

class UserSearchForm(FlaskForm):
    search = StringField('Search Users', render_kw={"placeholder": "Name, email, ID or phone"})
    submit = SubmitField('Search')

class TransactionSearchForm(FlaskForm):
    search = StringField('Search Transactions', render_kw={"placeholder": "Transaction ID, description..."})
    transaction_type = SelectField('Type', choices=[
        ('', 'All Types'),
        ('DEPOSIT', 'Deposit'),
        ('TRANSFER', 'Transfer'),
        ('BILL_PAYMENT', 'Bill Payment')
    ])
    start_date = DateField('Start Date', validators=[Optional()])
    end_date = DateField('End Date', validators=[Optional()])
    submit = SubmitField('Search')

class NotificationSettingsForm(FlaskForm):
    email_notifications = BooleanField('Email Notifications')
    sms_notifications = BooleanField('SMS Notifications')
    submit = SubmitField('Save Settings')

# ==================== FLASK-LOGIN USER LOADER ====================

@login_manager.user_loader
def load_user(user_id):
    """Load user by ID - handles both regular users and admins"""
    user = User.query.get(int(user_id))
    if user:
        return user
    admin = Admin.query.get(int(user_id))
    if admin:
        return admin
    return None

# ==================== USER ROUTES ====================

@app.route('/')
def index():
    """Home page"""
    if current_user.is_authenticated:
        if hasattr(current_user, 'is_super_admin') and current_user.is_super_admin:
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    form = RegistrationForm()
    
    if form.validate_on_submit():
        dob = extract_dob_from_id(form.id_number.data)
        
        if not dob:
            flash('Invalid date of birth in ID', 'danger')
            return render_template('register.html', form=form)
        
        is_valid_age, age = validate_minimum_age(dob)
        if not is_valid_age:
            flash(f'You must be at least 18 years old. You are {age} years old.', 'danger')
            return render_template('register.html', form=form)
        
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        
        user = User(
            full_name=form.full_name.data,
            id_number=form.id_number.data,
            email=form.email.data,
            password_hash=hashed_password,
            phone_number=form.phone_number.data,
            date_of_birth=dob,
            is_active=True
        )
        
        db.session.add(user)
        db.session.commit()
        
        account_number = generate_account_number()
        account = Account(
            account_number=account_number,
            account_type='MAIN',
            balance=0.0,
            user_id=user.id
        )
        
        db.session.add(account)
        db.session.commit()
        
        create_notification(
            user_id=user.id,
            title='Welcome to Nkuna Bank!',
            message=f'Welcome {user.full_name}! Your account has been created successfully. Your account number is {account_number}. Please save it securely.',
            notification_type='SUCCESS'
        )
        
        flash(f'Account created successfully! Your account number is: {account_number}. Please save it.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    form = LoginForm()
    
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        
        if user and bcrypt.check_password_hash(user.password_hash, form.password.data):
            if not user.is_active:
                flash('Your account has been deactivated. Please contact support.', 'danger')
                return render_template('login.html', form=form)
            
            login_user(user, remember=form.remember.data)
            
            create_notification(
                user_id=user.id,
                title='Login Successful',
                message='You have successfully logged into your Nkuna Bank account.',
                notification_type='INFO'
            )
            
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('Login failed. Please check your email and password.', 'danger')
    
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    """User logout"""
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    """User dashboard"""
    if hasattr(current_user, 'is_super_admin') and current_user.is_super_admin:
        return redirect(url_for('admin_dashboard'))
    
    main_account = get_main_account(current_user.id)
    
    recent_transactions = Transaction.query.filter_by(user_id=current_user.id)\
        .order_by(Transaction.created_at.desc())\
        .limit(10)\
        .all()
    
    goals = Goal.query.filter_by(
        user_id=current_user.id,
        is_active=True
    ).order_by(Goal.target_date.asc()).all()
    
    for goal in goals:
        goal.progress = calculate_goal_progress(goal)
        goal.days_remaining = get_days_remaining(goal.target_date)
    
    unread_notifications = get_unread_notifications(current_user.id, limit=5)
    
    recent_bills = BillPayment.query.filter_by(
        user_id=current_user.id
    ).order_by(BillPayment.created_at.desc())\
     .limit(5).all()
    
    total_balance = sum(account.balance for account in current_user.accounts)
    
    check_low_balance_alert(current_user.id)
    
    return render_template('dashboard.html',
                         user=current_user,
                         main_account=main_account,
                         transactions=recent_transactions,
                         goals=goals,
                         notifications=unread_notifications,
                         recent_bills=recent_bills,
                         total_balance=total_balance,
                         format_currency=format_currency,
                         get_days_remaining=get_days_remaining,
                         current_datetime=datetime.utcnow(),
                         can_undo_transaction=can_undo_transaction)

@app.route('/deposit', methods=['GET', 'POST'])
@login_required
def deposit():
    """Deposit money"""
    form = DepositForm()
    
    recent_deposits = Transaction.query.filter_by(
        user_id=current_user.id,
        transaction_type='DEPOSIT'
    ).order_by(
        Transaction.created_at.desc()
    ).limit(5).all()
    
    if form.validate_on_submit():
        amount = form.amount.data
        main_account = get_main_account(current_user.id)
        
        if main_account:
            transaction_id = generate_transaction_id()
            transaction = Transaction(
                transaction_id=transaction_id,
                from_account='DEPOSIT',
                to_account=main_account.account_number,
                amount=amount,
                transaction_type='DEPOSIT',
                description=form.description.data or 'Cash deposit',
                status='COMPLETED',
                user_id=current_user.id
            )
            
            main_account.balance += amount
            
            db.session.add(transaction)
            db.session.commit()
            
            create_notification(
                user_id=current_user.id,
                title='Deposit Successful',
                message=f'You have successfully deposited {format_currency(amount)} into your account.',
                notification_type='SUCCESS'
            )
            
            flash(f'Successfully deposited {format_currency(amount)}', 'success')
            return redirect(url_for('dashboard'))
    
    return render_template('deposit.html', 
                         form=form, 
                         main_account=get_main_account(current_user.id),
                         recent_deposits=recent_deposits,
                         format_currency=format_currency)

@app.route('/transfer', methods=['GET', 'POST'])
@login_required
def transfer():
    """Transfer money"""
    form = TransferForm()
    main_account = get_main_account(current_user.id)
    
    recent_transfers = Transaction.query.filter_by(
        user_id=current_user.id,
        transaction_type='TRANSFER'
    ).order_by(
        Transaction.created_at.desc()
    ).limit(5).all()
    
    if form.validate_on_submit():
        to_account_number = re.sub(r'\D', '', form.to_account.data.strip())
        amount = form.amount.data
        description = form.description.data
        
        recipient_account = Account.query.filter_by(account_number=to_account_number).first()
        
        if not recipient_account:
            flash('Recipient account does not exist.', 'danger')
            return render_template('transfer.html', form=form, main_account=main_account, recent_transfers=recent_transfers, format_currency=format_currency)
        
        if to_account_number == main_account.account_number:
            flash('Cannot transfer to your own account.', 'danger')
            return render_template('transfer.html', form=form, main_account=main_account, recent_transfers=recent_transfers, format_currency=format_currency)
        
        if not validate_transfer_limit(current_user.id, amount):
            flash('Daily transfer limit of R50,000 exceeded.', 'danger')
            return render_template('transfer.html', form=form, main_account=main_account, recent_transfers=recent_transfers, format_currency=format_currency)
        
        fee = calculate_transaction_fee(amount)
        total_deduction = amount + fee
        
        if main_account.balance < total_deduction:
            flash(f'Insufficient balance. Need {format_currency(total_deduction)}, have {format_currency(main_account.balance)}', 'danger')
            return render_template('transfer.html', form=form, main_account=main_account, recent_transfers=recent_transfers, format_currency=format_currency)
        
        transaction_id = generate_transaction_id()
        
        transaction = Transaction(
            transaction_id=transaction_id,
            from_account=main_account.account_number,
            to_account=to_account_number,
            amount=amount,
            transaction_type='TRANSFER',
            description=description,
            status='COMPLETED',
            fee=fee,
            undo_deadline=datetime.utcnow() + timedelta(minutes=15),
            user_id=current_user.id
        )
        
        main_account.balance -= total_deduction
        recipient_account.balance += amount
        
        record_bank_revenue(
            revenue_type='TRANSACTION_FEE',
            amount=fee,
            description=f'Transfer fee for transaction {transaction_id}',
            reference_id=transaction_id
        )
        
        db.session.add(transaction)
        db.session.commit()
        
        create_notification(
            user_id=current_user.id,
            title='Transfer Sent',
            message=f'You have successfully transferred {format_currency(amount)} to account {to_account_number}. Transaction ID: {transaction_id}',
            notification_type='SUCCESS'
        )
        
        create_notification(
            user_id=recipient_account.user_id,
            title='Money Received',
            message=f'You have received {format_currency(amount)} from account {main_account.account_number}.',
            notification_type='INFO'
        )
        
        flash(f'Transfer of {format_currency(amount)} successful! Transaction ID: {transaction_id}', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('transfer.html', form=form, main_account=main_account, recent_transfers=recent_transfers, format_currency=format_currency)

@app.route('/undo_transaction/<transaction_id>', methods=['POST'])
@login_required
def undo_transaction(transaction_id):
    """Undo a transaction"""
    transaction = Transaction.query.filter_by(
        transaction_id=transaction_id,
        user_id=current_user.id
    ).first()
    
    if not transaction:
        flash('Transaction not found.', 'danger')
        return redirect(url_for('history'))
    
    if not can_undo_transaction(transaction):
        flash('This transaction cannot be undone. Time limit expired.', 'danger')
        return redirect(url_for('history'))
    
    recipient_account = Account.query.filter_by(account_number=transaction.to_account).first()
    if not recipient_account or recipient_account.balance < transaction.amount:
        flash('Cannot undo transaction. Recipient has insufficient balance.', 'danger')
        return redirect(url_for('history'))
    
    sender_account = Account.query.filter_by(account_number=transaction.from_account).first()
    
    if not sender_account:
        flash('Sender account not found.', 'danger')
        return redirect(url_for('history'))
    
    sender_account.balance += transaction.amount + transaction.fee
    recipient_account.balance -= transaction.amount
    
    transaction.status = 'UNDONE'
    
    create_notification(
        user_id=current_user.id,
        title='Transaction Undone',
        message=f'Your transfer of {format_currency(transaction.amount)} has been successfully undone.',
        notification_type='INFO'
    )
    
    create_notification(
        user_id=recipient_account.user_id,
        title='Transaction Reversed',
        message=f'A transaction of {format_currency(transaction.amount)} from account {sender_account.account_number} has been reversed.',
        notification_type='WARNING'
    )
    
    db.session.commit()
    
    flash(f'Transaction successfully undone. {format_currency(transaction.amount)} returned to your account.', 'success')
    return redirect(url_for('history'))

@app.route('/history')
@login_required
def history():
    """Transaction history"""
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    transaction_type = request.args.get('type', '')
    search = request.args.get('search', '')
    
    query = Transaction.query.filter_by(user_id=current_user.id)
    
    if transaction_type:
        query = query.filter_by(transaction_type=transaction_type)
    
    if search:
        query = query.filter(or_(
            Transaction.transaction_id.ilike(f'%{search}%'),
            Transaction.description.ilike(f'%{search}%'),
            Transaction.from_account.ilike(f'%{search}%'),
            Transaction.to_account.ilike(f'%{search}%')
        ))
    
    transactions = query.order_by(Transaction.created_at.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)
    
    total_deposits = sum(t.amount for t in transactions.items if t.transaction_type == 'DEPOSIT')
    total_transfers = sum(t.amount for t in transactions.items if t.transaction_type == 'TRANSFER')
    total_fees = sum(t.fee for t in transactions.items if t.fee)
    
    return render_template('history.html',
                         transactions=transactions,
                         can_undo_transaction=can_undo_transaction,
                         format_currency=format_currency,
                         total_deposits=total_deposits,
                         total_transfers=total_transfers,
                         total_fees=total_fees,
                         current_filter=transaction_type,
                         current_search=search)

@app.route('/goals', methods=['GET', 'POST'])
@login_required
def goals():
    """Goal savings management"""
    form = GoalForm()
    main_account = get_main_account(current_user.id)
    
    if form.validate_on_submit():
        goal_account_number = generate_account_number()
        goal_account = Account(
            account_number=goal_account_number,
            account_type='GOAL',
            balance=0.0,
            user_id=current_user.id
        )
        
        db.session.add(goal_account)
        db.session.flush()
        
        goal = Goal(
            name=form.name.data,
            target_amount=form.target_amount.data,
            target_date=form.target_date.data,
            auto_deposit=form.auto_deposit.data,
            auto_deposit_amount=form.auto_deposit_amount.data if form.auto_deposit.data else None,
            auto_deposit_day=form.auto_deposit_day.data if form.auto_deposit.data else None,
            user_id=current_user.id,
            account_id=goal_account.id
        )
        
        db.session.add(goal)
        db.session.commit()
        
        create_notification(
            user_id=current_user.id,
            title='Goal Created',
            message=f'Your goal "{form.name.data}" has been created successfully!',
            notification_type='SUCCESS'
        )
        
        flash(f'Goal "{form.name.data}" created successfully!', 'success')
        return redirect(url_for('goals'))
    
    user_goals = Goal.query.filter_by(
        user_id=current_user.id,
        is_active=True
    ).order_by(Goal.target_date.asc()).all()
    
    total_saved = 0
    completed_goals = 0
    total_days_remaining = 0
    total_completion = 0
    
    for goal in user_goals:
        goal.progress = calculate_goal_progress(goal)
        goal.days_remaining = get_days_remaining(goal.target_date)
        goal.formatted_amount = format_currency(goal.current_amount)
        goal.formatted_target = format_currency(goal.target_amount)
        total_saved += goal.current_amount
        
        if goal.current_amount >= goal.target_amount:
            completed_goals += 1
        
        total_days_remaining += goal.days_remaining
        total_completion += goal.progress
    
    avg_days_remaining = total_days_remaining / len(user_goals) if user_goals else 0
    avg_completion = total_completion / len(user_goals) if user_goals else 0
    
    return render_template('goals.html',
                         form=form,
                         goals=user_goals,
                         main_account=main_account,
                         format_currency=format_currency,
                         total_saved=total_saved,
                         completed_goals=completed_goals,
                         avg_days_remaining=avg_days_remaining,
                         avg_completion=avg_completion)

@app.route('/goals/<int:goal_id>/deposit', methods=['POST'])
@login_required
def deposit_to_goal(goal_id):
    """Deposit money to a goal"""
    goal = Goal.query.get_or_404(goal_id)
    
    if goal.user_id != current_user.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('goals'))
    
    try:
        amount = float(request.form.get('amount', 0))
    except ValueError:
        flash('Invalid amount.', 'danger')
        return redirect(url_for('goals'))
    
    if amount <= 0:
        flash('Invalid amount.', 'danger')
        return redirect(url_for('goals'))
    
    main_account = get_main_account(current_user.id)
    goal_account = Account.query.get(goal.account_id)
    
    if not main_account or not goal_account:
        flash('Account not found.', 'danger')
        return redirect(url_for('goals'))
    
    if main_account.balance < amount:
        flash('Insufficient balance in main account.', 'danger')
        return redirect(url_for('goals'))
    
    main_account.balance -= amount
    goal_account.balance += amount
    goal.current_amount += amount
    
    transaction_id = generate_transaction_id()
    transaction = Transaction(
        transaction_id=transaction_id,
        from_account=main_account.account_number,
        to_account=goal_account.account_number,
        amount=amount,
        transaction_type='GOAL_DEPOSIT',
        description=f'Deposit to goal: {goal.name}',
        status='COMPLETED',
        user_id=current_user.id
    )
    
    db.session.add(transaction)
    
    if goal.current_amount >= goal.target_amount:
        create_notification(
            user_id=current_user.id,
            title='Goal Achieved! 🎉',
            message=f'Congratulations! You have achieved your goal "{goal.name}"!',
            notification_type='SUCCESS'
        )
    
    db.session.commit()
    
    flash(f'Successfully deposited {format_currency(amount)} to "{goal.name}"', 'success')
    return redirect(url_for('goals'))

@app.route('/goals/<int:goal_id>/withdraw', methods=['POST'])
@login_required
def withdraw_from_goal(goal_id):
    """Withdraw money from a goal"""
    goal = Goal.query.get_or_404(goal_id)
    
    if goal.user_id != current_user.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('goals'))
    
    try:
        amount = float(request.form.get('amount', 0))
    except ValueError:
        flash('Invalid amount.', 'danger')
        return redirect(url_for('goals'))
    
    if amount <= 0:
        flash('Invalid amount.', 'danger')
        return redirect(url_for('goals'))
    
    main_account = get_main_account(current_user.id)
    goal_account = Account.query.get(goal.account_id)
    
    if not main_account or not goal_account:
        flash('Account not found.', 'danger')
        return redirect(url_for('goals'))
    
    if goal_account.balance < amount:
        flash('Insufficient balance in goal account.', 'danger')
        return redirect(url_for('goals'))
    
    goal_account.balance -= amount
    main_account.balance += amount
    goal.current_amount -= amount
    
    transaction_id = generate_transaction_id()
    transaction = Transaction(
        transaction_id=transaction_id,
        from_account=goal_account.account_number,
        to_account=main_account.account_number,
        amount=amount,
        transaction_type='GOAL_WITHDRAWAL',
        description=f'Withdrawal from goal: {goal.name}',
        status='COMPLETED',
        user_id=current_user.id
    )
    
    db.session.add(transaction)
    db.session.commit()
    
    flash(f'Successfully withdrew {format_currency(amount)} from "{goal.name}"', 'success')
    return redirect(url_for('goals'))

@app.route('/goals/<int:goal_id>/delete', methods=['POST'])
@login_required
def delete_goal(goal_id):
    """Delete a goal"""
    goal = Goal.query.get_or_404(goal_id)
    
    if goal.user_id != current_user.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('goals'))
    
    if goal.current_amount > 0:
        main_account = get_main_account(current_user.id)
        goal_account = Account.query.get(goal.account_id)
        
        if main_account and goal_account:
            goal_account.balance -= goal.current_amount
            main_account.balance += goal.current_amount
            
            transaction_id = generate_transaction_id()
            transaction = Transaction(
                transaction_id=transaction_id,
                from_account=goal_account.account_number,
                to_account=main_account.account_number,
                amount=goal.current_amount,
                transaction_type='GOAL_DELETION',
                description=f'Goal deletion: {goal.name}',
                status='COMPLETED',
                user_id=current_user.id
            )
            db.session.add(transaction)
    
    goal.is_active = False
    
    create_notification(
        user_id=current_user.id,
        title='Goal Deleted',
        message=f'Your goal "{goal.name}" has been deleted.',
        notification_type='INFO'
    )
    
    db.session.commit()
    
    flash(f'Goal "{goal.name}" has been deleted.', 'success')
    return redirect(url_for('goals'))

@app.route('/bills', methods=['GET', 'POST'])
@login_required
def bills():
    """Bill payments"""
    form = BillPaymentForm()
    main_account = get_main_account(current_user.id)
    
    if form.validate_on_submit():
        amount = form.amount.data
        
        if main_account.balance < amount:
            flash('Insufficient balance.', 'danger')
            return render_template('bills.html', form=form, main_account=main_account)
        
        bill = BillPayment(
            user_id=current_user.id,
            bill_type=form.bill_type.data,
            amount=amount,
            reference_number=form.reference_number.data,
            meter_number=form.phone_number.data if form.bill_type.data in ['AIR_TIME', 'DATA'] else None,
            status='COMPLETED'
        )
        
        main_account.balance -= amount
        
        transaction_id = generate_transaction_id()
        transaction = Transaction(
            transaction_id=transaction_id,
            from_account=main_account.account_number,
            to_account='BILL_PAYMENT',
            amount=amount,
            transaction_type='BILL_PAYMENT',
            description=f'{form.bill_type.data}: {form.reference_number.data}',
            status='COMPLETED',
            user_id=current_user.id
        )
        
        commission = amount * 0.01
        if commission > 0:
            record_bank_revenue(
                revenue_type='BILL_COMMISSION',
                amount=commission,
                description=f'Commission for {form.bill_type.data} payment',
                reference_id=transaction_id
            )
        
        db.session.add(bill)
        db.session.add(transaction)
        db.session.commit()
        
        create_notification(
            user_id=current_user.id,
            title='Bill Payment Successful',
            message=f'Your {form.bill_type.data.lower()} payment of {format_currency(amount)} was successful.',
            notification_type='SUCCESS'
        )
        
        flash(f'Bill payment of {format_currency(amount)} successful!', 'success')
        return redirect(url_for('dashboard'))
    
    recent_bills = BillPayment.query.filter_by(
        user_id=current_user.id
    ).order_by(BillPayment.created_at.desc())\
     .limit(10).all()
    
    return render_template('bills.html', 
                         form=form, 
                         main_account=main_account,
                         recent_bills=recent_bills,
                         format_currency=format_currency)

@app.route('/notifications')
@login_required
def notifications():
    """View notifications"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    notifications_query = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(Notification.created_at.desc())
    
    notifications = notifications_query.paginate(page=page, per_page=per_page, error_out=False)
    
    unread_count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()
    
    return render_template('notifications.html',
                         notifications=notifications,
                         unread_count=unread_count,
                         format_currency=format_currency)

@app.route('/notifications/read/<int:notification_id>', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    """Mark a notification as read"""
    success = mark_notification_as_read(notification_id)
    if success:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Notification not found'}), 404

@app.route('/notifications/read-all', methods=['POST'])
@login_required
def mark_all_notifications_read():
    """Mark all notifications as read"""
    mark_all_notifications_as_read(current_user.id)
    return jsonify({'success': True})

@app.route('/notifications/delete/<int:notification_id>', methods=['DELETE'])
@login_required
def delete_notification(notification_id):
    """Delete a notification"""
    notification = Notification.query.get_or_404(notification_id)
    
    if notification.user_id != current_user.id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    db.session.delete(notification)
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/profile')
@login_required
def profile():
    """User profile"""
    accounts = Account.query.filter_by(user_id=current_user.id).all()
    total_balance = sum(account.balance for account in accounts)
    main_account = get_main_account(current_user.id)
    
    return render_template('profile.html',
                         user=current_user,
                         accounts=accounts,
                         main_account=main_account,
                         total_balance=total_balance,
                         format_currency=format_currency,
                         datetime=datetime)

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """User settings"""
    form = NotificationSettingsForm()
    
    if form.validate_on_submit():
        flash('Settings updated successfully!', 'success')
        return redirect(url_for('settings'))
    
    return render_template('settings.html', form=form)


@app.route('/how-it-works')
def how_it_works():
    """How It Works page - step by step guide"""
    return render_template('how_it_works.html')

# ==================== ADMIN ROUTES ====================

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login"""
    if current_user.is_authenticated and hasattr(current_user, 'is_super_admin'):
        return redirect(url_for('admin_dashboard'))
    
    form = AdminLoginForm()
    
    if form.validate_on_submit():
        admin = Admin.query.filter_by(email=form.email.data).first()
        
        if admin and bcrypt.check_password_hash(admin.password_hash, form.password.data):
            login_user(admin, remember=form.remember.data)
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid admin credentials.', 'danger')
    
    return render_template('admin/login.html', form=form)

@app.route('/admin/logout')
@login_required
def admin_logout():
    """Admin logout"""
    if not hasattr(current_user, 'is_super_admin'):
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('index'))
    
    logout_user()
    flash('Admin logged out successfully.', 'info')
    return redirect(url_for('admin_login'))

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    """Admin dashboard"""
    if not isinstance(current_user, Admin):
        flash('Unauthorized access. Admin privileges required.', 'danger')
        return redirect(url_for('index'))
    
    total_users = User.query.count()
    total_transactions = Transaction.query.count()
    total_deposits = Transaction.query.filter_by(transaction_type='DEPOSIT').count()
    
    total_balance = db.session.query(func.sum(Account.balance)).scalar() or 0
    
    total_fees = db.session.query(func.sum(BankRevenue.amount)).scalar() or 0
    
    recent_transactions = Transaction.query\
        .order_by(Transaction.created_at.desc())\
        .limit(10)\
        .all()
    
    recent_users = User.query\
        .order_by(User.created_at.desc())\
        .limit(5)\
        .all()
    
    return render_template('admin/dashboard.html',
                         total_users=total_users,
                         total_transactions=total_transactions,
                         total_deposits=total_deposits,
                         total_balance=format_currency(total_balance),
                         total_fees=format_currency(total_fees),
                         recent_transactions=recent_transactions,
                         recent_users=recent_users,
                         format_currency=format_currency,
                         current_time=datetime.utcnow())

@app.route('/admin/revenue')
@login_required
def admin_revenue():
    """Revenue dashboard"""
    if not isinstance(current_user, Admin):
        flash('Unauthorized access. Admin privileges required.', 'danger')
        return redirect(url_for('index'))
    
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    revenue_type = request.args.get('type')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    min_amount = request.args.get('min_amount', type=float)
    max_amount = request.args.get('max_amount', type=float)
    
    query = BankRevenue.query
    
    if revenue_type and revenue_type != 'ALL':
        query = query.filter_by(revenue_type=revenue_type)
    
    if start_date:
        query = query.filter(BankRevenue.created_at >= start_date)
    
    if end_date:
        query = query.filter(BankRevenue.created_at <= end_date)
    
    if min_amount:
        query = query.filter(BankRevenue.amount >= min_amount)
    
    if max_amount:
        query = query.filter(BankRevenue.amount <= max_amount)
    
    revenues = query.order_by(BankRevenue.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    total_revenue = db.session.query(func.sum(BankRevenue.amount)).scalar() or 0
    
    today = datetime.now().date()
    today_revenue = db.session.query(func.sum(BankRevenue.amount)).filter(
        func.date(BankRevenue.created_at) == today
    ).scalar() or 0
    
    yesterday = today - timedelta(days=1)
    yesterday_revenue = db.session.query(func.sum(BankRevenue.amount)).filter(
        func.date(BankRevenue.created_at) == yesterday
    ).scalar() or 0
    today_change = today_revenue - yesterday_revenue
    
    start_of_month = today.replace(day=1)
    month_revenue = db.session.query(func.sum(BankRevenue.amount)).filter(
        BankRevenue.created_at >= start_of_month
    ).scalar() or 0
    
    start_of_last_month = (start_of_month - timedelta(days=1)).replace(day=1)
    end_of_last_month = start_of_month - timedelta(days=1)
    last_month_revenue = db.session.query(func.sum(BankRevenue.amount)).filter(
        BankRevenue.created_at >= start_of_last_month,
        BankRevenue.created_at <= end_of_last_month
    ).scalar() or 0
    
    if last_month_revenue > 0:
        monthly_growth = round(((month_revenue - last_month_revenue) / last_month_revenue) * 100, 1)
    else:
        monthly_growth = 100.0 if month_revenue > 0 else 0.0
    
    avg_fee = db.session.query(func.avg(BankRevenue.amount)).filter(
        BankRevenue.revenue_type == 'TRANSACTION_FEE'
    ).scalar() or 0
    
    revenue_types = db.session.query(
        BankRevenue.revenue_type,
        func.sum(BankRevenue.amount).label('total_amount')
    ).group_by(BankRevenue.revenue_type).all()
    
    revenue_by_type = {}
    for rev_type, amount in revenue_types:
        percentage = round((amount / total_revenue) * 100, 2) if total_revenue > 0 else 0
        revenue_by_type[rev_type] = {
            'amount': amount,
            'percentage': percentage
        }
    
    transaction_fees_total = db.session.query(func.sum(BankRevenue.amount)).filter(
        BankRevenue.revenue_type == 'TRANSACTION_FEE'
    ).scalar() or 0
    
    bill_commissions_total = db.session.query(func.sum(BankRevenue.amount)).filter(
        BankRevenue.revenue_type == 'BILL_COMMISSION'
    ).scalar() or 0
    
    transaction_fees_percentage = round((transaction_fees_total / total_revenue) * 100, 1) if total_revenue > 0 else 0
    bill_commissions_percentage = round((bill_commissions_total / total_revenue) * 100, 1) if total_revenue > 0 else 0
    
    thirty_days_ago = datetime.now() - timedelta(days=30)
    sixty_days_ago = datetime.now() - timedelta(days=60)
    
    recent_revenue = db.session.query(func.sum(BankRevenue.amount)).filter(
        BankRevenue.created_at >= thirty_days_ago
    ).scalar() or 0
    
    previous_revenue = db.session.query(func.sum(BankRevenue.amount)).filter(
        BankRevenue.created_at >= sixty_days_ago,
        BankRevenue.created_at < thirty_days_ago
    ).scalar() or 0
    
    if previous_revenue > 0:
        growth_rate = round(((recent_revenue - previous_revenue) / previous_revenue) * 100, 1)
    else:
        growth_rate = 100.0 if recent_revenue > 0 else 0.0
    
    return render_template('admin/revenue.html',
                         revenues=revenues,
                         total_revenue=total_revenue,
                         today_revenue=today_revenue,
                         today_change=today_change,
                         month_revenue=month_revenue,
                         monthly_growth=monthly_growth,
                         avg_fee=avg_fee,
                         revenue_by_type=revenue_by_type,
                         transaction_fees_total=transaction_fees_total,
                         bill_commissions_total=bill_commissions_total,
                         transaction_fees_percentage=transaction_fees_percentage,
                         bill_commissions_percentage=bill_commissions_percentage,
                         growth_rate=growth_rate,
                         format_currency=format_currency)

@app.route('/admin/users')
@login_required
def admin_users():
    """Users management"""
    if not isinstance(current_user, Admin):
        flash('Unauthorized access. Admin privileges required.', 'danger')
        return redirect(url_for('index'))
    
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    status_filter = request.args.get('status', '')
    sort_by = request.args.get('sort', 'newest')
    
    query = User.query
    
    if search:
        query = query.filter(
            or_(
                User.full_name.ilike(f'%{search}%'),
                User.email.ilike(f'%{search}%'),
                User.id_number.ilike(f'%{search}%'),
                User.phone_number.ilike(f'%{search}%')
            )
        )
    
    if status_filter == 'active':
        query = query.filter(User.is_active == True)
    elif status_filter == 'inactive':
        query = query.filter(User.is_active == False)
    
    if sort_by == 'oldest':
        query = query.order_by(User.created_at.asc())
    elif sort_by == 'name':
        query = query.order_by(User.full_name.asc())
    else:
        query = query.order_by(User.created_at.desc())
    
    per_page = 20
    users = query.paginate(page=page, per_page=per_page, error_out=False)
    
    active_users_count = User.query.filter_by(is_active=True).count()
    inactive_users_count = User.query.filter_by(is_active=False).count()
    
    today = datetime.now().date()
    today_users_count = User.query.filter(
        func.date(User.created_at) == today
    ).count()
    
    current_date = datetime.now().date()
    
    return render_template('admin/users.html', 
                         users=users,
                         active_users_count=active_users_count,
                         inactive_users_count=inactive_users_count,
                         today_users_count=today_users_count,
                         current_date=current_date,
                         format_currency=format_currency)

@app.route('/admin/users/<int:user_id>/toggle', methods=['POST'])
@login_required
def toggle_user_status(user_id):
    """Toggle user status"""
    if not isinstance(current_user, Admin):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    user = User.query.get_or_404(user_id)
    user.is_active = not user.is_active
    db.session.commit()
    
    status = "activated" if user.is_active else "deactivated"
    
    if user.is_active:
        create_notification(
            user_id=user.id,
            title='Account Reactivated',
            message='Your Nkuna Bank account has been reactivated by an administrator.',
            notification_type='INFO'
        )
    else:
        create_notification(
            user_id=user.id,
            title='Account Deactivated',
            message='Your Nkuna Bank account has been deactivated by an administrator. Please contact support for assistance.',
            notification_type='WARNING'
        )
    
    return jsonify({
        'success': True,
        'message': f'User {user.email} has been {status}.',
        'is_active': user.is_active
    })

@app.route('/admin/transactions')
@login_required
def admin_transactions():
    """Transactions overview"""
    if not isinstance(current_user, Admin):
        flash('Unauthorized access. Admin privileges required.', 'danger')
        return redirect(url_for('index'))
    
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    transactions = Transaction.query\
        .order_by(Transaction.created_at.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)
    
    total_amount = sum(t.amount for t in transactions.items)
    total_fees = sum(t.fee for t in transactions.items if t.fee)
    
    return render_template('admin/transactions.html',
                         transactions=transactions,
                         total_amount=total_amount,
                         total_fees=total_fees,
                         format_currency=format_currency)

# ==================== API ENDPOINTS ====================

@app.route('/api/check_account/<account_number>')
def check_account(account_number):
    """API endpoint to check if account exists"""
    account = Account.query.filter_by(account_number=account_number).first()
    
    if account:
        return jsonify({
            'exists': True,
            'account_type': account.account_type,
            'user_name': account.user.full_name if account.user else 'Unknown',
            'account_balance': account.balance
        })
    else:
        return jsonify({'exists': False})

@app.route('/api/get_balance')
@login_required
def get_balance():
    """API endpoint to get current balance"""
    main_account = get_main_account(current_user.id)
    if main_account:
        return jsonify({
            'success': True,
            'balance': main_account.balance,
            'formatted_balance': format_currency(main_account.balance)
        })
    return jsonify({'success': False, 'balance': 0})

@app.route('/api/calculate_fee/<amount>')
@login_required
def calculate_fee_api(amount):
    """API endpoint to calculate transaction fee"""
    try:
        amount_float = float(amount)
        fee = calculate_transaction_fee(amount_float)
        return jsonify({
            'success': True,
            'amount': amount_float,
            'fee': fee,
            'total': amount_float + fee,
            'formatted_fee': format_currency(fee),
            'formatted_total': format_currency(amount_float + fee)
        })
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid amount'})

@app.route('/api/notification-count')
@login_required
def notification_count():
    """Get unread notification count for AJAX updates"""
    unread_count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).filter(
        Notification.expires_at > datetime.utcnow()
    ).count()
    
    return jsonify({
        'success': True,
        'unread_count': unread_count
    })

# ==================== APPLICATION STARTUP ====================

def create_default_admin():
    """Create default admin user if none exists"""
    try:
        admin = Admin.query.filter_by(email='admin@nkunabank.co.za').first()
        
        if not admin:
            hashed_password = bcrypt.generate_password_hash('Admin@123').decode('utf-8')
            admin = Admin(
                email='admin@nkunabank.co.za',
                password_hash=hashed_password,
                full_name='System Administrator',
                is_super_admin=True
            )
            db.session.add(admin)
            db.session.commit()
            print("✅ Default admin user created: admin@nkunabank.co.za / Admin@123")
        else:
            print("✅ Admin already exists")
    except Exception as e:
        print(f"⚠️  Could not create admin (database might not be ready): {e}")

def init_app():
    """Initialize the application and database"""
    with app.app_context():
        try:
            from app import User, Account, Transaction, Goal, BillPayment, Admin, Notification, BankRevenue
            
            print("🔧 Models imported successfully")
            print("📊 Creating database tables...")
            db.create_all()
            print("✅ Database tables created!")
            
            print("👤 Creating default admin...")
            create_default_admin()
            
            print("🔍 Testing database connection...")
            user_count = User.query.count()
            print(f"✅ Database working! Users: {user_count}")
            
        except Exception as e:
            print(f"❌ Database init failed: {str(e)}")
            import traceback
            print(f"❌ Traceback: {traceback.format_exc()}")           
            
# Initialize the app when this file is imported
init_app()

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

# ==================== MAIN ====================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)