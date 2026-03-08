# Feature Specification: Platinum Tier — Always-On Cloud AI Employee

**Feature Branch**: `001-platinum-tier`
**Created**: 2026-03-08
**Status**: Draft
**Input**: User description: "Extend system to Platinum Tier. Add: Always-on cloud deployment, Local + Cloud agent separation, Git-based vault sync, Claim-by-move rule, Single-writer Dashboard rule, Secrets never synced, Health monitoring, VM deployment architecture"

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Always-On Cloud Processing (Priority: P1)

A user publishes a new task to their Obsidian vault on a Saturday evening and shuts down their laptop. By Sunday morning, the task has been claimed, processed, and its output written back to the vault — all by a cloud agent running on a VM, with no local machine involved.

**Why this priority**: This is the defining capability of Platinum Tier. Without continuous cloud operation, all other Platinum features are moot. It directly eliminates the "laptop must be on" limitation of Gold Tier.

**Independent Test**: Deploy only the cloud agent on a VM. Create a task file in the Git-synced vault. Shut down all local machines. Verify the task is processed and output committed to Git within 10 minutes.

**Acceptance Scenarios**:

1. **Given** the cloud agent is deployed and running on a VM, **When** a task file is pushed to the Git vault from any source, **Then** the cloud agent picks up, processes, and outputs the result within 10 minutes, without any local machine being active.
2. **Given** the cloud VM has been running for 7 days, **When** inspecting agent logs, **Then** no manual restarts or human interventions are recorded.
3. **Given** the VM reboots unexpectedly, **When** the VM comes back online, **Then** the cloud agent automatically restarts and resumes processing.

---

### User Story 2 - Local and Cloud Agent Coexistence (Priority: P2)

An operator runs the AI employee locally for quick, interactive tasks while the cloud agent handles long-running and overnight tasks. Both agents work on the same vault without stepping on each other.

**Why this priority**: Without clear separation, agents will conflict — processing the same tasks twice or corrupting outputs. Safe coexistence is a prerequisite for all multi-agent work.

**Independent Test**: Run one local and one cloud agent simultaneously against the same vault. Publish 20 tasks. Verify each task is processed exactly once, with no duplicates or skipped items.

**Acceptance Scenarios**:

1. **Given** both a local agent and a cloud agent are running, **When** 10 tasks are published, **Then** each task is processed by exactly one agent (no duplicates, no skips).
2. **Given** the local agent is offline, **When** a task is published, **Then** the cloud agent claims and processes it without waiting for the local agent.
3. **Given** the cloud agent is offline, **When** a task is published, **Then** the local agent claims and processes it independently.

---

### User Story 3 - Git-Based Vault Synchronisation (Priority: P3)

A user creates a task on their local machine. Without any manual action, that task appears in the cloud agent's view of the vault within minutes, is processed, and the result is available locally when the user next opens their laptop.

**Why this priority**: Git sync is the transport layer connecting local and cloud. All other multi-agent features depend on a reliable, conflict-minimising sync mechanism.

**Independent Test**: Write a task file locally. Confirm Git push occurs automatically. Confirm the cloud VM pulls and sees the file. Confirm cloud output is pushed and available locally after pull.

**Acceptance Scenarios**:

1. **Given** a task file is created locally, **When** the automated Git sync runs, **Then** the task file is available on the cloud VM within 5 minutes.
2. **Given** the cloud agent writes an output file, **When** the automated Git sync runs, **Then** the output is available locally within 5 minutes.
3. **Given** both agents write different files simultaneously, **When** Git sync runs, **Then** both changes are merged without conflict or data loss.
4. **Given** the network is unavailable during sync, **When** connectivity is restored, **Then** the next sync run succeeds and no data is lost.

---

### User Story 4 - Safe Task Claiming (Claim-by-Move Rule) (Priority: P4)

Two agents see the same new task at the same time. Only one of them successfully claims it and processes it. The other moves on without duplication.

**Why this priority**: Without atomic claiming, two agents will process the same task, wasting compute and potentially producing conflicting outputs. This safety rule is foundational to multi-agent correctness.

**Independent Test**: Simulate two agents polling simultaneously for the same task file. Verify exactly one agent's claim succeeds (file moved) and exactly one output is produced.

**Acceptance Scenarios**:

