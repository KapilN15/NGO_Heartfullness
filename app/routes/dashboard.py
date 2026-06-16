from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user
from datetime import date, timedelta
from sqlalchemy import func, extract, cast, Integer
from app.models import Member, Session, Attendance, AuditLog, ImportHistory
from app import db

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/dashboard')
@login_required
def index():
    today = date.today()

    # Stats — exclude deleted members from main counts
    total_members    = Member.query.filter(Member.status != 'deleted').count()
    active_members   = Member.query.filter_by(status='active').count()
    inactive_members = Member.query.filter_by(status='inactive').count()
    deleted_members  = Member.query.filter_by(status='deleted').count()

    total_sessions     = Session.query.count()
    completed_sessions = Session.query.filter_by(status='completed').count()
    upcoming_sessions  = Session.query.filter(
        Session.date >= today, Session.status == 'scheduled'
    ).count()

    total_attendance   = Attendance.query.count()
    present_attendance = Attendance.query.filter_by(status='present').count()
    attendance_pct     = round(present_attendance / total_attendance * 100, 1) if total_attendance > 0 else 0

    # Notifications
    sessions_today = Session.query.filter_by(date=today).all()
    upcoming_list  = Session.query.filter(
        Session.date > today, Session.status == 'scheduled'
    ).order_by(Session.date).limit(5).all()
    recent_imports  = ImportHistory.query.order_by(ImportHistory.imported_at.desc()).limit(3).all()
    recent_members  = Member.query.filter(Member.status != 'deleted').order_by(Member.created_at.desc()).limit(3).all()

    return render_template('dashboard/index.html',
        total_members=total_members,
        active_members=active_members,
        inactive_members=inactive_members,
        deleted_members=deleted_members,
        total_sessions=total_sessions,
        completed_sessions=completed_sessions,
        upcoming_sessions=upcoming_sessions,
        total_attendance=total_attendance,
        attendance_pct=attendance_pct,
        sessions_today=sessions_today,
        upcoming_list=upcoming_list,
        recent_imports=recent_imports,
        recent_members=recent_members,
    )


@dashboard_bp.route('/dashboard/chart-data')
@login_required
def chart_data():
    # ── Gender distribution (active only) ───────────────────
    gender_data = (
        db.session.query(Member.gender, func.count(Member.id))
        .filter_by(status='active')
        .group_by(Member.gender)
        .all()
    )

    # ── Religion distribution (active only) ─────────────────
    religion_data = (
        db.session.query(Member.religion, func.count(Member.id))
        .filter_by(status='active')
        .group_by(Member.religion)
        .all()
    )

    # ── Age groups (active only) ─────────────────────────────
    members = Member.query.filter_by(status='active').with_entities(Member.age).all()
    age_groups = {'18-25': 0, '26-35': 0, '36-45': 0, '46-55': 0, '55+': 0}
    for (age,) in members:
        if age:
            if age <= 25:   age_groups['18-25'] += 1
            elif age <= 35: age_groups['26-35'] += 1
            elif age <= 45: age_groups['36-45'] += 1
            elif age <= 55: age_groups['46-55'] += 1
            else:           age_groups['55+']   += 1

    # ── Monthly member growth (last 6 months) ────────────────
    # PostgreSQL-compatible: use extract(year) + extract(month)
    monthly = []
    today = date.today()
    for i in range(5, -1, -1):
        # Step back i months from today's month
        month_offset = (today.month - 1 - i) % 12 + 1
        year_offset  = today.year + ((today.month - 1 - i) // 12)
        count = Member.query.filter(
            extract('year',  Member.join_date) == year_offset,
            extract('month', Member.join_date) == month_offset,
        ).count()
        import calendar
        label = f"{calendar.month_abbr[month_offset]} {year_offset}"
        monthly.append({'month': label, 'count': count})

    # ── Attendance trend (last 5 completed sessions) ─────────
    sessions = (
        Session.query.filter_by(status='completed')
        .order_by(Session.date.desc())
        .limit(5)
        .all()
    )
    att_trend = []
    for s in reversed(sessions):
        total   = Attendance.query.filter_by(session_id=s.id).count()
        present = Attendance.query.filter_by(session_id=s.id, status='present').count()
        pct     = round(present / total * 100, 1) if total > 0 else 0
        att_trend.append({'session': s.session_name[:20], 'pct': pct})

    # ── Member status breakdown (for doughnut) ───────────────
    status_data = (
        db.session.query(Member.status, func.count(Member.id))
        .group_by(Member.status)
        .all()
    )

    return jsonify({
        'gender':   {'labels': [g[0] or 'Unknown' for g in gender_data],   'data': [g[1] for g in gender_data]},
        'religion': {'labels': [r[0] or 'Unknown' for r in religion_data], 'data': [r[1] for r in religion_data]},
        'age':      {'labels': list(age_groups.keys()),                     'data': list(age_groups.values())},
        'monthly':  {'labels': [m['month'] for m in monthly],              'data': [m['count'] for m in monthly]},
        'attendance':{'labels': [a['session'] for a in att_trend],         'data': [a['pct'] for a in att_trend]},
        'status':   {'labels': [s[0].title() for s in status_data],        'data': [s[1] for s in status_data]},
    })
