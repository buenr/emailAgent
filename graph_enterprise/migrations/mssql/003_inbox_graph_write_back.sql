-- Per-inbox toggle: when 0, pipeline classifies but skips Graph category PATCH (dry-run).

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.inbox') AND name = N'graph_write_back_enabled'
)
    ALTER TABLE dbo.inbox ADD graph_write_back_enabled BIT NOT NULL CONSTRAINT DF_inbox_graph_write_back DEFAULT (1);
