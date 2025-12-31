from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, abort, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_socketio import SocketIO, join_room, leave_room, emit
from datetime import datetime, timedelta
import json
import logging
import os
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'app.db')

app = Flask(__name__)
# Load secret key from env if present
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-this-secret')  # change in production

# Allow overriding DB via DATABASE_URL (useful for MySQL/Postgres in production).
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + DB_PATH

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Basic logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Socket.IO (used to run the app below)
socketio = SocketIO(app)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'student', 'lecturer', 'staff', 'admin'
    batch_id = db.Column(db.Integer, db.ForeignKey('batch.id'), nullable=True)

    @property
    def batch(self):
        if self.batch_id:
            return Batch.query.get(self.batch_id)
        return None

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        return self.role == 'admin'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def seed_admin():
    # Ensure exactly one admin seeded if no users exist
    if User.query.count() == 0:
        admin = User(username='admin', role='admin')
        admin.set_password('adminpass')
        db.session.add(admin)
        db.session.commit()
        logger.info('Seeded admin user: username=admin password=adminpass')


def init_app():
    # Explicit initialization called at startup to be compatible with newer Flask versions
    # Must run inside application context so extensions (SQLAlchemy) can access app settings
    with app.app_context():
        db.create_all()
        seed_admin()
        # create other tables as needed
        db.create_all()


# Optional DB config environment (for informational logging)
DB_CONFIG = {
    'host': os.environ.get('MYSQL_HOST', 'localhost'),
    'user': os.environ.get('MYSQL_USER', ''),
    'password': os.environ.get('MYSQL_PASSWORD', ''),
    'database': os.environ.get('MYSQL_DB', 'app.db')
}


class Batch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    # reverse relation: users


