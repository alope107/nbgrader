from __future__ import division

from nbgrader import utils

from sqlalchemy import (create_engine, ForeignKey, Column, String, Text,
    DateTime, Interval, Float, Enum, UniqueConstraint)
from sqlalchemy.orm import sessionmaker, scoped_session, relationship, column_property
from sqlalchemy.orm.exc import NoResultFound, FlushError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import and_
from sqlalchemy import select, func, exists, case, literal_column

from uuid import uuid4

Base = declarative_base()

class InvalidEntry(ValueError):
    pass
class MissingEntry(ValueError):
    pass


def new_uuid():
    return uuid4().hex


class Assignment(Base):
    __tablename__ = "assignment"

    id = Column(String(32), primary_key=True, default=new_uuid)
    name = Column(String(128), unique=True, nullable=False)
    duedate = Column(DateTime())

    notebooks = relationship("Notebook", backref="assignment", order_by="Notebook.name")
    submissions = relationship("SubmittedAssignment", backref="assignment")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "duedate": self.duedate,
            "num_submissions": self.num_submissions,
            "max_score": self.max_score,
            "max_code_score": self.max_code_score,
            "max_written_score": self.max_written_score,
        }

    def __repr__(self):
        return self.name

class Notebook(Base):
    __tablename__ = "notebook"
    __table_args__ = (UniqueConstraint('name', 'assignment_id'),)

    id = Column(String(32), primary_key=True, default=new_uuid)
    name = Column(String(128), nullable=False)

    assignment_id = Column(String(32), ForeignKey('assignment.id'))

    grade_cells = relationship("GradeCell", backref="notebook")
    solution_cells = relationship("SolutionCell", backref="notebook")

    submissions = relationship("SubmittedNotebook", backref="notebook")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "num_submissions": self.num_submissions,
            "max_score": self.max_score,
            "max_code_score": self.max_code_score,
            "max_written_score": self.max_written_score,
            "needs_manual_grade": self.needs_manual_grade
        }

    def __repr__(self):
        return "{}/{}".format(self.assignment, self.name)


class GradeCell(Base):
    __tablename__ = "grade_cell"
    __table_args__ = (UniqueConstraint('name', 'notebook_id'),)

    id = Column(String(32), primary_key=True, default=new_uuid)
    name = Column(String(128), nullable=False)
    max_score = Column(Float(), nullable=False)
    cell_type = Column(Enum("code", "markdown"), nullable=False)
    source = Column(Text())
    checksum = Column(String(128))

    notebook_id = Column(String(32), ForeignKey('notebook.id'))

    assignment = association_proxy("notebook", "assignment")

    grades = relationship("Grade", backref="cell")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "max_score": self.max_score,
            "cell_type": self.cell_type,
            "source": self.source,
            "checksum": self.checksum,
            "notebook": self.notebook.name,
            "assignment": self.assignment.name
        }

    def __repr__(self):
        return "{}/{}".format(self.notebook, self.name)


class SolutionCell(Base):
    __tablename__ = "solution_cell"
    __table_args__ = (UniqueConstraint('name', 'notebook_id'),)

    id = Column(String(32), primary_key=True, default=new_uuid)
    name = Column(String(128), nullable=False)

    notebook_id = Column(String(32), ForeignKey('notebook.id'))

    assignment = association_proxy("notebook", "assignment")

    comments = relationship("Comment", backref="cell")
    cell_type = Column(Enum("code", "markdown"), nullable=False)
    source = Column(Text())
    checksum = Column(String(128))

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "notebook": self.notebook.name,
            "assignment": self.assignment.name,
            "cell_type": self.cell_type,
            "source": self.source,
            "checksum": self.checksum
        }

    def __repr__(self):
        return "{}/{}".format(self.notebook, self.name)


class Student(Base):
    __tablename__ = "student"

    id = Column(String(128), primary_key=True, nullable=False)
    first_name = Column(String(128))
    last_name = Column(String(128))
    email = Column(String(128))

    submissions = relationship("SubmittedAssignment", backref="student")

    def to_dict(self):
        return {
            "id": self.id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "email": self.email,
            "score": self.score,
            "max_score": self.max_score
        }

    def __repr__(self):
        return self.id


class SubmittedAssignment(Base):
    __tablename__ = "submitted_assignment"
    __table_args__ = (UniqueConstraint('assignment_id', 'student_id'),)

    id = Column(String(32), primary_key=True, default=new_uuid)
    assignment_id = Column(String(32), ForeignKey('assignment.id'))
    student_id = Column(String(128), ForeignKey('student.id'))

    timestamp = Column(DateTime())
    extension = Column(Interval())

    notebooks = relationship("SubmittedNotebook", backref="assignment")

    @property
    def duedate(self):
        orig_duedate = self.assignment.duedate
        if self.extension is not None:
            return orig_duedate + self.extension
        else:
            return orig_duedate

    @property
    def total_seconds_late(self):
        if self.timestamp is None or self.duedate is None:
            return 0
        else:
            return max(0, (self.timestamp - self.duedate).total_seconds())

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.assignment.name,
            "student": self.student.id,
            "duedate": self.duedate.isoformat() if self.duedate is not None else None,
            "timestamp": self.timestamp.isoformat() if self.timestamp is not None else None,
            "extension": self.extension.total_seconds() if self.extension is not None else None,
            "total_seconds_late": self.total_seconds_late,
            "score": self.score,
            "max_score": self.max_score,
            "code_score": self.code_score,
            "max_code_score": self.max_code_score,
            "written_score": self.written_score,
            "max_written_score": self.max_written_score,
            "needs_manual_grade": self.needs_manual_grade
        }

    def __repr__(self):
        return "{} for {}".format(self.assignment, self.student)


