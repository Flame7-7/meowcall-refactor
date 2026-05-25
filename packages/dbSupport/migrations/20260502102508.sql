-- Create enum type "AppealStatus"
CREATE TYPE "AppealStatus" AS ENUM ('PENDING', 'REJECTED', 'ACCEPTED');
-- Modify "Report" table
ALTER TABLE "Report" DROP CONSTRAINT "Report_messageId_fkey", ALTER COLUMN "messageId" DROP NOT NULL;
-- Create "Appeal" table
CREATE TABLE "Appeal" (
 "id" text NOT NULL,
 "infractionId" text NOT NULL,
 "userId" text NULL,
 "serverId" text NULL,
 "serverName" text NULL,
 "status" "AppealStatus" NOT NULL DEFAULT 'PENDING',
 "createdAt" timestamp NULL DEFAULT now(),
 "updatedAt" timestamp NULL DEFAULT now(),
 "expiresAt" timestamp NULL,
 PRIMARY KEY ("id"),
 CONSTRAINT "Appeal_infractionId_fkey" FOREIGN KEY ("infractionId") REFERENCES "Infraction" ("id") ON UPDATE NO ACTION ON DELETE NO ACTION,
 CONSTRAINT "Appeal_serverId_fkey" FOREIGN KEY ("serverId") REFERENCES "ServerData" ("id") ON UPDATE NO ACTION ON DELETE NO ACTION,
 CONSTRAINT "Appeal_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User" ("id") ON UPDATE NO ACTION ON DELETE NO ACTION
);
