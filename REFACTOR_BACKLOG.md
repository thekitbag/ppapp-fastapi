# Refactor Backlog

Outstanding items from the initial repository review (scores unchanged).

## P0 / P1

- [ ] **Unify status/enums between models/schemas and fix drift in recommendations** (Urgency **6/10**, Importance **8/10**)  
  Impact if not done: subtle behavior mismatches (e.g., recommendation scoring checks `"todo"` while app uses `backlog/week/today/...`), dead logic, and future breakage when statuses evolve.

- [ ] **Split `GoalService` into cohesive modules** (Urgency **5/10**, Importance **7/10**)  
  Impact if not done: slower iteration, higher bug rate, and “small change breaks unrelated feature” risk due to a large, multi-responsibility service.

## P2

- [ ] **Standardize timezone policy (UTC) + naive/aware handling** (Urgency **5/10**, Importance **6/10**)  
  Impact if not done: flaky due-date logic, inconsistent filtering/sorting, and subtle serialization/comparison bugs.

- [ ] **Centralize ID generation and conventions** (Urgency **4/10**, Importance **6/10**)  
  Impact if not done: inconsistent IDs across tables/APIs, harder debugging/searching, and migration/interop pain later.

- [ ] **Reduce router boilerplate with shared dependency providers** (Urgency **3/10**, Importance **5/10**)  
  Impact if not done: repetitive endpoint code, inconsistent dependency wiring, and slower endpoint additions.

- [ ] **Tighten exception handling patterns** (Urgency **4/10**, Importance **5/10**)  
  Impact if not done: noisy logs with hidden root causes, inconsistent error shapes, and operational issues that are harder to triage.

