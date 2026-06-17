from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.models import User, ROLE_HIERARCHY, ROLE_DISPLAY, role_rank
from app import db
from app.utils.audit import log_action

users_bp = Blueprint('users', __name__)


# ─── helpers ──────────────────────────────────────────────────────────────────

def _can_access_user_management():
    """Coordinator+ can view; trainer cannot."""
    return current_user.role in ('boss_super_admin', 'super_admin', 'admin', 'coordinator')


def _can_access_user_logs():
    """User Logs is narrower than User Management: Admin and above only."""
    return current_user.role in ('boss_super_admin', 'super_admin', 'admin')


def _deny(msg='Access Denied.'):
    log_action('Unauthorized Access Attempt', msg)
    flash(msg, 'danger')
    return redirect(url_for('dashboard.index'))


def _allowed_create_roles():
    """Roles the current user is allowed to create."""
    r = current_user.role
    if r in ('boss_super_admin', 'super_admin'):
        return ['super_admin', 'admin', 'coordinator', 'trainer']
    if r == 'admin':
        return ['admin', 'coordinator', 'trainer']
    if r == 'coordinator':
        return ['trainer']
    return []


# ─── index ────────────────────────────────────────────────────────────────────

@users_bp.route('/users')
@login_required
def index():
    if not _can_access_user_management():
        return _deny('Access Denied.')

    search   = request.args.get('search', '')
    role_f   = request.args.get('role', '')
    status_f = request.args.get('status', '')
    sort_by  = request.args.get('sort', 'role')  # role | created

    q = User.query
    if search:
        q = q.filter(db.or_(
            User.username.ilike(f'%{search}%'),
            User.full_name.ilike(f'%{search}%'),
            User.email.ilike(f'%{search}%'),
        ))
    if role_f:   q = q.filter_by(role=role_f)
    if status_f: q = q.filter_by(status=status_f)

    all_users = q.all()

    if sort_by == 'created':
        all_users.sort(key=lambda u: u.created_at)
    else:
        all_users.sort(key=lambda u: (role_rank(u.role), u.username))

    # Group by role for sectioned display
    grouped = {}
    for r in ROLE_HIERARCHY:
        grouped[r] = [u for u in all_users if u.role == r]

    # Super admins for transfer (boss_super_admin sees them)
    super_admins_for_transfer = []
    if current_user.is_boss_super_admin():
        super_admins_for_transfer = User.query.filter_by(role='super_admin', status='active').all()

    return render_template(
        'users/index.html',
        users=all_users,
        grouped=grouped,
        role_hierarchy=ROLE_HIERARCHY,
        role_display=ROLE_DISPLAY,
        search=search, role_f=role_f, status_f=status_f, sort_by=sort_by,
        super_admins_for_transfer=super_admins_for_transfer,
        allowed_create_roles=_allowed_create_roles(),
    )


# ─── add ──────────────────────────────────────────────────────────────────────

@users_bp.route('/users/add', methods=['GET', 'POST'])
@login_required
def add():
    allowed = _allowed_create_roles()
    if not allowed:
        return _deny('Access Denied.')

    if request.method == 'POST':
        username  = request.form.get('username', '').strip()
        password  = request.form.get('password', '')
        role      = request.form.get('role', '')
        full_name = request.form.get('full_name', '').strip()
        email     = request.form.get('email', '').strip()

        # Backend role validation
        if role not in allowed:
            log_action('Unauthorized Access Attempt',
                       f'{current_user.username} tried to create role {role}')
            flash('You are not allowed to create that role.', 'danger')
            return redirect(url_for('users.add'))

        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'danger')
            return redirect(url_for('users.add'))
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return redirect(url_for('users.add'))

        user = User(username=username, role=role, full_name=full_name,
                    email=email, status='active', created_by=current_user.id)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        log_action('Created User', f'Created user {username} with role {role}',
                   target_username=username, target_role=ROLE_DISPLAY.get(role, role))
        flash(f'User {username} created successfully.', 'success')
        return redirect(url_for('users.index'))

    return render_template('users/form.html', user=None, action='Add', allowed_roles=allowed)


# ─── edit ─────────────────────────────────────────────────────────────────────

