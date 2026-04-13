ALTER TABLE agentic_workflow
ADD workflow_filter NVARCHAR(MAX) NULL,
    response_prompt_id INT NULL,
    auto_send BIT NOT NULL DEFAULT 0;

ALTER TABLE agentic_workflow
ADD CONSTRAINT FK_agentic_workflow_response_prompt_template
FOREIGN KEY (response_prompt_id) REFERENCES prompt_template(id);
