from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, abort
from flask_login import login_required, current_user, logout_user, login_user
from datetime import datetime, timedelta
from sqlalchemy import or_, and_

from models import db, User, Account, Transaction, Goal, BillPayment, Notification
from forms import (
    RegistrationForm, LoginForm, TransferForm, DepositForm, 
    GoalForm, GoalDepositForm, GoalWithdrawalForm, BillPaymentForm,
    NotificationSettingsForm
)
from utils import (
    validate_south_african_id, extract_dob_from_id, generate_account_number,
    generate_transaction_id, calculate_transaction_fee, get_main_account,
    can_undo_transaction, get_days_remaining, format_currency,
    validate_minimum_age, validate_phone_number, create_notification,
    validate_account_ownership, validate_transfer_limit, validate_amount,
    record_bank_revenue, get_unread_notifications, mark_notification_as_read,
    mark_all_notifications_as_read, calculate_goal_progress
)

# Create blueprint
user_bp = Blueprint('user', __name__, url_prefix='')

@user_bp.route('/')
def index():
    """Home page"""
    if current_user.is_authenticated:
        if hasattr(current_user, 'is_super_admin') and current_user.is_super_admin:
            return redirect(url_for('admin.admin_dashboard'))
        return redirect(url_for('user.dashboard'))
    return render_template('index.html')

@user_bp.route('/register', methods=['GET', 'POST'])
def register():
    """User registration"""
    if current_user.is_authenticated:
        return redirect(url_for('user.dashboard'))
    
    form = RegistrationForm()
    
    if form.validate_on_submit():
        # Extract date of birth from ID
        dob = extract_dob_from_id(form.id_number.data)
        
        if not dob:
            flash('Invalid date of birth in ID', 'danger')
            return render_template('register.html', form=form)
        
        # Check minimum age (18 years)
        is_valid_age, age = validate_minimum_age(dob)
        if not is_valid_age:
            flash(f'You must be at least 18 years old. You are {age} years old.', 'danger')
            return render_template('register.html', form=form)
        
        # Hash password
        from flask_bcrypt import Bcrypt
        bcrypt = Bcrypt()
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        
        # Create user
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
        
        # Generate account number and create main account
        account_number = generate_account_number()
        account = Account(
            account_number=account_number,
            account_type='MAIN',
            balance=0.0,
            user_id=user.id
        )
        
        db.session.add(account)
        db.session.commit()
        
        # Create welcome notification
        create_notification(
            user_id=user.id,
            title='Welcome to Nkuna Bank!',
            message=f'Welcome {user.full_name}! Your account has been created successfully. Your account number is {account_number}. Please save it securely.',
            notification_type='SUCCESS'
        )
        
        flash(f'Account created successfully! Your account number is: {account_number}. Please save it.', 'success')
        return redirect(url_for('user.login'))
    
    return render_template('register.html', form=form)

@user_bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if current_user.is_authenticated:
        return redirect(url_for('user.dashboard'))
    
    form = LoginForm()
    
    if form.validate_on_submit():
        from flask_bcrypt import Bcrypt
        bcrypt = Bcrypt()
        
        user = User.query.filter_by(email=form.email.data).first()
        
        if user and bcrypt.check_password_hash(user.password_hash, form.password.data):
            if not user.is_active:
                flash('Your account has been deactivated. Please contact support.', 'danger')
                return render_template('login.html', form=form)
            
            login_user(user, remember=form.remember.data)
            
            # Create login notification
            create_notification(
                user_id=user.id,
                title='Login Successful',
                message='You have successfully logged into your Nkuna Bank account.',
                notification_type='INFO'
            )
            
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('user.dashboard'))
        else:
            flash('Login failed. Please check your email and password.', 'danger')
    
    return render_template('login.html', form=form)

@user_bp.route('/logout')
@login_required
def logout():
    """User logout"""
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('user.index'))

