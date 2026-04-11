-- Per-inbox subject LIKE rules before Gemini (hybrid classification).

IF COL_LENGTH(N'dbo.inbox', N'subject_classify_enabled') IS NULL
BEGIN
    ALTER TABLE dbo.inbox ADD subject_classify_enabled BIT NOT NULL CONSTRAINT DF_inbox_subject_classify_enabled DEFAULT (0);
END;

IF COL_LENGTH(N'dbo.inbox', N'subject_classify_rules_json') IS NULL
BEGIN
    ALTER TABLE dbo.inbox ADD subject_classify_rules_json NVARCHAR(MAX) NULL;
END;