1. **Given** a task file sits in the `inbox/` folder, **When** an agent claims it, **Then** the file is atomically moved to `in-progress/` with the agent's identity recorded before any processing begins.
2. **Given** two agents attempt to claim the same task simultaneously, **When** both attempt the move, **Then** exactly one succeeds and the other skips the task without error.
3. **Given** a claimed task's agent crashes mid-processing, **When** a recovery timeout elapses, **Then** the task is returned to `inbox/` for re-claiming.

---

### User Story 5 - Safe Dashboard Updates (Single-Writer Rule) (Priority: P5)

Multiple agents report their status to a shared dashboard file. The dashboard always shows a coherent, non-corrupted view — never a half-written or interleaved state.

**Why this priority**: A corrupted dashboard is worse than no dashboard. The single-writer rule prevents file corruption and ensures operators always see accurate agent status.

**Independent Test**: Have three agents attempt simultaneous dashboard writes. Inspect the dashboard file after each write cycle. Verify it is always valid markdown with no corruption or truncation.

**Acceptance Scenarios**:

1. **Given** multiple agents are running, **When** all attempt to update the dashboard at the same time, **Then** updates are serialised so the file is never in a partial or corrupt state.
2. **Given** an agent crashes while holding the dashboard write lock, **When** the lock timeout elapses, **Then** other agents can acquire the lock and continue writing.
3. **Given** the dashboard is updated by the cloud agent, **When** the local agent reads it, **Then** the local agent sees a complete, valid dashboard without re-writing it.

---

### User Story 6 - Secrets Never Synced (Priority: P6)

An operator configures API keys and cloud credentials on both machines. When vault sync runs, no secrets ever appear in Git history or vault files — they remain exclusively in environment-level configuration outside the vault.

**Why this priority**: A single accidental secret commit can compromise the entire system and is difficult to reverse from Git history. This is a security invariant that must hold unconditionally.

**Independent Test**: Configure secrets as environment variables. Inspect every Git commit in the vault's history. Verify no secret values, key patterns, or credential files appear.

**Acceptance Scenarios**:

1. **Given** agents are configured with API keys and tokens, **When** vault sync commits and pushes, **Then** no secrets appear in any committed file or Git history.
2. **Given** a user accidentally places a `.env` file inside the vault directory, **When** Git sync runs, **Then** the sync process refuses to commit the file and alerts the operator.
3. **Given** the vault is cloned fresh on a new machine, **When** the agent starts, **Then** it reports missing secrets clearly and refuses to proceed until they are provided externally.

---

### User Story 7 - Health Monitoring and Alerting (Priority: P7)

An operator knows within 5 minutes if any agent — cloud or local — has stopped responding. A heartbeat file is updated periodically; a monitor checks it and raises an alert if it goes stale.

**Why this priority**: Without health monitoring, a silently dead cloud agent means tasks pile up unnoticed. Operators need confidence that the always-on system is actually always on.

**Independent Test**: Stop an agent process. Verify that after the heartbeat timeout, a health alert is recorded (log entry, file, or notification). Verify the alert clears when the agent resumes.

**Acceptance Scenarios**:

1. **Given** an agent is running, **When** the heartbeat monitor checks, **Then** the agent's heartbeat file shows a timestamp within the last expected interval.
2. **Given** an agent process is killed, **When** two heartbeat intervals pass without an update, **Then** the health monitor records an alert indicating which agent is unresponsive.
3. **Given** an alert is raised for a downed agent, **When** the agent restarts and resumes heartbeats, **Then** the health monitor records recovery and clears the alert.

---

### Edge Cases

