from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
import json
import csv
import io
from datetime import datetime
import uuid

from app.repositories import TaskRepository
from app.schemas import TaskCreate
from app.models import StatusEnum
from .base import BaseService


class ImportService(BaseService):
    """Service for importing tasks from external sources."""
    
    def __init__(self, db: Session):
        super().__init__(db)
        self.task_repo = TaskRepository(db)
    
    def import_from_trello_json(self, json_content: str, user_id: str) -> Dict[str, Any]:
        """Import tasks from Trello JSON export."""
        try:
            trello_data = json.loads(json_content)
            
            # Extract cards from lists
            cards = []
            for trello_list in trello_data.get('lists', []):
                list_name = trello_list.get('name', '').lower()
                status = self._map_list_name_to_status(list_name)
                
                for card in trello_list.get('cards', []):
                    if not card.get('closed', False):  # Skip archived cards
                        card['mapped_status'] = status
                        cards.append(card)
            
            # Also check if cards are directly in the JSON (alternative format)
            if 'cards' in trello_data:
                for card in trello_data['cards']:
                    if not card.get('closed', False):
                        # Try to find the list this card belongs to
                        list_id = card.get('idList')
                        list_name = ''
                        for trello_list in trello_data.get('lists', []):
                            if trello_list.get('id') == list_id:
                                list_name = trello_list.get('name', '').lower()
                                break
                        
                        card['mapped_status'] = self._map_list_name_to_status(list_name)
                        cards.append(card)
            
            return self._create_tasks_from_cards(cards, user_id)
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse Trello JSON: {str(e)}")
            raise ValueError(f"Invalid JSON format: {str(e)}")
        except Exception as e:
            self.logger.error(f"Failed to import from Trello JSON: {str(e)}")
            raise
    
    def import_from_trello_csv(self, csv_content: str, user_id: str) -> Dict[str, Any]:
        """Import tasks from Trello CSV export."""
        try:
            cards = []
            csv_file = io.StringIO(csv_content)
            reader = csv.DictReader(csv_file)
            
            for row in reader:
                # Map CSV columns to card format
                list_name = row.get('List', '').lower()
                card = {
                    'name': row.get('Card Name', row.get('Title', '')),
                    'desc': row.get('Description', ''),
                    'due': row.get('Due Date', ''),
                    'mapped_status': self._map_list_name_to_status(list_name)
                }
                cards.append(card)
            
            return self._create_tasks_from_cards(cards, user_id)
            
        except Exception as e:
            self.logger.error(f"Failed to import from Trello CSV: {str(e)}")
            raise
    
    def _map_list_name_to_status(self, list_name: str) -> str:
        """Map Trello list names to task statuses."""
        list_name = list_name.lower().strip()
        
        # Common Trello list name patterns
        if 'backlog' in list_name or 'ideas' in list_name or 'later' in list_name:
            return StatusEnum.backlog.value
        elif 'to do' in list_name or 'todo' in list_name or 'this week' in list_name or 'week' in list_name:
            return StatusEnum.week.value
        elif 'today' in list_name or 'doing' in list_name or 'in progress' in list_name:
            return StatusEnum.today.value
        elif 'done' in list_name or 'completed' in list_name:
            return StatusEnum.done.value
        elif 'waiting' in list_name or 'blocked' in list_name:
            return StatusEnum.waiting.value
        else:
            # Default mapping for unknown list names
            return StatusEnum.week.value
    
    def _create_tasks_from_cards(self, cards: List[Dict], user_id: str) -> Dict[str, Any]:
        """Create tasks from card data."""
        try:
            imported_tasks = []
            task_ids = []
            
            for card in cards:
                # Create task data
                task_data = TaskCreate(
                    title=card.get('name', 'Untitled Task').strip() or 'Untitled Task',
                    description=card.get('desc', '').strip() or None,
                    status=card.get('mapped_status', StatusEnum.week.value),
                    soft_due_at=self._parse_due_date(card.get('due'))
                )
                
                # Create the task
                task = self.task_repo.create_with_tags(task_data, user_id)
                imported_tasks.append(task)
                task_ids.append(task.id)
                
                self.logger.debug(f"Imported task: {task.title} -> {task.status}")
            
            self.commit()
            
            self.logger.info(f"Successfully imported {len(imported_tasks)} tasks from Trello")
            
            return {
                "imported_count": len(imported_tasks),
                "task_ids": task_ids
            }
            
        except Exception as e:
            self.rollback()
            self.logger.error(f"Failed to create tasks from cards: {str(e)}")
            raise
    
    def _parse_due_date(self, due_date_str: Optional[str]) -> Optional[datetime]:
        """Parse due date from various formats."""
        if not due_date_str or not due_date_str.strip():
            return None
        
        due_date_str = due_date_str.strip()
        
        # Common date formats from Trello
        date_formats = [
            '%Y-%m-%dT%H:%M:%S.%fZ',  # ISO format with microseconds
            '%Y-%m-%dT%H:%M:%SZ',     # ISO format
            '%Y-%m-%d',               # Simple date
            '%m/%d/%Y',               # US format
            '%d/%m/%Y',               # EU format
        ]
        
        for fmt in date_formats:
            try:
                return datetime.strptime(due_date_str, fmt)
            except ValueError:
                continue
        
        self.logger.warning(f"Could not parse due date: {due_date_str}")
        return None