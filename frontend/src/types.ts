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
  entries: Entry[];
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
  created_at: string;
  my_role?: string;
  members?: HouseholdMember[];
};

export type CategoryItem = { id: string; label: string };

export type Vocabulary = {
  categories: CategoryItem[];
  aa_residual?: { id: string; label: string; description?: string };
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