- What happens when Git sync fails mid-push due to network loss — is the local working tree left in a clean state?
- What if a claimed task's `in-progress/` move succeeds on the file system but Git sync runs before the output is written — does the task appear orphaned?
- What if the dashboard lock file is left behind after a hard crash — how long before it is considered stale and released?
- What if two agents push conflicting commits to Git simultaneously — which push wins and how are conflicts resolved?
- What if a secrets guard mis-classifies a legitimate file as a secret — can an operator override it?
- What happens to in-progress tasks if the cloud VM is terminated and recreated with a fresh disk?

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST run at least one cloud agent continuously on a VM, independently of any local machine being active.
- **FR-002**: System MUST distinguish agent identity (local vs. cloud) and record which agent claimed and processed each task.
- **FR-003**: System MUST automatically sync vault contents (tasks, outputs, notes) between local and cloud environments using Git push/pull on a scheduled interval of no more than 5 minutes.
- **FR-004**: Agents MUST claim tasks using the claim-by-move rule: the task file is atomically moved from an `inbox/` area to an `in-progress/` area (including agent identity) before any processing begins.
- **FR-005**: If an agent that claimed a task does not complete it within a configurable timeout (default 30 minutes), the system MUST return the task to `inbox/` for re-claiming.
- **FR-006**: Dashboard writes MUST be serialised using a single-writer rule: only one agent may write to the dashboard file at a time; a file-based or equivalent lock MUST be used.
- **FR-007**: Dashboard write locks MUST expire after a configurable staleness timeout (default 60 seconds) to recover from agent crashes during writes.
- **FR-008**: Secrets (API keys, tokens, credentials) MUST be stored outside the vault directory and MUST never be committed to the Git-synced vault.
- **FR-009**: The Git sync process MUST include a pre-commit guard that detects and blocks commits containing files matching secret patterns (e.g., `.env`, `*.key`, `*secret*`, credential-like strings).
- **FR-010**: Each agent MUST write a timestamped heartbeat record to a designated vault location at a regular interval (default every 60 seconds).
- **FR-011**: A health monitor process MUST check heartbeat records and raise an alert (written to a designated alert log) when any agent's heartbeat is older than a configurable threshold (default 5 minutes).
- **FR-012**: The cloud deployment MUST be documented as a VM-based architecture with step-by-step setup instructions covering agent installation, secrets configuration, Git access, and auto-start on reboot.

### Key Entities

- **Cloud Agent**: An always-on process running on a cloud VM; has a unique identity; participates in claim-by-move and dashboard protocols.
- **Local Agent**: An agent process running on the user's local machine; same codebase as cloud agent, different identity and configuration.
- **Task File**: A markdown file representing a unit of work; resides in `inbox/` when unclaimed, `in-progress/<agent-id>/` when claimed, `done/` or `output/` when complete.
- **Vault**: The Obsidian markdown directory synced between local and cloud via Git; the shared source of truth for tasks, outputs, and agent state.
- **Dashboard**: A single shared markdown file updated by agents to report their current status, last task, and health; subject to the single-writer rule.
- **Heartbeat Record**: A timestamped file or entry written by each agent at a fixed interval to indicate it is alive and running.
- **Secrets Store**: Any configuration store (environment variables, secret manager, local-only config file) that lives outside the vault path and is never committed to Git.
- **Health Monitor**: A process or scheduled check that reads heartbeat records and writes alerts when agents are unresponsive.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The cloud agent processes tasks continuously for 7 consecutive days without manual intervention or restarting by an operator.
- **SC-002**: A task published to the vault from a local machine is picked up and processed by the cloud agent within 10 minutes, end-to-end (including Git sync cycles).
- **SC-003**: Zero tasks are processed more than once (no duplicates) and zero eligible tasks are permanently skipped across 100 consecutive task submissions in a concurrent local + cloud agent environment.
- **SC-004**: Zero secrets, credentials, or `.env`-type files appear in any Git commit in the vault's history across the lifetime of the system.
- **SC-005**: An operator is notified (via alert log entry) within 5 minutes of any agent failing to produce a heartbeat.
- **SC-006**: The dashboard file is always valid and coherent — never partially written or corrupted — across 1000 simulated concurrent write attempts.
- **SC-007**: A new cloud VM can be provisioned and have the full agent system running within 30 minutes following the documented deployment steps.

---

## Assumptions

- The existing Gold Tier Python codebase (watchdog + schedule) is the implementation foundation for Platinum Tier.
- A Linux cloud VM (Ubuntu 22.04 or equivalent) with Git and Python 3.12 installed is available or can be provisioned.
- Git remote access (SSH key or token) can be configured on the VM without storing credentials in the vault.
- The vault directory is a Git repository with a remote (e.g., GitHub, GitLab, or self-hosted).
- Git auto-sync intervals of 60 seconds are acceptable latency for task propagation between agents.
- File system atomic move operations (within the same partition) are sufficient for the claim-by-move rule on both local and VM environments.
- Alerting in the first iteration is file/log-based; push notifications (email, Slack) are a future enhancement.
- Agent auto-restart on VM reboot uses the OS service manager (e.g., systemd) — the specific mechanism is an implementation detail.