@user_bp.route('/dashboard')
@login_required
def dashboard():
    """User dashboard"""
    main_account = get_main_account(current_user.id)
    
    # Recent transactions (last 10)
    recent_transactions = Transaction.query.filter_by(user_id=current_user.id)\
        .order_by(Transaction.created_at.desc())\
        .limit(10)\
        .all()
    
    # Active goals
    goals = Goal.query.filter_by(
        user_id=current_user.id,
        is_active=True
    ).order_by(Goal.target_date.asc()).all()
    
    # Calculate progress for each goal
    for goal in goals:
        goal.progress = calculate_goal_progress(goal)
        goal.days_remaining = get_days_remaining(goal.target_date)
    
    # Unread notifications
    unread_notifications = get_unread_notifications(current_user.id, limit=5)
    
    # Recent bill payments
    recent_bills = BillPayment.query.filter_by(
        user_id=current_user.id
    ).order_by(BillPayment.created_at.desc())\
     .limit(5).all()
    
    # Calculate total balance across all accounts
    total_balance = sum(account.balance for account in current_user.accounts)
    
    # Check for low balance alert
    from utils import check_low_balance_alert
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
                         get_days_remaining=get_days_remaining)

@user_bp.route('/deposit', methods=['GET', 'POST'])
@login_required
def deposit():
    """Deposit money"""
    form = DepositForm()
    
    if form.validate_on_submit():
        amount = float(form.amount.data)
        main_account = get_main_account(current_user.id)
        
        if main_account:
            # Create transaction record
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
            
            # Update balance
            main_account.balance += amount
            
            db.session.add(transaction)
            db.session.commit()
            
            # Create notification
            create_notification(
                user_id=current_user.id,
                title='Deposit Successful',
                message=f'You have successfully deposited {format_currency(amount)} into your account.',
                notification_type='SUCCESS'
            )
            
            flash(f'Successfully deposited {format_currency(amount)}', 'success')
            return redirect(url_for('user.dashboard'))
    
    return render_template('deposit.html', form=form)

@user_bp.route('/transfer', methods=['GET', 'POST'])
@login_required
def transfer():
    """Transfer money to another account"""
    form = TransferForm()
    main_account = get_main_account(current_user.id)
    
    if form.validate_on_submit():
        to_account_number = form.to_account.data.strip()
        amount = float(form.amount.data)
        description = form.description.data
        
        # Check if recipient account exists
        recipient_account = Account.query.filter_by(account_number=to_account_number).first()
        
        if not recipient_account:
            flash('Recipient account does not exist.', 'danger')
            return render_template('transfer.html', form=form, main_account=main_account)
        
        # Check if transferring to own account
        if to_account_number == main_account.account_number:
            flash('Cannot transfer to your own account.', 'danger')
            return render_template('transfer.html', form=form, main_account=main_account)
        
        # Check daily transfer limit
        if not validate_transfer_limit(current_user.id, amount):
            flash(f'Daily transfer limit of R50,000 exceeded.', 'danger')
            return render_template('transfer.html', form=form, main_account=main_account)
        
        # Calculate transaction fee
        fee = calculate_transaction_fee(amount)
        total_deduction = amount + fee
        
        # Check balance
        if main_account.balance < total_deduction:
            flash(f'Insufficient balance. Need {format_currency(total_deduction)}, have {format_currency(main_account.balance)}', 'danger')
            return render_template('transfer.html', form=form, main_account=main_account)
        
        # Generate transaction ID
        transaction_id = generate_transaction_id()
        
        # Create transaction
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
        
        # Update balances
        main_account.balance -= total_deduction
        recipient_account.balance += amount
        
        # Record bank revenue
        record_bank_revenue(
            revenue_type='TRANSACTION_FEE',
            amount=fee,
            description=f'Transfer fee for transaction {transaction_id}',
            reference_id=transaction_id
        )
        
        db.session.add(transaction)
        db.session.commit()
        
        # Create notifications for both users
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
        return redirect(url_for('user.dashboard'))
    
    return render_template('transfer.html', form=form, main_account=main_account)