class Exam(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    batch_id = db.Column(db.Integer, db.ForeignKey('batch.id'))
    # The exam is started by the lecturer; window = started_at .. started_at + duration_minutes
    started_at = db.Column(db.DateTime, nullable=True)
    duration_minutes = db.Column(db.Integer, nullable=False, default=30)  # required duration in minutes
    results_published = db.Column(db.Boolean, nullable=False, default=False)


class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exam.id'))
    text = db.Column(db.Text, nullable=False)
    choices = db.Column(db.Text, nullable=False)  # JSON list of choices
    correct = db.Column(db.Integer, nullable=False)  # index into choices


class ExamAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exam.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    started_at = db.Column(db.DateTime, nullable=False)
    finished_at = db.Column(db.DateTime, nullable=True)
    deadline = db.Column(db.DateTime, nullable=True)
    answers = db.Column(db.Text, nullable=True)  # JSON mapping question_id -> choice_index
    events = db.Column(db.Text, nullable=True)  # JSON list of event records (anti-cheat logs)
    score = db.Column(db.Float, nullable=True)
    agent_token = db.Column(db.String(200), nullable=True)  # short-lived token for native agent reporting
    
    # Relationships
    exam = db.relationship('Exam', backref='attempts', foreign_keys=[exam_id])
    user = db.relationship('User', backref='attempts', foreign_keys=[user_id])



def admin_required(func):
    from functools import wraps

    @wraps(func)
    def decorated_view(*args, **kwargs):
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        if not getattr(current_user, 'role', None) == 'admin':
            flash('Admin access required', 'danger')
            return redirect(url_for('index'))
        return func(*args, **kwargs)

    return decorated_view


def lecturer_required(func):
    from functools import wraps

    @wraps(func)
    def decorated_view(*args, **kwargs):
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        # Allow lecturers, staff, and admins to access lecturer routes
        if getattr(current_user, 'role', None) not in ('lecturer', 'staff', 'admin'):
            flash('Lecturer access required', 'danger')
            return redirect(url_for('index'))
        return func(*args, **kwargs)

    return decorated_view


@app.route('/')
@login_required
def index():
    # Role-specific home dashboard
    role = getattr(current_user, 'role', None)
    now = datetime.now()
    if role == 'admin':
        students = User.query.filter_by(role='student').all()
        lecturers = User.query.filter_by(role='lecturer').all()
        return render_template('index.html', role='admin', students=students, lecturers=lecturers)

    if role == 'lecturer':
        exams = Exam.query.filter_by(creator_id=current_user.id).all()
        exams_info = []
        for e in exams:
            if e.started_at:
                window_end = e.started_at + timedelta(minutes=int(e.duration_minutes))
                if now < e.started_at:
                    status = 'not_started'
                elif e.started_at <= now <= window_end:
                    status = 'started'
                else:
                    status = 'finished'
            else:
                status = 'not_started'
                window_end = None
            # show only exams that are active or can be started (not finished)
            if status != 'finished':
                exams_info.append({'exam': e, 'status': status, 'started_at': e.started_at, 'window_end': window_end})
        return render_template('index.html', role='lecturer', exams=exams_info, now=now)

    if role == 'student':
        # student sees welcome + rules and any active exams for their batch
        active_exams = []
        if current_user.batch_id:
            exams = Exam.query.filter(Exam.batch_id == current_user.batch_id).all()
            for e in exams:
                if e.started_at:
                    window_end = e.started_at + timedelta(minutes=int(e.duration_minutes))
                    if e.started_at <= now <= window_end:
                        active_exams.append({'exam': e, 'started_at': e.started_at, 'window_end': window_end})

        rules = [
            'No use of external resources unless permitted.',
            'Do not switch windows during the exam.',
            'Do not communicate with other students.',
            'Submit only once; you cannot retake after submission.'
        ]
        return render_template('index.html', role='student', active_exams=active_exams, rules=rules)

    # default: generic welcome
    return render_template('index.html', role=role)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash('Logged in successfully.', 'success')
            next_page = request.args.get('next') or url_for('index')
            return redirect(next_page)
        flash('Invalid credentials', 'danger')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out', 'info')
    return redirect(url_for('index'))


@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    users = User.query.all()
    return render_template('admin.html', users=users)


@app.route('/admin/add_user', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role')

        if not username or not password or not role:
            flash('All fields are required', 'warning')
            return redirect(url_for('add_user'))

        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return redirect(url_for('add_user'))

        # Enforce single admin user
        if role == 'admin':
            existing_admin = User.query.filter_by(role='admin').first()
            if existing_admin:
                flash('An admin user already exists. Only one admin is allowed.', 'danger')
                return redirect(url_for('add_user'))

        user = User(username=username, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash(f'User {username} created with role {role}', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('add_user.html')


@app.route('/admin/batches', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_batches():
    if request.method == 'POST':
        name = request.form.get('name')
        if name:
            if Batch.query.filter_by(name=name).first():
                flash('Batch already exists', 'warning')
            else:
                b = Batch(name=name)
                db.session.add(b)
                db.session.commit()
                flash('Batch created', 'success')
        return redirect(url_for('manage_batches'))

    batches = Batch.query.all()
    return render_template('manage_batches.html', batches=batches)


@app.route('/admin/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        role = request.form.get('role')
        password = request.form.get('password')
        batch_id = request.form.get('batch_id')

        # If changing to admin, ensure another admin doesn't already exist (unless editing that admin)
        if role == 'admin':
            existing_admin = User.query.filter_by(role='admin').first()
            if existing_admin and existing_admin.id != user.id:
                flash('An admin user already exists. Only one admin is allowed.', 'danger')
                return redirect(url_for('edit_user', user_id=user.id))

        # Update password if provided
        if password:
            user.set_password(password)
        user.role = role
        # assign or clear batch for students
        try:
            if role == 'student' and batch_id:
                user.batch_id = int(batch_id)
            else:
                user.batch_id = None
        except ValueError:
            user.batch_id = None
        db.session.commit()
        flash(f'User {user.username} updated', 'success')
        return redirect(url_for('admin_dashboard'))

    batches = Batch.query.all()
    return render_template('edit_user.html', user=user, batches=batches)


@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    # Prevent deleting self
    if current_user.id == user.id:
        flash('You cannot delete your own account while logged in.', 'warning')
        return redirect(url_for('admin_dashboard'))

    # Prevent deleting the only admin
    if user.role == 'admin':
        flash('Deleting the admin user is not allowed.', 'danger')
        return redirect(url_for('admin_dashboard'))

    db.session.delete(user)
    db.session.commit()
    flash(f'User {user.username} deleted', 'info')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/change_my_password', methods=['GET', 'POST'])
@login_required
@admin_required
def change_own_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if not current_user.check_password(current_password):
            flash('Current password is incorrect', 'danger')
            return redirect(url_for('change_own_password'))

        if new_password != confirm_password:
            flash('New passwords do not match', 'warning')
            return redirect(url_for('change_own_password'))

        current_user.set_password(new_password)
        db.session.commit()
        flash('Password updated successfully', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('change_own_password.html')


@app.route('/admin/export_users')
@login_required
@admin_required
def export_users():
    import csv
    from io import StringIO
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['id', 'username', 'role'])
    for u in User.query.all():
        cw.writerow([u.id, u.username, u.role])
    output = si.getvalue()
    from flask import make_response
    resp = make_response(output)
    resp.headers['Content-Type'] = 'text/csv'
    resp.headers['Content-Disposition'] = 'attachment; filename=users.csv'
    return resp


@app.route('/teacher/exams')
@login_required
@lecturer_required
def teacher_exams():
    now = datetime.now()
    # lecturers see their own exams; staff and admin may view all exams
    if getattr(current_user, 'role', None) in ('staff', 'admin'):
        exams = Exam.query.all()
    else:
        exams = Exam.query.filter_by(creator_id=current_user.id).all()
    exams_info = []
    for e in exams:
        if e.started_at:
            window_end = e.started_at + timedelta(minutes=int(e.duration_minutes))
            if now < e.started_at:
                status = 'not_started'
            elif e.started_at <= now <= window_end:
                status = 'started'
            else:
                status = 'finished'
        else:
            status = 'not_started'
            window_end = None
        exams_info.append({'exam': e, 'status': status, 'started_at': e.started_at, 'window_end': window_end})
    return render_template('teacher_exams.html', exams=exams_info, now=now)


@app.route('/teacher/exam/<int:exam_id>/attempts')
@login_required
@lecturer_required
def teacher_exam_attempts(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    # Only the exam creator (lecturer) or admin may view attempts; staff are not allowed here
    role = getattr(current_user, 'role', None)
    if role == 'staff':
        flash('Not authorized', 'danger')
        return redirect(url_for('teacher_exams'))
    if exam.creator_id != current_user.id and current_user.role != 'admin':
        flash('Not authorized', 'danger')
        return redirect(url_for('teacher_exams'))
    # finalize any attempts that have passed their deadline before listing
    finalize_all_attempts_for_exam(exam)
    attempts = ExamAttempt.query.filter_by(exam_id=exam.id).all()
    # attach user if possible
    for a in attempts:
        try:
            a.user = User.query.get(a.user_id)
        except Exception:
            a.user = None
    return render_template('teacher_attempts.html', exam=exam, attempts=attempts)


@app.route('/teacher/attempt/<int:attempt_id>')
@login_required
@lecturer_required
def view_attempt(attempt_id):
    attempt = ExamAttempt.query.get_or_404(attempt_id)
    exam = Exam.query.get_or_404(attempt.exam_id)
    # Only the exam creator (lecturer) or admin may view individual attempts; staff are not allowed here
    role = getattr(current_user, 'role', None)
    if role == 'staff':
        flash('Not authorized', 'danger')
        return redirect(url_for('teacher_exams'))
    if exam.creator_id != current_user.id and current_user.role != 'admin':
        flash('Not authorized', 'danger')
        return redirect(url_for('teacher_exams'))
    # ensure attempts past deadline are finalized before viewing
    try:
        finalize_attempt(attempt)
    except NameError:
        # finalize_attempt will be defined below; if not yet, we'll skip
        pass

    # prepare questions and answers mapping
    raw_questions = Question.query.filter_by(exam_id=exam.id).all()
    questions = []
    for q in raw_questions:
        try:
            choices = json.loads(q.choices)
        except Exception:
            choices = []
        questions.append({'id': q.id, 'text': q.text, 'choices': choices, 'correct': q.correct})
    answers = {}
    try:
        if attempt.answers:
            answers = json.loads(attempt.answers)
    except Exception:
        answers = {}
    attempt_user = None
    try:
        attempt_user = User.query.get(attempt.user_id)
    except Exception:
        attempt_user = None
    can_mark = (current_user.role in ('lecturer', 'admin') and exam.creator_id == current_user.id)
    return render_template('attempt_view.html', exam=exam, attempt=attempt, questions=questions, answers=answers, attempt_user=(attempt_user.username if attempt_user else attempt.user_id), can_mark=can_mark)


@app.route('/teacher/attempt/<int:attempt_id>/events')
@login_required
def view_attempt_events(attempt_id):
    attempt = ExamAttempt.query.get_or_404(attempt_id)
    exam = Exam.query.get_or_404(attempt.exam_id)

    # authorization: allow examiner (creator), staff, or admin
    role = getattr(current_user, 'role', None)
    if role == 'lecturer':
        if exam.creator_id != current_user.id and current_user.role != 'admin':
            flash('Not authorized', 'danger')
            return redirect(url_for('teacher_exams'))
    elif role == 'staff' or role == 'admin':
        # staff and admin may view
        pass
    else:
        flash('Not authorized', 'danger')
        return redirect(url_for('index'))

    # parse events JSON
    records = []
    try:
        records = json.loads(attempt.events) if attempt.events else []
    except Exception:
        records = []

    # export CSV if requested
    if request.args.get('export') == 'csv':
        import csv
        from io import StringIO
        si = StringIO()
        cw = csv.writer(si)
        cw.writerow(['index', 'timestamp', 'event', 'data', 'ip', 'user_agent'])
        for i, r in enumerate(records, start=1):
            cw.writerow([i, r.get('ts'), r.get('event'), json.dumps(r.get('data') or {}), r.get('ip'), r.get('ua')])
        from flask import make_response
        resp = make_response(si.getvalue())
        resp.headers['Content-Type'] = 'text/csv'
        resp.headers['Content-Disposition'] = f'attachment; filename=attempt_{attempt.id}_events.csv'
        return resp

    return render_template('attempt_events.html', attempt=attempt, exam=exam, records=records)


@app.route('/teacher/attempt/<int:attempt_id>/live')
@login_required
def live_attempt_events(attempt_id):
    attempt = ExamAttempt.query.get_or_404(attempt_id)
    exam = Exam.query.get_or_404(attempt.exam_id)

    # authorization: allow examiner (creator), staff, or admin
    role = getattr(current_user, 'role', None)
    if role == 'lecturer':
        if exam.creator_id != current_user.id and current_user.role != 'admin':
            flash('Not authorized', 'danger')
            return redirect(url_for('teacher_exams'))
    elif role == 'staff' or role == 'admin':
        pass
    else:
        flash('Not authorized', 'danger')
        return redirect(url_for('index'))

    # load existing records for initial display
    records = []
    try:
        records = json.loads(attempt.events) if attempt.events else []
    except Exception:
        records = []

    return render_template('live_attempt_events.html', attempt=attempt, exam=exam, records=records)


@app.route('/staff/live_attempts')
@login_required
def staff_live_attempts():
    # only staff and admin allowed
    role = getattr(current_user, 'role', None)
    if role not in ('staff', 'admin'):
        flash('Not authorized', 'danger')
        return redirect(url_for('index'))

    # find active attempts (not finished and within deadline if any)
    now = datetime.now()
    attempts = []
    for a in ExamAttempt.query.filter_by().all():
        if a.finished_at:
            continue
        # if deadline set and passed, skip (finalized elsewhere)
        if a.deadline and now > a.deadline:
            continue
        # attach related user/exam for display
        try:
            a.user = User.query.get(a.user_id)
        except Exception:
            a.user = None
        try:
            a.exam = Exam.query.get(a.exam_id)
        except Exception:
            a.exam = None
        attempts.append(a)

    return render_template('staff_live_list.html', attempts=attempts)


@app.route('/staff/live_all')
@login_required
def staff_live_all():
    role = getattr(current_user, 'role', None)
    if role not in ('staff', 'admin'):
        flash('Not authorized', 'danger')
        return redirect(url_for('index'))
    return render_template('staff_live_all.html')


@app.route('/teacher/attempt/<int:attempt_id>/mark', methods=['POST'])
@login_required
@lecturer_required
def mark_attempt(attempt_id):
    attempt = ExamAttempt.query.get_or_404(attempt_id)
    exam = Exam.query.get_or_404(attempt.exam_id)
    # Only the exam creator (lecturer) or admin may mark; staff are not allowed to mark
    role = getattr(current_user, 'role', None)
    if role == 'staff':
        flash('Not authorized', 'danger')
        return redirect(url_for('teacher_exams'))
    if exam.creator_id != current_user.id and current_user.role != 'admin':
        flash('Not authorized', 'danger')
        return redirect(url_for('teacher_exams'))
    # parse manual score
    score_raw = request.form.get('score')
    try:
        score = float(score_raw)
    except Exception:
        flash('Invalid score value', 'warning')
        return redirect(url_for('view_attempt', attempt_id=attempt.id))
    attempt.score = score
    # allow lecturer to mark finished now
    if not attempt.finished_at:
        attempt.finished_at = datetime.now()
    db.session.commit()
    flash('Attempt marked/updated', 'success')
    return redirect(url_for('view_attempt', attempt_id=attempt.id))


@app.route('/teacher/create_exam', methods=['GET', 'POST'])
@login_required
@lecturer_required
def create_exam():
    # staff are not allowed to create exams
    if getattr(current_user, 'role', None) == 'staff':
        flash('Not authorized to create exams', 'danger')
        return redirect(url_for('teacher_exams'))
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        batch_id = request.form.get('batch_id')
        duration_raw = request.form.get('duration_minutes')
        if not title or not batch_id:
            flash('Title and batch are required', 'warning')
            return redirect(url_for('create_exam'))

        # duration is required and is the per-student duration in minutes
        duration_minutes = None
        if duration_raw:
            try:
                duration_minutes = int(duration_raw)
            except ValueError:
                duration_minutes = None
        if not duration_minutes or duration_minutes <= 0:
            flash('Valid duration (minutes) is required', 'warning')
            return redirect(url_for('create_exam'))

        # exam starts when the lecturer explicitly starts it (started_at == None initially)
        exam = Exam(title=title, description=description, creator_id=current_user.id,
                    batch_id=int(batch_id), started_at=None,
                    duration_minutes=duration_minutes)
        db.session.add(exam)
        db.session.commit()
        flash('Exam created', 'success')
        return redirect(url_for('teacher_exams'))

    batches = Batch.query.all()
    return render_template('create_exam.html', batches=batches)



@app.route('/image/<path:filename>')
def image_file(filename):
    # serve image assets located in the project's `image/` folder
    image_dir = os.path.join(BASE_DIR, 'image')
    return send_from_directory(image_dir, filename)


@app.route('/teacher/exam/<int:exam_id>/add_question', methods=['GET', 'POST'])
@login_required
@lecturer_required
def add_question(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    # Allow owners (lecturers), admin, and staff to add questions; other roles not allowed
    role = getattr(current_user, 'role', None)
    if role == 'lecturer':
        if exam.creator_id != current_user.id and current_user.role != 'admin':
            flash('Not authorized', 'danger')
            return redirect(url_for('teacher_exams'))
    elif role == 'staff' or role == 'admin':
        # staff and admin may add questions for any exam
        pass
    else:
        flash('Not authorized', 'danger')
        return redirect(url_for('index'))

    if request.method == 'POST':
        text = request.form.get('text')
        choices_raw = request.form.get('choices')
        correct = request.form.get('correct')
        if not text or not choices_raw or correct is None:
            flash('All fields are required', 'warning')
            return redirect(url_for('add_question', exam_id=exam.id))
        choices = [c.strip() for c in choices_raw.splitlines() if c.strip()]
        try:
            correct_idx = int(correct)
        except ValueError:
            flash('Correct index must be a number (0-based)', 'danger')
            return redirect(url_for('add_question', exam_id=exam.id))
        if correct_idx < 0 or correct_idx >= len(choices):
            flash('Correct index out of range', 'danger')
            return redirect(url_for('add_question', exam_id=exam.id))

        q = Question(exam_id=exam.id, text=text, choices=json.dumps(choices), correct=correct_idx)
        db.session.add(q)
        db.session.commit()
        flash('Question added', 'success')
        return redirect(url_for('teacher_exams'))

    return render_template('add_question.html', exam=exam)


@app.route('/teacher/exam/<int:exam_id>/manage_questions', methods=['GET', 'POST'])
@login_required
@lecturer_required
def manage_questions(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    # Allow owners (lecturers), admin, and staff to manage questions; other roles not allowed
    role = getattr(current_user, 'role', None)
    if role == 'lecturer':
        if exam.creator_id != current_user.id and current_user.role != 'admin':
            flash('Not authorized', 'danger')
            return redirect(url_for('teacher_exams'))
    elif role == 'staff' or role == 'admin':
        # staff and admin may manage questions for any exam
        pass
    else:
        flash('Not authorized', 'danger')
        return redirect(url_for('index'))

    if request.method == 'POST':
        op = request.form.get('op')
        if op == 'add':
            text = request.form.get('text')
            choices_raw = request.form.get('choices')
            correct = request.form.get('correct')
            if not text or not choices_raw or correct is None:
                flash('All fields are required', 'warning')
                return redirect(url_for('manage_questions', exam_id=exam.id))
            choices = [c.strip() for c in choices_raw.splitlines() if c.strip()]
            try:
                correct_idx = int(correct)
            except ValueError:
                flash('Correct index must be a number (0-based)', 'danger')
                return redirect(url_for('manage_questions', exam_id=exam.id))
            if correct_idx < 0 or correct_idx >= len(choices):
                flash('Correct index out of range', 'danger')
                return redirect(url_for('manage_questions', exam_id=exam.id))
            q = Question(exam_id=exam.id, text=text, choices=json.dumps(choices), correct=correct_idx)
            db.session.add(q)
            db.session.commit()
            flash('Question added', 'success')
            return redirect(url_for('manage_questions', exam_id=exam.id))

        if op == 'edit':
            qid = request.form.get('question_id')
            q = Question.query.get_or_404(qid)
            text = request.form.get('text')
            choices_raw = request.form.get('choices')
            correct = request.form.get('correct')
            choices = [c.strip() for c in choices_raw.splitlines() if c.strip()]
            try:
                correct_idx = int(correct)
            except ValueError:
                correct_idx = 0
            q.text = text
            q.choices = json.dumps(choices)
            q.correct = correct_idx
            db.session.commit()
            flash('Question updated', 'success')
            return redirect(url_for('manage_questions', exam_id=exam.id))

        if op == 'delete':
            qid = request.form.get('question_id')
            q = Question.query.get_or_404(qid)
            db.session.delete(q)
            db.session.commit()
            flash('Question deleted', 'info')
            return redirect(url_for('manage_questions', exam_id=exam.id))

    raw_questions = Question.query.filter_by(exam_id=exam.id).all()
    questions = []
    for q in raw_questions:
        try:
            choices_list = json.loads(q.choices)
        except Exception:
            choices_list = []
        questions.append({'id': q.id, 'text': q.text, 'choices_list': choices_list, 'correct': q.correct})
    return render_template('manage_questions.html', exam=exam, questions=questions)


def grade_attempt(attempt):
    # compute score from stored answers (answers is JSON mapping question_id->choice_index)
    try:
        answers = json.loads(attempt.answers) if attempt.answers else {}
    except Exception:
        answers = {}
    total = 0
    correct = 0
    for q in Question.query.filter_by(exam_id=attempt.exam_id).all():
        total += 1
        ans = answers.get(str(q.id))
        try:
            if ans is not None and int(ans) == int(q.correct):
                correct += 1
        except Exception:
            pass
    attempt.score = (correct / total * 100.0) if total > 0 else 0.0


def force_finalize_attempt(attempt):
    # Force finalize an attempt immediately and grade it
    if attempt.finished_at:
        return
    attempt.finished_at = datetime.now()
    try:
        grade_attempt(attempt)
    except Exception:
        attempt.score = attempt.score or 0.0
    db.session.commit()


def finalize_attempt(attempt):
    # If an attempt passed its deadline and is not finished, finalize and grade it
    if attempt.finished_at:
        return
    now = datetime.now()
    if attempt.deadline and now > attempt.deadline:
        attempt.finished_at = attempt.deadline
        grade_attempt(attempt)
        db.session.commit()


def finalize_all_attempts_for_exam(exam):
    for a in ExamAttempt.query.filter_by(exam_id=exam.id).all():
        finalize_attempt(a)


@app.route('/teacher/exam/<int:exam_id>/start', methods=['POST'])
@login_required
def start_exam_by_teacher(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    role = getattr(current_user, 'role', None)
    # allow lecturer (owner), staff, or admin to start the exam
    if role == 'lecturer':
        if exam.creator_id != current_user.id and current_user.role != 'admin':
            flash('Not authorized', 'danger')
            return redirect(url_for('teacher_exams'))
    elif role in ('staff', 'admin'):
        # staff/admin may start any exam
        pass
    else:
        flash('Not authorized', 'danger')
        return redirect(url_for('index'))

    if exam.started_at:
        flash('Exam already started', 'info')
        return redirect(url_for('teacher_exams'))
    exam.started_at = datetime.now()
    db.session.commit()
    flash('Exam started for students', 'success')
    return redirect(url_for('teacher_exams'))


@app.route('/teacher/exam/<int:exam_id>/publish', methods=['POST'])
@login_required
@lecturer_required
def publish_results(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    # only exam creator (lecturer) or admin may publish
    if current_user.role == 'lecturer' and exam.creator_id != current_user.id and current_user.role != 'admin':
        flash('Not authorized', 'danger')
        return redirect(url_for('teacher_exams'))
    # toggle publish value
    new = request.form.get('publish')
    try:
        if new in ('1', 'true', 'True'):
            exam.results_published = True
        else:
            exam.results_published = False
        db.session.commit()
        flash('Results publish status updated', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Failed to update publish status', 'danger')
    return redirect(url_for('teacher_exams'))


@app.route('/student/exams')
@login_required
def student_exams():
    if current_user.role != 'student':
        flash('Student access required', 'warning')
        return redirect(url_for('index'))
    now = datetime.now()
    exams = []
    if current_user.batch_id:
        exams = Exam.query.filter(Exam.batch_id == current_user.batch_id).all()
    exams_info = []
    for e in exams:
        # determine status based on lecturer start and window
        if e.started_at:
            window_end = e.started_at + timedelta(minutes=int(e.duration_minutes))
            if now < e.started_at:
                status = 'not_started'
            elif e.started_at <= now <= window_end:
                status = 'started'
            else:
                status = 'finished'
        else:
            status = 'not_started'
            window_end = None

        # check if the current student already has an attempt for this exam
        existing_attempt = ExamAttempt.query.filter_by(exam_id=e.id, user_id=current_user.id).order_by(ExamAttempt.id.desc()).first()
        attempt_exists = bool(existing_attempt)
        attempt_id = existing_attempt.id if existing_attempt else None
        attempt_finished = bool(existing_attempt.finished_at) if existing_attempt else False

        # student can start only if window is open and they have no prior attempt
        can_start = (status == 'started' and not attempt_exists)

        exams_info.append({'exam': e, 'status': status, 'can_start': can_start, 'started_at': e.started_at, 'window_end': window_end, 'attempt_exists': attempt_exists, 'attempt_id': attempt_id, 'attempt_finished': attempt_finished})
    return render_template('student_exams.html', exams=exams_info, now=now)


@app.route('/student/results')
@login_required
def student_results():
    if current_user.role != 'student':
        flash('Student access required', 'warning')
        return redirect(url_for('index'))
    # get all attempts for this student
    attempts = ExamAttempt.query.filter_by(user_id=current_user.id).order_by(ExamAttempt.started_at.desc()).all()
    enriched = []
    for a in attempts:
        try:
            exam = Exam.query.get(a.exam_id)
        except Exception:
            exam = None
        # Check if exam was terminated
        is_terminated = False
        if a.events:
            try:
                events_data = json.loads(a.events)
                for event in events_data:
                    if 'exam_terminated_by_staff' in event.get('event', ''):
                        is_terminated = True
                        break
            except Exception:
                pass
        enriched.append({'attempt': a, 'exam': exam, 'is_terminated': is_terminated})
    return render_template('student_results.html', attempts=enriched)


@app.route('/student/start_exam/<int:exam_id>', methods=['POST'])
@login_required
def start_exam(exam_id):
    if current_user.role != 'student':
        flash('Student access required', 'warning')
        return redirect(url_for('index'))
    exam = Exam.query.get_or_404(exam_id)
    now = datetime.now()
    # exam must have been started by the lecturer
    if not exam.started_at or now < exam.started_at:
        flash('Exam not currently available (lecturer has not started it yet)', 'danger')
        return redirect(url_for('student_exams'))
    # Prevent multiple attempts: if the student already has an attempt, handle accordingly
    existing_attempt = ExamAttempt.query.filter_by(exam_id=exam.id, user_id=current_user.id).order_by(ExamAttempt.id.desc()).first()
    if existing_attempt:
        # If they already submitted (finished_at set), disallow retry
        if existing_attempt.finished_at:
            flash('You have already submitted this exam and cannot retake it.', 'info')
            return redirect(url_for('student_exams'))
        # If they have an unfinished attempt, redirect them to resume it
        flash('Resuming your in-progress attempt.', 'info')
        return redirect(url_for('take_exam', attempt_id=existing_attempt.id))

    # create a new attempt
    attempt = ExamAttempt(exam_id=exam.id, user_id=current_user.id, started_at=now)
    # If exam has a per-student duration, set a deadline on the attempt
    if exam.duration_minutes:
        attempt.deadline = now + timedelta(minutes=int(exam.duration_minutes))
    else:
        attempt.deadline = None
    # generate a short-lived token students can use with a native monitoring agent
    try:
        attempt.agent_token = secrets.token_urlsafe(18)
    except Exception:
        attempt.agent_token = None
    db.session.add(attempt)
    db.session.commit()
    return redirect(url_for('take_exam', attempt_id=attempt.id))


@app.route('/student/take/<int:attempt_id>', methods=['GET', 'POST'])
@login_required
def take_exam(attempt_id):
    attempt = ExamAttempt.query.get_or_404(attempt_id)
    exam = Exam.query.get_or_404(attempt.exam_id)
    if attempt.user_id != current_user.id:
        flash('Not authorized', 'danger')
        return redirect(url_for('student_exams'))
    if request.method == 'POST':
        # prevent re-submitting a finished attempt
        if attempt.finished_at:
            flash('This attempt has already been submitted.', 'info')
            return redirect(url_for('student_exams'))

        # collect answers
        answers = {}
        for q in Question.query.filter_by(exam_id=exam.id).all():
            val = request.form.get(f'question_{q.id}')
            try:
                answers[str(q.id)] = int(val) if val is not None else None
            except ValueError:
                answers[str(q.id)] = None

        # grade
        total = 0
        correct = 0
        for q in Question.query.filter_by(exam_id=exam.id).all():
            total += 1
            ans = answers.get(str(q.id))
            if ans is not None and ans == q.correct:
                correct += 1

        score = (correct / total * 100.0) if total > 0 else 0.0
        attempt.answers = json.dumps(answers)
        # if deadline exists and we're past it, set finished_at to the deadline; else now
        now = datetime.now()
        if attempt.deadline and now > attempt.deadline:
            attempt.finished_at = attempt.deadline
        else:
            attempt.finished_at = now
        attempt.score = score
        db.session.commit()
        flash(f'Exam submitted. Score: {score:.2f}%', 'success')
        return redirect(url_for('student_exams'))

    # GET: show exam with questions and timer
    raw_questions = Question.query.filter_by(exam_id=exam.id).all()
    questions = []
    for q in raw_questions:
        try:
            choices = json.loads(q.choices)
        except Exception:
            choices = []
        questions.append({'id': q.id, 'text': q.text, 'choices': choices, 'correct': q.correct})
    # compute deadline for this attempt (use attempt.deadline if set)
    deadline = attempt.deadline
    try:
        deadline_ts = int(deadline.timestamp() * 1000)
    except Exception:
        deadline_ts = None
    # load saved answers (if any) so template can pre-select
    saved_answers = {}
    try:
        if attempt.answers:
            saved_answers = json.loads(attempt.answers)
    except Exception:
        saved_answers = {}

    # compute ms timestamps for template (avoid calling Python builtins inside Jinja)
    try:
        started_at_ms = int(attempt.started_at.timestamp() * 1000) if attempt and attempt.started_at else None
    except Exception:
        started_at_ms = None
    try:
        lecturer_started_ms = int(exam.started_at.timestamp() * 1000) if exam and exam.started_at else None
    except Exception:
        lecturer_started_ms = None

    # Ensure agent_token is set for the attempt
    if not attempt.agent_token:
        try:
            attempt.agent_token = secrets.token_urlsafe(18)
            db.session.commit()
        except Exception:
            attempt.agent_token = None

    return render_template('take_exam.html', exam=exam, attempt=attempt, questions=questions, deadline=deadline, deadline_ts=deadline_ts, saved_answers=saved_answers, started_at_ms=started_at_ms, lecturer_started_ms=lecturer_started_ms)


@app.route('/student/save_attempt/<int:attempt_id>', methods=['POST'])
@login_required
def save_attempt(attempt_id):
    attempt = ExamAttempt.query.get_or_404(attempt_id)
    if attempt.user_id != current_user.id:
        return {'status': 'error', 'message': 'Not authorized'}, 403
    # Accept JSON payload or form-encoded data
    payload = None
    try:
        payload = request.get_json(silent=True)
    except Exception:
        payload = None
    answers = None
    if payload and 'answers' in payload:
        answers = payload['answers']
    else:
        # collect from form fields
        answers = {}
        for q in Question.query.filter_by(exam_id=attempt.exam_id).all():
            val = request.form.get(f'question_{q.id}')
            try:
                answers[str(q.id)] = int(val) if val is not None else None
            except Exception:
                answers[str(q.id)] = None
    # store partial answers
    try:
        attempt.answers = json.dumps(answers)
        db.session.commit()
        return {'status': 'ok'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}, 500


@app.route('/student/report_event/<int:attempt_id>', methods=['POST'])
@login_required
def report_event(attempt_id):
    attempt = ExamAttempt.query.get_or_404(attempt_id)
    if attempt.user_id != current_user.id:
        return {'status': 'error', 'message': 'Not authorized'}, 403

    payload = request.get_json(silent=True) or {}
    event = payload.get('event') or 'unknown'
    data = payload.get('data') or {}

    # build event record
    rec = {
        'ts': datetime.now().isoformat(),
        'event': event,
        'data': data,
        'ip': request.remote_addr,
        'ua': request.headers.get('User-Agent'),
        'source': 'browser'
    }

    # append to attempt.events (JSON list)
    try:
        existing = json.loads(attempt.events) if attempt.events else []
    except Exception:
        existing = []
    existing.append(rec)
    attempt.events = json.dumps(existing)
    db.session.commit()

    # Emit this event to any live monitors subscribed to this attempt
    try:
        room = f'attempt_{attempt.id}'
        socketio.emit('attempt_event', {'attempt_id': attempt.id, 'record': rec}, room=room)
        # also emit to global staff room for live monitoring across all attempts
        socketio.emit('attempt_event_all', {'attempt_id': attempt.id, 'record': rec}, room='all_attempts')
    except Exception:
        logger.exception('Failed to emit socket event')

    # certain events should force finish (e.g., leaving fullscreen)
    if event in ('fullscreen_exit', 'forced_exit'):
        force_finalize_attempt(attempt)
        return {'status': 'finished', 'message': 'Attempt finalized due to anti-cheat trigger'}

    return {'status': 'ok'}


@app.route('/student/force_finish/<int:attempt_id>', methods=['POST'])
@login_required
def force_finish(attempt_id):
    attempt = ExamAttempt.query.get_or_404(attempt_id)
    if attempt.user_id != current_user.id:
        return {'status': 'error', 'message': 'Not authorized'}, 403
    force_finalize_attempt(attempt)
    return {'status': 'ok', 'message': 'Finalized'}


@app.route('/agent/report_event', methods=['POST'])
def agent_report_event():
    """Endpoint for native agent reporting. Expects JSON: {attempt_id, token, event, data}
    This endpoint is unauthenticated but requires the attempt-specific token to match.
    """
    payload = request.get_json(silent=True) or {}
    attempt_id = payload.get('attempt_id')
    token = payload.get('token')
    event = payload.get('event') or 'agent_unknown'
    data = payload.get('data') or {}

    if not attempt_id or not token:
        return {'status': 'error', 'message': 'attempt_id and token required'}, 400

    try:
        attempt = ExamAttempt.query.get(int(attempt_id))
    except Exception:
        return {'status': 'error', 'message': 'invalid attempt_id'}, 400

    if not attempt or not attempt.agent_token or token != attempt.agent_token:
        return {'status': 'error', 'message': 'invalid token'}, 403

    # build record
    rec = {
        'ts': datetime.now().isoformat(),
        'event': event,
        'data': data,
        'ip': request.remote_addr,
        'ua': request.headers.get('User-Agent'),
        'source': 'agent'
    }

    # append and commit
    try:
        existing = json.loads(attempt.events) if attempt.events else []
    except Exception:
        existing = []
    existing.append(rec)
    attempt.events = json.dumps(existing)
    db.session.commit()

    # emit to live monitors as well
    try:
        room = f'attempt_{attempt.id}'
        socketio.emit('attempt_event', {'attempt_id': attempt.id, 'record': rec}, room=room)
        socketio.emit('attempt_event_all', {'attempt_id': attempt.id, 'record': rec}, room='all_attempts')
    except Exception:
        logger.exception('emit failed')

    return {'status': 'ok'}


def load_attempt_records(attempt_id):
    """Load all activity records for an attempt"""
    attempt = ExamAttempt.query.get_or_404(attempt_id)
    
    # Load records from the database (stored in attempt.events as JSON)
    records = []
    try:
        if attempt.events:
            records = json.loads(attempt.events)
    except Exception:
        records = []
    
    return records

@app.route('/exam/<int:exam_id>/ai-alerts')
@login_required
def exam_ai_alerts(exam_id):
    if current_user.role not in ['lecturer', 'admin', 'staff']:
        abort(403)
    
    exam = Exam.query.get_or_404(exam_id)
    
    # Get all attempts for this exam
    attempts = ExamAttempt.query.filter_by(exam_id=exam_id).all()
    
    alerts = []
    for attempt in attempts:
        # Analyze logs for suspicious activity
        analysis = analyze_attempt_logs(attempt.id)
        if analysis['is_suspicious']:
            alerts.append({
                'id': attempt.id,
                'attempt_id': attempt.id,
                'student_id': attempt.user_id,
                'student_name': attempt.user.username if attempt.user else f"User {attempt.user_id}",
                'severity': analysis['severity'],
                'violation_type': analysis['violation_type'],
                'description': analysis['description'],
                'activities': analysis['activities'],
                'timestamp': attempt.started_at,
                'reviewed': False,
                'notes': None
            })
    
    # Sort by severity
    severity_order = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
    alerts.sort(key=lambda x: severity_order.get(x['severity'], 4))
    
    # Calculate statistics
    stats = {
        'critical': sum(1 for a in alerts if a['severity'] == 'CRITICAL'),
        'high': sum(1 for a in alerts if a['severity'] == 'HIGH'),
        'medium': sum(1 for a in alerts if a['severity'] == 'MEDIUM'),
        'total_students': len(attempts)
    }
    
    return render_template('exam_ai_alerts.html', 
                         exam=exam, 
                         alerts=alerts, 
                         stats=stats)

def analyze_attempt_logs(attempt_id):
    """AI-based analysis of exam attempt logs"""
    records = load_attempt_records(attempt_id)
    
    # Count violations
    violations = {
        'fullscreen_exit': 0,
        'window_blur': 0,
        'window_hidden': 0,
        'shortcut_blocked': 0,
        'tab_switch': 0
    }
    
    activities = []
    
    for record in records:
        event = record.get('event', '').lower()
        data = record.get('data', {})
        
        # Check for fullscreen exit
        if 'fullscreen' in event and ('exit' in event or 'change' in event):
            violations['fullscreen_exit'] += 1
        # Check for window blur (tab switching)
        if 'blur' in event:
            violations['window_blur'] += 1
        # Check for window hidden (tab switching/minimizing)
        if 'hidden' in event:
            violations['window_hidden'] += 1
        # Check for shortcut blocked (screenshot attempts, Windows key, cheating shortcuts)
        if 'shortcut' in event and 'blocked' in event:
            violations['shortcut_blocked'] += 1
    
    # Detect tab switching patterns (blur followed by focus)
    for i in range(len(records) - 1):
        curr_event = records[i].get('event', '').lower()
        next_event = records[i+1].get('event', '').lower()
        if 'blur' in curr_event and 'focus' in next_event:
            violations['tab_switch'] += 1
    
    # Determine severity and create description
    is_suspicious = False
    severity = 'LOW'
    violation_type = 'Normal Activity'
    description = 'No suspicious activity detected.'
    
    # Critical violations - Fullscreen exits
    if violations['fullscreen_exit'] >= 1:
        is_suspicious = True
        severity = 'CRITICAL'
        violation_type = '🚫 Fullscreen Exit Detected'
        description = f'Student exited fullscreen mode {violations["fullscreen_exit"]} time(s), indicating possible exam window closure or switching to other applications.'
        activities.append({
            'event': 'FULLSCREEN_EXIT',
            'description': 'Pressed ESC or exited exam window',
            'count': violations['fullscreen_exit'],
            'badge_color': 'danger'
        })
    
    # High risk violations - Screenshot/cheating shortcuts
    if violations['shortcut_blocked'] >= 1:
        is_suspicious = True
        if severity != 'CRITICAL':
            severity = 'HIGH'
        violation_type = '📸 Screenshot/Cheating Shortcuts Detected'
        description = f'Attempted to use screenshot or cheating shortcuts {violations["shortcut_blocked"]} time(s) (Windows key, Print Screen, Win+Shift+S, etc.).'
        activities.append({
            'event': 'SCREENSHOT_ATTEMPT',
            'description': 'Tried to capture screen or use cheating shortcuts',
            'count': violations['shortcut_blocked'],
            'badge_color': 'warning'
        })
    
    # Medium-High risk - Tab switching
    if violations['tab_switch'] >= 3:
        is_suspicious = True
        if severity not in ['CRITICAL', 'HIGH']:
            severity = 'MEDIUM'
        violation_type = '🔄 Tab Switching Detected'
        description = f'Switched between windows/tabs {violations["tab_switch"]} times using Alt+Tab or similar actions.'
        activities.append({
            'event': 'TAB_SWITCH',
            'description': 'Switched to other windows/applications',
            'count': violations['tab_switch'],
            'badge_color': 'info'
        })
    
    # Medium risk - Window blur (losing focus)
    if violations['window_blur'] >= 5:
        is_suspicious = True
        if severity not in ['CRITICAL', 'HIGH']:
            severity = 'MEDIUM'
        activities.append({
            'event': 'WINDOW_BLUR',
            'description': 'Lost focus on exam window (switched tabs)',
            'count': violations['window_blur'],
            'badge_color': 'secondary'
        })
    
    # Medium risk - Window hidden
    if violations['window_hidden'] >= 3:
        is_suspicious = True
        if severity not in ['CRITICAL', 'HIGH']:
            severity = 'MEDIUM'
        activities.append({
            'event': 'WINDOW_HIDDEN',
            'description': 'Exam window was hidden/minimized (switched tabs)',
            'count': violations['window_hidden'],
            'badge_color': 'warning'
        })
    
    return {
        'is_suspicious': is_suspicious,
        'severity': severity,
        'violation_type': violation_type,
        'description': description,
        'activities': activities,
        'violations': violations
    }

@app.route('/api/alerts/<int:alert_id>/review', methods=['POST'])
@login_required
def review_alert(alert_id):
    if current_user.role not in ['lecturer', 'admin', 'staff']:
        abort(403)
    
    data = request.get_json()
    # Here you would save the review status to database
    # For now, just return success
    return jsonify({'success': True, 'message': 'Alert reviewed'})


@app.route('/teacher/attempt/<int:attempt_id>/terminate', methods=['POST'])
@login_required
def terminate_attempt(attempt_id):
    """Terminate/force-finish a student's exam attempt (for cheating/violations)"""
    attempt = ExamAttempt.query.get_or_404(attempt_id)
    exam = Exam.query.get_or_404(attempt.exam_id)
    
    # Authorization: lecturer (owner), staff, or admin can terminate
    role = getattr(current_user, 'role', None)
    if role == 'lecturer':
        if exam.creator_id != current_user.id and current_user.role != 'admin':
            flash('Not authorized', 'danger')
            return redirect(url_for('teacher_exams'))
    elif role not in ('staff', 'admin'):
        flash('Not authorized', 'danger')
        return redirect(url_for('index'))
    
    # Check if already finished
    if attempt.finished_at:
        flash('Attempt is already finished', 'info')
        return redirect(request.referrer or url_for('teacher_exams'))
    
    # Force finalize the attempt with 0 score
    attempt.finished_at = datetime.now()
    attempt.score = 0.0  # Set score to 0 for terminated exams
    db.session.commit()
    
    # Log the termination event
    rec = {
        'ts': datetime.now().isoformat(),
        'event': 'exam_terminated_by_staff',
        'data': {
            'terminated_by': current_user.username,
            'terminated_by_role': current_user.role,
            'reason': 'Suspicious activity detected'
        },
        'ip': request.remote_addr,
        'ua': request.headers.get('User-Agent'),
        'source': 'system'
    }
    
    try:
        existing = json.loads(attempt.events) if attempt.events else []
    except Exception:
        existing = []
    existing.append(rec)
    attempt.events = json.dumps(existing)
    db.session.commit()
    
    # Emit socket event to notify the student (if connected)
    try:
        room = f'attempt_{attempt.id}'
        socketio.emit('exam_terminated', {
            'attempt_id': attempt.id,
            'message': 'Your exam has been terminated due to suspicious activity.'
        }, room=room)
    except Exception:
        logger.exception('Failed to emit termination event')
    
    flash(f'Exam attempt terminated for student. Student will be notified.', 'success')
    return redirect(request.referrer or url_for('exam_ai_alerts', exam_id=exam.id))


if __name__ == '__main__':
    # Use environment variables with sensible defaults
    # Support Pterodactyl which may expose the port via different env vars
    port_env = os.environ.get('PORT') or os.environ.get('SERVER_PORT') or os.environ.get('SERVER_HTTP_PORT')
    try:
        port = int(port_env) if port_env else 25570
    except ValueError:
        port = 25570
    host = os.environ.get('HOST', '0.0.0.0')

    # Run explicit initialization (avoid relying on deprecated decorators)
    init_app()

    logger.info(f"Starting server on {host}:{port}")
    logger.info(f"Using database URL: {app.config.get('SQLALCHEMY_DATABASE_URI')}")
    # If DB_CONFIG looks like MySQL, log its database name (informational only)
    if DB_CONFIG.get('database'):
        logger.info(f"Using MySQL database (env): {DB_CONFIG['database']}")

    # Run via Socket.IO wrapper — this enables WebSocket support if needed.
    socketio.run(
        app,
        host=host,
        port=port,
        debug=False,
        allow_unsafe_werkzeug=True
    )


# Socket.IO handlers for live monitoring
@socketio.on('join_attempt')
def handle_join_attempt(data):
    try:
        attempt_id = int(data.get('attempt_id'))
    except Exception:
        return
    attempt = ExamAttempt.query.get(attempt_id)
    if not attempt:
        return
    exam = Exam.query.get(attempt.exam_id)
    role = getattr(current_user, 'role', None)
    # authorize: exam creator (lecturer), staff, admin
    if role == 'lecturer':
        if exam.creator_id != current_user.id and current_user.role != 'admin':
            return
    elif role in ('staff', 'admin'):
        pass
    else:
        return
    room = f'attempt_{attempt_id}'
    join_room(room)
    emit('joined', {'status': 'ok', 'attempt_id': attempt_id})


@socketio.on('join_all_attempts')
def handle_join_all_attempts(data):
    # authorize only staff and admin to join the global room
    role = getattr(current_user, 'role', None)
    if role not in ('staff', 'admin'):
        return
    join_room('all_attempts')
    emit('joined_all', {'status': 'ok'})


@socketio.on('leave_attempt')
def handle_leave_attempt(data):
    try:
        attempt_id = int(data.get('attempt_id'))
    except Exception:
        return
    room = f'attempt_{attempt_id}'
    try:
        leave_room(room)
    except Exception:
        pass