@users_bp.route('/users/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit(id):
    target = User.query.get_or_404(id)

    # Boss super admin can only be edited by themselves
    if target.role == 'boss_super_admin' and current_user.id != target.id:
        log_action('Unauthorized Access Attempt',
                   f'{current_user.username} tried to edit Boss Super Admin {target.username}')
        flash('Boss Super Admin cannot be edited by others.', 'danger')
        return redirect(url_for('users.index'))

    # General permission check
    if not current_user.can_manage_user(target):
        log_action('Unauthorized Access Attempt',
                   f'{current_user.username} tried to edit {target.username}')
        flash('Access Denied.', 'danger')
        return redirect(url_for('users.index'))

    if request.method == 'POST':
        target.full_name = request.form.get('full_name', '').strip()
        target.email     = request.form.get('email', '').strip()

        # Self-protection: nobody (except via Transfer Ownership for the Boss
        # role) may change their own role or status — even if their normal
        # permissions would otherwise allow editing same-role accounts.
        is_self = (target.id == current_user.id)

        # Only boss_super_admin/super_admin can change roles; never allow
        # promoting to boss_super_admin via this form
        if not is_self and current_user.role in ('boss_super_admin', 'super_admin') and target.role != 'boss_super_admin':
            new_role = request.form.get('role', target.role)
            if new_role == 'boss_super_admin':
                flash('Use Transfer Ownership to assign Boss Super Admin.', 'danger')
                return redirect(url_for('users.index'))
            target.role = new_role

        # Status change — never deactivate boss_super_admin, never self-deactivate
        if not is_self and target.role != 'boss_super_admin':
            target.status = request.form.get('status', 'active')

        db.session.commit()
        log_action('Edited User', f'Edited user {target.username}',
                   target_username=target.username, target_role=target.role_display)
        flash('User updated.', 'success')
        return redirect(url_for('users.index'))

    # Allowed roles for the role dropdown
    if current_user.role in ('boss_super_admin', 'super_admin'):
        allowed_roles = ['super_admin', 'admin', 'coordinator', 'trainer']
    elif current_user.role == 'admin':
        allowed_roles = ['admin', 'coordinator', 'trainer']
    else:
        allowed_roles = []

    return render_template('users/form.html', user=target, action='Edit', allowed_roles=allowed_roles)


# ─── delete ───────────────────────────────────────────────────────────────────

@users_bp.route('/users/delete/<int:id>', methods=['POST'])
@login_required
def delete(id):
    target = User.query.get_or_404(id)

    if target.role == 'boss_super_admin':
        log_action('Unauthorized Access Attempt',
                   f'{current_user.username} tried to delete Boss Super Admin')
        flash('Boss Super Admin cannot be deleted.', 'danger')
        return redirect(url_for('users.index'))

    if target.id == current_user.id:
        log_action('Unauthorized Access Attempt',
                   f'{current_user.username} tried to delete their own account')
        flash('Cannot delete your own account.', 'danger')
        return redirect(url_for('users.index'))

    if not current_user.can_manage_user(target):
        log_action('Unauthorized Access Attempt',
                   f'{current_user.username} tried to delete {target.username}')
        flash('Access Denied.', 'danger')
        return redirect(url_for('users.index'))

    confirm = request.form.get('confirm_delete')
    if confirm != '1':
        flash('Please confirm the deletion.', 'warning')
        return redirect(url_for('users.index'))

    username = target.username
    role     = target.role
    db.session.delete(target)
    db.session.commit()
    log_action('Deleted User', f'Deleted user {username} (role: {role})',
               target_username=username, target_role=ROLE_DISPLAY.get(role, role))
    flash(f'User {username} has been deleted.', 'success')
    return redirect(url_for('users.index'))


# ─── change password ──────────────────────────────────────────────────────────

@users_bp.route('/users/change-password/<int:id>', methods=['POST'])
@login_required
def change_password(id):
    target = User.query.get_or_404(id)

    if target.role == 'boss_super_admin' and current_user.id != target.id:
        log_action('Unauthorized Access Attempt',
                   f'{current_user.username} tried to reset Boss Super Admin password')
        flash('Cannot reset Boss Super Admin password.', 'danger')
        return redirect(url_for('users.index'))

    if target.id == current_user.id:
        flash('Use Profile → Change Password to update your own password.', 'warning')
        return redirect(url_for('users.index'))

    if not current_user.has_role('boss_super_admin', 'super_admin'):
        flash('Only Super Admin or Boss Super Admin can reset passwords.', 'danger')
        return redirect(url_for('users.index'))

    if not current_user.can_manage_user(target):
        log_action('Unauthorized Access Attempt',
                   f'{current_user.username} tried to reset password of {target.username}')
        flash('Access Denied.', 'danger')
        return redirect(url_for('users.index'))

    new_pass = request.form.get('new_password', '')
    if len(new_pass) < 6:
        flash('Password must be at least 6 characters.', 'danger')
        return redirect(url_for('users.index'))

    target.set_password(new_pass)
    db.session.commit()
    log_action('Reset Password', f'Reset password for {target.username}',
               target_username=target.username, target_role=target.role_display)
    flash(f'Password changed for {target.username}.', 'success')
    return redirect(url_for('users.index'))


# ─── toggle status ────────────────────────────────────────────────────────────

@users_bp.route('/users/toggle-status/<int:id>', methods=['POST'])
@login_required
def toggle_status(id):
    target = User.query.get_or_404(id)

    if target.role == 'boss_super_admin':
        log_action('Unauthorized Access Attempt',
                   f'{current_user.username} tried to toggle Boss Super Admin status')
        flash('Boss Super Admin cannot be deactivated.', 'danger')
        return redirect(url_for('users.index'))

    if target.id == current_user.id:
        flash('Cannot disable your own account.', 'danger')
        return redirect(url_for('users.index'))

    if not current_user.can_manage_user(target):
        log_action('Unauthorized Access Attempt',
                   f'{current_user.username} tried to toggle status of {target.username}')
        flash('Access Denied.', 'danger')
        return redirect(url_for('users.index'))

    target.status = 'inactive' if target.status == 'active' else 'active'
    db.session.commit()
    action_label = 'Activated User' if target.status == 'active' else 'Deactivated User'
    log_action(action_label, f'Set {target.username} to {target.status}',
               target_username=target.username, target_role=target.role_display)
    flash(f'User {target.username} is now {target.status}.', 'success')
    return redirect(url_for('users.index'))


# ─── transfer boss ownership ──────────────────────────────────────────────────

@users_bp.route('/users/transfer-boss', methods=['POST'])
@login_required
def transfer_boss():
    if not current_user.is_boss_super_admin():
        log_action('Unauthorized Access Attempt',
                   f'{current_user.username} tried to transfer Boss Super Admin ownership')
        flash('Only Boss Super Admin can transfer ownership.', 'danger')
        return redirect(url_for('users.index'))

    confirm = request.form.get('confirm_transfer')
    new_boss_id = request.form.get('new_boss_id', type=int)

    if confirm != '1' or not new_boss_id:
        flash('Please confirm the transfer.', 'warning')
        return redirect(url_for('users.index'))

    new_boss = User.query.get_or_404(new_boss_id)

    if new_boss.role != 'super_admin':
        flash('Only an existing Super Admin can receive Boss ownership.', 'danger')
        return redirect(url_for('users.index'))

    old_boss_username = current_user.username

    # Demote current boss → super_admin
    current_user.role = 'super_admin'
    # Promote new boss
    new_boss.role = 'boss_super_admin'
    db.session.commit()

    log_action('Transferred Boss Super Admin',
               f'{old_boss_username} transferred Boss Super Admin to {new_boss.username}',
               target_username=new_boss.username, target_role='Boss Super Admin')
    flash(f'Boss Super Admin transferred to {new_boss.username}. You are now a Super Admin.', 'success')
    return redirect(url_for('users.index'))


# ─── user logs (restricted: Admin and above only) ─────────────────────────────

USER_LOG_ACTIONS = [
    'Created User', 'Edited User', 'Deleted User',
    'Activated User', 'Deactivated User',
    'Reset Password', 'Changed Password',
    'Transferred Boss Super Admin', 'Unauthorized Access Attempt',
]


@users_bp.route('/users/logs')
@login_required
def logs():
    if not _can_access_user_logs():
        return _deny('Access Denied. User Logs is restricted to Admin and above.')

    from app.models import AuditLog
    from datetime import datetime as _dt

    page      = request.args.get('page', 1, type=int)
    search    = request.args.get('search', '')
    role_f    = request.args.get('role', '')
    action_f  = request.args.get('action', '')
    date_from = request.args.get('date_from', '')
    date_to   = request.args.get('date_to', '')
    sort_by   = request.args.get('sort', 'newest')  # newest | oldest

    q = AuditLog.query.filter(AuditLog.action.in_(USER_LOG_ACTIONS))

    # Visibility scoping for the Logs page itself (separate from, and tighter
    # than, the page-access check above):
    #   - Admin   : can only see log rows performed by fellow Admins (same role tier)
    #   - Super Admin / Boss Super Admin : no restriction, can see every role
    # "Boss Super Admin" is also dropped from the Role filter choices entirely.
    role_choices = [r for r in ROLE_HIERARCHY if r != 'boss_super_admin']

    if current_user.role == 'admin':
        q = q.filter(AuditLog.role == 'admin')
        role_choices = ['admin']
        role_f = 'admin'

    if search:
        q = q.filter(db.or_(
            AuditLog.username.ilike(f'%{search}%'),
            AuditLog.target_username.ilike(f'%{search}%'),
        ))
    if role_f and current_user.role != 'admin':
        q = q.filter_by(role=role_f)
    if action_f: q = q.filter_by(action=action_f)
    if date_from:
        try:
            q = q.filter(AuditLog.timestamp >= _dt.strptime(date_from, '%Y-%m-%d'))
        except Exception:
            pass
    if date_to:
        try:
            q = q.filter(AuditLog.timestamp <= _dt.strptime(date_to + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
        except Exception:
            pass

    if sort_by == 'oldest':
        q = q.order_by(AuditLog.timestamp.asc())
    else:
        q = q.order_by(AuditLog.timestamp.desc())

    log_entries = q.paginate(page=page, per_page=20, error_out=False)

    return render_template(
        'users/logs.html',
        logs=log_entries,
        search=search, role_f=role_f, action_f=action_f,
        date_from=date_from, date_to=date_to, sort_by=sort_by,
        actions=USER_LOG_ACTIONS, role_hierarchy=role_choices, role_display=ROLE_DISPLAY,
    )