class SubmittedNotebook(Base):
    __tablename__ = "submitted_notebook"
    __table_args__ = (UniqueConstraint('notebook_id', 'assignment_id'),)

    id = Column(String(32), primary_key=True, default=new_uuid)
    notebook_id = Column(String(32), ForeignKey('notebook.id'))
    assignment_id = Column(String(32), ForeignKey('submitted_assignment.id'))

    grades = relationship("Grade", backref="notebook")
    comments = relationship("Comment", backref="notebook")

    student = association_proxy('assignment', 'student')

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.notebook.name,
            "student": self.student.id,
            "score": self.score,
            "max_score": self.max_score,
            "code_score": self.code_score,
            "max_code_score": self.max_code_score,
            "written_score": self.written_score,
            "max_written_score": self.max_written_score,
            "needs_manual_grade": self.needs_manual_grade,
            "failed_tests": self.failed_tests
        }

    def __repr__(self):
        return "{} for {}".format(self.notebook, self.student)


class Grade(Base):
    __tablename__ = "grade"
    __table_args__ = (UniqueConstraint('cell_id', 'notebook_id'),)

    id = Column(String(32), primary_key=True, default=new_uuid)
    cell_id = Column(String(32), ForeignKey('grade_cell.id'))
    notebook_id = Column(String(32), ForeignKey('submitted_notebook.id'))

    auto_score = Column(Float())
    manual_score = Column(Float())

    assignment = association_proxy('notebook', 'assignment')
    student = association_proxy('notebook', 'student')

    score = column_property(case(
        [
            (manual_score != None, manual_score),
            (auto_score != None, auto_score)
        ],
        else_=literal_column("0.0")
    ))

    needs_manual_grade = column_property(
        (auto_score == None) & (manual_score == None))

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.cell.name,
            "notebook": self.notebook.notebook.name,
            "assignment": self.assignment.assignment.name,
            "student": self.student.id,
            "auto_score": self.auto_score,
            "manual_score": self.manual_score,
            "max_score": self.max_score,
            "needs_manual_grade": self.needs_manual_grade,
            "failed_tests": self.failed_tests,
            "cell_type": self.cell_type
        }

    def __repr__(self):
        return "{} for {}".format(self.cell, self.student)


class Comment(Base):
    __tablename__ = "comment"
    __table_args__ = (UniqueConstraint('cell_id', 'notebook_id'),)

    id = Column(String(32), primary_key=True, default=new_uuid)
    cell_id = Column(String(32), ForeignKey('solution_cell.id'))
    notebook_id = Column(String(32), ForeignKey('submitted_notebook.id'))

    comment = Column(Text())

    assignment = association_proxy('notebook', 'assignment')
    student = association_proxy('notebook', 'student')

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.cell.name,
            "notebook": self.notebook.notebook.name,
            "assignment": self.assignment.assignment.name,
            "student": self.student.id,
            "comment": self.comment,
        }

    def __repr__(self):
        return "{} for {}".format(self.cell, self.student)


## Needs manual grade

SubmittedNotebook.needs_manual_grade = column_property(
    exists().where(and_(
        Grade.notebook_id == SubmittedNotebook.id,
        Grade.needs_manual_grade))\
    .correlate_except(Grade), deferred=True)

SubmittedAssignment.needs_manual_grade = column_property(
    exists().where(and_(
        SubmittedNotebook.assignment_id == SubmittedAssignment.id,
        Grade.notebook_id == SubmittedNotebook.id,
        Grade.needs_manual_grade))\
    .correlate_except(Grade), deferred=True)

Notebook.needs_manual_grade = column_property(
    exists().where(and_(
        Notebook.id == SubmittedNotebook.notebook_id,
        Grade.notebook_id == SubmittedNotebook.id,
        Grade.needs_manual_grade))\
    .correlate_except(Grade), deferred=True)


## Overall scores

SubmittedNotebook.score = column_property(
    select([func.coalesce(func.sum(Grade.score), 0.0)])\
        .where(Grade.notebook_id == SubmittedNotebook.id)\
        .correlate_except(Grade), deferred=True)

SubmittedAssignment.score = column_property(
    select([func.coalesce(func.sum(Grade.score), 0.0)])\
        .where(and_(
            SubmittedNotebook.assignment_id == SubmittedAssignment.id,
            Grade.notebook_id == SubmittedNotebook.id))\
        .correlate_except(Grade), deferred=True)

Student.score = column_property(
    select([func.coalesce(func.sum(Grade.score), 0.0)])\
        .where(and_(
            SubmittedAssignment.student_id == Student.id,
            SubmittedNotebook.assignment_id == SubmittedAssignment.id,
            Grade.notebook_id == SubmittedNotebook.id))\
        .correlate_except(Grade), deferred=True)


## Overall max scores

Grade.max_score = column_property(
    select([GradeCell.max_score])\
        .where(Grade.cell_id == GradeCell.id)\
        .correlate_except(GradeCell), deferred=True)

Notebook.max_score = column_property(
    select([func.coalesce(func.sum(GradeCell.max_score), 0.0)])\
        .where(GradeCell.notebook_id == Notebook.id)\
        .correlate_except(GradeCell), deferred=True)

SubmittedNotebook.max_score = column_property(
    select([Notebook.max_score])\
        .where(SubmittedNotebook.notebook_id == Notebook.id)\
        .correlate_except(Notebook), deferred=True)

Assignment.max_score = column_property(
    select([func.coalesce(func.sum(GradeCell.max_score), 0.0)])\
        .where(and_(
            Notebook.assignment_id == Assignment.id,
            GradeCell.notebook_id == Notebook.id))\
        .correlate_except(GradeCell), deferred=True)

SubmittedAssignment.max_score = column_property(
    select([Assignment.max_score])\
        .where(SubmittedAssignment.assignment_id == Assignment.id)\
        .correlate_except(Assignment), deferred=True)

Student.max_score = column_property(
    select([func.coalesce(func.sum(Assignment.max_score), 0.0)])\
        .correlate_except(Assignment), deferred=True)


## Written scores

SubmittedNotebook.written_score = column_property(
    select([func.coalesce(func.sum(Grade.score), 0.0)])\
        .where(and_(
            Grade.notebook_id == SubmittedNotebook.id,
            GradeCell.id == Grade.cell_id,
            GradeCell.cell_type == "markdown"))\
        .correlate_except(Grade), deferred=True)

