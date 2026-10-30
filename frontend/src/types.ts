export type Person = {
  id: number;
  user_id: number;
  display_name: string;
  credentials?: Credential[];
};

export type User = {
  id: number;
  email: string;
  person: Person | null;
};

export type Credential = {
  id: number;
  person_id: number;
  source_type: string;
  label: string | null;
  configured: boolean;
  last_validated_at: string | null;
  updated_at: string;
};

export type ClassificationStatus = "unclassified" | "pending" | "confirmed";

export type DedupStatus = "unmatched" | "suggested" | "linked" | "ignored";

export type Entry = {
  id: number;
  bill_id: number;
  name: string;
  quantity: string;
  unit_price: string | null;
  discount: string;
  amount: string;
  currency: string;
  category_id: string | null;
  tags?: string[];
  note: string | null;
  image_url?: string | null;
  classification_status?: ClassificationStatus;
  category_confidence?: string | null;
};

export type Bill = {
  id: number;
  source_type: string;
  person_id: number;
  occurred_at: string;
  merchant: string | null;
  currency: string;
  note: string | null;
  total_amount: string;
  dedup_status?: DedupStatus | string;
  dedup_primary_id?: number | null;
  entries: Entry[];
};

/** Bill summary without entries (dedup list payloads). */
export type BillSummary = Omit<Bill, "entries"> & { entries?: Entry[] };

export type DedupLink = {
  id: number;
  household_id: number;
  primary_bill_id: number;
  secondary_bill_id: number;
  status: "suggested" | "linked" | "ignored" | string;
  score: string | null;
  reason: string | null;
  created_at: string;
  resolved_at: string | null;
  primary_bill: BillSummary | null;
  secondary_bill: BillSummary | null;
};

export type InternalTransferLink = {
  id: number;
  household_id: number;
  outgoing_bill_id: number;
  incoming_bill_id: number;
  reference: string;
  status: "linked" | string;
  previous_categories: Record<string, string | null>;
  matched_at: string;
  created_at: string;
  outgoing_bill: BillSummary | null;
  incoming_bill: BillSummary | null;
};

export type Invite = {
  id: number;
  code: string;
  household_id?: number | null;
  household_name?: string | null;
  display_name_hint: string | null;
  target_email?: string | null;
  status?: string;
  used: boolean;
  created_at: string;
  expires_at: string | null;
};

export type HouseholdMember = {
  id: number;
  household_id: number;
  person_id: number;
  display_name: string | null;
  email: string | null;
  role: "owner" | "member" | string;
  joined_at: string;
  left_at: string | null;
  active: boolean;
};

export type Household = {
  id: number;
  name: string;
  owner_person_id: number;
  jev_context?: string;
  created_at: string;
  my_role?: string;
  members?: HouseholdMember[];
};

export type CategoryItem = { id: string; label: string };

export type Vocabulary = {
  categories: CategoryItem[];
  aa_residual?: { id: string; label: string; description?: string };
};

export type AaResidual = {
  id: string;
  label: string;
  description?: string;
};

export type AaRule = {
  id: number;
  household_id: number;
  name: string | null;
  source_types: string[];
  category_ids: string[];
  enabled: boolean;
  shares: Record<string, string>;
  shares_total: string;
  residual_percent: string;
  aa_residual?: AaResidual;
  created_at: string;
  updated_at: string;
};

export type SettlementTransfer = {
  from_person_id: number;
  from_display_name: string;
  to_person_id: number;
  to_display_name: string;
  amount: string;
};

export type SettlementBalance = {
  person_id: number;
  display_name: string;
  net: string;
};

export type SettlementLineMemberShare = {
  display_name: string;
  percent: string;
  amount: string;
};

export type SettlementLine = {
  entry_id: number;
  bill_id: number;
  name: string;
  amount: string;
  currency: string;
  category_id: string | null;
  source_type: string;
  merchant: string | null;
  occurred_at: string;
  payer_person_id: number;
  payer_display_name: string;
  matched: boolean;
  reason: string | null;
  rule_id: number | null;
  rule_name: string | null;
  residual_amount: string;
  member_shares: Record<string, SettlementLineMemberShare>;
};

export type SettlementResult = {
  currency: string;
  entry_count_matched: number;
  entry_count_unmatched: number;
  matched_amount: string;
  unmatched_amount: string;
  residual_total: string;
  aa_residual?: AaResidual;
  balances: SettlementBalance[];
  transfers: SettlementTransfer[];
  lines?: SettlementLine[];
};

export type Settlement = {
  id: number;
  household_id: number;
  created_by_person_id: number;
  period_start: string;
  period_end: string;
  granularity: string | null;
  currency: string;
  status: "draft" | "confirmed" | "settled" | string;
  result: SettlementResult;
  note: string | null;
  created_at: string;
  confirmed_at: string | null;
  settled_at: string | null;
};

export type PendingEntry = Entry & {
  bill: {
    id: number;
    merchant: string | null;
    source_type: string;
    occurred_at: string;
    currency: string;
  } | null;
};
