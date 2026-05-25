-- Modify "Message" table
ALTER TABLE "Message" DROP COLUMN "imageURL", ADD COLUMN "imagesURL" character varying[] NULL;
