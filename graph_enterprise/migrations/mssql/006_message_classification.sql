-- Per-message classification persistence linked to run_log.
IF OBJECT_ID(N'dbo.message_classification', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.message_classification (
        id BIGINT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        run_log_id INT NOT NULL REFERENCES dbo.run_log (id) ON DELETE CASCADE,
        email_id NVARCHAR(255) NOT NULL,
        subject NVARCHAR(MAX) NULL,
        sender NVARCHAR(500) NULL,
        category NVARCHAR(255) NOT NULL,
        received_at NVARCHAR(64) NULL,
        created_at DATETIME2(7) NOT NULL DEFAULT SYSUTCDATETIME()
    );
    CREATE INDEX IX_message_classification_run_log ON dbo.message_classification (run_log_id);
END;
