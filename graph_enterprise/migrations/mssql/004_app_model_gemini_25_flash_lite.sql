-- Add default Gemini 2.5 Flash Lite model row for existing databases (idempotent).

IF OBJECT_ID(N'dbo.app_model', N'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM dbo.app_model WHERE name = N'gemini-2.5-flash-lite')
BEGIN
    INSERT INTO dbo.app_model (name, created_at, updated_at)
    VALUES (
        N'gemini-2.5-flash-lite',
        FORMAT(GETUTCDATE(), 'yyyy-MM-ddTHH:mm:ssZ'),
        FORMAT(GETUTCDATE(), 'yyyy-MM-ddTHH:mm:ssZ')
    );
END;
