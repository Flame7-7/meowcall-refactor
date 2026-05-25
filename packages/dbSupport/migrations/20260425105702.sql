-- Create enum type "InfractionType"
CREATE TYPE "InfractionType" AS ENUM ('BAN', 'MUTE', 'WARNING');
-- Create enum type "InfractionStatus"
CREATE TYPE "InfractionStatus" AS ENUM ('ACTIVE', 'REVOKED', 'EXPIRED', 'APPEALED');
-- Create enum type "ReportStatus"
CREATE TYPE "ReportStatus" AS ENUM ('PENDING', 'RESOLVED', 'IGNORED');
-- Create enum type "Badges"
CREATE TYPE "Badges" AS ENUM ('DEVELOPER', 'STAFF', 'PREMIUM', 'VOTER');
-- Create enum type "MessageStatus"
CREATE TYPE "MessageStatus" AS ENUM ('PENDING', 'ACTIVE', 'DELETED');
-- Create "User" table
CREATE TABLE "User" (
 "id" text NOT NULL,
 "name" text NULL,
 "image" text NULL,
 "useServerNickname" boolean NOT NULL DEFAULT false,
 "useServerProfile" boolean NOT NULL DEFAULT false,
 "useAutoTranslate" boolean NOT NULL DEFAULT false,
 "hideBadges" boolean NOT NULL DEFAULT false,
 "voteCount" integer NOT NULL DEFAULT 0,
 "messageCount" integer NOT NULL DEFAULT 0,
 "callCount" integer NOT NULL DEFAULT 0,
 "locale" text NULL,
 "badges" "Badges"[] NOT NULL DEFAULT '{}',
 "lastVoted" timestamp NULL,
 "lastMessageAt" timestamp NULL,
 "createdAt" timestamp NULL DEFAULT now(),
 "updatedAt" timestamp NULL DEFAULT now(),
 PRIMARY KEY ("id")
);
-- Create index "User_lastVoted_idx" to table: "User"
CREATE INDEX "User_lastVoted_idx" ON "User" ("lastVoted");
-- Create index "User_messageCount_idx" to table: "User"
CREATE INDEX "User_messageCount_idx" ON "User" ("messageCount");
-- Create index "User_voteCount_idx" to table: "User"
CREATE INDEX "User_voteCount_idx" ON "User" ("voteCount");
-- Create "ServerData" table
CREATE TABLE "ServerData" (
 "id" text NOT NULL,
 "name" text NOT NULL,
 "iconUrl" text NULL,
 "customPrefix" text NULL,
 "createdAt" timestamp NOT NULL DEFAULT now(),
 "updatedAt" timestamp NOT NULL DEFAULT now(),
 PRIMARY KEY ("id")
);
-- Create "Blacklist" table
CREATE TABLE "Blacklist" (
 "id" text NOT NULL,
 "moderatorId" text NOT NULL,
 "reason" character varying(500) NOT NULL,
 "userId" text NULL,
 "serverId" text NULL,
 "serverName" text NULL,
 "status" "InfractionStatus" NOT NULL DEFAULT 'ACTIVE',
 "notified" boolean NOT NULL DEFAULT false,
 "createdAt" timestamp NULL DEFAULT now(),
 "updatedAt" timestamp NULL DEFAULT now(),
 "expiresAt" timestamp NULL,
 PRIMARY KEY ("id"),
 CONSTRAINT "Blacklist_moderatorId_fkey" FOREIGN KEY ("moderatorId") REFERENCES "User" ("id") ON UPDATE NO ACTION ON DELETE NO ACTION,
 CONSTRAINT "Blacklist_serverId_fkey" FOREIGN KEY ("serverId") REFERENCES "ServerData" ("id") ON UPDATE NO ACTION ON DELETE NO ACTION,
 CONSTRAINT "Blacklist_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User" ("id") ON UPDATE NO ACTION ON DELETE NO ACTION
);
-- Create index "Blacklist_server_active_idx" to table: "Blacklist"
CREATE INDEX "Blacklist_server_active_idx" ON "Blacklist" ("serverId", "expiresAt") WHERE (status = 'ACTIVE'::"InfractionStatus");
-- Create index "Blacklist_user_active_idx" to table: "Blacklist"
CREATE INDEX "Blacklist_user_active_idx" ON "Blacklist" ("userId", "expiresAt") WHERE (status = 'ACTIVE'::"InfractionStatus");
-- Create "Connection" table
CREATE TABLE "Connection" (
 "id" text NOT NULL,
 "channelId" text NOT NULL,
 "webhookURL" text NOT NULL,
 "serverId" text NOT NULL,
 "createdAt" timestamp NOT NULL DEFAULT now(),
 "lastUpdated" timestamp NOT NULL DEFAULT now(),
 "lastActive" timestamp NOT NULL DEFAULT now(),
 "parentId" text NULL,
 PRIMARY KEY ("id"),
 CONSTRAINT "Connection_channelId_key" UNIQUE ("channelId"),
 CONSTRAINT "Connection_channelId_serverId_key" UNIQUE ("channelId", "serverId"),
 CONSTRAINT "Connection_serverId_fkey" FOREIGN KEY ("serverId") REFERENCES "ServerData" ("id") ON UPDATE NO ACTION ON DELETE NO ACTION
);
-- Create index "Connection_channelId_idx" to table: "Connection"
CREATE INDEX "Connection_channelId_idx" ON "Connection" ("channelId");
-- Create index "Connection_lastActive_idx" to table: "Connection"
CREATE INDEX "Connection_lastActive_idx" ON "Connection" ("lastActive");
-- Create index "Connection_serverId_idx" to table: "Connection"
CREATE INDEX "Connection_serverId_idx" ON "Connection" ("serverId");
-- Create "Infraction" table
CREATE TABLE "Infraction" (
 "id" text NOT NULL,
 "moderatorId" text NOT NULL,
 "reason" character varying(500) NOT NULL,
 "expiresAt" timestamp NULL,
 "type" "InfractionType" NOT NULL,
 "userId" text NULL,
 "serverId" text NULL,
 "severName" text NULL,
 "status" "InfractionStatus" NOT NULL DEFAULT 'ACTIVE',
 "notified" boolean NOT NULL DEFAULT false,
 "createdAt" timestamp NULL DEFAULT now(),
 "updatedAt" timestamp NULL DEFAULT now(),
 PRIMARY KEY ("id"),
 CONSTRAINT "Infraction_moderatorId_fkey" FOREIGN KEY ("moderatorId") REFERENCES "User" ("id") ON UPDATE NO ACTION ON DELETE NO ACTION,
 CONSTRAINT "Infraction_serverId_fkey" FOREIGN KEY ("serverId") REFERENCES "ServerData" ("id") ON UPDATE NO ACTION ON DELETE NO ACTION,
 CONSTRAINT "Infraction_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User" ("id") ON UPDATE NO ACTION ON DELETE NO ACTION
);
-- Create index "Infraction_server_active_idx" to table: "Infraction"
CREATE INDEX "Infraction_server_active_idx" ON "Infraction" ("serverId", "type", "expiresAt") WHERE (status = 'ACTIVE'::"InfractionStatus");
-- Create index "Infraction_user_active_idx" to table: "Infraction"
CREATE INDEX "Infraction_user_active_idx" ON "Infraction" ("userId", "type", "expiresAt") WHERE (status = 'ACTIVE'::"InfractionStatus");
-- Create "Message" table
CREATE TABLE "Message" (
 "id" text NOT NULL,
 "content" character varying(4000) NOT NULL,
 "guildId" text NOT NULL,
 "channelId" text NOT NULL,
 "authorId" text NOT NULL,
 "status" "MessageStatus" NOT NULL DEFAULT 'ACTIVE',
 "referredMessageId" text NULL,
 "imageURL" character varying NULL,
 "deletionQueuedAt" timestamp NULL,
 "retentionUntil" timestamp NULL,
 "createdAt" timestamp NULL DEFAULT now(),
 "updatedAt" timestamp NULL DEFAULT now(),
 PRIMARY KEY ("id"),
 CONSTRAINT "Message_referredMessageId_fkey" FOREIGN KEY ("referredMessageId") REFERENCES "Message" ("id") ON UPDATE NO ACTION ON DELETE NO ACTION
);
-- Create index "Message_createdAt_idx" to table: "Message"
CREATE INDEX "Message_createdAt_idx" ON "Message" ("createdAt" DESC);
-- Create index "Message_guildId_authorId_idx" to table: "Message"
CREATE INDEX "Message_guildId_authorId_idx" ON "Message" ("guildId", "authorId");
-- Create index "Message_referredMesasageId_idx" to table: "Message"
CREATE INDEX "Message_referredMesasageId_idx" ON "Message" ("referredMessageId");
-- Create index "Message_status_createdAt_idx" to table: "Message"
CREATE INDEX "Message_status_createdAt_idx" ON "Message" ("status", "createdAt" DESC);
-- Create "MessageReaction" table
CREATE TABLE "MessageReaction" (
 "id" character varying NOT NULL,
 "messageId" text NOT NULL,
 "emoji" character varying(64) NOT NULL,
 "users" text[] NOT NULL,
 PRIMARY KEY ("id"),
 CONSTRAINT "MessageReaction_messageId_emoji_key" UNIQUE ("messageId", "emoji"),
 CONSTRAINT "MessageReaction_messageId_fkey" FOREIGN KEY ("messageId") REFERENCES "Message" ("id") ON UPDATE NO ACTION ON DELETE CASCADE
);
-- Create "Report" table
CREATE TABLE "Report" (
 "id" text NOT NULL,
 "reporterUserId" text NOT NULL,
 "reportedUserId" text NOT NULL,
 "reportedServerId" text NOT NULL,
 "messageId" text NOT NULL,
 "reason" text NOT NULL,
 "status" "ReportStatus" NOT NULL DEFAULT 'PENDING',
 "actionTaken" text NULL,
 "resolvedBy" text NULL,
 "reportMessageId" text NULL,
 "reportChannelId" text NULL,
 "createdAt" timestamp NULL DEFAULT now(),
 "updatedAt" timestamp NULL DEFAULT now(),
 "resolvedAt" timestamp NULL,
 PRIMARY KEY ("id"),
 CONSTRAINT "Report_messageId_fkey" FOREIGN KEY ("messageId") REFERENCES "Message" ("id") ON UPDATE NO ACTION ON DELETE NO ACTION,
 CONSTRAINT "Report_reportedServerId_fkey" FOREIGN KEY ("reportedServerId") REFERENCES "ServerData" ("id") ON UPDATE NO ACTION ON DELETE NO ACTION,
 CONSTRAINT "Report_reportedUserId_fkey" FOREIGN KEY ("reportedUserId") REFERENCES "User" ("id") ON UPDATE NO ACTION ON DELETE NO ACTION,
 CONSTRAINT "Report_reporterUserId_fkey" FOREIGN KEY ("reporterUserId") REFERENCES "User" ("id") ON UPDATE NO ACTION ON DELETE NO ACTION,
 CONSTRAINT "Report_resolvedBy_fkey" FOREIGN KEY ("resolvedBy") REFERENCES "User" ("id") ON UPDATE NO ACTION ON DELETE NO ACTION
);