SubmittedAssignment.written_score = column_property(
    select([func.coalesce(func.sum(Grade.score), 0.0)])\
        .where(and_(
            SubmittedNotebook.assignment_id == SubmittedAssignment.id,
            Grade.notebook_id == SubmittedNotebook.id,
            GradeCell.id == Grade.cell_id,
            GradeCell.cell_type == "markdown"))\
        .correlate_except(Grade), deferred=True)


## Written max scores

Notebook.max_written_score = column_property(
    select([func.coalesce(func.sum(GradeCell.max_score), 0.0)])\
        .where(and_(
            GradeCell.notebook_id == Notebook.id,
            GradeCell.cell_type == "markdown"))\
        .correlate_except(GradeCell), deferred=True)

SubmittedNotebook.max_written_score = column_property(
    select([Notebook.max_written_score])\
        .where(Notebook.id == SubmittedNotebook.notebook_id)\
        .correlate_except(Notebook), deferred=True)

Assignment.max_written_score = column_property(
    select([func.coalesce(func.sum(GradeCell.max_score), 0.0)])\
        .where(and_(
            Notebook.assignment_id == Assignment.id,
            GradeCell.notebook_id == Notebook.id,
            GradeCell.cell_type == "markdown"))\
        .correlate_except(GradeCell), deferred=True)

SubmittedAssignment.max_written_score = column_property(
    select([Assignment.max_written_score])\
        .where(Assignment.id == SubmittedAssignment.assignment_id)\
        .correlate_except(Assignment), deferred=True)


## Code scores

SubmittedNotebook.code_score = column_property(
    select([func.coalesce(func.sum(Grade.score), 0.0)])\
        .where(and_(
            Grade.notebook_id == SubmittedNotebook.id,
            GradeCell.id == Grade.cell_id,
            GradeCell.cell_type == "code"))\
        .correlate_except(Grade), deferred=True)

SubmittedAssignment.code_score = column_property(
    select([func.coalesce(func.sum(Grade.score), 0.0)])\
        .where(and_(
            SubmittedNotebook.assignment_id == SubmittedAssignment.id,
            Grade.notebook_id == SubmittedNotebook.id,
            GradeCell.id == Grade.cell_id,
            GradeCell.cell_type == "code"))\
        .correlate_except(Grade), deferred=True)


## Code max scores

Notebook.max_code_score = column_property(
    select([func.coalesce(func.sum(GradeCell.max_score), 0.0)])\
        .where(and_(
            GradeCell.notebook_id == Notebook.id,
            GradeCell.cell_type == "code"))\
        .correlate_except(GradeCell), deferred=True)

SubmittedNotebook.max_code_score = column_property(
    select([Notebook.max_code_score])\
        .where(Notebook.id == SubmittedNotebook.notebook_id)\
        .correlate_except(Notebook), deferred=True)

Assignment.max_code_score = column_property(
    select([func.coalesce(func.sum(GradeCell.max_score), 0.0)])\
        .where(and_(
            Notebook.assignment_id == Assignment.id,
            GradeCell.notebook_id == Notebook.id,
            GradeCell.cell_type == "code"))\
        .correlate_except(GradeCell), deferred=True)

SubmittedAssignment.max_code_score = column_property(
    select([Assignment.max_code_score])\
        .where(Assignment.id == SubmittedAssignment.assignment_id)\
        .correlate_except(Assignment), deferred=True)


## Number of submissions

Assignment.num_submissions = column_property(
    select([func.count(SubmittedAssignment.id)])\
        .where(SubmittedAssignment.assignment_id == Assignment.id)\
        .correlate_except(SubmittedAssignment), deferred=True)

Notebook.num_submissions = column_property(
    select([func.count(SubmittedNotebook.id)])\
        .where(SubmittedNotebook.notebook_id == Notebook.id)\
        .correlate_except(SubmittedNotebook), deferred=True)


## Cell type

Grade.cell_type = column_property(
    select([GradeCell.cell_type])\
        .where(Grade.cell_id == GradeCell.id)\
        .correlate_except(GradeCell), deferred=True)


## Failed tests

Grade.failed_tests = column_property(
    (Grade.auto_score < Grade.max_score) & (Grade.cell_type == "code"))

SubmittedNotebook.failed_tests = column_property(
    exists().where(and_(
        Grade.notebook_id == SubmittedNotebook.id,
        Grade.failed_tests))\
    .correlate_except(Grade), deferred=True)


