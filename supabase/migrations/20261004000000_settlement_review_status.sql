alter type public.trade_case_status
  add value if not exists 'flagged_for_review';

alter type public.settlement_status
  add value if not exists 'flagged_for_review';