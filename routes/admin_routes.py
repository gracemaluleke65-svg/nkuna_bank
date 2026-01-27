from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user, logout_user, login_user
from datetime import datetime, timedelta
from sqlalchemy import func, desc

from models import db, User, Account, Transaction, Goal, BillPayment, Notification, Admin, BankRevenue
from forms import AdminLoginForm, UserSearchForm, TransactionSearchForm
from utils import (
    format_currency, generate_account_number, get_days_remaining,
    calculate_bank_health, apply_monthly_charges, create_notification
)
from flask_bcrypt import Bcrypt

# Create blueprint
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login"""
    if current_user.is_authenticated and hasattr(current_user, 'is_super_admin'):
        return redirect(url_for('admin.admin_dashboard'))
    
    form = AdminLoginForm()
    
    if form.validate_on_submit():
        bcrypt = Bcrypt()
        admin = Admin.query.filter_by(email=form.email.data).first()
        
        if admin and bcrypt.check_password_hash(admin.password_hash, form.password.data):
            login_user(admin)
            return redirect(url_for('admin.admin_dashboard'))
        else:
            flash('Invalid admin credentials.', 'danger')
    
    return render_template('admin/login.html', form=form)

@admin_bp.route('/logout')
@login_required
def admin_logout():
    """Admin logout"""
    if not hasattr(current_user, 'is_super_admin'):
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('user.index'))
    
    logout_user()
    flash('Admin logged out successfully.', 'info')
    return redirect(url_for('admin.admin_login'))

@admin_bp.route('/dashboard')
@login_required
def admin_dashboard():
    """Admin dashboard"""
    if not hasattr(current_user, 'is_super_admin'):
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('user.index'))
    
    # Get bank health metrics
    bank_health = calculate_bank_health()
    
    # Recent activities
    recent_transactions = Transaction.query\
        .order_by(Transaction.created_at.desc())\
        .limit(10)\
        .all()
    
    recent_users = User.query\
        .order_by(User.created_at.desc())\
        .limit(5)\
        .all()
    
    # Revenue statistics
    revenue_today = BankRevenue.query.filter(
        func.date(BankRevenue.created_at) == datetime.now().date()
    ).all()
    
    revenue_this_month = BankRevenue.query.filter(
        func.strftime('%Y-%m', BankRevenue.created_at) == datetime.now().strftime('%Y-%m')
    ).all()
    
    total_revenue_today = sum(r.amount for r in revenue_today)
    total_revenue_month = sum(r.amount for r in revenue_this_month)
    
    # Transaction statistics
    transactions_today = Transaction.query.filter(
        func.date(Transaction.created_at) == datetime.now().date()
    ).count()
    
    # User statistics
    new_users_today = User.query.filter(
        func.date(User.created_at) == datetime.now().date()
    ).count()
    
    active_users = User.query.filter_by(is_active=True).count()
    
    return render_template('admin/dashboard.html',
                         bank_health=bank_health,
                         recent_transactions=recent_transactions,
                         recent_users=recent_users,
                         revenue_today=revenue_today,
                         total_revenue_today=format_currency(total_revenue_today),
                         total_revenue_month=format_currency(total_revenue_month),
                         transactions_today=transactions_today,
                         new_users_today=new_users_today,
                         active_users=active_users,
                         format_currency=format_currency)

@admin_bp.route('/users', methods=['GET', 'POST'])
@login_required
def admin_users():
    """User management"""
    if not hasattr(current_user, 'is_super_admin'):
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('user.index'))
    
    form = UserSearchForm()
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Build query
    query = User.query
    
    if form.validate_on_submit() or request.method == 'POST':
        search = request.form.get('search', '')
        if search:
            query = query.filter(
                db.or_(
                    User.full_name.ilike(f'%{search}%'),
                    User.email.ilike(f'%{search}%'),
                    User.id_number.ilike(f'%{search}%'),
                    User.phone_number.ilike(f'%{search}%')
                )
            )
    
    # Order by creation date
    users = query.order_by(User.created_at.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('admin/users.html', 
                         users=users, 
                         form=form,
                         format_currency=format_currency)

@admin_bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@login_required
def toggle_user_status(user_id):
    """Toggle user active status"""
    if not hasattr(current_user, 'is_super_admin'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    user = User.query.get_or_404(user_id)
    user.is_active = not user.is_active
    db.session.commit()
    
    status = "activated" if user.is_active else "deactivated"
    
    # Create notification for user
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

@admin_bp.route('/users/<int:user_id>/details')
@login_required
def user_details(user_id):
    """Get user details"""
    if not hasattr(current_user, 'is_super_admin'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    user = User.query.get_or_404(user_id)
    
    # Get user accounts
    accounts = Account.query.filter_by(user_id=user_id).all()
    
    # Get user transactions
    transactions = Transaction.query.filter_by(user_id=user_id)\
        .order_by(Transaction.created_at.desc())\
        .limit(10)\
        .all()
    
    # Calculate totals
    total_balance = sum(account.balance for account in accounts)
    
    return jsonify({
        'success': True,
        'user': {
            'id': user.id,
            'full_name': user.full_name,
            'email': user.email,
            'id_number': user.id_number,
            'phone_number': user.phone_number,
            'date_of_birth': user.date_of_birth.strftime('%Y-%m-%d') if user.date_of_birth else None,
            'is_active': user.is_active,
            'created_at': user.created_at.strftime('%Y-%m-%d %H:%M'),
            'total_balance': total_balance,
            'formatted_balance': format_currency(total_balance)
        },
        'accounts': [
            {
                'id': acc.id,
                'account_number': acc.account_number,
                'account_type': acc.account_type,
                'balance': acc.balance,
                'formatted_balance': format_currency(acc.balance)
            }
            for acc in accounts
        ],
        'recent_transactions': [
            {
                'id': t.id,
                'transaction_id': t.transaction_id,
                'type': t.transaction_type,
                'amount': t.amount,
                'formatted_amount': format_currency(t.amount),
                'description': t.description,
                'status': t.status,
                'created_at': t.created_at.strftime('%Y-%m-%d %H:%M')
            }
            for t in transactions
        ]
    })

@admin_bp.route('/transactions', methods=['GET', 'POST'])
@login_required
def admin_transactions():
    """Transaction management"""
    if not hasattr(current_user, 'is_super_admin'):
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('user.index'))
    
    form = TransactionSearchForm()
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Build query
    query = Transaction.query
    
    if form.validate_on_submit() or request.method == 'POST':
        search = request.form.get('search', '')
        transaction_type = request.form.get('transaction_type', '')
        start_date = request.form.get('start_date', '')
        end_date = request.form.get('end_date', '')
        
        if search:
            query = query.filter(
                db.or_(
                    Transaction.transaction_id.ilike(f'%{search}%'),
                    Transaction.description.ilike(f'%{search}%'),
                    Transaction.from_account.ilike(f'%{search}%'),
                    Transaction.to_account.ilike(f'%{search}%'),
                    User.full_name.ilike(f'%{search}%')
                )
            ).join(User)
        
        if transaction_type:
            query = query.filter_by(transaction_type=transaction_type)
        
        if start_date:
            try:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
                query = query.filter(Transaction.created_at >= start_date_obj)
            except ValueError:
                pass
        
        if end_date:
            try:
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
                # Add one day to include the entire end date
                end_date_obj = end_date_obj + timedelta(days=1)
                query = query.filter(Transaction.created_at <= end_date_obj)
            except ValueError:
                pass
    
    # Order by creation date
    transactions = query.order_by(Transaction.created_at.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)
    
    # Calculate totals
    total_amount = sum(t.amount for t in transactions.items)
    total_fees = sum(t.fee for t in transactions.items if t.fee)
    
    return render_template('admin/transactions.html',
                         transactions=transactions,
                         form=form,
                         total_amount=total_amount,
                         total_fees=total_fees,
                         format_currency=format_currency)

@admin_bp.route('/revenue')
@login_required
def admin_revenue():
    """Revenue management"""
    if not hasattr(current_user, 'is_super_admin'):
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('user.index'))
    
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Get revenue records
    revenue = BankRevenue.query.order_by(BankRevenue.created_at.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)
    
    # Calculate totals
    total_revenue = db.session.query(func.sum(BankRevenue.amount)).scalar() or 0
    
    # Revenue by type
    revenue_by_type = db.session.query(
        BankRevenue.revenue_type,
        func.sum(BankRevenue.amount).label('total')
    ).group_by(BankRevenue.revenue_type).all()
    
    # Monthly revenue
    monthly_revenue = db.session.query(
        func.strftime('%Y-%m', BankRevenue.created_at).label('month'),
        func.sum(BankRevenue.amount).label('total')
    ).group_by('month')\
     .order_by(desc('month'))\
     .limit(6).all()
    
    return render_template('admin/revenue.html',
                         revenue=revenue,
                         total_revenue=total_revenue,
                         revenue_by_type=revenue_by_type,
                         monthly_revenue=monthly_revenue,
                         format_currency=format_currency)

@admin_bp.route('/apply_monthly_fees', methods=['POST'])
@login_required
def apply_monthly_fees():
    """Apply monthly account fees"""
    if not hasattr(current_user, 'is_super_admin'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    try:
        accounts_processed = apply_monthly_charges()
        return jsonify({
            'success': True,
            'message': f'Monthly fees applied to {accounts_processed} accounts.',
            'accounts_processed': accounts_processed
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@admin_bp.route('/create_admin', methods=['POST'])
@login_required
def create_admin():
    """Create new admin account"""
    if not (hasattr(current_user, 'is_super_admin') and current_user.is_super_admin):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'No data provided'}), 400
    
    email = data.get('email')
    password = data.get('password')
    full_name = data.get('full_name', '')
    
    if not email or not password:
        return jsonify({'success': False, 'message': 'Email and password are required'}), 400
    
    # Check if admin already exists
    existing_admin = Admin.query.filter_by(email=email).first()
    if existing_admin:
        return jsonify({'success': False, 'message': 'Admin with this email already exists'}), 400
    
    # Hash password
    bcrypt = Bcrypt()
    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
    
    # Create admin
    admin = Admin(
        email=email,
        password_hash=hashed_password,
        full_name=full_name,
        is_super_admin=False  # Only current super admin can create other super admins
    )
    
    db.session.add(admin)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'Admin account created for {email}',
        'admin_id': admin.id
    })

@admin_bp.route('/system_stats')
@login_required
def system_stats():
    """Get system statistics"""
    if not hasattr(current_user, 'is_super_admin'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    # User statistics
    total_users = User.query.count()
    active_users = User.query.filter_by(is_active=True).count()
    new_users_today = User.query.filter(
        func.date(User.created_at) == datetime.now().date()
    ).count()
    
    # Account statistics
    total_accounts = Account.query.count()
    main_accounts = Account.query.filter_by(account_type='MAIN').count()
    goal_accounts = Account.query.filter_by(account_type='GOAL').count()
    
    # Transaction statistics
    total_transactions = Transaction.query.count()
    transactions_today = Transaction.query.filter(
        func.date(Transaction.created_at) == datetime.now().date()
    ).count()
    
    # Balance statistics
    total_deposits = db.session.query(func.sum(Account.balance)).scalar() or 0
    
    # Revenue statistics
    total_revenue = db.session.query(func.sum(BankRevenue.amount)).scalar() or 0
    revenue_today = db.session.query(func.sum(BankRevenue.amount)).filter(
        func.date(BankRevenue.created_at) == datetime.now().date()
    ).scalar() or 0
    
    return jsonify({
        'success': True,
        'stats': {
            'users': {
                'total': total_users,
                'active': active_users,
                'new_today': new_users_today,
                'inactive': total_users - active_users
            },
            'accounts': {
                'total': total_accounts,
                'main': main_accounts,
                'goal': goal_accounts
            },
            'transactions': {
                'total': total_transactions,
                'today': transactions_today
            },
            'balances': {
                'total_deposits': total_deposits,
                'formatted_deposits': format_currency(total_deposits)
            },
            'revenue': {
                'total': total_revenue,
                'today': revenue_today,
                'formatted_total': format_currency(total_revenue),
                'formatted_today': format_currency(revenue_today)
            }
        }
    })