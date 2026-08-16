# Spec: Thematic Data Import

## ADDED Requirements

### Requirement: Field Mapping Configuration

The system SHALL provide a field mapping configuration file that defines the mapping from V2.0 pinyin abbreviation field names (TYBH, SJD, YJZ, etc.) to V3.0 English snake_case field names (parcel_id, soil_ph, organic_matter, etc.) for all 5 thematic models.

#### Scenario: Field mapping dictionary

- WHEN the field mapping configuration is loaded
- THEN the system SHALL have mapping dictionaries for all 5 models (stability_risk, quality_grade, obstacle_diagnosis, acidification_remediation, organic_matter)
- AND each mapping dictionary SHALL map source field names to target database column names

### Requirement: Multi-format Data Import

The system SHALL support importing data from multiple file formats: Shapefile (.shp), CSV (.csv), and Excel (.xlsx).

#### Scenario: CSV import with encoding detection

- WHEN a CSV file is imported
- THEN the system SHALL attempt UTF-8 encoding first
- AND fall back to GBK encoding if UTF-8 fails
- AND successfully parse all data rows

#### Scenario: Shapefile import with geometry

- WHEN a Shapefile is imported
- THEN the system SHALL read both attribute data and geometry
- AND store geometry in the PostGIS geom column

#### Scenario: Excel import

- WHEN an Excel file is imported
- THEN the system SHALL read all sheets and columns
- AND map columns to target database fields

### Requirement: Execution Log Recording

The system SHALL record execution metadata in the model_execution_log table before and after each model data import.

#### Scenario: Execution log entry creation

- WHEN a model data import starts
- THEN the system SHALL insert a record into model_execution_log with agent_id, model_id, layer_id, started_at, and status='running'
- AND after import completes, update the record with status='ok', duration_ms, and completed_at

### Requirement: Data Integrity Validation

The system SHALL validate data integrity after import.

#### Scenario: Row count validation

- WHEN data import is complete
- THEN the system SHALL report the number of rows imported for each model
- AND verify the count matches the source data row count

#### Scenario: Field completeness check

- WHEN data import is complete
- THEN the system SHALL verify all required fields are populated
- AND report any missing or null values in required fields
