-- ETA pipeline config columns on inbox.

IF COL_LENGTH(N'dbo.inbox', N'eta_lookup_enabled') IS NULL
BEGIN
    ALTER TABLE dbo.inbox ADD eta_lookup_enabled BIT NOT NULL CONSTRAINT DF_inbox_eta_lookup_enabled DEFAULT (0);
END;

IF COL_LENGTH(N'dbo.inbox', N'eta_lookup_api_url') IS NULL
BEGIN
    ALTER TABLE dbo.inbox ADD eta_lookup_api_url NVARCHAR(2048) NULL;
END;

IF COL_LENGTH(N'dbo.inbox', N'eta_lookup_api_key') IS NULL
BEGIN
    ALTER TABLE dbo.inbox ADD eta_lookup_api_key NVARCHAR(2048) NULL;
END;

IF COL_LENGTH(N'dbo.inbox', N'eta_draft_enabled') IS NULL
BEGIN
    ALTER TABLE dbo.inbox ADD eta_draft_enabled BIT NOT NULL CONSTRAINT DF_inbox_eta_draft_enabled DEFAULT (1);
END;
