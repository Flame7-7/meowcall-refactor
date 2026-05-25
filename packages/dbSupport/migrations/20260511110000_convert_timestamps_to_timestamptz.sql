-- Convert all timestamp columns to timestamptz.
-- Existing data is currently stored as UTC in naive timestamp columns,
-- so interpret each existing value as UTC during conversion.

ALTER TABLE "User"
    ALTER COLUMN "lastVoted" TYPE timestamptz USING "lastVoted" AT TIME ZONE 'UTC',
    ALTER COLUMN "lastMessageAt" TYPE timestamptz USING "lastMessageAt" AT TIME ZONE 'UTC',
    ALTER COLUMN "createdAt" TYPE timestamptz USING "createdAt" AT TIME ZONE 'UTC',
    ALTER COLUMN "updatedAt" TYPE timestamptz USING "updatedAt" AT TIME ZONE 'UTC';

ALTER TABLE "ServerData"
    ALTER COLUMN "createdAt" TYPE timestamptz USING "createdAt" AT TIME ZONE 'UTC',
    ALTER COLUMN "updatedAt" TYPE timestamptz USING "updatedAt" AT TIME ZONE 'UTC';

ALTER TABLE "Blacklist"
    ALTER COLUMN "createdAt" TYPE timestamptz USING "createdAt" AT TIME ZONE 'UTC',
    ALTER COLUMN "updatedAt" TYPE timestamptz USING "updatedAt" AT TIME ZONE 'UTC',
    ALTER COLUMN "expiresAt" TYPE timestamptz USING "expiresAt" AT TIME ZONE 'UTC';

ALTER TABLE "Connection"
    ALTER COLUMN "createdAt" TYPE timestamptz USING "createdAt" AT TIME ZONE 'UTC',
    ALTER COLUMN "lastUpdated" TYPE timestamptz USING "lastUpdated" AT TIME ZONE 'UTC',
    ALTER COLUMN "lastActive" TYPE timestamptz USING "lastActive" AT TIME ZONE 'UTC';

ALTER TABLE "Infraction"
    ALTER COLUMN "expiresAt" TYPE timestamptz USING "expiresAt" AT TIME ZONE 'UTC',
    ALTER COLUMN "createdAt" TYPE timestamptz USING "createdAt" AT TIME ZONE 'UTC',
    ALTER COLUMN "updatedAt" TYPE timestamptz USING "updatedAt" AT TIME ZONE 'UTC';

ALTER TABLE "Message"
    ALTER COLUMN "deletionQueuedAt" TYPE timestamptz USING "deletionQueuedAt" AT TIME ZONE 'UTC',
    ALTER COLUMN "retentionUntil" TYPE timestamptz USING "retentionUntil" AT TIME ZONE 'UTC',
    ALTER COLUMN "createdAt" TYPE timestamptz USING "createdAt" AT TIME ZONE 'UTC',
    ALTER COLUMN "updatedAt" TYPE timestamptz USING "updatedAt" AT TIME ZONE 'UTC';

ALTER TABLE "Report"
    ALTER COLUMN "createdAt" TYPE timestamptz USING "createdAt" AT TIME ZONE 'UTC',
    ALTER COLUMN "updatedAt" TYPE timestamptz USING "updatedAt" AT TIME ZONE 'UTC',
    ALTER COLUMN "resolvedAt" TYPE timestamptz USING "resolvedAt" AT TIME ZONE 'UTC';

ALTER TABLE "Account"
    ALTER COLUMN "accessTokenExpiresAt" TYPE timestamptz USING "accessTokenExpiresAt" AT TIME ZONE 'UTC',
    ALTER COLUMN "refreshTokenExpiresAt" TYPE timestamptz USING "refreshTokenExpiresAt" AT TIME ZONE 'UTC',
    ALTER COLUMN "createdAt" TYPE timestamptz USING "createdAt" AT TIME ZONE 'UTC',
    ALTER COLUMN "updatedAt" TYPE timestamptz USING "updatedAt" AT TIME ZONE 'UTC';

ALTER TABLE "Session"
    ALTER COLUMN "expiresAt" TYPE timestamptz USING "expiresAt" AT TIME ZONE 'UTC',
    ALTER COLUMN "createdAt" TYPE timestamptz USING "createdAt" AT TIME ZONE 'UTC',
    ALTER COLUMN "updatedAt" TYPE timestamptz USING "updatedAt" AT TIME ZONE 'UTC';

ALTER TABLE "Appeal"
    ALTER COLUMN "createdAt" TYPE timestamptz USING "createdAt" AT TIME ZONE 'UTC',
    ALTER COLUMN "updatedAt" TYPE timestamptz USING "updatedAt" AT TIME ZONE 'UTC',
    ALTER COLUMN "expiresAt" TYPE timestamptz USING "expiresAt" AT TIME ZONE 'UTC';

ALTER TABLE "UserphoneCall"
    ALTER COLUMN "createdAt" TYPE timestamptz USING "createdAt" AT TIME ZONE 'UTC',
    ALTER COLUMN "updatedAt" TYPE timestamptz USING "updatedAt" AT TIME ZONE 'UTC',
    ALTER COLUMN "endedAt" TYPE timestamptz USING "endedAt" AT TIME ZONE 'UTC';