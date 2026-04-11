-- Add category_histogram JSON column to run_log for per-run classification breakdown.
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'run_log' AND COLUMN_NAME = 'category_histogram')
BEGIN
    ALTER TABLE dbo.run_log ADD category_histogram NVARCHAR(MAX) NULL;
END;
