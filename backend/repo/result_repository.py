from typing import Optional, List, Dict, Any
from datetime import date
from sqlalchemy.orm import Session
from repo.sql_models import TestResult


class TestResultRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, test_id: int) -> Optional[TestResult]:
        return self.session.get(TestResult, test_id)

    def add(self, test: TestResult) -> TestResult:
        self.session.add(test)
        self.session.commit()
        self.session.refresh(test)
        return test

    def update(self, test_id: int, update_data: Dict[str, Any]) -> Optional[TestResult]:
        test = self.get(test_id)
        if test is None:
            return None

        for key, value in update_data.items():
            if hasattr(test, key):
                setattr(test, key, value)

        self.session.commit()
        self.session.refresh(test)
        return test

    def delete(self, test_id: int) -> bool:
        test = self.get(test_id)
        if test is None:
            return False
        self.session.delete(test)
        self.session.commit()
        return True

    def list(self, skip: int = 0, limit: int = 100) -> List[TestResult]:
        return (
            self.session
            .query(TestResult)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_by_patient(self, patient_id: str) -> List[TestResult]:
        return (
            self.session
            .query(TestResult)
            .filter(TestResult.patient_id == patient_id)
            .order_by(TestResult.test_date.desc())
            .all()
        )

    def filter(
        self,
        patient_id: Optional[str] = None,
        test_name: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[TestResult]:
        query = self.session.query(TestResult)

        if patient_id:
            query = query.filter(TestResult.patient_id == patient_id)
        if test_name:
            query = query.filter(TestResult.test_name.ilike(f"%{test_name}%"))
        if start_date:
            query = query.filter(TestResult.test_date >= start_date)
        if end_date:
            query = query.filter(TestResult.test_date <= end_date)

        return query.order_by(TestResult.test_date.desc()).all()
