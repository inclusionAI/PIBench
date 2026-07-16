ALTER TABLE "teams" ADD COLUMN "alipay_external_agreement_no" text;--> statement-breakpoint
ALTER TABLE "teams" ADD COLUMN "alipay_agreement_no" text;--> statement-breakpoint
ALTER TABLE "teams" ADD COLUMN "alipay_buyer_user_id" text;--> statement-breakpoint
ALTER TABLE "teams" ADD COLUMN "alipay_last_out_trade_no" text;--> statement-breakpoint
ALTER TABLE "teams" ADD COLUMN "alipay_last_trade_no" text;--> statement-breakpoint
ALTER TABLE "teams" ADD COLUMN "alipay_last_amount" varchar(20);--> statement-breakpoint
ALTER TABLE "teams" ADD COLUMN "alipay_payment_status" varchar(32);--> statement-breakpoint
ALTER TABLE "teams" ADD COLUMN "alipay_next_deduct_time" varchar(32);--> statement-breakpoint
ALTER TABLE "teams" ADD CONSTRAINT "teams_alipay_external_agreement_no_unique" UNIQUE("alipay_external_agreement_no");--> statement-breakpoint
ALTER TABLE "teams" ADD CONSTRAINT "teams_alipay_agreement_no_unique" UNIQUE("alipay_agreement_no");--> statement-breakpoint
ALTER TABLE "teams" ADD CONSTRAINT "teams_alipay_last_out_trade_no_unique" UNIQUE("alipay_last_out_trade_no");