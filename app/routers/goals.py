from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import uuid

from app import crud, models, schemas
from app.db import get_db

router = APIRouter()

@router.post("/goals", response_model=schemas.Goal)
def create_goal(goal: schemas.GoalCreate, db: Session = Depends(get_db)):
    goal_id = f"goal_{uuid.uuid4()}"
    return crud.create_goal(db=db, goal=goal, id=goal_id)

@router.get("/goals", response_model=List[schemas.Goal])
def read_goals(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    goals = crud.get_goals(db, skip=skip, limit=limit)
    return goals
