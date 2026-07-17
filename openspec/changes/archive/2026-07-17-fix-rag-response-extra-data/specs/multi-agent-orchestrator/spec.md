## ADDED Requirements

### Requirement: Chat API Response Model Results Format
The system SHALL ensure that the `/api/v1/chat/` response only includes model results relevant to the caller and SHALL NOT expose internal orchestrator or AgentManager execution details inside `data.model_results`.

#### Scenario: RAG question returns no model_results
- **WHEN** a question is routed to the RAG chain (`question_type == 0`)
- **THEN** the response `data` SHALL NOT contain a `model_results` field

#### Scenario: Multi-agent question returns simplified model_results
- **WHEN** a question is routed to multi-agent models (`question_type != 0`)
- **THEN** the response `data.model_results` SHALL only contain the per-model outcome summary agreed in the API contract
- **AND** SHALL NOT contain the raw `data` or `details` fields from AgentManager

## MODIFIED Requirements

### Requirement: Multi-Agent Orchestration
The system SHALL provide a multi-agent orchestrator that supports concurrent execution of up to six professional models.

#### Scenario: Execute multiple models concurrently
- **WHEN** a request is submitted that requires multiple models
- **THEN** the system SHALL execute the models concurrently

#### Scenario: Coordinate model execution order
- **WHEN** models have dependencies on each other
- **THEN** the system SHALL execute them in the correct order

#### Scenario: Aggregate results from concurrent models
- **WHEN** all concurrent models complete
- **THEN** the system SHALL aggregate their outputs into a caller-facing format
- **AND** SHALL NOT forward raw agent metadata such as `details`, `confidence`, or internal `evidence` arrays as part of the public chat response
