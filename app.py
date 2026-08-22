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
    def
