## ADDED Requirements

### Requirement: Document Content Deduplication
The system SHALL detect duplicate documents based on file content hash (SHA-256) and reject duplicate uploads within the same user scope.

#### Scenario: Upload duplicate document with different filename
- **WHEN** a user uploads a file whose content hash matches an existing document owned by the same user
- **THEN** the system SHALL reject the upload with a 409 Conflict error and include the existing document ID in the response

#### Scenario: Upload same content by different users
- **WHEN** a user uploads a file whose content hash matches a document owned by a different user
- **THEN** the system SHALL accept the upload and create a new document record

#### Scenario: Upload first occurrence of content
- **WHEN** a user uploads a file whose content hash does not match any existing document owned by the same user
- **THEN** the system SHALL accept the upload, compute and store the SHA-256 hash in the document record

#### Scenario: Historical document without hash
- **WHEN** a user uploads a file and existing documents have NULL file_hash values
- **THEN** the system SHALL skip NULL hash documents during deduplication check and only compare against non-NULL hashes

## MODIFIED Requirements

### Requirement: Document Management
The system SHALL manage documents with metadata and status.

#### Scenario: List user documents
- **WHEN** a user requests their document list
- **THEN** the system SHALL return all documents owned by the user

#### Scenario: Get document details
- **WHEN** a user requests document details
- **THEN** the system SHALL return document metadata and status

#### Scenario: Delete document
- **WHEN** a user deletes a document
- **THEN** the system SHALL remove the database record, delete associated embeddings from the vector store, and delete the physical file from the upload directory

#### Scenario: Delete document when physical file is missing
- **WHEN** a user deletes a document and the physical file no longer exists in the upload directory
- **THEN** the system SHALL log a warning, continue to remove the database record and vector store embeddings, and return success

#### Scenario: Delete document when physical file deletion fails
- **WHEN** a user deletes a document and physical file deletion raises an error (e.g., permission denied)
- **THEN** the system SHALL log the error, continue to remove the database record and vector store embeddings, and return success

#### Scenario: Delete document when vector store deletion fails
- **WHEN** a user deletes a document and vector store deletion raises an error
- **THEN** the system SHALL log the error, continue to remove the database record and physical file, and return success
