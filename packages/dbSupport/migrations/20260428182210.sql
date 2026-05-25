-- Modify "MessageReaction" table
ALTER TABLE "MessageReaction" DROP COLUMN "users";
-- Modify "User" table
ALTER TABLE "User" DROP COLUMN "badges";
-- Drop enum type "Badges"
DROP TYPE "Badges";
