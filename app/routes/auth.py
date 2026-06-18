from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from app.models import User
from app.utils.audit import log_action
from app import db

auth_bp = Blueprint('auth', __name__)

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


@auth_bp.route('/')
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter_by(username=username).first()

        if user:
            now = datetime.utcnow()

            # Auto-unlock if the lockout window has passed
            if user.account_locked_until and now >= user.account_locked_until:
                user.failed_login_attempts = 0
                user.account_locked_until = None
                db.session.commit()

            # Still locked?
            if user.account_locked_until and now < user.account_locked_until:
                log_action('Unauthorized Access Attempt',
                           f'Login attempt on locked account: {username}',
                           target_username=user.username, target_role=user.role_display)
                flash('Too many failed login attempts. Please try again after 15 minutes.', 'danger')
                return render_template('auth/login.html')

            if user.check_password(password):
                if user.status != 'active':
                    flash('Invalid username or password.', 'danger')
                    log_action('Login Failed', f'Login attempt on inactive account: {username}')
                    return render_template('auth/login.html')

                user.failed_login_attempts = 0
                user.account_locked_until = None
                db.session.commit()
                login_user(user, remember=False)
                log_action('Login', f'User {username} logged in successfully.')
                next_page = request.args.get('next')
                return redirect(next_page or url_for('dashboard.index'))

            # Wrong password — count it as a failed attempt
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1

            if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
                user.account_locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
                db.session.commit()
                log_action('Unauthorized Access Attempt',
                           f'Account locked after {MAX_FAILED_ATTEMPTS} failed attempts: {username}',
                           target_username=user.username, target_role=user.role_display)
                flash('Too many failed login attempts. Please try again after 15 minutes.', 'danger')
                return render_template('auth/login.html')

            db.session.commit()
            flash('Invalid username or password.', 'danger')
            log_action('Login Failed', f'Failed login attempt for username: {username}')
        else:
            flash('Invalid username or password.', 'danger')
            log_action('Login Failed', f'Failed login attempt for username: {username}')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    log_action('Logout', f'User {current_user.username} logged out.')
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/set-theme', methods=['GET', 'POST'])
@login_required
def set_theme():
    theme = request.args.get('theme') or request.form.get('theme', 'light')
    if theme not in ('light', 'dark'):
        theme = 'light'
    current_user.theme = theme
    db.session.commit()
    return {'status': 'ok'}


# ─── profile / change own password ────────────────────────────────────────────

@auth_bp.route('/profile')
@login_required
def profile():
    return render_template('auth/profile.html')


@auth_bp.route('/profile/change-password', methods=['POST'])
@login_required
def change_own_password():
    current_password = request.form.get('current_password', '')
    new_password     = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')

    if not current_user.check_password(current_password):
        flash('Current password is incorrect.', 'danger')
        return redirect(url_for('auth.profile'))

    if len(new_password) < 6:
        flash('New password must be at least 6 characters.', 'danger')
        return redirect(url_for('auth.profile'))

    if new_password != confirm_password:
        flash('New password and confirmation do not match.', 'danger')
        return redirect(url_for('auth.profile'))

    current_user.set_password(new_password)
    db.session.commit()
    log_action('Changed Password', f'{current_user.username} changed their own password.',
               target_username=current_user.username, target_role=current_user.role_display)
    flash('Your password has been changed successfully.', 'success')
    return redirect(url_for('auth.profile'))