class Gradebook(object):
    """The gradebook object to interface with the database holding
    nbgrader grades.

    """

    def __init__(self, db_url):
        """Initialize the connection to the database.

        Parameters
        ----------
        db_url : string
            The URL to the database, e.g. sqlite:///grades.db

        """
        # create the connection to the database
        engine = create_engine(db_url)
        self.db = scoped_session(sessionmaker(autoflush=True, bind=engine))

        # this creates all the tables in the database if they don't already exist
        Base.metadata.create_all(bind=engine)

    #### Students

    @property
    def students(self):
        """A list of all students in the database."""
        return self.db.query(Student)\
            .order_by(Student.last_name, Student.first_name)\
            .all()

    def add_student(self, student_id, **kwargs):
        """Add a new student to the database.

        Parameters
        ----------
        student_id : string
            The unique id of the student
        **kwargs : dict
            other keyword arguments to the nbgrader.api.Student object

        Returns
        -------
        nbgrader.api.Student object

        """

        student = Student(id=student_id, **kwargs)
        self.db.add(student)
        try:
            self.db.commit()
        except (IntegrityError, FlushError) as e:
            self.db.rollback()
            raise InvalidEntry(*e.args)
        return student

    def find_student(self, student_id):
        """Find a student.

        Parameters
        ----------
        student_id : string
            The unique id of the student

        Returns
        -------
        nbgrader.api.Student object

        """

        try:
            student = self.db.query(Student)\
                .filter(Student.id == student_id)\
                .one()
        except NoResultFound:
            raise MissingEntry("No such student: {}".format(student_id))

        return student

    def update_or_create_student(self, name, **kwargs):
        """Update an existing student, or create it if it doesn't exist.

        Parameters
        ----------
        name : string
            the name of the student
        **kwargs : dict
            additional keyword arguments for the nbgrader.api.Student object

        Returns
        -------
        nbgrader.api.Student object

        """

        try:
            student = self.find_student(name)
        except MissingEntry:
            student = self.add_student(name, **kwargs)
        else:
            for attr in kwargs:
                setattr(student, attr, kwargs[attr])
            try:
                self.db.commit()
            except (IntegrityError, FlushError) as e:
                self.db.rollback()
                raise InvalidEntry(*e.args)

        return student

    def remove_student(self, name):
        """Deletes an existing student from the gradebook, including any
        submissions the might be associated with that student.

        Parameters
        ----------
        name : string
            the name of the student to delete

        """
        student = self.find_student(name)

        for submission in student.submissions:
            self.remove_submission(submission.assignment.name, name)

        self.db.delete(student)

        try:
            self.db.commit()
        except (IntegrityError, FlushError) as e:
            self.db.rollback()
            raise InvalidEntry(*e.args)

    #### Assignments

    @property
    def assignments(self):
        """A list of all assignments in the gradebook."""
        return self.db.query(Assignment)\
            .order_by(Assignment.duedate, Assignment.name)\
            .all()

    def add_assignment(self, name, **kwargs):
        """Add a new assignment to the gradebook.

        Parameters
        ----------
        name : string
            the unique name of the new assignment
        **kwargs : dict
            additional keyword arguments for the nbgrader.api.Assignment object

        Returns
        -------
        nbgrader.api.Assignment object

        """
        if 'duedate' in kwargs:
            kwargs['duedate'] = utils.parse_utc(kwargs['duedate'])
        assignment = Assignment(name=name, **kwargs)
        self.db.add(assignment)
        try:
            self.db.commit()
        except (IntegrityError, FlushError) as e:
            self.db.rollback()
            raise InvalidEntry(*e.args)
        return assignment

    def find_assignment(self, name):
        """Find an assignment in the gradebook.

        Parameters
        ----------
        name : string
            the unique name of the assignment

        Returns
        -------
        nbgrader.api.Assignment object

        """

        try:
            assignment = self.db.query(Assignment)\
                .filter(Assignment.name == name)\
                .one()
        except NoResultFound:
            raise MissingEntry("No such assignment: {}".format(name))

        return assignment

    def update_or_create_assignment(self, name, **kwargs):
        """Update an existing assignment, or create it if it doesn't exist.

        Parameters
        ----------
        name : string
            the name of the assignment
        **kwargs : dict
            additional keyword arguments for the nbgrader.api.Assignment object

        Returns
        -------
        nbgrader.api.Assignment object

        """

        try:
            assignment = self.find_assignment(name)
        except MissingEntry:
            assignment = self.add_assignment(name, **kwargs)
        else:
            for attr in kwargs:
                if attr == 'duedate':
                    setattr(assignment, attr, utils.parse_utc(kwargs[attr]))
                else:
                    setattr(assignment, attr, kwargs[attr])
            try:
                self.db.commit()
            except (IntegrityError, FlushError) as e:
                self.db.rollback()
                raise InvalidEntry(*e.args)

        return assignment

    def remove_assignment(self, name):
        """Deletes an existing assignment from the gradebook, including any
        submissions the might be associated with that assignment.

        Parameters
        ----------
        name : string
            the name of the assignment to delete

        """
        assignment = self.find_assignment(name)

        for submission in assignment.submissions:
            self.remove_submission(name, submission.student.id)

        for notebook in assignment.notebooks:
            for grade_cell in notebook.grade_cells:
                self.db.delete(grade_cell)
            for solution_cell in notebook.solution_cells:
                self.db.delete(solution_cell)
            self.db.delete(notebook)

        self.db.delete(assignment)

        try:
            self.db.commit()
        except (IntegrityError, FlushError) as e:
            self.db.rollback()
            raise InvalidEntry(*e.args)

    #### Notebooks

    def add_notebook(self, name, assignment, **kwargs):
        """Add a new notebook to an assignment.

        Parameters
        ----------
        name : string
            the name of the new notebook
        assignment : string
            the name of an existing assignment
        **kwargs : dict
            additional keyword arguments for the nbgrader.api.Notebook object

        Returns
        -------
        nbgrader.api.Notebook object

        """

        notebook = Notebook(
            name=name, assignment=self.find_assignment(assignment), **kwargs)
        self.db.add(notebook)
        try:
            self.db.commit()
        except (IntegrityError, FlushError) as e:
            self.db.rollback()
            raise InvalidEntry(*e.args)
        return notebook

    def find_notebook(self, name, assignment):
        """Find a particular notebook in an assignment.

        Parameters
        ----------
        name : string
            the name of the notebook
        assignment : string
            the name of the assignment

        Returns
        -------
        nbgrader.api.Notebook object

        """

        try:
            notebook = self.db.query(Notebook)\
                .join(Assignment, Assignment.id == Notebook.assignment_id)\
                .filter(Notebook.name == name, Assignment.name == assignment)\
                .one()
        except NoResultFound:
            raise MissingEntry("No such notebook: {}/{}".format(assignment, name))

        return notebook

    def update_or_create_notebook(self, name, assignment, **kwargs):
        """Update an existing notebook, or create it if it doesn't exist.

        Parameters
        ----------
        name : string
            the name of the notebook
        assignment : string
            the name of the assignment
        **kwargs : dict
            additional keyword arguments for the nbgrader.api.Notebook object

        Returns
        -------
        nbgrader.api.Notebook object

        """

        try:
            notebook = self.find_notebook(name, assignment)
        except MissingEntry:
            notebook = self.add_notebook(name, assignment, **kwargs)
        else:
            for attr in kwargs:
                setattr(notebook, attr, kwargs[attr])
            try:
                self.db.commit()
            except (IntegrityError, FlushError) as e:
                self.db.rollback()
                raise InvalidEntry(*e.args)

        return notebook

    #### Grade cells

    def add_grade_cell(self, name, notebook, assignment, **kwargs):
        """Add a new grade cell to an existing notebook of an existing
        assignment.

        Parameters
        ----------
        name : string
            the name of the new grade cell
        notebook : string
            the name of an existing notebook
        assignment : string
            the name of an existing assignment
        **kwargs : dict
            additional keyword arguments for nbgrader.api.GradeCell

        Returns
        -------
        nbgrader.api.GradeCell

        """

        notebook = self.find_notebook(notebook, assignment)
        grade_cell = GradeCell(name=name, notebook=notebook, **kwargs)
        self.db.add(grade_cell)
        try:
            self.db.commit()
        except (IntegrityError, FlushError) as e:
            self.db.rollback()
            raise InvalidEntry(*e.args)
        return grade_cell

    def find_grade_cell(self, name, notebook, assignment):
        """Find a grade cell in a particular notebook of an assignment.

        Parameters
        ----------
        name : string
            the name of the grade cell
        notebook : string
            the name of the notebook
        assignment : string
            the name of the assignment

        Returns
        -------
        nbgrader.api.GradeCell

        """

        try:
            grade_cell = self.db.query(GradeCell)\
                .join(Notebook, Notebook.id == GradeCell.notebook_id)\
                .join(Assignment, Assignment.id == Notebook.assignment_id)\
                .filter(
                    GradeCell.name == name,
                    Notebook.name == notebook,
                    Assignment.name == assignment)\
                .one()
        except NoResultFound:
            raise MissingEntry("No such grade cell: {}/{}/{}".format(assignment, notebook, name))

        return grade_cell

    def update_or_create_grade_cell(self, name, notebook, assignment, **kwargs):
        """Update an existing grade cell in a notebook of an assignment, or
        create the grade cell if it does not exist.

        Parameters
        ----------
        name : string
            the name of the grade cell
        notebook : string
            the name of the notebook
        assignment : string
            the name of the assignment
        **kwargs : dict
            additional keyword arguments for nbgrader.api.GradeCell

        Returns
        -------
        nbgrader.api.GradeCell

        """

        try:
            grade_cell = self.find_grade_cell(name, notebook, assignment)
        except MissingEntry:
            grade_cell = self.add_grade_cell(name, notebook, assignment, **kwargs)
        else:
            for attr in kwargs:
                setattr(grade_cell, attr, kwargs[attr])
            try:
                self.db.commit()
            except (IntegrityError, FlushError) as e:
                self.db.rollback()
                raise InvalidEntry(*e.args)

        return grade_cell

    #### Solution cells

    def add_solution_cell(self, name, notebook, assignment, **kwargs):
        """Add a new solution cell to an existing notebook of an existing
        assignment.

        Parameters
        ----------
        name : string
            the name of the new solution cell
        notebook : string
            the name of an existing notebook
        assignment : string
            the name of an existing assignment
        **kwargs : dict
            additional keyword arguments for nbgrader.api.SolutionCell

        Returns
        -------
        nbgrader.api.SolutionCell

        """

        notebook = self.find_notebook(notebook, assignment)
        solution_cell = SolutionCell(name=name, notebook=notebook, **kwargs)
        self.db.add(solution_cell)
        try:
            self.db.commit()
        except (IntegrityError, FlushError) as e:
            self.db.rollback()
            raise InvalidEntry(*e.args)
        return solution_cell

    def find_solution_cell(self, name, notebook, assignment):
        """Find a solution cell in a particular notebook of an assignment.

        Parameters
        ----------
        name : string
            the name of the solution cell
        notebook : string
            the name of the notebook
        assignment : string
            the name of the assignment

        Returns
        -------
        nbgrader.api.SolutionCell

        """

        try:
            solution_cell = self.db.query(SolutionCell)\
                .join(Notebook, Notebook.id == SolutionCell.notebook_id)\
                .join(Assignment, Assignment.id == Notebook.assignment_id)\
                .filter(SolutionCell.name == name, Notebook.name == notebook, Assignment.name == assignment)\
                .one()
        except NoResultFound:
            raise MissingEntry("No such solution cell: {}/{}/{}".format(assignment, notebook, name))

        return solution_cell

    def update_or_create_solution_cell(self, name, notebook, assignment, **kwargs):
        """Update an existing solution cell in a notebook of an assignment, or
        create the solution cell if it does not exist.

        Parameters
        ----------
        name : string
            the name of the solution cell
        notebook : string
            the name of the notebook
        assignment : string
            the name of the assignment
        **kwargs : dict
            additional keyword arguments for nbgrader.api.SolutionCell

        Returns
        -------
        nbgrader.api.SolutionCell

        """

        try:
            solution_cell = self.find_solution_cell(name, notebook, assignment)
        except MissingEntry:
            solution_cell = self.add_solution_cell(name, notebook, assignment, **kwargs)
        else:
            for attr in kwargs:
                setattr(solution_cell, attr, kwargs[attr])
            try:
                self.db.commit()
            except (IntegrityError, FlushError) as e:
                raise InvalidEntry(*e.args)

        return solution_cell

    #### Submissions

    def add_submission(self, assignment, student, **kwargs):
        """Add a new submission of an assignment by a student.

        This method not only creates the high-level submission object, but also
        mirrors the entire structure of the existing assignment. Thus, once this
        method has been called, the new submission exists and is completely
        ready to be filled in with grades and comments.

        Parameters
        ----------
        assignment : string
            the name of an existing assignment
        student : string
            the name of an existing student
        **kwargs : dict
            additional keyword arguments for nbgrader.api.SubmittedAssignment

        Returns
        -------
        nbgrader.api.SubmittedAssignment

        """

        if 'timestamp' in kwargs:
            kwargs['timestamp'] = utils.parse_utc(kwargs['timestamp'])

        try:
            submission = SubmittedAssignment(
                assignment=self.find_assignment(assignment),
                student=self.find_student(student),
                **kwargs)

            for notebook in submission.assignment.notebooks:
                nb = SubmittedNotebook(notebook=notebook, assignment=submission)

                for grade_cell in notebook.grade_cells:
                    Grade(cell=grade_cell, notebook=nb)

                for solution_cell in notebook.solution_cells:
                    Comment(cell=solution_cell, notebook=nb)

            self.db.add(submission)
            self.db.commit()

        except (IntegrityError, FlushError) as e:
            self.db.rollback()
            raise InvalidEntry(*e.args)

        return submission

    def find_submission(self, assignment, student):
        """Find a student's submission for a given assignment.

        Parameters
        ----------
        assignment : string
            the name of an assignment
        student : string
            the unique id of a student

        Returns
        -------
        nbgrader.api.SubmittedAssignment object

        """

        try:
            submission = self.db.query(SubmittedAssignment)\
                .join(Assignment, Assignment.id == SubmittedAssignment.assignment_id)\
                .join(Student, Student.id == SubmittedAssignment.student_id)\
                .filter(Assignment.name == assignment, Student.id == student)\
                .one()
        except NoResultFound:
            raise MissingEntry("No such submission: {} for {}".format(
                assignment, student))

        return submission

    def update_or_create_submission(self, assignment, student, **kwargs):
        """Update an existing submission of an assignment by a given student,
        or create a new submission if it doesn't exist.

        See nbgrader.api.Gradebook.add_submission for additional details.

        Parameters
        ----------
        assignment : string
            the name of an existing assignment
        student : string
            the name of an existing student
        **kwargs : dict
            additional keyword arguments for nbgrader.api.SubmittedAssignment

        Returns
        -------
        nbgrader.api.SubmittedAssignment

        """

        try:
            submission = self.find_submission(assignment, student)
        except MissingEntry:
            submission = self.add_submission(assignment, student, **kwargs)
        else:
            for attr in kwargs:
                if attr == 'timestamp':
                    setattr(submission, attr, utils.parse_utc(kwargs[attr]))
                else:
                    setattr(submission, attr, kwargs[attr])
            try:
                self.db.commit()
            except (IntegrityError, FlushError) as e:
                self.db.rollback()
                raise InvalidEntry(*e.args)

        return submission

    def remove_submission(self, assignment, student):
        """Removes a submission from the database.

        Parameters
        ----------
        assignment : string
            the name of an assignment
        student : string
            the name of a student

        """
        submission = self.find_submission(assignment, student)

        for notebook in submission.notebooks:
            for grade in notebook.grades:
                self.db.delete(grade)
            for comment in notebook.comments:
                self.db.delete(comment)
            self.db.delete(notebook)

        self.db.delete(submission)

        try:
            self.db.commit()
        except (IntegrityError, FlushError) as e:
            self.db.rollback()
            raise InvalidEntry(*e.args)

    def assignment_submissions(self, assignment):
        """Find all submissions of a given assignment.

        Parameters
        ----------
        assignment : string
            the name of an assignment

        Returns
        -------
        list of nbgrader.api.SubmittedAssignment objects

        """

        return self.db.query(SubmittedAssignment)\
            .join(Assignment, Assignment.id == SubmittedAssignment.assignment_id)\
            .filter(Assignment.name == assignment)\
            .all()

    def notebook_submissions(self, notebook, assignment):
        """Find all submissions of a given notebook in a given assignment.

        Parameters
        ----------
        notebook : string
            the name of an assignment
        assignment : string
            the name of an assignment

        Returns
        -------
        list of nbgrader.api.SubmittedNotebook objects

        """

        return self.db.query(SubmittedNotebook)\
            .join(Notebook, Notebook.id == SubmittedNotebook.notebook_id)\
            .join(SubmittedAssignment, SubmittedAssignment.id == SubmittedNotebook.assignment_id)\
            .join(Assignment, Assignment.id == SubmittedAssignment.assignment_id)\
            .filter(Notebook.name == notebook, Assignment.name == assignment)\
            .all()

    def student_submissions(self, student):
        """Find all submissions by a given student.

        Parameters
        ----------
        student : string
            the student's unique id

        Returns
        -------
        list of nbgrader.api.SubmittedAssignment objects

        """

        return self.db.query(SubmittedAssignment)\
            .join(Student, Student.id == SubmittedAssignment.student_id)\
            .filter(Student.id == student)\
            .all()

    def find_submission_notebook(self, notebook, assignment, student):
        """Find a particular notebook in a student's submission for a given 
        assignment.

        Parameters
        ----------
        notebook : string
            the name of a notebook
        assignment : string
            the name of an assignment
        student : string
            the unique id of a student

        Returns
        -------
        nbgrader.api.SubmittedNotebook object

        """
        
        try:
            notebook = self.db.query(SubmittedNotebook)\
                .join(Notebook, Notebook.id == SubmittedNotebook.notebook_id)\
                .join(SubmittedAssignment, SubmittedAssignment.id == SubmittedNotebook.assignment_id)\
                .join(Assignment, Assignment.id == SubmittedAssignment.assignment_id)\
                .join(Student, Student.id == SubmittedAssignment.student_id)\
                .filter(
                    Notebook.name == notebook,
                    Assignment.name == assignment,
                    Student.id == student)\
                .one()
        except NoResultFound:
            raise MissingEntry("No such submitted notebook: {}/{} for {}".format(
                assignment, notebook, student))

        return notebook

    def find_submission_notebook_by_id(self, notebook_id):
        """Find a submitted notebook by its unique id.

        Parameters
        ----------
        notebook_id : string
            the unique id of the submitted notebook

        Returns
        -------
        nbgrader.api.SubmittedNotebook object

        """

        try:
            notebook = self.db.query(SubmittedNotebook)\
                .filter(SubmittedNotebook.id == notebook_id)\
                .one()
        except NoResultFound:
            raise MissingEntry("No such submitted notebook: {}".format(notebook_id))

        return notebook

    def find_grade(self, grade_cell, notebook, assignment, student):
        """Find a particular grade in a notebook in a student's submission 
        for a given assignment.

        Parameters
        ----------
        grade_cell : string
            the name of a grade cell
        notebook : string
            the name of a notebook
        assignment : string
            the name of an assignment
        student : string
            the unique id of a student

        Returns
        -------
        nbgrader.api.Grade object

        """
        try:
            grade = self.db.query(Grade)\
                .join(GradeCell, GradeCell.id == Grade.cell_id)\
                .join(SubmittedNotebook, SubmittedNotebook.id == Grade.notebook_id)\
                .join(Notebook, Notebook.id == SubmittedNotebook.notebook_id)\
                .join(SubmittedAssignment, SubmittedAssignment.id == SubmittedNotebook.assignment_id)\
                .join(Assignment, Assignment.id == SubmittedAssignment.assignment_id)\
                .join(Student, Student.id == SubmittedAssignment.student_id)\
                .filter(
                    GradeCell.name == grade_cell,
                    Notebook.name == notebook,
                    Assignment.name == assignment,
                    Student.id == student)\
                .one()
        except NoResultFound:
            raise MissingEntry("No such grade: {}/{}/{} for {}".format(
                assignment, notebook, grade_cell, student))

        return grade

    def find_grade_by_id(self, grade_id):
        """Find a grade by its unique id.

        Parameters
        ----------
        grade_id : string
            the unique id of the grade

        Returns
        -------
        nbgrader.api.Grade object

        """

        try:
            grade = self.db.query(Grade).filter(Grade.id == grade_id).one()
        except NoResultFound:
            raise MissingEntry("No such grade: {}".format(grade_id))

        return grade

    def find_comment(self, solution_cell, notebook, assignment, student):
        """Find a particular comment in a notebook in a student's submission 
        for a given assignment.

        Parameters
        ----------
        solution_cell : string
            the name of a solution cell
        notebook : string
            the name of a notebook
        assignment : string
            the name of an assignment
        student : string
            the unique id of a student

        Returns
        -------
        nbgrader.api.Comment object

        """

        try:
            comment = self.db.query(Comment)\
                .join(SolutionCell, SolutionCell.id == Comment.cell_id)\
                .join(SubmittedNotebook, SubmittedNotebook.id == Comment.notebook_id)\
                .join(Notebook, Notebook.id == SubmittedNotebook.notebook_id)\
                .join(SubmittedAssignment, SubmittedAssignment.id == SubmittedNotebook.assignment_id)\
                .join(Assignment, Assignment.id == SubmittedAssignment.assignment_id)\
                .join(Student, Student.id == SubmittedAssignment.student_id)\
                .filter(
                    SolutionCell.name == solution_cell,
                    Notebook.name == notebook,
                    Assignment.name == assignment,
                    Student.id == student)\
                .one()
        except NoResultFound:
            raise MissingEntry("No such comment: {}/{}/{} for {}".format(
                assignment, notebook, solution_cell, student))

        return comment

    def find_comment_by_id(self, comment_id):
        """Find a comment by its unique id.

        Parameters
        ----------
        comment_id : string
            the unique id of the comment

        Returns
        -------
        nbgrader.api.Comment object

        """
        
        try:
            comment = self.db.query(Comment).filter(Comment.id == comment_id).one()
        except NoResultFound:
            raise MissingEntry("No such comment: {}".format(comment_id))

        return comment

    def average_assignment_score(self, assignment_id):
        """Compute the average score for an assignment.

        Parameters
        ----------
        assignment_id : string
            the name of the assignment

        Returns
        -------
        float : the average score

        """

        assignment = self.find_assignment(assignment_id)
        if assignment.num_submissions == 0:
            return 0.0

        score_sum = self.db.query(func.coalesce(func.sum(Grade.score), 0.0))\
            .join(GradeCell, Notebook, Assignment)\
            .filter(Assignment.name == assignment_id).scalar()
        return score_sum / assignment.num_submissions

    def average_assignment_code_score(self, assignment_id):
        """Compute the average code score for an assignment.

        Parameters
        ----------
        assignment_id : string
            the name of the assignment

        Returns
        -------
        float : the average code score

        """

        assignment = self.find_assignment(assignment_id)
        if assignment.num_submissions == 0:
            return 0.0

        score_sum = self.db.query(func.coalesce(func.sum(Grade.score), 0.0))\
            .join(GradeCell, Notebook, Assignment)\
            .filter(and_(
                Assignment.name == assignment_id,
                Notebook.assignment_id == Assignment.id,
                GradeCell.notebook_id == Notebook.id,
                Grade.cell_id == GradeCell.id,
                GradeCell.cell_type == "code")).scalar()
        return score_sum / assignment.num_submissions

    def average_assignment_written_score(self, assignment_id):
        """Compute the average written score for an assignment.

        Parameters
        ----------
        assignment_id : string
            the name of the assignment

        Returns
        -------
        float : the average writtenscore

        """

        assignment = self.find_assignment(assignment_id)
        if assignment.num_submissions == 0:
            return 0.0

        score_sum = self.db.query(func.coalesce(func.sum(Grade.score), 0.0))\
            .join(GradeCell, Notebook, Assignment)\
            .filter(and_(
                Assignment.name == assignment_id,
                Notebook.assignment_id == Assignment.id,
                GradeCell.notebook_id == Notebook.id,
                Grade.cell_id == GradeCell.id,
                GradeCell.cell_type == "markdown")).scalar()
        return score_sum / assignment.num_submissions

    def average_notebook_score(self, notebook_id, assignment_id):
        """Compute the average score for a particular notebook in an assignment.

        Parameters
        ----------
        notebook_id : string
            the name of the notebook
        assignment_id : string
            the name of the assignment

        Returns
        -------
        float : the average score

        """

        notebook = self.find_notebook(notebook_id, assignment_id)
        if notebook.num_submissions == 0:
            return 0.0

        score_sum = self.db.query(func.coalesce(func.sum(Grade.score), 0.0))\
            .join(SubmittedNotebook, Notebook, Assignment)\
            .filter(and_(
                Notebook.name == notebook_id,
                Assignment.name == assignment_id)).scalar()
        return score_sum / notebook.num_submissions

    def average_notebook_code_score(self, notebook_id, assignment_id):
        """Compute the average code score for a particular notebook in an 
        assignment.

        Parameters
        ----------
        notebook_id : string
            the name of the notebook
        assignment_id : string
            the name of the assignment

        Returns
        -------
        float : the average code score

        """

        notebook = self.find_notebook(notebook_id, assignment_id)
        if notebook.num_submissions == 0:
            return 0.0

        score_sum = self.db.query(func.coalesce(func.sum(Grade.score), 0.0))\
            .join(GradeCell, Notebook, Assignment)\
            .filter(and_(
                Notebook.name == notebook_id,
                Assignment.name == assignment_id,
                Notebook.assignment_id == Assignment.id,
                GradeCell.notebook_id == Notebook.id,
                Grade.cell_id == GradeCell.id,
                GradeCell.cell_type == "code")).scalar()
        return score_sum / notebook.num_submissions

    def average_notebook_written_score(self, notebook_id, assignment_id):
        """Compute the average written score for a particular notebook in an 
        assignment.

        Parameters
        ----------
        notebook_id : string
            the name of the notebook
        assignment_id : string
            the name of the assignment

        Returns
        -------
        float : the average written score

        """

        notebook = self.find_notebook(notebook_id, assignment_id)
        if notebook.num_submissions == 0:
            return 0.0

        score_sum = self.db.query(func.coalesce(func.sum(Grade.score), 0.0))\
            .join(GradeCell, Notebook, Assignment)\
            .filter(and_(
                Notebook.name == notebook_id,
                Assignment.name == assignment_id,
                Notebook.assignment_id == Assignment.id,
                GradeCell.notebook_id == Notebook.id,
                Grade.cell_id == GradeCell.id,
                GradeCell.cell_type == "markdown")).scalar()
        return score_sum / notebook.num_submissions

    def student_dicts(self):
        """Returns a list of dictionaries containing student data. Equivalent
        to calling Student.to_dict() for each student, except that this method
        is implemented using proper SQL joins and is much faster.

        """
        # subquery the scores
        scores = self.db.query(
            Student.id,
            func.sum(Grade.score).label("score")
        ).join(SubmittedAssignment, SubmittedNotebook, Grade)\
         .group_by(Student.id)\
         .subquery()

        # full query
        students = self.db.query(
            Student.id, Student.first_name, Student.last_name,
            Student.email, func.coalesce(scores.c.score, 0.0),
            func.sum(GradeCell.max_score)
        ).outerjoin(scores, Student.id == scores.c.id)\
         .group_by(Student.id)\
         .all()

        keys = ["id", "first_name", "last_name", "email", "score", "max_score"]
        return [dict(zip(keys, x)) for x in students]

    def notebook_submission_dicts(self, notebook_id, assignment_id):
        """Returns a list of dictionaries containing submission data. Equivalent
        to calling SubmittedNotebook.to_dict() for each submission, except that 
        this method is implemented using proper SQL joins and is much faster.

        Parameters
        ----------
        notebook_id : string
            the name of the notebook
        assignment_id : string
            the name of the assignment

        """
        # subquery the code scores
        code_scores = self.db.query(
            SubmittedNotebook.id,
            func.sum(Grade.score).label("code_score"), 
            func.sum(GradeCell.max_score).label("max_code_score"),
        ).join(SubmittedAssignment, Notebook, Assignment, Student, Grade, GradeCell)\
         .filter(GradeCell.cell_type == "code")\
         .group_by(SubmittedNotebook.id)\
         .subquery()

        # subquery for the written scores
        written_scores = self.db.query(
            SubmittedNotebook.id,
            func.sum(Grade.score).label("written_score"), 
            func.sum(GradeCell.max_score).label("max_written_score"),
        ).join(SubmittedAssignment, Notebook, Assignment, Student, Grade, GradeCell)\
         .filter(GradeCell.cell_type == "markdown")\
         .group_by(SubmittedNotebook.id)\
         .subquery()

        # subquery for needing manual grading
        manual_grade = self.db.query(
            SubmittedNotebook.id,
            exists().where(Grade.needs_manual_grade).label("needs_manual_grade")
        ).join(SubmittedAssignment, Assignment, Notebook)\
         .filter(
             Grade.notebook_id == SubmittedNotebook.id,
             Grade.needs_manual_grade)\
         .group_by(SubmittedNotebook.id)\
         .subquery()

        # subquery for failed tests
        failed_tests = self.db.query(
            SubmittedNotebook.id,
            exists().where(Grade.failed_tests).label("failed_tests")
        ).join(SubmittedAssignment, Assignment, Notebook)\
         .filter(
             Grade.notebook_id == SubmittedNotebook.id,
             Grade.failed_tests)\
         .group_by(SubmittedNotebook.id)\
         .subquery()

        # full query
        submissions = self.db.query(
            SubmittedNotebook.id, Notebook.name, Student.id,
            func.sum(Grade.score), func.sum(GradeCell.max_score),
            code_scores.c.code_score, code_scores.c.max_code_score,
            written_scores.c.written_score, written_scores.c.max_written_score,
            func.coalesce(manual_grade.c.needs_manual_grade, False),
            func.coalesce(failed_tests.c.failed_tests, False)
        ).join(SubmittedAssignment, Notebook, Assignment, Student, Grade, GradeCell)\
         .outerjoin(code_scores, SubmittedNotebook.id == code_scores.c.id)\
         .outerjoin(written_scores, SubmittedNotebook.id == written_scores.c.id)\
         .outerjoin(manual_grade, SubmittedNotebook.id == manual_grade.c.id)\
         .outerjoin(failed_tests, SubmittedNotebook.id == failed_tests.c.id)\
         .filter(and_(
             Notebook.name == notebook_id,
             Assignment.name == assignment_id,
             Student.id == SubmittedAssignment.student_id,
             SubmittedAssignment.id == SubmittedNotebook.assignment_id,
             SubmittedNotebook.id == Grade.notebook_id,
             GradeCell.id == Grade.cell_id))\
         .group_by(Student.id)\
         .all()

        keys = [
            "id", "name", "student", 
            "score", "max_score", 
            "code_score", "max_code_score", 
            "written_score", "max_written_score",
            "needs_manual_grade",
            "failed_tests"
        ]
        return [dict(zip(keys, x)) for x in submissions]
