from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime, date
from app.models import Member, Category
from app import db
from app.utils.audit import log_action

members_bp = Blueprint('members', __name__)


def require_permission(perm):
    from functools import wraps
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.can(perm):
                flash('Access denied.', 'danger')
                return redirect(url_for('dashboard.index'))
            return f(*args, **kwargs)
        return decorated
    return decorator


def parse_date(val):
    if not val or str(val).strip() in ('', 'None', 'nan'):
        return date.today()
    for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%m/%d/%Y'):
        try:
            return datetime.strptime(str(val).strip()[:10], fmt).date()
        except Exception:
            pass
    return date.today()


@members_bp.route('/members')
@login_required
def index():
    page = request.args.get('page', 1, type=int)
    search     = request.args.get('search', '')
    gender_f   = request.args.get('gender', '')
    status_f   = request.args.get('status', '')
    area_f     = request.args.get('area', '')
    category_f = request.args.get('category', '')
    religion_f = request.args.get('religion', '')

    q = Member.query.filter(Member.status != 'deleted')
    if search:
        q = q.filter(db.or_(
            Member.full_name.ilike(f'%{search}%'),
            Member.member_id.ilike(f'%{search}%'),
            Member.mobile_number.ilike(f'%{search}%'),
            Member.area.ilike(f'%{search}%'),
        ))
    if gender_f:   q = q.filter(Member.gender == gender_f)
    if status_f:   q = q.filter(Member.status == status_f)
    if area_f:     q = q.filter(Member.area.ilike(f'%{area_f}%'))
    if religion_f: q = q.filter(Member.religion == religion_f)
    if category_f:
        cat = Category.query.get(int(category_f))
        if cat:
            q = q.filter(Member.categories.contains(cat))

    members    = q.order_by(Member.id.desc()).paginate(page=page, per_page=15, error_out=False)
    areas      = [a[0] for a in db.session.query(Member.area).distinct().all() if a[0]]
    religions  = [r[0] for r in db.session.query(Member.religion).distinct().all() if r[0]]
    categories = Category.query.filter_by(status='active').all()

    return render_template('members/index.html', members=members, search=search,
                           gender_f=gender_f, status_f=status_f, area_f=area_f,
                           category_f=category_f, religion_f=religion_f,
                           areas=areas, religions=religions, categories=categories)


@members_bp.route('/members/add', methods=['GET', 'POST'])
@login_required
@require_permission('manage_members')
def add():
    categories = Category.query.filter_by(status='active').all()
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        if not full_name:
            flash('Full name is required.', 'danger')
            return render_template('members/form.html', member=None, action='Add', categories=categories)

        member = Member(
            member_id    = Member.generate_member_id(),
            full_name    = full_name,
            gender       = request.form.get('gender', '').strip() or None,
            age          = request.form.get('age', type=int),
            religion     = request.form.get('religion', '').strip() or None,
            mobile_number= request.form.get('mobile_number', '').strip() or None,
            area         = (request.form.get('area', '').strip() or '').upper() or None,
            join_date    = parse_date(request.form.get('join_date')),
            status       = request.form.get('status', 'active'),
            created_by   = current_user.id,
        )
        for cat_id in request.form.getlist('categories'):
            cat = Category.query.get(int(cat_id))
            if cat:
                member.categories.append(cat)

        db.session.add(member)
        db.session.commit()
        log_action('Add Member', f'Added member {member.member_id} - {member.full_name}')
        flash(f'Member {member.full_name} added successfully with ID {member.member_id}.', 'success')
        return redirect(url_for('members.index'))

    return render_template('members/form.html', member=None, action='Add', categories=categories)


