"""Transactional write use cases and a genuinely read-only bulk planner."""
from datetime import datetime
from app.exceptions import ValidationError
from app.mcp_schemas import GoalDraft, TaskDraft, GoalPatch, TaskPatch, BatchGoal, BatchTask
from app.repositories.mcp_write import MCPWriteRepository
from app.schemas import GoalCreate, GoalUpdate, TaskCreate, TaskUpdate, TaskGoalLink
from app.services.base import atomic
from app.services.goal import GoalService
from app.services.task import TaskService
from app.services.mcp_read import MCPReadService, utc


class MCPWriteService:
    def __init__(self, db, user_id):
        self.db, self.user_id = db, user_id
        self.repo = MCPWriteRepository(db, user_id)
        self.read = MCPReadService(db, user_id)
        self.goals, self.tasks = GoalService(db), TaskService(db)

    @staticmethod
    def _dates(soft, hard):
        if soft and hard and utc(soft) > utc(hard):
            raise ValidationError('soft_due_at cannot be after hard_due_at')

    def _create_goal(self, draft, parent_id):
        return self.goals.create_goal(GoalCreate(
            **draft.model_dump(exclude={'parent', 'key'}), parent_goal_id=parent_id), self.user_id)

    def _create_task(self, draft, goal_ids, project_id):
        self._dates(draft.soft_due_at, draft.hard_due_at)
        result, _ = self.tasks.create_task(TaskCreate(
            **draft.model_dump(exclude={'goals', 'project', 'key'}),
            goals=list(dict.fromkeys(goal_ids)), project_id=project_id), self.user_id)
        if draft.status == 'done':
            self.tasks.update_task(result.id, self.user_id, {'status': 'done'})
        return result.id

    def create_goal(self, **arguments):
        draft = GoalDraft.model_validate(arguments)
        with atomic(self.db):
            parent_id = self.read.resolve_goal(draft.parent) if draft.parent is not None else None
            return self._create_goal(draft, parent_id).model_dump(mode='json')

    def create_task(self, **arguments):
        draft = TaskDraft.model_validate(arguments)
        with atomic(self.db):
            ids = [self.read.resolve_goal(ref) for ref in draft.goals]
            project_id = self.repo.resolve_project(draft.project)
            task_id = self._create_task(draft, ids, project_id)
            return self.read.task_results([task_id])[0]

    def update_goal(self, goal, **changes):
        patch = GoalPatch.model_validate(changes)
        payload = GoalUpdate.model_validate(patch.model_dump(exclude_unset=True))
        with atomic(self.db):
            goal_id = self.read.resolve_goal(goal)
            return self.goals.update_goal(goal_id, self.user_id,
                payload.model_dump(exclude_unset=True)).model_dump(mode='json')

    def update_task(self, task_id, **changes):
        patch = TaskPatch.model_validate(changes)
        native = {key: value for key, value in patch.model_dump(exclude_unset=True).items()
                  if key in ('title', 'description', 'status', 'soft_due_at', 'hard_due_at')}
        # Reuse REST's due-date validation, including explicit null clearing.
        native = TaskUpdate.model_validate(native).model_dump(exclude_unset=True)
        with atomic(self.db):
            task = self.repo.task(task_id)
            additions = {self.read.resolve_goal(ref) for ref in patch.add_goals}
            removals = {self.read.resolve_goal(ref) for ref in patch.remove_goals}
            if additions & removals:
                raise ValidationError('The same goal cannot be added and removed together')
            self._dates(native.get('soft_due_at', task.soft_due_at), native.get('hard_due_at', task.hard_due_at))
            if 'add_tags' in changes or 'remove_tags' in changes:
                tags = {tag.name for tag in task.tags if tag.user_id == self.user_id}
                native['tags'] = sorted((tags - set(patch.remove_tags)) | set(patch.add_tags))
            if changes:
                native['updated_at'] = datetime.utcnow()
                self.tasks.update_task(task_id, self.user_id, native)
            self.repo.remove_goal_links(task, removals)
            existing = self.repo.existing_goal_ids(task)
            for goal_id in sorted(additions - existing):
                self.goals.link_tasks_to_goal(goal_id, self.user_id, TaskGoalLink(task_ids=[task_id]))
            self.db.flush()
            return self.read.task_results([task_id])[0]

    def _plan(self, goals, tasks):
        """Resolve the whole batch using SELECTs only; no ORM objects are added."""
        existing = {goal.id: goal for goal in self.read.repo.goals()}
        aliases = {}
        errors = []
        def error(path, message):
            errors.append({'path': path, 'message': message})
        def alias(name, target):
            if name is not None:
                aliases.setdefault(name, set()).add(target)
        for goal in existing.values():
            alias(goal.id, ('existing', goal.id))
            alias(goal.plan_ref, ('existing', goal.id))
        keys = set()
        refs = {goal.plan_ref for goal in existing.values() if goal.plan_ref is not None}
        for kind, items in [('goals', goals), ('tasks', tasks)]:
            for i, item in enumerate(items):
                if item.key is not None:
                    if not item.key.strip() or item.key in keys or item.key in aliases:
                        error(f'{kind}[{i}].key', 'Batch keys must be nonblank, unique and must not shadow an existing goal reference')
                    keys.add(item.key)
                if kind == 'goals':
                    if item.plan_ref is not None:
                        if item.plan_ref in refs:
                            error(f'goals[{i}].plan_ref', 'Goal plan_ref already exists for this user or batch')
                        refs.add(item.plan_ref)
                    alias(item.key, ('batch', i))
                    alias(item.plan_ref, ('batch', i))
        for key in keys:
            if len(aliases.get(key, set())) > 1:
                error('keys', f"Batch key '{key}' conflicts with another goal reference")
        def resolve(reference, path):
            matches = aliases.get(reference, set())
            if len(matches) != 1:
                error(path, f"Goal reference '{reference}' " + ('not found' if not matches else 'is ambiguous'))
                return None
            return next(iter(matches))
        def describe(target):
            if target is None:
                return None
            kind, value = target
            if kind == 'existing':
                return {'source': kind, 'id': value, 'plan_ref': existing[value].plan_ref}
            draft = goals[value]
            return {'source': kind, 'batch_index': value, 'key': draft.key, 'plan_ref': draft.plan_ref}

        parents = []
        for i, draft in enumerate(goals):
            parent = resolve(draft.parent, f'goals[{i}].parent') if draft.parent is not None else None
            parents.append(parent)
            if draft.parent is not None and parent is None:
                continue
            parent_type = None
            if parent:
                parent_type = (existing[parent[1]].type.value if existing[parent[1]].type else None) if parent[0] == 'existing' else goals[parent[1]].type
            expected = {'quarterly': 'annual', 'weekly': 'quarterly'}.get(draft.type)
            if draft.type == 'annual' and parent is not None:
                error(f'goals[{i}].parent', 'Annual goals cannot have a parent')
            elif expected and parent_type != expected:
                error(f'goals[{i}].parent', f'{draft.type.capitalize()} goals require a {expected} parent')
        order, state = [], {}
        def visit(index):
            if state.get(index) == 1:
                error(f'goals[{index}].parent', 'Goal hierarchy contains a cycle')
                return
            if state.get(index) == 2:
                return
            state[index] = 1
            parent = parents[index]
            if parent and parent[0] == 'batch':
                visit(parent[1])
            state[index] = 2
            order.append(index)
        for i in range(len(goals)):
            visit(i)

        task_goals, projects = [], []
        for i, draft in enumerate(tasks):
            resolved = [resolve(ref, f'tasks[{i}].goals[{j}]') for j, ref in enumerate(draft.goals)]
            task_goals.append(list(dict.fromkeys(resolved)))
            project = None
            try:
                project = self.repo.resolve_project(draft.project)
                self._dates(draft.soft_due_at, draft.hard_due_at)
            except ValidationError as exc:
                error(f'tasks[{i}]', exc.message)
            projects.append(project)
        known_tags = {tag.name for tag in self.read.repo.tags()}
        preview = {
            'valid': not errors, 'committed': False, 'errors': errors,
            'goals': [{**draft.model_dump(), 'parent': describe(parents[i])} for i, draft in enumerate(goals)],
            'tasks': [{**draft.model_dump(), 'goals': [describe(ref) for ref in task_goals[i]],
                       'project': {'id': projects[i]} if projects[i] else None} for i, draft in enumerate(tasks)],
            'tags_to_create': sorted({tag for draft in tasks for tag in draft.tags} - known_tags),
        }
        return preview, order, parents, task_goals, projects

    def bulk_create(self, goals=None, tasks=None, dry_run=True):
        if type(dry_run) is not bool:
            raise ValidationError('dry_run must be a JSON boolean')
        goals = [BatchGoal.model_validate(goal) for goal in (goals or [])]
        tasks = [BatchTask.model_validate(task) for task in (tasks or [])]
        if len(goals) + len(tasks) > 1000:
            raise ValidationError('A batch can contain at most 1000 goals and tasks')
        if dry_run:
            with self.db.no_autoflush:
                preview, *_ = self._plan(goals, tasks)
            return {'dry_run': True, **preview}
        with atomic(self.db):
            preview, order, parents, task_goals, projects = self._plan(goals, tasks)
            if not preview['valid']:
                return {'dry_run': False, **preview}
            created = {}
            def actual_id(target):
                return target[1] if target[0] == 'existing' else created[target[1]].id
            for index in order:
                parent_id = actual_id(parents[index]) if parents[index] else None
                created[index] = self._create_goal(goals[index], parent_id)
            task_ids = [self._create_task(draft, [actual_id(ref) for ref in task_goals[i]], projects[i])
                        for i, draft in enumerate(tasks)]
            rendered = self.read.task_results(task_ids)
            return {'dry_run': False, 'valid': True, 'committed': True, 'errors': [],
                    'goals': [{'key': goals[i].key, **created[i].model_dump(mode='json')} for i in range(len(goals))],
                    'tasks': [{'key': draft.key, **task} for draft, task in zip(tasks, rendered)],
                    'tags_created': preview['tags_to_create']}
