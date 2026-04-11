-- Add per-inbox Graph fetch filter JSON (see InboxFetchFilter in config.models).

IF COL_LENGTH(N'dbo.inbox', N'fetch_filter_json') IS NULL
BEGIN
    ALTER TABLE dbo.inbox ADD fetch_filter_json NVARCHAR(MAX) NULL;
END;