@members_bp.route('/members/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@require_permission('manage_members')
def edit(id):
    member     = Member.query.get_or_404(id)
    categories = Category.query.filter_by(status='active').all()

    if request.method == 'POST':
        member.full_name    = request.form.get('full_name', '').strip()
        member.gender       = request.form.get('gender', '').strip() or None
        member.age          = request.form.get('age', type=int)
        member.religion     = request.form.get('religion', '').strip() or None
        member.mobile_number= request.form.get('mobile_number', '').strip() or None
        member.area         = (request.form.get('area', '').strip() or '').upper() or None
        member.join_date    = parse_date(request.form.get('join_date'))
        old_status = member.status
        member.status       = request.form.get('status', 'active')
        member.updated_by   = current_user.id
        member.updated_at   = datetime.utcnow()

        # Track inactive date
        if old_status == 'active' and member.status == 'inactive' and not member.inactive_date:
            member.inactive_date = datetime.utcnow()
        elif member.status == 'active':
            member.inactive_date = None

        member.categories.clear()
        for cat_id in request.form.getlist('categories'):
            cat = Category.query.get(int(cat_id))
            if cat:
                member.categories.append(cat)

        db.session.commit()
        log_action('Edit Member', f'Edited member {member.member_id} - {member.full_name}')
        flash('Member updated successfully.', 'success')
        return redirect(url_for('members.index'))

    return render_template('members/form.html', member=member, action='Edit', categories=categories)


@members_bp.route('/members/view/<int:id>')
@login_required
def view(id):
    member = Member.query.get_or_404(id)
    from app.models import Attendance, Session as Sess
    records = db.session.query(Attendance, Sess).join(
        Sess, Attendance.session_id == Sess.id
    ).filter(Attendance.member_id == id).order_by(Sess.date.desc()).limit(20).all()

    total   = len(records)
    present = sum(1 for a, s in records if a.status == 'present')
    pct     = round(present / total * 100, 1) if total > 0 else 0
    return render_template('members/view.html', member=member, records=records,
                           total_att=total, present_att=present, pct=pct)


@members_bp.route('/members/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('manage_members')
def delete(id):
    member = Member.query.get_or_404(id)
    old_status = member.status
    member.status = 'inactive'
    if old_status == 'active' and not member.inactive_date:
        member.inactive_date = datetime.utcnow()
    member.updated_by = current_user.id
    member.updated_at = datetime.utcnow()
    db.session.commit()
    log_action('Deactivate Member', f'Deactivated member {member.member_id} - {member.full_name}')
    flash(f'Member {member.full_name} has been deactivated.', 'success')
    return redirect(url_for('members.index'))


@members_bp.route('/members/permanent-delete/<int:id>', methods=['POST'])
@login_required
def permanent_delete(id):
    member = Member.query.get_or_404(id)
    confirmed = request.form.get('confirm_delete')
    if not confirmed:
        flash('Please confirm the deletion.', 'danger')
        return redirect(url_for('members.edit', id=id))

    member_id_str = member.member_id
    member_name = member.full_name
    member.status = 'deleted'
    member.deleted_date = datetime.utcnow()
    member.deleted_by = current_user.id
    member.updated_at = datetime.utcnow()
    db.session.commit()
    log_action('Permanent Delete Member', f'Permanently deleted member {member_id_str} - {member_name}')
    flash(f'Member {member_name} ({member_id_str}) has been permanently deleted.', 'success')
    return redirect(url_for('members.index'))


@members_bp.route('/members/export-csv')
@login_required
def export_csv():
    import csv
    import io
    from flask import Response

    status_filter = request.args.get('status', 'all')  # all, active, inactive, deleted

    q = Member.query
    if status_filter == 'active':
        q = q.filter_by(status='active')
    elif status_filter == 'inactive':
        q = q.filter_by(status='inactive')
    elif status_filter == 'deleted':
        q = q.filter_by(status='deleted')
    # else 'all' → no filter

    members = q.order_by(Member.member_id).all()

    output = io.StringIO()
    writer = csv.writer(output)

    # Header row
    writer.writerow([
        'Member ID', 'Full Name', 'Gender', 'Age', 'Religion',
        'Mobile Number', 'Area', 'Categories', 'Join Date',
        'Status', 'Inactive Date', 'Deleted Date',
        'Created At', 'Updated At'
    ])

    for m in members:
        cats = ', '.join(c.name for c in m.categories) if m.categories else ''
        writer.writerow([
            m.member_id,
            m.full_name,
            m.gender or '',
            m.age or '',
            m.religion or '',
            m.mobile_number or '',
            m.area or '',
            cats,
            m.join_date.strftime('%d-%m-%Y') if m.join_date else '',
            m.status,
            m.inactive_date.strftime('%d-%m-%Y') if m.inactive_date else '',
            m.deleted_date.strftime('%d-%m-%Y') if m.deleted_date else '',
            m.created_at.strftime('%d-%m-%Y %H:%M') if m.created_at else '',
            m.updated_at.strftime('%d-%m-%Y %H:%M') if m.updated_at else '',
        ])

    filename = f"members_{status_filter}_{date.today().strftime('%Y%m%d')}.csv"
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )



@members_bp.route('/members/bulk-delete', methods=['POST'])
@login_required
@require_permission('manage_members')
def bulk_delete():
    member_ids = request.form.getlist('member_ids')
    confirmed = request.form.get('confirm_bulk_delete')

    if not confirmed:
        flash('Please confirm the bulk deletion.', 'danger')
        return redirect(url_for('members.index'))

    if not member_ids:
        flash('No members selected.', 'warning')
        return redirect(url_for('members.index'))

    count = 0
    for mid in member_ids:
        m = Member.query.get(int(mid))
        if m and m.status != 'deleted':
            m.status = 'deleted'
            m.deleted_date = datetime.utcnow()
            m.deleted_by = current_user.id
            m.updated_at = datetime.utcnow()
            count += 1

    db.session.commit()
    log_action('Bulk Permanent Delete', f'Bulk deleted {count} members by {current_user.username}')
    flash(f'{count} member(s) have been permanently deleted.', 'success')
    return redirect(url_for('members.index'))


# ── Members History ──────────────────────────────────────────────────────────

@members_bp.route('/members/history')
@login_required
def history():
    page = request.args.get('page', 1, type=int)
    search    = request.args.get('search', '')
    status_f  = request.args.get('status', '')
    join_from = request.args.get('join_from', '')
    join_to   = request.args.get('join_to', '')
    inactive_from = request.args.get('inactive_from', '')
    inactive_to   = request.args.get('inactive_to', '')
    deleted_from  = request.args.get('deleted_from', '')
    deleted_to    = request.args.get('deleted_to', '')

    q = Member.query.filter(Member.status.in_(['inactive', 'deleted']))

    if search:
        q = q.filter(db.or_(
            Member.full_name.ilike(f'%{search}%'),
            Member.member_id.ilike(f'%{search}%'),
        ))
    if status_f:
        q = q.filter(Member.status == status_f)
    if join_from:
        try:
            q = q.filter(Member.join_date >= datetime.strptime(join_from, '%Y-%m-%d').date())
        except Exception:
            pass
    if join_to:
        try:
            q = q.filter(Member.join_date <= datetime.strptime(join_to, '%Y-%m-%d').date())
        except Exception:
            pass
    if inactive_from:
        try:
            q = q.filter(Member.inactive_date >= datetime.strptime(inactive_from, '%Y-%m-%d'))
        except Exception:
            pass
    if inactive_to:
        try:
            q = q.filter(Member.inactive_date <= datetime.strptime(inactive_to, '%Y-%m-%d'))
        except Exception:
            pass
    if deleted_from:
        try:
            q = q.filter(Member.deleted_date >= datetime.strptime(deleted_from, '%Y-%m-%d'))
        except Exception:
            pass
    if deleted_to:
        try:
            q = q.filter(Member.deleted_date <= datetime.strptime(deleted_to, '%Y-%m-%d'))
        except Exception:
            pass

    members = q.order_by(Member.updated_at.desc()).paginate(page=page, per_page=20, error_out=False)

    return render_template('members/history.html', members=members, search=search,
                           status_f=status_f, join_from=join_from, join_to=join_to,
                           inactive_from=inactive_from, inactive_to=inactive_to,
                           deleted_from=deleted_from, deleted_to=deleted_to)


@members_bp.route('/members/restore/<int:id>', methods=['POST'])
@login_required
@require_permission('manage_members')
def restore(id):
    member = Member.query.get_or_404(id)
    if member.status not in ('deleted', 'inactive'):
        flash('Member is already active.', 'info')
        return redirect(url_for('members.history'))

    member.status = 'active'
    member.deleted_date = None
    member.deleted_by = None
    member.inactive_date = None
    member.updated_by = current_user.id
    member.updated_at = datetime.utcnow()
    db.session.commit()
    log_action('Restore Member', f'Restored member {member.member_id} - {member.full_name}')
    flash(f'Member {member.full_name} has been restored to active status.', 'success')
    return redirect(url_for('members.history'))
