from datetime import date, datetime
from typing import List, Dict, Optional

from sqlalchemy import Boolean, String, Integer, DateTime, Text, ForeignKey, create_engine, event, func, Index, Date, Float

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
    __table_args__ = (
        Index("ix_testresults_patient_date", "patient_id", "test_date"),
        Index("ix_testresults_patient_name", "patient_id", "test_name"),
        Index("ix_testresults_session_id", "session_id"),
    )

    test_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False, index=True)
    test_name: Mapped[Optional[str]] = mapped_column(String(100))
    test_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    recording_file: Mapped[Optional[str]] = mapped_column(String(512))
    frame_count: Mapped[Optional[int]] = mapped_column(Integer)
    session_id: Mapped[Optional[str]] = mapped_column(String(64))
    fps: Mapped[Optional[int]] = mapped_column(Integer)
    summary_available: Mapped[Optional[bool]] = mapped_column(Boolean)
    dtw: Mapped[Optional[Dict]] = mapped_column(JSON)
    extra: Mapped[Optional[Dict]] = mapped_column(JSON)
    patient: Mapped["Patient"] = relationship(back_populates="testresults")
    ml_predictions: Mapped[List["MLPrediction"]] = relationship(
        "MLPrediction",
        back_populates="test_result",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class MLPrediction(Base):
    __tablename__ = "ml_predictions"
    __table_args__ = (
        Index("ix_ml_predictions_test_result", "test_result_id"),
        Index("ix_ml_predictions_patient_created", "patient_id", "created_at"),
        Index("ix_ml_predictions_session", "session_id"),
        Index("ix_ml_predictions_type", "prediction_type"),
    )

    prediction_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    test_result_id: Mapped[int] = mapped_column(
        ForeignKey("testresults.test_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    patient_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    test_name: Mapped[Optional[str]] = mapped_column(String(100))

    prediction_type: Mapped[str] = mapped_column(String(64), nullable=False)
    video_model: Mapped[Optional[str]] = mapped_column(String(128))
    classifier_model: Mapped[Optional[str]] = mapped_column(String(128))
    model_version: Mapped[Optional[str]] = mapped_column(String(128))
    model_artifact_path: Mapped[Optional[str]] = mapped_column(String(512))

    predicted_label: Mapped[str] = mapped_column(String(64), nullable=False)
    probability: Mapped[Optional[float]] = mapped_column(Float)
    score: Mapped[Optional[float]] = mapped_column(Float)

    input_video_path: Mapped[Optional[str]] = mapped_column(String(512))
    input_filename: Mapped[Optional[str]] = mapped_column(String(512))
    embedding_artifact_path: Mapped[Optional[str]] = mapped_column(String(512))

    request_json: Mapped[Optional[Dict]] = mapped_column(JSON)
    response_json: Mapped[Optional[Dict]] = mapped_column(JSON)
    error_json: Mapped[Optional[Dict]] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    test_result: Mapped["TestResult"] = relationship("TestResult", back_populates="ml_predictions")

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



