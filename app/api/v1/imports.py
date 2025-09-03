from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any, List
import json
import csv
import io

from app.db import get_db
from app.services.imports import ImportService

router = APIRouter()


def get_import_service(db: Session = Depends(get_db)) -> ImportService:
    """Dependency to get ImportService instance."""
    return ImportService(db)


@router.post("/trello")
def import_trello(
    file: UploadFile = File(...),
    import_service: ImportService = Depends(get_import_service)
):
    """Import tasks from Trello export file (JSON or CSV format)."""
    
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    file_extension = file.filename.lower().split('.')[-1]
    
    if file_extension not in ['json', 'csv']:
        raise HTTPException(
            status_code=400, 
            detail="Only JSON and CSV files are supported"
        )
    
    try:
        content = file.file.read().decode('utf-8')
        
        if file_extension == 'json':
            result = import_service.import_from_trello_json(content)
        else:  # csv
            result = import_service.import_from_trello_csv(content)
        
        return {
            "message": "Import completed successfully",
            "imported_tasks": result["imported_count"],
            "task_ids": result["task_ids"]
        }
        
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")
    finally:
        file.file.close()