@user_bp.route('/undo_transaction/<transaction_id>', methods=['POST'])
@login_required
def undo_transaction(transaction_id):
    """Undo a transaction within 15-minute window"""
    transaction = Transaction.query.filter_by(
        transaction_id=transaction_id,
        user_id=current_user.id
    ).first()
    
    if not transaction:
        flash('Transaction not found.', 'danger')
        return redirect(url_for('user.transaction_history'))
    
    # Check if can be undone
    if not can_undo_transaction(transaction):
        flash('This transaction cannot be undone. Time limit expired.', 'danger')
        return redirect(url_for('user.transaction_history'))
    
    # Check if recipient still has enough balance
    recipient_account = Account.query.filter_by(account_number=transaction.to_account).first()
    if not recipient_account or recipient_account.balance < transaction.amount:
        flash('Cannot undo transaction. Recipient has insufficient balance.', 'danger')
        return redirect(url_for('user.transaction_history'))
    
    # Get sender's account
    sender_account = Account.query.filter_by(account_number=transaction.from_account).first()
    
    if not sender_account:
        flash('Sender account not found.', 'danger')
        return redirect(url_for('user.transaction_history'))
    
    # Reverse the transaction
    sender_account.balance += transaction.amount + transaction.fee
    recipient_account.balance -= transaction.amount
    
    # Update transaction status
    transaction.status = 'UNDONE'
    
    # Create notifications
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
    return redirect(url_for('user.transaction_history'))

@user_bp.route('/history')
@login_required
def transaction_history():
    """Transaction history"""
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    # Get filter parameters
    transaction_type = request.args.get('type', '')
    search = request.args.get('search', '')
    
    # Build query
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
    
    # Order by date (newest first)
    transactions = query.order_by(Transaction.created_at.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)
    
    # Calculate totals
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

@user_bp.route('/goals', methods=['GET', 'POST'])
@login_required
def goals():
    """Goal savings management"""
    form = GoalForm()
    main_account = get_main_account(current_user.id)
    
    if form.validate_on_submit():
        # Create goal account
        goal_account_number = generate_account_number()
        goal_account = Account(
            account_number=goal_account_number,
            account_type='GOAL',
            balance=0.0,
            user_id=current_user.id
        )
        
        db.session.add(goal_account)
        db.session.flush()  # Get the account ID
        
        # Create goal
        goal = Goal(
            name=form.name.data,
            target_amount=float(form.target_amount.data),
            target_date=form.target_date.data,
            auto_deposit=form.auto_deposit.data,
            auto_deposit_amount=float(form.auto_deposit_amount.data) if form.auto_deposit.data else None,
            auto_deposit_day=form.auto_deposit_day.data if form.auto_deposit.data else None,
            user_id=current_user.id,
            account_id=goal_account.id
        )
        
        db.session.add(goal)
        db.session.commit()
        
        # Create notification
        create_notification(
            user_id=current_user.id,
            title='Goal Created',
            message=f'Your goal "{form.name.data}" has been created successfully!',
            notification_type='SUCCESS'
        )
        
        flash(f'Goal "{form.name.data}" created successfully!', 'success')
        return redirect(url_for('user.goals'))
    
    # Get user's goals
    user_goals = Goal.query.filter_by(
        user_id=current_user.id,
        is_active=True
    ).order_by(Goal.created_at.desc()).all()
    
    # Calculate progress for each goal
    for goal in user_goals:
        goal.progress = calculate_goal_progress(goal)
        goal.days_remaining = get_days_remaining(goal.target_date)
        goal.formatted_amount = format_currency(goal.current_amount)
        goal.formatted_target = format_currency(goal.target_amount)
    
    return render_template('goals.html',
                         form=form,
                         goals=user_goals,
                         main_account=main_account,
                         format_currency=format_currency)

@user_bp.route('/goals/<int:goal_id>/deposit', methods=['POST'])
@login_required
def deposit_to_goal(goal_id):
    """Deposit money to a goal"""
    goal = Goal.query.get_or_404(goal_id)
    
    if goal.user_id != current_user.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('user.goals'))
    
    try:
        amount = float(request.form.get('amount', 0))
    except ValueError:
        flash('Invalid amount.', 'danger')
        return redirect(url_for('user.goals'))
    
    if amount <= 0:
        flash('Invalid amount.', 'danger')
        return redirect(url_for('user.goals'))
    
    main_account = get_main_account(current_user.id)
    goal_account = Account.query.get(goal.account_id)
    
    if not main_account or not goal_account:
        flash('Account not found.', 'danger')
        return redirect(url_for('user.goals'))
    
    if main_account.balance < amount:
        flash('Insufficient balance in main account.', 'danger')
        return redirect(url_for('user.goals'))
    
    # Transfer from main to goal
    main_account.balance -= amount
    goal_account.balance += amount
    goal.current_amount += amount
    
    # Record transaction
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
    
    # Check if goal is achieved
    if goal.current_amount >= goal.target_amount:
        create_notification(
            user_id=current_user.id,
            title='Goal Achieved! 🎉',
            message=f'Congratulations! You have achieved your goal "{goal.name}"!',
            notification_type='SUCCESS'
        )
    
    db.session.commit()
    
    flash(f'Successfully deposited {format_currency(amount)} to "{goal.name}"', 'success')
    return redirect(url_for('user.goals'))

