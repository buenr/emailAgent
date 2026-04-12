-- Agentic workflow: customizable extraction + API chaining per inbox.
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'agentic_workflow')
CREATE TABLE agentic_workflow (
    id                      INT IDENTITY(1,1) PRIMARY KEY,
    inbox_id                INT NOT NULL,
    name                    NVARCHAR(255) NOT NULL DEFAULT '',
    extraction_prompt_id    INT NOT NULL,
    trigger_categories      NVARCHAR(MAX) NOT NULL,   -- JSON array of category names
    function_declarations   NVARCHAR(MAX) NULL,        -- JSON array of function schemas
    agent_api_names         NVARCHAR(MAX) NOT NULL DEFAULT '[]',  -- JSON array of API names
    webhook_url             NVARCHAR(2048) NULL,
    is_active               BIT NOT NULL DEFAULT 1,
    created_at              DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    updated_at              DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    FOREIGN KEY (inbox_id) REFERENCES inbox(id),
    FOREIGN KEY (extraction_prompt_id) REFERENCES prompt_template(id)
);
