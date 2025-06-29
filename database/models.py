from sqlalchemy import Column, Integer, String, Text, Date, DateTime, Enum, ForeignKey, Float, BigInteger, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True)
    name = Column(String(100))
    role = Column(Enum('ProductOwner', 'Developer', 'CEO'))
    joined_at = Column(DateTime)
    last_login = Column(DateTime)
    total_points = Column(Integer, default=0)


    tasks = relationship('Task', backref='user')
    daily_reports = relationship('DailyReport', backref='user')
    created_projects = relationship('Project', backref='creator')
    retrospectives = relationship('Retrospective', backref='holder')
    sprint_reviews = relationship('SprintReview', backref='creator')


class Project(Base):
    __tablename__ = 'projects'
    id = Column(Integer, primary_key=True)
    name = Column(String(150))
    description = Column(Text)
    created_by = Column(Integer, ForeignKey('users.id'))
    created_at = Column(DateTime)


class Sprint(Base):
    __tablename__ = 'sprints'
    id = Column(Integer, primary_key=True)
    start_date = Column(Date)
    end_date = Column(Date)
    status = Column(Enum('Active', 'Completed'))
    created_by = Column(Integer, ForeignKey('users.id'))  # سازنده اسپرینت

    tasks = relationship('Task', backref='sprint')
    daily_reports = relationship('DailyReport', backref='sprint')
    sprint_reviews = relationship('SprintReview', backref='sprint')
    retrospectives = relationship('Retrospective', backref='sprint')


class Task(Base):
    __tablename__ = 'tasks'
    id = Column(Integer, primary_key=True)
    sprint_id = Column(Integer, ForeignKey('sprints.id'), nullable=True)
    title = Column(String(255))
    description = Column(Text)
    assigned_to = Column(Integer, ForeignKey('users.id'), nullable=True)
    status = Column(Enum('NotStarted', 'InProgress', 'InReview', 'Completed', 'Backlog'), default='Backlog')
    story_point = Column(Integer, nullable=True)
    created_at = Column(DateTime)
    reviewed = Column(Boolean, default=False)
    project_id = Column(Integer, ForeignKey('projects.id'))


class DailyReport(Base):
    __tablename__ = 'dailyreports'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    sprint_id = Column(Integer, ForeignKey('sprints.id'))
    report_date = Column(Date)
    completed_tasks = Column(Text)
    planned_tasks = Column(Text)
    blockers = Column(Text)


class SprintReview(Base):
    __tablename__ = 'sprintreviews'
    id = Column(Integer, primary_key=True)
    sprint_id = Column(Integer, ForeignKey('sprints.id'))
    created_by = Column(Integer, ForeignKey('users.id'))
    review_date = Column(Date)
    notes = Column(Text)
    completed_percentage = Column(Float)


class Retrospective(Base):
    __tablename__ = 'retrospectives'
    id = Column(Integer, primary_key=True)
    sprint_id = Column(Integer, ForeignKey('sprints.id'))
    held_by = Column(Integer, ForeignKey('users.id'))
    retro_date = Column(Date)
    discussion_points = Column(Text)