@user_bp.route('/goals/<int:goal_id>/withdraw', methods=['POST'])
@login_required
def withdraw_from_goal(goal_id):
    """Withdraw money from a goal"""
    goal = Goal.query.get_or_404(goal_id)
    
    if goal.user_id != current_user.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('user.goals'))
    
    try:
        amount = float(request.form.get('amount', 0))
    except ValueError:
        flash('Invalid amount.', 'danger')
        return redirect(url_for('user.goals'))
    
    if amount <= 0:
        flash('Invalid amount.', 'danger')
        return redirect(url_for('user.goals'))
    
    main_account = get_main_account(current_user.id)
    goal_account = Account.query.get(goal.account_id)
    
    if not main_account or not goal_account:
        flash('Account not found.', 'danger')
        return redirect(url_for('user.goals'))
    
    if goal_account.balance < amount:
        flash('Insufficient balance in goal account.', 'danger')
        return redirect(url_for('user.goals'))
    
    # Transfer from goal to main
    goal_account.balance -= amount
    main_account.balance += amount
    goal.current_amount -= amount
    
    # Record transaction
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
    return redirect(url_for('user.goals'))

@user_bp.route('/goals/<int:goal_id>/delete', methods=['POST'])
@login_required
def delete_goal(goal_id):
    """Delete a goal (mark as inactive)"""
    goal = Goal.query.get_or_404(goal_id)
    
    if goal.user_id != current_user.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('user.goals'))
    
    # Return money to main account
    main_account = get_main_account(current_user.id)
    goal_account = Account.query.get(goal.account_id)
    
    if goal_account and goal_account.balance > 0:
        main_account.balance += goal_account.balance
        
        # Record transaction
        transaction_id = generate_transaction_id()
        transaction = Transaction(
            transaction_id=transaction_id,
            from_account=goal_account.account_number,
            to_account=main_account.account_number,
            amount=goal_account.balance,
            transaction_type='GOAL_WITHDRAWAL',
            description=f'Goal closure: {goal.name}',
            status='COMPLETED',
            user_id=current_user.id
        )
        db.session.add(transaction)
    
    # Mark goal as inactive
    goal.is_active = False
    db.session.commit()
    
    create_notification(
        user_id=current_user.id,
        title='Goal Closed',
        message=f'Your goal "{goal.name}" has been closed successfully.',
        notification_type='INFO'
    )
    
    flash(f'Goal "{goal.name}" has been closed successfully.', 'success')
    return redirect(url_for('user.goals'))

