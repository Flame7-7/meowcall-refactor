-- Create enum type "UserphoneCallStatus"
CREATE TYPE "UserphoneCallStatus" AS ENUM ('WAITING', 'ACTIVE', 'ENDED');
-- Create "UserphoneCall" table
CREATE TABLE "UserphoneCall" (
 "id" text NOT NULL,
 "channelId" text NOT NULL,
 "guildId" text NOT NULL,
 "userId" text NOT NULL,
 "pairedCallId" text NULL,
 "status" "UserphoneCallStatus" NOT NULL DEFAULT 'WAITING',
 "createdAt" timestamp NOT NULL DEFAULT now(),
 "updatedAt" timestamp NULL DEFAULT now(),
 "endedAt" timestamp NULL,
 PRIMARY KEY ("id"),
 CONSTRAINT "UserphoneCall_pairedCallId_fkey" FOREIGN KEY ("pairedCallId") REFERENCES "UserphoneCall" ("id") ON UPDATE NO ACTION ON DELETE NO ACTION,
 CONSTRAINT "UserphoneCall_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User" ("id") ON UPDATE NO ACTION ON DELETE NO ACTION
);
-- Create index "UserphoneCall_channelId_idx" to table: "UserphoneCall"
CREATE INDEX "UserphoneCall_channelId_idx" ON "UserphoneCall" ("channelId");
-- Create index "UserphoneCall_status_createdAt_idx" to table: "UserphoneCall"
CREATE INDEX "UserphoneCall_status_createdAt_idx" ON "UserphoneCall" ("status", "createdAt");
-- Create index "UserphoneCall_status_idx" to table: "UserphoneCall"
CREATE INDEX "UserphoneCall_status_idx" ON "UserphoneCall" ("status");
-- Create index "UserphoneCall_userId_idx" to table: "UserphoneCall"
CREATE INDEX "UserphoneCall_userId_idx" ON "UserphoneCall" ("userId");
