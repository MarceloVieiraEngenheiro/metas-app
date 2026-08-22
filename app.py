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
    priority = db.Column(db.String(20), default='media')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    checklist_items = db.relationship(
        'ChecklistItem', backref='goal',
        cascade='all, delete-orphan', lazy=True,
        order_by='ChecklistItem.id'
    )

    @property
    def progress(self):
        total = len(self.checklist_items)
        if total == 0:
            return 0
        done = sum(1 for i in self.checklist_items if i.completed)
        return int((done / total) * 100)

    @property
    def days_left(self):
        if not self.deadline:
            return None
        return (self.deadline - date.today()).days

    @property
    def is_overdue(self):
        if not self.deadline:
            return False
        return date.today() > self.deadline and self.progress < 100

    @property
    def is_completed(self):
        return self.progress == 100 and len(self.checklist_items) > 0

    @property
    def status_label(self):
        if self.is_completed:
            return 'Concluida'
        if self.is_overdue:
            return 'Atrasada'
        if self.progress > 0:
            return 'Em andamento'
        return 'Nao iniciada'

    @property
    def status_class(self):
        if self.is_completed:
            return 'success'
        if self.is_overdue:
            return 'danger'
        if self.progress > 0:
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
            flash('Fac,a login para acessar.', 'warning')
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

# ============ AUTENTICACAO ============
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

# ============ ROTAS PRINCIPAIS ============
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
    goals.sort(key=lambda g: (not g.is_overdue, g.deadline is None, g.deadline or date.max))
    years = [y[0] for y in db.session.query(Goal.year).filter_by(user_id=user.id).distinct().order_by(Goal.year.desc()).all()]
    if date.today().year not in years:
        years.insert(0, date.today().year)
    total = len(goals)
    completed = sum(1 for g in goals if