@user_bp.route('/bills', methods=['GET', 'POST'])
@login_required
def bills():
    """Bill payments"""
    form = BillPaymentForm()
    main_account = get_main_account(current_user.id)
    
    if form.validate_on_submit():
        amount = float(form.amount.data)
        bill_type = form.bill_type.data
        
        # Check balance
        if main_account.balance < amount:
            flash('Insufficient balance.', 'danger')
            return render_template('bills.html', form=form, main_account=main_account)
        
        # Process bill payment
        bill = BillPayment(
            user_id=current_user.id,
            bill_type=bill_type,
            amount=amount,
            reference_number=form.reference_number.data,
            meter_number=form.phone_number.data if bill_type in ['AIR_TIME', 'DATA'] else None,
            provider=form.provider.data,
            status='COMPLETED'
        )
        
        # Deduct from balance
        main_account.balance -= amount
        
        # Record transaction
        transaction_id = generate_transaction_id()
        transaction = Transaction(
            transaction_id=transaction_id,
            from_account=main_account.account_number,
            to_account='BILL_PAYMENT',
            amount=amount,
            transaction_type='BILL_PAYMENT',
            description=f'{bill_type}: {form.reference_number.data}',
            status='COMPLETED',
            user_id=current_user.id
        )
        
        # Record bank revenue (small commission)
        commission = amount * 0.01  # 1% commission
        if commission > 0:
            record_bank_revenue(
                revenue_type='BILL_COMMISSION',
                amount=commission,
                description=f'Commission for {bill_type} payment',
                reference_id=transaction_id
            )
        
        db.session.add(bill)
        db.session.add(transaction)
        db.session.commit()
        
        # Create notification
        create_notification(
            user_id=current_user.id,
            title='Bill Payment Successful',
            message=f'Your {bill_type.lower()} payment of {format_currency(amount)} was successful.',
            notification_type='SUCCESS'
        )
        
        flash(f'Bill payment of {format_currency(amount)} successful!', 'success')
        return redirect(url_for('user.dashboard'))
    
    # Get recent bill payments
    recent_bills = BillPayment.query.filter_by(
        user_id=current_user.id
    ).order_by(BillPayment.created_at.desc())\
     .limit(10).all()
    
    return render_template('bills.html', 
                         form=form, 
                         main_account=main_account,
                         recent_bills=recent_bills)

@user_bp.route('/notifications')
@login_required
def notifications():
    """View notifications"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Get notifications
    notifications_query = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(Notification.created_at.desc())
    
    notifications = notifications_query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Count unread notifications
    unread_count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()
    
    return render_template('notifications.html',
                         notifications=notifications,
                         unread_count=unread_count,
                         format_currency=format_currency)

@user_bp.route('/notifications/read/<int:notification_id>', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    """Mark a notification as read"""
    success = mark_notification_as_read(notification_id)
    if success:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Notification not found'}), 404

@user_bp.route('/notifications/read-all', methods=['POST'])
@login_required
def mark_all_notifications_read():
    """Mark all notifications as read"""
    mark_all_notifications_as_read(current_user.id)
    return jsonify({'success': True})

@user_bp.route('/notifications/clear', methods=['POST'])
@login_required
def clear_notifications():
    """Clear all notifications"""
    Notification.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({'success': True})

@user_bp.route('/profile')
@login_required
def profile():
    """User profile"""
    # Get user's accounts
    accounts = Account.query.filter_by(user_id=current_user.id).all()
    
    # Calculate totals
    total_balance = sum(account.balance for account in accounts)
    
    # Get account statistics
    main_account = get_main_account(current_user.id)
    
    return render_template('profile.html',
                         user=current_user,
                         accounts=accounts,
                         main_account=main_account,
                         total_balance=total_balance,
                         format_currency=format_currency)

@user_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """User settings"""
    form = NotificationSettingsForm()
    
    if form.validate_on_submit():
        # In a real app, save these to user settings
        flash('Settings updated successfully!', 'success')
        return redirect(url_for('user.settings'))
    
    return render_template('settings.html', form=form)

# API Endpoints
@user_bp.route('/api/check_account/<account_number>')
def check_account(account_number):
    """API endpoint to check if account exists (for AJAX validation)"""
    account = Account.query.filter_by(account_number=account_number).first()
    
    if account:
        return jsonify({
            'exists': True,
            'account_type': account.account_type,
            'user_name': account.owner.full_name if account.owner else 'Unknown',
            'account_balance': account.balance
        })
    else:
        return jsonify({'exists': False})

@user_bp.route('/api/get_balance')
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

@user_bp.route('/api/get_notifications')
@login_required
def get_notifications_api():
    """API endpoint to get notifications"""
    unread_notifications = get_unread_notifications(current_user.id, limit=10)
    
    notifications_data = []
    for notification in unread_notifications:
        notifications_data.append({
            'id': notification.id,
            'title': notification.title,
            'message': notification.message,
            'type': notification.notification_type,
            'created_at': notification.created_at.strftime('%Y-%m-%d %H:%M'),
            'is_read': notification.is_read
        })
    
    return jsonify({
        'success': True,
        'notifications': notifications_data,
        'count': len(notifications_data)
    })

@user_bp.route('/api/calculate_fee/<amount>')
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

# Error handlers
@user_bp.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@user_bp.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500