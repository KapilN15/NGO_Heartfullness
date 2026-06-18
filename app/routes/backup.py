import os
import zipfile
import io
import csv
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file, current_app
from flask_login import login_required, current_user
from app.models import Member, Session, Attendance, AuditLog, User, Category, SessionCategory, ImportHistory
from app import db
from app.utils.audit import log_action

backup_bp = Blueprint('backup', __name__)


def get_backup_dir():
    d = current_app.config.get('BACKUP_FOLDER') or os.path.join(current_app.instance_path, 'backups')
    os.makedirs(d, exist_ok=True)
    return d


def _build_csv_zip():
    """Build a ZIP of all tables as CSV files and return a BytesIO buffer."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:

        # Members
        mbuf = io.StringIO()
        w = csv.writer(mbuf)
        w.writerow(['member_id', 'full_name', 'gender', 'age', 'religion',
                    'mobile_number', 'area', 'join_date', 'status', 'categories'])
        for m in Member.query.all():
            cats = ', '.join(c.name for c in m.categories)
            w.writerow([m.member_id, m.full_name, m.gender, m.age, m.religion,
                        m.mobile_number, m.area, m.join_date, m.status, cats])
        zf.writestr('members.csv', mbuf.getvalue())

        # Sessions
        sbuf = io.StringIO()
        w = csv.writer(sbuf)
        w.writerow(['session_id', 'session_name', 'category', 'date',
                    'start_time', 'end_time', 'venue', 'status'])
        for s in Session.query.all():
            w.writerow([s.session_id, s.session_name,
                        s.category.name if s.category else '',
                        s.date, s.start_time, s.end_time, s.venue, s.status])
        zf.writestr('sessions.csv', sbuf.getvalue())

        # Attendance
        abuf = io.StringIO()
        w = csv.writer(abuf)
        w.writerow(['session_id', 'session_name', 'member_id', 'member_name', 'status', 'marked_at'])
        for a in Attendance.query.all():
            w.writerow([
                a.session.session_id if a.session else '',
                a.session.session_name if a.session else '',
                a.member.member_id if a.member else '',
                a.member.full_name if a.member else '',
                a.status, a.marked_at,
            ])
        zf.writestr('attendance.csv', abuf.getvalue())

        # Users
        ubuf = io.StringIO()
        w = csv.writer(ubuf)
        w.writerow(['username', 'full_name', 'role', 'email', 'status', 'created_at'])
        for u in User.query.all():
            w.writerow([u.username, u.full_name, u.role, u.email, u.status, u.created_at])
        zf.writestr('users.csv', ubuf.getvalue())

        # Categories
        cbuf = io.StringIO()
        w = csv.writer(cbuf)
        w.writerow(['name', 'description', 'status', 'member_count'])
        for c in Category.query.all():
            w.writerow([c.name, c.description, c.status, c.total_member_count])
        zf.writestr('categories.csv', cbuf.getvalue())

        # Session categories
        scbuf = io.StringIO()
        w = csv.writer(scbuf)
        w.writerow(['name', 'description', 'status'])
        for sc in SessionCategory.query.all():
            w.writerow([sc.name, sc.description, sc.status])
        zf.writestr('session_categories.csv', scbuf.getvalue())

    buf.seek(0)
    return buf


class BackupInfo:
    def __init__(self, name, path):
        self.name = name
        self.path = path
        stat = os.stat(path)
        self.size = stat.st_size
        self.date = datetime.fromtimestamp(stat.st_mtime)


@backup_bp.route('/backup')
@login_required
def index():
    if not current_user.has_role('super_admin'):
        flash('Only Super Admin can access backup.', 'danger')
        return redirect(url_for('dashboard.index'))
    backup_dir = get_backup_dir()
    backups = []
    for f in sorted(os.listdir(backup_dir), reverse=True):
        if f.endswith('.zip'):
            backups.append(BackupInfo(f, os.path.join(backup_dir, f)))
    return render_template('backup/index.html', backups=backups)


@backup_bp.route('/backup/create', methods=['POST'])
@login_required
def create():
    if not current_user.has_role('super_admin'):
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))
    try:
        backup_dir = get_backup_dir()
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'heartfulness_backup_{ts}.zip'
        dest = os.path.join(backup_dir, filename)
        buf = _build_csv_zip()
        with open(dest, 'wb') as f:
            f.write(buf.read())
        log_action('Create Backup', f'Database backup created: {filename}')
        flash(f'Backup created successfully: {filename}', 'success')
    except Exception as e:
        flash(f'Backup failed: {str(e)}', 'danger')
    return redirect(url_for('backup.index'))


@backup_bp.route('/backup/download/<filename>')
@login_required
def download(filename):
    if not current_user.has_role('super_admin'):
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))
    backup_dir = get_backup_dir()
    path = os.path.join(backup_dir, filename)
    if not os.path.exists(path):
        flash('Backup file not found.', 'danger')
        return redirect(url_for('backup.index'))
    return send_file(path, as_attachment=True, download_name=filename)


@backup_bp.route('/backup/restore', methods=['POST'])
@login_required
def restore():
    """Restore is not applicable for PostgreSQL on Render.
    Direct users to use the Export CSV and re-import workflow instead."""
    if not current_user.has_role('super_admin'):
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))
    flash('Restore from file is not supported on PostgreSQL. '
          'Use "Export All Data" to download a CSV backup, '
          'then re-import members via the CSV Import feature.', 'warning')
    return redirect(url_for('backup.index'))


@backup_bp.route('/backup/export-csv')
@login_required
def export_all_csv():
    if not current_user.has_role('super_admin'):
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))
    try:
        buf = _build_csv_zip()
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_action('Export Data', 'Exported all data as CSV ZIP')
        return send_file(buf, mimetype='application/zip', as_attachment=True,
                         download_name=f'heartfulness_export_{ts}.zip')
    except Exception as e:
        flash(f'Export failed: {str(e)}', 'danger')
        return redirect(url_for('backup.index'))
