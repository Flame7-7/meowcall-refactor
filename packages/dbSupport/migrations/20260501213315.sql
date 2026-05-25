-- Create enum type "Badges"
CREATE TYPE "Badges" AS ENUM ('DEVELOPER', 'STAFF', 'PREMIUM', 'VOTER');
-- Modify "User" table
ALTER TABLE "User" ADD COLUMN "badges" "Badges"[] NOT NULL DEFAULT '{}';
-- Create "Account" table
CREATE TABLE "Account" (
 "id" text NOT NULL,
 "accountId" text NOT NULL,
 "providerId" text NOT NULL,
 "userId" text NOT NULL,
 "accessToken" text NULL,
 "refreshToken" text NULL,
 "idToken" text NULL,
 "accessTokenExpiresAt" timestamp NULL,
 "refreshTokenExpiresAt" timestamp NULL,
 "scope" text NULL,
 "password" text NULL,
 "createdAt" timestamp NOT NULL DEFAULT now(),
 "updatedAt" timestamp NOT NULL DEFAULT now(),
 PRIMARY KEY ("id"),
 CONSTRAINT "Account_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User" ("id") ON UPDATE NO ACTION ON DELETE CASCADE
);
-- Create "Session" table
CREATE TABLE "Session" (
 "id" text NOT NULL,
 "expiresAt" timestamp NOT NULL,
 "token" text NOT NULL,
 "createdAt" timestamp NOT NULL DEFAULT now(),
 "updatedAt" timestamp NOT NULL DEFAULT now(),
 "ipAddress" text NULL,
 "userAgent" text NULL,
 "userId" text NOT NULL,
 PRIMARY KEY ("id"),
 CONSTRAINT "Session_token_key" UNIQUE ("token"),
 CONSTRAINT "Session_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User" ("id") ON UPDATE NO ACTION ON DELETE CASCADE
);
