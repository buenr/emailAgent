-- Greenfield SQL Server: full classifier schema (run when no tables exist).

IF OBJECT_ID(N'dbo.prompt_template', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.prompt_template (
        id INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        name NVARCHAR(256) NOT NULL UNIQUE,
        body NVARCHAR(MAX) NOT NULL,
        created_at NVARCHAR(64) NOT NULL,
        updated_at NVARCHAR(64) NOT NULL
    );
END;

IF OBJECT_ID(N'dbo.classification_set', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.classification_set (
        id INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        name NVARCHAR(256) NOT NULL UNIQUE,
        created_at NVARCHAR(64) NOT NULL,
        updated_at NVARCHAR(64) NOT NULL
    );
END;

IF OBJECT_ID(N'dbo.category', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.category (
        id INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        classification_set_id INT NOT NULL REFERENCES dbo.classification_set (id) ON DELETE CASCADE,
        name NVARCHAR(512) NOT NULL,
        description NVARCHAR(MAX) NOT NULL DEFAULT N'',
        sort_order INT NOT NULL DEFAULT 0
    );
END;

IF OBJECT_ID(N'dbo.app_model', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.app_model (
        id INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        name NVARCHAR(256) NOT NULL UNIQUE,
        is_active BIT NOT NULL DEFAULT 1,
        created_at NVARCHAR(64) NOT NULL,
        updated_at NVARCHAR(64) NOT NULL
    );
    -- Seed some default models (first is the usual default when GEMINI_MODEL is unset)
    INSERT INTO dbo.app_model (name, created_at, updated_at) VALUES (N'gemini-2.5-flash-lite', FORMAT(GETUTCDATE(), 'yyyy-MM-ddTHH:mm:ssZ'), FORMAT(GETUTCDATE(), 'yyyy-MM-ddTHH:mm:ssZ'));
    INSERT INTO dbo.app_model (name, created_at, updated_at) VALUES (N'gemini-3.1-pro', FORMAT(GETUTCDATE(), 'yyyy-MM-ddTHH:mm:ssZ'), FORMAT(GETUTCDATE(), 'yyyy-MM-ddTHH:mm:ssZ'));
    INSERT INTO dbo.app_model (name, created_at, updated_at) VALUES (N'gemini-3.1-flash-lite', FORMAT(GETUTCDATE(), 'yyyy-MM-ddTHH:mm:ssZ'), FORMAT(GETUTCDATE(), 'yyyy-MM-ddTHH:mm:ssZ'));
END;

IF OBJECT_ID(N'dbo.inbox', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.inbox (
        id INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        mailbox_id NVARCHAR(512) NOT NULL UNIQUE,
        prompt_template_id INT NOT NULL REFERENCES dbo.prompt_template (id),
        classification_set_id INT NOT NULL REFERENCES dbo.classification_set (id),
        app_model_id INT NULL REFERENCES dbo.app_model (id),
        timezone NVARCHAR(128) NOT NULL DEFAULT N'UTC',
        mail_folder NVARCHAR(256) NOT NULL DEFAULT N'inbox',
        max_messages_per_run INT NULL,
        patch_max_workers INT NOT NULL DEFAULT 4,
        polling_interval_minutes INT NOT NULL DEFAULT 5,
        is_active BIT NOT NULL DEFAULT 1,
        graph_write_back_enabled BIT NOT NULL DEFAULT 1,
        last_run_at DATETIME2(7) NULL,
        next_run_at DATETIME2(7) NULL,
        fetch_filter_json NVARCHAR(MAX) NULL,
        subject_classify_enabled BIT NOT NULL DEFAULT 0,
        subject_classify_rules_json NVARCHAR(MAX) NULL,
        created_at NVARCHAR(64) NOT NULL,
        updated_at NVARCHAR(64) NOT NULL
    );
END;

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

-- For upgrading older DBs without scheduling columns, run 001_schema_scheduling.sql.
