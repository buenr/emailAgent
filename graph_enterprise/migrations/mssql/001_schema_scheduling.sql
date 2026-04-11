-- Idempotent SQL Server schema: classifier config + scheduling + run_log + app_setting
-- Run manually or via init_db when MSSQL_ODBC_CONNECTION_STRING is set.

IF OBJECT_ID(N'dbo.run_log', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.run_log (
        id BIGINT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        inbox_id INT NOT NULL,
        status NVARCHAR(16) NOT NULL,
        fetched_count INT NOT NULL DEFAULT 0,
        classified_count INT NOT NULL DEFAULT 0,
        tagged_count INT NOT NULL DEFAULT 0,
        failures INT NOT NULL DEFAULT 0,
        latency_ms FLOAT NOT NULL DEFAULT 0,
        total_tokens_used INT NULL,
        error_message NVARCHAR(MAX) NULL,
        created_at DATETIME2(7) NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_run_log_inbox FOREIGN KEY (inbox_id) REFERENCES dbo.inbox (id) ON DELETE CASCADE
    );
    CREATE INDEX IX_run_log_inbox_created ON dbo.run_log (inbox_id, created_at DESC);
END;

IF OBJECT_ID(N'dbo.app_setting', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.app_setting (
        [key] NVARCHAR(128) NOT NULL PRIMARY KEY,
        [value] NVARCHAR(MAX) NOT NULL
    );
    INSERT INTO dbo.app_setting ([key], [value]) VALUES (N'global_polling_paused', N'false');
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.inbox') AND name = N'polling_interval_minutes'
)
    ALTER TABLE dbo.inbox ADD polling_interval_minutes INT NOT NULL CONSTRAINT DF_inbox_polling DEFAULT (5);

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.inbox') AND name = N'is_active'
)
    ALTER TABLE dbo.inbox ADD is_active BIT NOT NULL CONSTRAINT DF_inbox_active DEFAULT (1);

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.inbox') AND name = N'last_run_at'
)
    ALTER TABLE dbo.inbox ADD last_run_at DATETIME2(7) NULL;

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.inbox') AND name = N'next_run_at'
)
    ALTER TABLE dbo.inbox ADD next_run_at DATETIME2(7) NULL;

-- Backfill next_run for active rows that have never been scheduled
UPDATE dbo.inbox
SET next_run_at = SYSUTCDATETIME()
WHERE next_run_at IS NULL AND is_active = 1;
