from datetime import date, datetime
from typing import List, Dict, Optional

from sqlalchemy import String, Integer, DateTime, Text, ForeignKey, create_engine, event, func, Index, Date

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from sqlalchemy.types import JSON

class Base(DeclarativeBase): pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(320), unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable = False)
    title: Mapped[str] = mapped_column(String(255), nullable = False)
    speciality: Mapped[str] = mapped_column(String(255), nullable = False)

    # one user -> many patients
    patients: Mapped[List["Patient"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",   # deleting a user deletes their patients
        passive_deletes=True,
        lazy="selectin",
    )

class Patient(Base):
    __tablename__ = "patients"

    patient_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    record_number: Mapped[Optional[str]] = mapped_column(String(32))
    # owner
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[Optional[str]] = mapped_column(String(255))
    dob: Mapped[Optional[date]] = mapped_column(Date)
    height: Mapped[Optional[int]] = mapped_column(Integer)
    weight: Mapped[Optional[int]] = mapped_column(Integer)
    severity: Mapped[Optional[str]] = mapped_column(String(50))

    # many patients -> one user
    user: Mapped["User"] = relationship(back_populates="patients")

    # children
    labresults: Mapped[List["LabResult"]] = relationship(
        "LabResult", back_populates="patient", cascade="all, delete-orphan", passive_deletes=True
    )
    doctornotes: Mapped[List["DoctorNote"]] = relationship(
        "DoctorNote", back_populates="patient", cascade="all, delete-orphan", passive_deletes=True
    )
    testresults: Mapped[List["TestResult"]] = relationship(
        "TestResult", back_populates="patient", cascade="all, delete-orphan", passive_deletes=True
    )

class LabResult(Base):
    __tablename__ = "labresults"
    lab_id: Mapped[str] = mapped_column(String, primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False, index=True)
    result_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    results: Mapped[Optional[str]] = mapped_column(Text)
    added_by: Mapped[Optional[str]] = mapped_column(String(255))
    patient: Mapped["Patient"] = relationship(back_populates="labresults")
    

class DoctorNote(Base):
    __tablename__ = "doctornotes"
    note_id: Mapped[str] = mapped_column(String, primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False, index=True)
    note_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    note: Mapped[Optional[str]] = mapped_column(Text)
    added_by: Mapped[Optional[str]] = mapped_column(String(255))
    patient: Mapped["Patient"] = relationship(back_populates="doctornotes")

class TestResult(Base):
    __tablename__ = "testresults"
    test_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False, index=True)
    test_name: Mapped[Optional[str]] = mapped_column(String(100))
    test_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    recording_file: Mapped[Optional[str]] = mapped_column(String(512))
    frame_count: Mapped[Optional[int]] = mapped_column(Integer)
    patient: Mapped["Patient"] = relationship(back_populates="testresults")

# SQLite FK enforcement
def _set_sqlite_pragma(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON;")
    cur.close()

if __name__ == "__main__":
    engine = create_engine("sqlite:///patients.db", echo=True, future=True)
    if engine.url.get_backend_name() == "sqlite":
        event.listen(engine, "connect", _set_sqlite_pragma)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    # example
    with Session() as s:
        u = User(
            username="doc_amy",
            full_name="Dr. Amy",
            email="amy@example.com",
            hashed_password="***",
            location="UF Health",
            title="Neurologist",
            speciality="Movement Disorders",
        )
        p = Patient(patient_id="P001", name="John Smith", user=u)  # assign owner
        s.add_all([u, p])
        s.commit()
        # s.query(Patient).filter_by(user_id=u.id).all()





