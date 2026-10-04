export type TradeStatus =
  | "received"
  | "processing"
  | "verified"
  | "review_required"
  | "rejected"
  | "settlement_pending"
  | "flagged_for_review"
  | "settled"
  | "settlement_failed";

export type SettlementStatus =
  | "not_eligible"
  | "pending"
  | "processing"
  | "flagged_for_review"
  | "completed"
  | "failed";

export interface TradeRecord {
  id: string;
  external_reference: string | null;
  status: TradeStatus;
  goods_description: string;
  hs_code: string | null;
  hs_code_confidence: number | null;
  origin_country: string;
  destination_country: string;
  cif_amount: string | number;
  currency: string | null;
  origin_eligible: boolean | null;
  origin_decision: Record<string, unknown>;
  rigs_score: number | null;
  rigs_components: Record<string, unknown>;
  settlement_status: SettlementStatus;
  paypal_payout_batch_id: string | null;
  error_code: string | null;
  preferential_margin?: number | string | null;
  created_at: string;
  updated_at: string;
}

export interface TradePage {
  items: TradeRecord[];
  next_cursor: string | null;
}
