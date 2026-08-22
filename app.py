import os
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'troque-esta-chave')

database_url = os.environ.get('DATABASE_URL', 'sqlite:///metas.db')
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True}

db = SQLAlchemy(app)

CATEGORIES = {
    'Saude': '#00B894',
    'Carreira': '#0984E3',
    'Financeiro': '#FDCB6E',
    'Pessoal': '#6C5CE7',
    'Educacao': '#E17055',
    'Familia': '#FD79A8',
    'Outros': '#636E72',
}

PRIORITIES = {
    'alta': '#E74C3C',
    'media': '#F39C12',
    'baixa': '#3498DB',
}

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    goals = db.relationship('Goal', backref='user', cascade='all, delete-orphan', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Goal(db.Model):
    __tablename__ = 'goals'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    category = db.Column(db.String(50), default='Pessoal')
    year = db.Column(db.Integer, nullable=False, default=date.today().year)
    deadline = db.Column(db.Date, nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    duration_days = db.Column(db.Integer, default=365)
    priority = db.Column(db.String(20), default='media')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    checklist_items = db.relationship(
        'ChecklistItem', backref='goal',
        cascade='all, delete-orphan', lazy=True,
        order_by='ChecklistItem.id'
    )

    @property
    def effective_deadline(self):
        if self.start_date and self.duration_days:
            return self.start_date + timedelta(days=self.duration_days)
        return self.deadline

    @property
    def progress(self):
        total = len(self.checklist_items)
        if total == 0:
            return 0
        done = sum(1 for i in self.checklist_items if i.completed)
        return int((done / total) * 100)

    @property
    def time_progress(self):
        if not self.start_date or not self.effective_deadline:
            return 0
        total_days = (self.effective_deadline - self.start_date).days
        if total_days <= 0:
            return 100
        elapsed = (date.today() - self.start_date).days
        return max(0, min(100, int((elapsed / total_days) * 100)))

    @property
    def overall_progress(self):
        return max(self.progress, self.time_progress)

    @property
    def days_left(self):
        if not self.effective_deadline:
            return None
        return (self.effective_deadline - date.today()).days

    @property
    def is_overdue(self):
        deadline = self.effective_deadline
        if not deadline:
            return False
        return date.today() > deadline and self.progress < 100

    @property
    def is_completed(self):
        return self.progress == 100 and len(self.checklist_items) > 0

    @property
    def status_label(self):
        if self.is_completed:
            return 'Concluida'
        if self.is_overdue:
            return 'Atrasada'
        if not self.start_date or date.today() < self.start_date:
            return 'Nao iniciada'
        if self.progress > 0 or self.time_progress > 0:
            return 'Em andamento'
        return 'Nao iniciada'

    @property
    def status_class(self):
        if self.is_completed:
            return 'success'
        if self.is_overdue:
            return 'danger'
        if not self.start_date or date.today() < self.start_date:
            return 'secondary'
        if self.progress > 0 or self.time_progress > 0:
            return 'warning'
        return 'secondary'

class ChecklistItem(db.Model):
    __tablename__ = 'checklist_items'
    id = db.Column(db.Integer, primary_key=True)
    goal_id = db.Column(db.Integer, db.ForeignKey('goals.id'), nullable=False)
    text = db.Column(db.String(300), nullable=False)
    completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Faca login para acessar.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None

@app.context_processor
def inject_globals():
    return {
        'now': datetime.now(),
        'categories': CATEGORIES,
        'priorities': PRIORITIES,
        'current_user': get_current_user()
    }
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name'].strip()
        email = request.form['email'].strip().lower()
        password = request.form['password']
        confirm = request.form['confirm']
        if not name or not email or not password:
            flash('Preencha todos os campos.', 'danger')
            return redirect(url_for('register'))
        if password != confirm:
            flash('As senhas nao coincidem.', 'danger')
            return redirect(url_for('register'))
        if len(password) < 6:
            flash('A senha deve ter no minimo 6 caracteres.', 'danger')
            return redirect(url_for('register'))
        if User.query.filter_by(email=email).first():
            flash('Este email ja esta cadastrado.', 'danger')
            return redirect(url_for('register'))
        user = User(name=name, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        session['user_id'] = user.id
        flash('Conta criada com sucesso! Bem-vindo!', 'success')
        return redirect(url_for('index'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            flash(f'Ola, {user.name}!', 'success')
            return redirect(url_for('index'))
        flash('Email ou senha incorretos.', 'danger')
        return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Voce saiu.', 'info')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    user = get_current_user()
    year = request.args.get('year', date.today().year, type=int)
    category = request.args.get('category', '')
    query = Goal.query.filter_by(user_id=user.id, year=year)
    if category:
        query = query.filter_by(category=category)
    goals = query.order_by(Goal.created_at.desc()).all()
    goals.sort(key=lambda g: (not g.is_overdue, g.effective_deadline is None, g.effective_deadline or date.max))
    years = [y[0] for y in db.session.query(Goal.year).filter_by(user_id=user.id).distinct().order_by(Goal.year.desc()).all()]
    if date.today().year not in years:
        years.insert(0, date.today().year)
    total = len(goals)
    completed = sum(1 for g in goals if g.is_completed)
    in_progress = sum(1 for g in goals if 0 < g.overall_progress < 100)
    overdue = sum(1 for g in goals if g.is_overdue)
    avg_progress = int(sum(g.overall_progress for g in goals) / total) if total > 0 else 0
    return render_template('index.html', goals=goals, years=years, current_year=year, current_category=category, stats={'total': total, 'completed': completed, 'in_progress': in_progress, 'overdue': overdue, 'avg_progress': avg_progress})

@app.route('/goal/new', methods=['GET', 'POST'])
@login_required
def new_goal():
    user = get_current_user()
    if request.method == 'POST':
        deadline_str = request.form.get('deadline', '').strip()
        deadline = datetime.strptime(deadline_str, '%Y-%m-%d').date() if deadline_str else None
        start_date_str = request.form.get('start_date', '').strip()
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
        duration_days = int(request.form.get('duration_days', 365))
        goal = Goal(user_id=user.id, title=request.form['title'].strip(), description=request.form.get('description', '').strip(), category=request.form.get('category', 'Pessoal'), year=int(request.form.get('year', date.today().year)), deadline=deadline, start_date=start_date, duration_days=duration_days, priority=request.form.get('priority', 'media'))
        db.session.add(goal)
        db.session.flush()
        for text in request.form.getlist('checklist[]'):
            if text.strip():
                db.session.add(ChecklistItem(goal_id=goal.id, text=text.strip()))
        db.session.commit()
        flash('Meta criada com sucesso!', 'success')
        return redirect(url_for('index'))
    return render_template('form.html', goal=None)

@app.route('/goal/<int:goal_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_goal(goal_id):
    user = get_current_user()
    goal = Goal.query.filter_by(id=goal_id, user_id=user.id).first_or_404()
    if request.method == 'POST':
        deadline_str = request.form.get('deadline', '').strip()
        goal.deadline = datetime.strptime(deadline_str, '%Y-%m-%d').date() if deadline_str else None
        start_date_str = request.form.get('start_date', '').strip()
        goal.start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
        goal.duration_days = int(request.form.get('duration_days', 365))
        goal.title = request.form['title'].strip()
        goal.description = request.form.get('description', '').strip()
        goal.category = request.form.get('category', 'Pessoal')
        goal.year = int(request.form.get('year', date.today().year))
        goal.priority = request.form.get('priority', 'media')
        ChecklistItem.query.filter_by(goal_id=goal.id).delete()
        for text in request.form.getlist('checklist[]'):
            if text.strip():
                db.session.add(ChecklistItem(goal_id=goal.id, text=text.strip()))
        db.session.commit()
        flash('Meta atualizada!', 'success')
        return redirect(url_for('index'))
    return render_template('form.html', goal=goal)

@app.route('/goal/<int:goal_id>/delete', methods=['POST'])
@login_required
def delete_goal(goal_id):
    user = get_current_user()
    goal = Goal.query.filter_by(id=goal_id, user_id=user.id).first_or_404()
    db.session.delete(goal)
    db.session.commit()
    flash('Meta excluida.', 'info')
    return redirect(url_for('index'))

@app.route('/api/checklist/<int:item_id>/toggle', methods=['POST'])
@login_required
def toggle_checklist(item_id):
    user = get_current_user()
    item = ChecklistItem.query.join(Goal).filter(ChecklistItem.id == item_id, Goal.user_id == user.id).first_or_404()
    item.completed = not item.completed
    db.session.commit()
    return jsonify({'completed': item.completed, 'progress': item.goal.progress, 'status': item.goal.status_label, 'status_class': item.goal.status_class})

@app.route('/api/checklist/<int:item_id>/delete', methods=['POST'])
@login_required
def delete_checklist(item_id):
    user = get_current_user()
    item = ChecklistItem.query.join(Goal).filter(ChecklistItem.id == item_id, Goal.user_id == user.id).first_or_404()
    goal = item.goal
    db.session.delete(item)
    db.session.commit()
    return jsonify({'progress': goal.progress, 'status': goal.status_label, 'status_class': goal.status_class})

@app.route('/api/goal/<int:goal_id>/checklist', methods=['POST'])
@login_required
def add_checklist_item(goal_id):
    user = get_current_user()
    goal = Goal.query.filter_by(id=goal_id, user_id=user.id).first_or_404()
    text = request.json.get('text', '').strip()
    if not text:
        return jsonify({'error': 'Texto vazio'}), 400
    item = ChecklistItem(goal_id=goal_id, text=text)
    db.session.add(item)
    db.session.commit()
    return jsonify({'id': item.id, 'text': item.text, 'completed': item.completed, 'progress': goal.progress, 'status': goal.status_label, 'status_class': goal.status_class})

@app.route('/api/reminders/send', methods=['POST'])
def send_reminders():
    import smtplib
    from email.mime.text import MIMEText
    smtp_host = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
    smtp_port = int(os.environ.get('SMTP_PORT', 587))
    smtp_user = os.environ.get('SMTP_USER', '')
    smtp_pass = os.environ.get('SMTP_PASS', '')
    recipient = os.environ.get('REMINDER_EMAIL', '')
    if not all([smtp_user, smtp_pass, recipient]):
        return jsonify({'error': 'SMTP nao configurado'}), 500
    soon = date.today() + timedelta(days=7)
    upcoming = [g for g in Goal.query.filter(Goal.deadline.isnot(None), Goal.deadline <= soon).all() if not g.is_completed and g.deadline >= date.today()]
    overdue = [g for g in Goal.query.filter(Goal.deadline.isnot(None), Goal.deadline < date.today()).all() if not g.is_completed]
    if not upcoming and not overdue:
        return jsonify({'message': 'Nenhum lembrete pendente.'})
    html = '<h2>Lembrete de Metas</h2>'
    if overdue:
        html += '<h3 style="color:red">Atrasadas</h3><ul>'
        for g in overdue:
            html += f'<li><b>{g.title}</b> (vencia em {g.deadline.strftime("%d/%m/%Y")}) - {g.progress}%</li>'
        html += '</ul>'
    if upcoming:
        html += '<h3 style="color:orange">Proximas do prazo</h3><ul>'
        for g in upcoming:
            html += f'<li><b>{g.title}</b> (vence em {g.deadline.strftime("%d/%m/%Y")}) - {g.progress}%</li>'
        html += '</ul>'
    msg = MIMEText(html, 'html')
    msg['Subject'] = f'Lembrete de Metas - {date.today().strftime("%d/%m/%Y")}'
    msg['From'] = smtp_user
    msg['To'] = recipient
    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
    return jsonify({'message': f'Lembretes enviados: {len(upcoming)} proximas, {len(overdue)} atrasadas.'})

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

@app.errorhandler(404)
def not_found(e):
    return redirect(url_for('index'))

with app.app_context():
    db.create_all()
    from sqlalchemy import text, inspect
    inspector = inspect(db.engine)
    columns = [c['name'] for c in inspector.get_columns('goals')]
    if 'start_date' not in columns:
        db.session.execute(text('ALTER TABLE goals ADD COLUMN start_date DATE'))
        db.session.commit()
        print('Coluna start_date adicionada!')
    if 'duration_days' not in columns:
        db.session.execute(text('ALTER TABLE goals ADD COLUMN duration_days INTEGER DEFAULT 365'))
        db.session.commit()
        print('Coluna duration_days adicionada!')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))